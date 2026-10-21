"""Transaction-owning BC06 commands and reauthorizing consumer projections."""
from datetime import date
from functools import wraps
from uuid import UUID
from sqlalchemy import select
from spesped.auth import require_authority,require_school_access,require_learner_access,school_today,active_at
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError,access_denied
from spesped.contexts.identity.models import School,SchoolMembership,UserAccount
from . import models as m, schemas as s
from .adapters import digest,current_goal,actual_experience
from .ports import SourceRequest,AuthorizedSource,DependencyRequest,FutureSession,MaterialAvailability


def row_view(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}


def json_view(value):
    from .adapters import canonical
    import json
    return json.loads(canonical(value))


def authority(db,actor,school_id,action):
    membership=require_school_access(db,actor,school_id)
    if membership.role in {'guardian','technical_administrator'}: raise access_denied()
    require_authority(db,actor,school_id,action)


def get(db,model,school_id,identifier,expected=None,lock=False):
    statement=select(model).where(model.school_id==school_id,model.id==str(identifier)).execution_options(populate_existing=True)
    if lock: statement=statement.with_for_update()
    row=db.scalar(statement)
    if row is None: raise access_denied()
    if expected is not None and row.version != expected: raise DomainError('version_conflict','Reload the changed record before retrying.',409)
    return row


def emit(db,actor,row,action,**payload):
    db.flush()
    record_audit(db,actor,row.school_id,action,type(row).__name__,row.id)
    db.add(m.CurriculumEvent(school_id=row.school_id,aggregate_id=row.id,aggregate_version=getattr(row,'version',1),actor_id=actor.user_id,event_type=action,causation_id=db.info.get('curriculum_request_key'),payload=json_view(payload)))
    db.flush()


def mutation(action):
    def decorate(fn):
        @wraps(fn)
        def wrapped(db,actor,school_id,*args):
            try:
                authority(db,actor,school_id,action)
                # Tenant serialization makes both command-key and publication races deterministic.
                db.scalar(select(School).where(School.id==school_id).with_for_update())
                command=args[-1]
                fingerprint=digest({'operation':fn.__name__,'target':[str(a) for a in args[:-1]],'command':command.model_dump(mode='json')})
                prior=db.scalar(select(m.CommandReceipt).where(m.CommandReceipt.school_id==school_id,m.CommandReceipt.actor_id==actor.user_id,m.CommandReceipt.request_key==command.request_key))
                if prior:
                    if prior.operation != fn.__name__ or prior.request_digest != fingerprint: raise DomainError('idempotency_conflict','This request key already identifies a different command.',409)
                    authorize_result(db,actor,school_id,prior.result)
                    result=prior.result
                    if result['kind']=='binding':result={'kind':'binding',**binding_view(db,actor,get(db,m.ThemeGoalBinding,school_id,result['id']))}
                    elif result['kind']=='experience':result=experience_view(db,actor,get(db,m.ResourceExperience,school_id,result['id']))
                    db.commit();return json_view(result)
                prior_request_key=db.info.get('curriculum_request_key')
                db.info['curriculum_request_key']=command.request_key
                try:result=json_view(fn(db,actor,school_id,*args))
                finally:
                    if prior_request_key is None:db.info.pop('curriculum_request_key',None)
                    else:db.info['curriculum_request_key']=prior_request_key
                db.add(m.CommandReceipt(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,operation=fn.__name__,request_digest=fingerprint,result=result))
                db.commit();return result
            except Exception:
                db.rollback();raise
        return wrapped
    return decorate


def authorize_result(db,actor,school_id,value):
    kind=value['kind']; ident=value['id']
    if kind=='resource':
        root=get(db,m.TeachingResource,school_id,ident)
        if value.get('state')=='withdrawn':own(actor,root)
        else:resolve_resource(db,actor,school_id,value['revision_id'])
    elif kind=='class_plan':
        authority(db,actor,school_id,'curriculum.read')
        sources(db,actor,school_id,value.get('content',{}).get('imported_sources',[]))
    elif kind=='scheme':
        authority(db,actor,school_id,'curriculum.read')
        sources(db,actor,school_id,value.get('content',{}).get('sources',[]))
    elif kind=='binding': binding_view(db,actor,get(db,m.ThemeGoalBinding,school_id,ident))
    elif kind=='impact': impact_access(db,actor,get(db,m.SessionImpact,school_id,ident))
    elif kind=='experience': require_learner_access(db,actor,school_id,value['learner_id'],'teaching.read')
    elif kind=='material': authority(db,actor,school_id,'materials.read')
    elif kind=='team': authority(db,actor,school_id,'resources.manage')


def read_contract(fn):
    @wraps(fn)
    def wrapped(db,*args,**kwargs):
        # Never flush/overwrite a caller's uncommitted permission or source edit.
        watched=('spesped.contexts.identity.models','spesped.contexts.evidence.models','spesped.contexts.plans.models','spesped.contexts.curriculum.models','spesped.contexts.administration.models')
        excluded={'AuditRecord','IdentityEvent','CurriculumEvent','CommandReceipt'}
        pending=set(db.dirty)|set(db.deleted)|set(db.new)
        if any(type(row).__module__ in watched and type(row).__name__ not in excluded for row in pending):
            raise DomainError('dependency_pending','Flush or roll back pending permission/source changes before resolving current content.',409)
        with db.no_autoflush:return fn(db,*args,**kwargs)
    return wrapped


@read_contract
def sources(db,actor,school_id,refs,purpose='read'):
    if not refs:return []
    port=db.info.get('curriculum_source_port')
    if port is None: raise DomainError('source_port_unavailable','Authorized original storage is unavailable.',503)
    values=[]
    for ref in refs:
        ref=s.SourceReference.model_validate(ref)
        if ref.learner_id:require_learner_access(db,actor,school_id,str(ref.learner_id),'evidence.read')
        if ref.case_id:raise access_denied()
        request=SourceRequest(school_id=school_id,reference=ref,purpose=purpose)
        value=AuthorizedSource.model_validate(port.resolve(db,actor,request))
        if value.request != request or value.original_digest != ref.digest: raise DomainError('source_contract','The source adapter did not return the exact authorized original.',409)
        values.append(value)
    return values


def own(actor,row):
    if actor.user_id != row.owner_id: raise access_denied()


def scheme_current(db,actor,school_id,revision_id,on_date=None):
    authority(db,actor,school_id,'curriculum.read')
    revision=get(db,m.SchemeRevision,school_id,revision_id)
    root=get(db,m.CurriculumScheme,school_id,revision.scheme_id)
    if revision.state != 'reviewed' or root.state != 'active':
        raise DomainError('scheme_not_current','Select the current school-reviewed curriculum and assessment scheme.',409)
    if on_date is not None and not revision.valid_from <= on_date <= revision.valid_until: raise DomainError('scheme_period','The reviewed scheme does not cover this date.',409)
    sources(db,actor,school_id,revision.sources)
    return revision


def scheme_view(db,actor,school_id,identifier):
    authority(db,actor,school_id,'curriculum.read')
    root=get(db,m.CurriculumScheme,school_id,identifier)
    revision=db.scalar(select(m.SchemeRevision).where(m.SchemeRevision.school_id==school_id,m.SchemeRevision.scheme_id==root.id,m.SchemeRevision.number==root.current_revision))
    sources(db,actor,school_id,revision.sources)
    assessment=db.scalar(select(m.AssessmentScheme).where(m.AssessmentScheme.school_id==school_id,m.AssessmentScheme.scheme_revision_id==revision.id))
    return {'kind':'scheme',**row_view(root),'content':row_view(revision),'assessment':row_view(assessment)}


def new_scheme_revision(db,actor,root,content):
    values=content.model_dump(mode='json',exclude={'assessment_rules'})
    values.update(valid_from=content.valid_from,valid_until=content.valid_until)
    revision=m.SchemeRevision(school_id=root.school_id,scheme_id=root.id,number=root.current_revision,state='draft',content_digest=digest(content.model_dump(mode='json')),authored_by=actor.user_id,**values)
    db.add(revision);db.flush()
    db.add(m.AssessmentScheme(school_id=root.school_id,scheme_revision_id=revision.id,rules=[r.model_dump(mode='json') for r in content.assessment_rules]))
    db.flush();return revision


@mutation('curriculum.manage')
def create_scheme(db,actor,school_id,command):
    sources(db,actor,school_id,command.content.sources)
    root=m.CurriculumScheme(school_id=school_id,owner_id=actor.user_id,state='active');db.add(root);db.flush()
    new_scheme_revision(db,actor,root,command.content);emit(db,actor,root,'curriculum.scheme.created')
    return scheme_view(db,actor,school_id,root.id)


@mutation('curriculum.manage')
def revise_scheme(db,actor,school_id,identifier,command):
    root=get(db,m.CurriculumScheme,school_id,identifier,command.expected_version,True);own(actor,root)
    if root.state!='active':raise DomainError('scheme_withdrawn','A withdrawn scheme cannot be revised.',409)
    sources(db,actor,school_id,command.content.sources)
    previous=db.scalar(select(m.SchemeRevision).where(m.SchemeRevision.scheme_id==root.id,m.SchemeRevision.number==root.current_revision))
    if previous.state=='draft':previous.state='superseded'
    root.current_revision+=1;root.version+=1
    new_scheme_revision(db,actor,root,command.content);emit(db,actor,root,'curriculum.scheme.revised')
    return scheme_view(db,actor,school_id,root.id)


def exact(root,revision,command):
    if root.version!=command.expected_version:raise DomainError('version_conflict','Reload the changed record.',409)
    if revision.id!=str(command.revision_id) or revision.content_digest!=command.content_digest:raise DomainError('revision_mismatch','Review the exact current revision and digest.',409)


@mutation('curriculum.publish')
def review_scheme(db,actor,school_id,identifier,command):
    root=get(db,m.CurriculumScheme,school_id,identifier,command.expected_version,True)
    revision=db.scalar(select(m.SchemeRevision).where(m.SchemeRevision.scheme_id==root.id,m.SchemeRevision.number==root.current_revision))
    exact(root,revision,command)
    if revision.state!='draft' or command.approved_on > school_today(db.get(School,school_id)):raise DomainError('scheme_review','A dated existing approval and a draft revision are required.',409)
    sources(db,actor,school_id,revision.sources)
    for prior in db.scalars(select(m.SchemeRevision).where(m.SchemeRevision.school_id==school_id,m.SchemeRevision.scheme_id==root.id,m.SchemeRevision.state=='reviewed')):
        capture_impacts(db,actor,school_id,'scheme',prior.id,revision.id);prior.state='superseded'
    revision.state='reviewed';revision.reviewed_by=actor.user_id;revision.reviewed_at=utcnow();revision.approval_reference=command.approval_reference;revision.approved_on=command.approved_on;revision.review_reason=command.reason;root.version+=1
    emit(db,actor,root,'curriculum.scheme.reviewed',revision_id=revision.id)
    return scheme_view(db,actor,school_id,root.id)


def class_view(db,actor,school_id,identifier):
    authority(db,actor,school_id,'curriculum.read')
    root=get(db,m.ClassLearningPlan,school_id,identifier)
    revision=db.scalar(select(m.ClassPlanRevision).where(m.ClassPlanRevision.school_id==school_id,m.ClassPlanRevision.plan_id==root.id,m.ClassPlanRevision.number==root.current_revision))
    sources(db,actor,school_id,revision.imported_sources)
    return {'kind':'class_plan',**row_view(root),'content':row_view(revision)}


def check_themes(db,actor,school_id,content):
    sources(db,actor,school_id,content.imported_sources)
    for theme in content.themes:
        for ref in theme.curriculum_references:
            revision=scheme_current(db,actor,school_id,ref.scheme_revision_id,theme.valid_from)
            scheme_current(db,actor,school_id,ref.scheme_revision_id,theme.valid_until)
            if not any(g['code']==ref.goal_code for g in revision.goals):raise DomainError('curriculum_goal','Select a goal in the exact reviewed scheme.',409)
        for material_id in theme.material_ids:get(db,m.MaterialCatalogItem,school_id,material_id)


def append_class(db,actor,root,content):
    values=content.model_dump(mode='json');values.update(valid_from=content.valid_from,valid_until=content.valid_until)
    revision=m.ClassPlanRevision(school_id=root.school_id,plan_id=root.id,number=root.current_revision,state='draft',content_digest=digest(content.model_dump(mode='json')),authored_by=actor.user_id,**values)
    db.add(revision);db.flush();return revision


@mutation('curriculum.manage')
def create_class_plan(db,actor,school_id,command):
    check_themes(db,actor,school_id,command.content)
    root=m.ClassLearningPlan(school_id=school_id,owner_id=actor.user_id,state='draft');db.add(root);db.flush()
    append_class(db,actor,root,command.content);emit(db,actor,root,'curriculum.class_plan.created')
    return class_view(db,actor,school_id,root.id)


@mutation('curriculum.manage')
def revise_class_plan(db,actor,school_id,identifier,command):
    root=get(db,m.ClassLearningPlan,school_id,identifier,command.expected_version,True);own(actor,root)
    if root.state=='withdrawn':raise DomainError('plan_withdrawn','A withdrawn class plan cannot be revised.',409)
    check_themes(db,actor,school_id,command.content)
    root.current_revision+=1;root.version+=1;root.state='draft'
    append_class(db,actor,root,command.content);emit(db,actor,root,'curriculum.class_plan.revised')
    return class_view(db,actor,school_id,root.id)


def capture_impacts(db,actor,school_id,kind,old_revision_id,new_revision_id):
    port=db.info.get('curriculum_future_session_port')
    if port is None:raise DomainError('session_impact_unavailable','The teaching dependency index must check affected future sessions.',503)
    request=DependencyRequest(school_id=school_id,kind=kind,old_revision_id=old_revision_id,new_revision_id=new_revision_id,changed_at=utcnow())
    for supplied in port.upcoming(db,actor,request):
        value=FutureSession.model_validate(supplied)
        if value.request!=request or value.planned_at<=request.changed_at or len(set(value.learner_ids))!=len(value.learner_ids):raise DomainError('session_impact_contract','Only exact upcoming session dependencies may be returned.',409)
        staff_valid(db,school_id,str(value.owner_id))
        existing=db.scalar(select(m.SessionImpact).where(m.SessionImpact.school_id==school_id,m.SessionImpact.old_revision_id==str(old_revision_id),m.SessionImpact.new_revision_id==(str(new_revision_id) if new_revision_id else None),m.SessionImpact.session_revision_id==str(value.session_revision_id)))
        if existing:continue
        row=m.SessionImpact(school_id=school_id,dependency_kind=kind,dependency_changed_at=request.changed_at,old_revision_id=str(old_revision_id),new_revision_id=str(new_revision_id) if new_revision_id else None,session_id=str(value.session_id),session_revision_id=str(value.session_revision_id),planned_at=value.planned_at,owner_id=str(value.owner_id),learner_ids=[str(i) for i in value.learner_ids],state='open')
        db.add(row);emit(db,actor,row,'curriculum.session.review_required')


@mutation('curriculum.publish')
def publish_class_plan(db,actor,school_id,identifier,command):
    root=get(db,m.ClassLearningPlan,school_id,identifier,command.expected_version,True)
    revision=db.scalar(select(m.ClassPlanRevision).where(m.ClassPlanRevision.plan_id==root.id,m.ClassPlanRevision.number==root.current_revision));exact(root,revision,command)
    if revision.state!='draft' or root.state=='withdrawn':raise DomainError('invalid_transition','Publish a current draft.',409)
    content=s.ClassPlanContent.model_validate({k:getattr(revision,k) for k in s.ClassPlanContent.model_fields})
    if not content.themes:raise DomainError('periods_missing','Retain the import and enter checked theme periods before publication.',409)
    check_themes(db,actor,school_id,content)
    previous=list(db.scalars(select(m.ClassPlanRevision).where(m.ClassPlanRevision.plan_id==root.id,m.ClassPlanRevision.state=='published')))
    for old in previous:
        capture_impacts(db,actor,school_id,'class_plan',old.id,revision.id);old.state='superseded'
    revision.state='published';revision.published_by=actor.user_id;revision.published_at=utcnow();revision.review_reason=command.reason;root.state='published';root.version+=1
    emit(db,actor,root,'curriculum.class_plan.published',revision_id=revision.id,superseded=[p.id for p in previous])
    return class_view(db,actor,school_id,root.id)


@read_contract
def current_class_context(db,actor,school_id,plan_revision_id,on_date,learner_id=None):
    """Read-only consumer port. No automatic pupil goal/theme equivalence."""
    authority(db,actor,school_id,'curriculum.read')
    if learner_id:require_learner_access(db,actor,school_id,str(learner_id),'plans.read')
    revision=get(db,m.ClassPlanRevision,school_id,plan_revision_id)
    root=get(db,m.ClassLearningPlan,school_id,revision.plan_id)
    if revision.state!='published' or root.state=='withdrawn':raise DomainError('class_plan_not_current','Select a published class plan revision.',409)
    if not revision.valid_from<=on_date<=revision.valid_until:raise DomainError('class_plan_period','The class plan does not cover this date.',409)
    sources(db,actor,school_id,revision.imported_sources)
    themes=[t for t in revision.themes if date.fromisoformat(t['valid_from'])<=on_date<=date.fromisoformat(t['valid_until'])]
    for theme in themes:
        for ref in theme['curriculum_references']:scheme_current(db,actor,school_id,ref['scheme_revision_id'],on_date)
    bindings=[]
    if learner_id:
        for row in db.scalars(select(m.ThemeGoalBinding).where(m.ThemeGoalBinding.school_id==school_id,m.ThemeGoalBinding.plan_revision_id==revision.id,m.ThemeGoalBinding.learner_id==str(learner_id),m.ThemeGoalBinding.state=='active')):
            if row.theme_id in {t['id'] for t in themes}:bindings.append(binding_view(db,actor,row))
    return {'kind':'class_context','revision_id':revision.id,'digest':revision.content_digest,'group_name':revision.group_name,'age_min':revision.age_min,'age_max':revision.age_max,'on_date':on_date,'themes':themes,'bindings':bindings}


@mutation('curriculum.manage')
def bind_goal(db,actor,school_id,command):
    require_learner_access(db,actor,school_id,str(command.learner_id),'plans.write')
    revision=get(db,m.ClassPlanRevision,school_id,command.plan_revision_id)
    theme=next((t for t in revision.themes if t['id']==str(command.theme_id)),None)
    if theme is None or revision.state!='published':raise DomainError('theme_not_current','Select an exact published theme.',409)
    current_class_context(db,actor,school_id,revision.id,date.fromisoformat(theme['valid_from']),str(command.learner_id))
    goal=current_goal(db,actor,school_id,str(command.learner_id),command.goal_revision_id)
    sources(db,actor,school_id,command.sources)
    existing=db.scalar(select(m.ThemeGoalBinding.id).where(m.ThemeGoalBinding.school_id==school_id,m.ThemeGoalBinding.plan_revision_id==str(command.plan_revision_id),m.ThemeGoalBinding.theme_id==str(command.theme_id),m.ThemeGoalBinding.learner_id==str(command.learner_id),m.ThemeGoalBinding.goal_revision_id==str(command.goal_revision_id),m.ThemeGoalBinding.state=='active'))
    if existing:raise DomainError('binding_exists','Correct the current exact theme/goal choice using its expected version.',409)
    values=command.model_dump(mode='json',exclude={'request_key'})
    row=m.ThemeGoalBinding(school_id=school_id,bound_by=actor.user_id,goal_digest=digest(goal),state='active',**values);db.add(row);emit(db,actor,row,'curriculum.theme.goal_bound')
    return {'kind':'binding',**binding_view(db,actor,row)}


@mutation('curriculum.manage')
def correct_goal_binding(db,actor,school_id,identifier,command):
    previous=get(db,m.ThemeGoalBinding,school_id,identifier,lock=True)
    require_learner_access(db,actor,school_id,previous.learner_id,'plans.write')
    if previous.version!=command.expected_version:raise DomainError('version_conflict','Reload the current exact theme/goal choice before correcting it.',409)
    if previous.state!='active':raise DomainError('binding_superseded','Correct the current exact theme/goal choice.',409)
    # Current dependencies must still be authorized; correction never inherits a
    # former actor's source rights or changes the learner/goal/theme coordinates.
    binding_view(db,actor,previous)
    sources(db,actor,school_id,command.sources)
    values=command.model_dump(mode='json',exclude={'request_key','expected_version','reason'})
    previous.state='superseded';previous.version+=1
    db.flush()  # Release the exact active-choice index before inserting its successor.
    row=m.ThemeGoalBinding(school_id=school_id,plan_revision_id=previous.plan_revision_id,
        theme_id=previous.theme_id,learner_id=previous.learner_id,goal_revision_id=previous.goal_revision_id,
        bound_by=actor.user_id,goal_digest=previous.goal_digest,supersedes_id=previous.id,
        correction_reason=command.reason,state='active',**values)
    db.add(row);emit(db,actor,row,'curriculum.theme.goal_binding_corrected',supersedes_id=previous.id)
    return {'kind':'binding',**binding_view(db,actor,row)}


def binding_view(db,actor,row):
    revision=get(db,m.ClassPlanRevision,row.school_id,row.plan_revision_id)
    if revision.state!='published':raise DomainError('binding_theme_changed','The exact published theme has changed and requires review.',409)
    require_learner_access(db,actor,row.school_id,row.learner_id,'plans.read')
    sources(db,actor,row.school_id,revision.imported_sources)
    theme=next((t for t in revision.themes if t['id']==row.theme_id),None)
    if theme is None:raise DomainError('binding_theme_changed','The bound theme requires review.',409)
    for ref in theme['curriculum_references']:scheme_current(db,actor,row.school_id,ref['scheme_revision_id'],date.fromisoformat(theme['valid_from']))
    goal=current_goal(db,actor,row.school_id,row.learner_id,row.goal_revision_id)
    if digest(goal)!=row.goal_digest:raise DomainError('goal_changed','The exact bound pupil goal needs review.',409)
    sources(db,actor,row.school_id,row.sources)
    successor=db.scalar(select(m.ThemeGoalBinding.id).where(m.ThemeGoalBinding.school_id==row.school_id,m.ThemeGoalBinding.supersedes_id==row.id))
    return {**row_view(row),'is_current':row.state=='active','superseded_by_id':successor}


def impact_access(db,actor,row):
    authority(db,actor,row.school_id,'curriculum.read')
    if row.owner_id!=actor.user_id:raise access_denied()
    for learner_id in row.learner_ids:require_learner_access(db,actor,row.school_id,learner_id,'teaching.read')


@mutation('curriculum.manage')
def decide_impact(db,actor,school_id,identifier,command):
    row=get(db,m.SessionImpact,school_id,identifier,command.expected_version,True);impact_access(db,actor,row)
    if row.state!='open' or row.planned_at<=utcnow():raise DomainError('impact_closed','Only an open future-session impact can be decided.',409)
    port=db.info.get('curriculum_future_session_port')
    if port is None:raise DomainError('session_impact_unavailable','The owning teaching context must recheck this exact session.',503)
    request=DependencyRequest(school_id=school_id,kind=row.dependency_kind,old_revision_id=row.old_revision_id,new_revision_id=row.new_revision_id,changed_at=row.dependency_changed_at)
    session=FutureSession(request=request,session_id=row.session_id,session_revision_id=row.session_revision_id,owner_id=row.owner_id,learner_ids=row.learner_ids,planned_at=row.planned_at)
    if port.validate_decision(db,actor,session,command.decision,command.replacement_session_revision_id) is not True:raise DomainError('session_changed','The owning context could not confirm this exact future-session decision.',409)
    row.state=command.decision;row.decision_reason=command.reason;row.decided_by=actor.user_id;row.decided_at=utcnow();row.replacement_session_revision_id=str(command.replacement_session_revision_id) if command.replacement_session_revision_id else None;row.version+=1
    emit(db,actor,row,'curriculum.session.impact_decided',decision=command.decision,replacement_session_revision_id=row.replacement_session_revision_id)
    return {'kind':'impact',**row_view(row)}


def team_member(db,actor,school_id,team_id):
    team=get(db,m.ResourceTeam,school_id,team_id)
    today=school_today(db.get(School,school_id))
    if team.state!='active' or db.scalar(select(m.TeamMember).where(m.TeamMember.school_id==school_id,m.TeamMember.team_id==team.id,m.TeamMember.user_id==actor.user_id,m.TeamMember.state=='active',m.TeamMember.valid_from<=today,m.TeamMember.valid_until>=today)) is None:raise access_denied()


def license_check(db,actor,root,revision,purpose,shared_descendant=None):
    today=school_today(db.get(School,root.school_id));rights=s.ResourceRights.model_validate(revision.rights)
    current=db.scalar(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id,m.ResourceRevision.number==root.current_revision))
    current_rights=s.ResourceRights.model_validate(current.rights)
    if purpose not in {'read','use','copy','ai'} or not getattr(current_rights,purpose):raise DomainError('resource_rights','Current resource rights no longer permit this use of a retained revision.',403)
    if today<current_rights.valid_from or (current_rights.valid_until and today>current_rights.valid_until):raise DomainError('resource_license_period','Current usage rights have expired.',409)
    if purpose not in {'read','use','copy','ai'} or not getattr(rights,purpose):raise DomainError('resource_rights','This exact resource license does not permit the requested action.',403)
    if today<rights.valid_from or (rights.valid_until and today>rights.valid_until):raise DomainError('resource_license_period','The resource usage rights do not cover today.',409)
    if root.owner_id!=actor.user_id:
        if root.visibility=='private' or root.shared_revision_id not in {revision.id,shared_descendant}:raise access_denied()
        if root.visibility=='school' and not rights.share_school:raise access_denied()
        if root.visibility=='team':
            if not rights.share_team:raise access_denied()
            team_member(db,actor,root.school_id,root.team_id)


@read_contract
def resolve_resource(db,actor,school_id,resource_revision_id,purpose='read',learner_id=None,_seen=None,_shared_descendant=None):
    """Read-only use port; exact source ancestry and rights rechecked every time."""
    authority(db,actor,school_id,'resources.read')
    if learner_id:require_learner_access(db,actor,school_id,str(learner_id),'teaching.read')
    revision=get(db,m.ResourceRevision,school_id,resource_revision_id);root=get(db,m.TeachingResource,school_id,revision.resource_id)
    if root.state=='withdrawn':raise DomainError('resource_withdrawn','This resource has been withdrawn from further use.',409)
    license_check(db,actor,root,revision,purpose,_shared_descendant)
    refs=sources(db,actor,school_id,revision.sources,purpose)
    seen=set(_seen or ())
    if revision.id in seen:raise DomainError('resource_lineage','Resource ancestry is invalid.',409)
    seen.add(revision.id)
    ancestors=[];originals=[];field_changes=[]
    baseline_id=revision.previous_revision_id or revision.original_revision_id
    if baseline_id:
        baseline=get(db,m.ResourceRevision,school_id,baseline_id)
        field_changes=[{'field':key,'original':getattr(baseline,key),'current':getattr(revision,key)} for key in s.ResourceContent.model_fields if getattr(baseline,key)!=getattr(revision,key)]
    for parent_id in dict.fromkeys([revision.original_revision_id,revision.previous_revision_id]):
        if parent_id:
            parent_row=get(db,m.ResourceRevision,school_id,parent_id)
            grant=(_shared_descendant or revision.id) if parent_row.resource_id==root.id else None
            parent=resolve_resource(db,actor,school_id,parent_id,purpose,learner_id,seen,grant)
            ancestors.append({'revision_id':parent['revision_id'],'digest':parent['content_digest']})
            originals.append({key:parent[key] for key in ('revision_id','content_digest','changes',*s.ResourceContent.model_fields)})
            originals.extend(parent['originals'])
    return {'kind':'resource','id':root.id,'version':root.version,'state':root.state,'visibility':root.visibility,'owner_id':root.owner_id,'revision_id':revision.id,**row_view(revision),'ancestors':ancestors,'field_changes':field_changes,'originals':list({v['revision_id']:v for v in originals}.values()),'authorized_originals':[v.model_dump(mode='json') for v in refs],'suitability':'human_confirmation_required'} | {'id':root.id}


def resource_view(db,actor,school_id,identifier):
    root=get(db,m.TeachingResource,school_id,identifier)
    revision=db.scalar(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id,m.ResourceRevision.number==root.current_revision))
    return resolve_resource(db,actor,school_id,revision.id)


def check_resource(db,actor,school_id,content):
    sources(db,actor,school_id,content.sources)
    for material_id in content.material_ids:get(db,m.MaterialCatalogItem,school_id,material_id)


def derivative_rights(parent,content):
    parent_rights=s.ResourceRights.model_validate(parent.rights)
    for name in ('read','use','copy','ai','share_team','share_school'):
        if getattr(content.rights,name) and not getattr(parent_rights,name):raise DomainError('derivative_rights','A derivative cannot expand original usage or sharing rights.',403)
    if content.rights.valid_from<parent_rights.valid_from or (parent_rights.valid_until and (content.rights.valid_until is None or content.rights.valid_until>parent_rights.valid_until)):
        raise DomainError('derivative_rights','A derivative cannot extend original license dates.',403)


def append_resource(db,actor,root,content,changes,original=None,previous=None):
    values=content.model_dump(mode='json')
    revision=m.ResourceRevision(school_id=root.school_id,resource_id=root.id,number=root.current_revision,original_revision_id=original,previous_revision_id=previous,changes=changes,content_digest=digest({'content':values,'changes':changes,'original':original,'previous':previous}),authored_by=actor.user_id,**values)
    db.add(revision);db.flush();return revision


@mutation('resources.manage')
def create_resource(db,actor,school_id,command):
    check_resource(db,actor,school_id,command.content)
    if command.original_revision_id:
        resolve_resource(db,actor,school_id,command.original_revision_id,'copy')
        original=get(db,m.ResourceRevision,school_id,command.original_revision_id)
        derivative_rights(original,command.content)
        if command.content.original_provenance!=original.original_provenance:raise DomainError('original_provenance','A variant must retain the original provenance.',409)
    root=m.TeachingResource(school_id=school_id,owner_id=actor.user_id,state='draft',visibility='private');db.add(root);db.flush()
    revision=append_resource(db,actor,root,command.content,list(command.changes),str(command.original_revision_id) if command.original_revision_id else None)
    emit(db,actor,root,'curriculum.resource.created',revision_id=revision.id)
    return resource_view(db,actor,school_id,root.id)


@mutation('resources.manage')
def revise_resource(db,actor,school_id,identifier,command):
    root=get(db,m.TeachingResource,school_id,identifier,command.expected_version,True);own(actor,root)
    old=db.scalar(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id,m.ResourceRevision.number==root.current_revision))
    resolve_resource(db,actor,school_id,old.id,'copy');check_resource(db,actor,school_id,command.content)
    if old.original_revision_id:derivative_rights(get(db,m.ResourceRevision,school_id,old.original_revision_id),command.content)
    if command.content.original_provenance!=old.original_provenance:raise DomainError('original_provenance','Retain the original provenance.',409)
    # Every revision starts private; sharing approval binds exact content.
    root.current_revision+=1;root.version+=1;root.visibility='private';root.team_id=None;root.state='draft';root.shared_at=None;root.shared_by=None;root.shared_revision_id=None
    revision=append_resource(db,actor,root,command.content,list(command.changes),old.original_revision_id,old.id)
    capture_impacts(db,actor,school_id,'resource',old.id,revision.id)
    emit(db,actor,root,'curriculum.resource.revised',old_revision_id=old.id,revision_id=revision.id)
    return resource_view(db,actor,school_id,root.id)


@mutation('resources.manage')
def share_resource(db,actor,school_id,identifier,command):
    root=get(db,m.TeachingResource,school_id,identifier,command.expected_version,True);own(actor,root)
    revision=db.scalar(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id,m.ResourceRevision.number==root.current_revision));exact(root,revision,command)
    resolve_resource(db,actor,school_id,revision.id)
    if command.visibility!='private':
        if not revision.rights['share_'+command.visibility]:raise DomainError('sharing_rights','The original license does not allow this sharing.',403)
        # Pupil-scoped content never becomes school/team library prose.
        if any(r.get('learner_id') or r.get('case_id') for r in revision.sources):raise DomainError('sharing_scope','Pupil sources cannot be shared as institutional resources.',403)
        if command.team_id:team_member(db,actor,school_id,str(command.team_id))
        for ancestor in resolve_resource(db,actor,school_id,revision.id)['ancestors']:
            parent=get(db,m.ResourceRevision,school_id,ancestor['revision_id'])
            if not parent.rights['share_'+command.visibility]:raise DomainError('sharing_rights','Original rights do not allow this derivative sharing.',403)
            if parent.resource_id!=root.id:
                parent_root=get(db,m.TeachingResource,school_id,parent.resource_id)
                compatible=(parent_root.visibility=='school' or (command.visibility=='team' and parent_root.visibility=='team' and parent_root.team_id==str(command.team_id)))
                if not compatible or parent_root.shared_revision_id!=parent.id:raise DomainError('original_sharing_required','The exact original must be explicitly shared with the same permitted audience first.',409)
    root.visibility=command.visibility;root.team_id=str(command.team_id) if command.team_id else None;root.shared_by=actor.user_id;root.shared_at=utcnow();root.shared_revision_id=revision.id;root.state='available' if command.visibility!='private' else 'draft';root.version+=1
    emit(db,actor,root,'curriculum.resource.sharing_changed',revision_id=revision.id,visibility=root.visibility)
    return resource_view(db,actor,school_id,root.id)


@mutation('resources.manage')
def withdraw_resource(db,actor,school_id,identifier,command):
    root=get(db,m.TeachingResource,school_id,identifier,command.expected_version,True);own(actor,root)
    if root.state=='withdrawn':raise DomainError('invalid_transition','The resource is already withdrawn.',409)
    revisions=list(db.scalars(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id)))
    for revision in revisions:capture_impacts(db,actor,school_id,'resource',revision.id,None)
    root.state='withdrawn';root.version+=1
    emit(db,actor,root,'curriculum.resource.withdrawn',revision_ids=[r.id for r in revisions])
    return {'kind':'resource','id':root.id,'version':root.version,'state':root.state}


@mutation('resources.manage')
def record_experience(db,actor,school_id,command):
    require_learner_access(db,actor,school_id,str(command.learner_id),'teaching.write')
    resolve_resource(db,actor,school_id,command.resource_revision_id,'use',command.learner_id)
    if command.observed_on>school_today(db.get(School,school_id)):raise DomainError('future_experience','Record actual experience after use.',409)
    actual_experience(db,actor,school_id,str(command.learner_id),command.session_delivery_revision_id,command.observed_on)
    values=command.model_dump(mode='json',exclude={'request_key'});values['observed_on']=command.observed_on
    row=m.ResourceExperience(school_id=school_id,recorded_by=actor.user_id,**values);db.add(row);emit(db,actor,row,'curriculum.resource.experience_recorded')
    return experience_view(db,actor,row)


@read_contract
def experience_view(db,actor,row):
    """A retained practitioner account is distinct from its current support.

    Actual corrections retain attributed prose with a visible review marker.
    Lost resource/original permission returns minimal historical coordinates only;
    sharing cannot recover original prose through an experience record.
    """
    authority(db,actor,row.school_id,'resources.read')
    require_learner_access(db,actor,row.school_id,row.learner_id,'teaching.read')
    if any(type(value).__module__=='spesped.contexts.teaching.models' for value in set(db.dirty)|set(db.deleted)|set(db.new)):
        raise DomainError('dependency_pending','Flush or roll back pending actual changes before reading experience support.',409)
    resource_status='current';actual_status='current'
    try:resolve_resource(db,actor,row.school_id,row.resource_revision_id,'read',row.learner_id)
    except DomainError as exc:
        if exc.code=='dependency_pending':raise
        if exc.status_code not in {403,409,503}:raise
        resource_status='unavailable'
    try:actual_experience(db,actor,row.school_id,row.learner_id,row.session_delivery_revision_id,row.observed_on)
    except DomainError as exc:
        if exc.status_code==409:actual_status='historical'
        elif exc.status_code in {403,503}:actual_status='unavailable'
        else:raise
    supported=resource_status=='current' and actual_status=='current'
    content_available=resource_status=='current' and actual_status!='unavailable'
    # No other pupil's actual, current participation, original or resource content
    # is copied into this projection. Its exact historic identifiers remain visible.
    value=row_view(row)
    if not content_available:value['experience']=None
    return {'kind':'experience',**value,'constitutes_approval':False,
        'state':'current' if supported else 'review_required','review_required':not supported,
        'actual_status':actual_status,'resource_status':resource_status,
        'source_status':'current' if supported else 'review_required','content_available':content_available}


def staff_valid(db,school_id,user_id):
    school=db.get(School,school_id);user=db.get(UserAccount,user_id,populate_existing=True)
    membership=db.scalar(select(SchoolMembership).where(SchoolMembership.school_id==school_id,SchoolMembership.user_id==user_id,*active_at(SchoolMembership,school_today(school))))
    if not user or user.state!='active' or not membership or membership.role in {'guardian','technical_administrator'}:raise DomainError('invalid_staff','Select a current school staff member.',409)


@mutation('resources.manage')
def create_team(db,actor,school_id,command):
    row=m.ResourceTeam(school_id=school_id,name=command.name,state='active');db.add(row);emit(db,actor,row,'curriculum.team.created')
    return {'kind':'team',**row_view(row)}


@mutation('resources.manage')
def set_team_member(db,actor,school_id,identifier,command):
    root=get(db,m.ResourceTeam,school_id,identifier,command.expected_version,True);staff_valid(db,school_id,str(command.user_id))
    row=db.scalar(select(m.TeamMember).where(m.TeamMember.school_id==school_id,m.TeamMember.team_id==root.id,m.TeamMember.user_id==str(command.user_id)))
    if row is None:
        row=m.TeamMember(school_id=school_id,team_id=root.id,user_id=str(command.user_id),valid_from=command.valid_from,valid_until=command.valid_until,state=command.state);db.add(row)
    else:row.valid_from=command.valid_from;row.valid_until=command.valid_until;row.state=command.state;row.version+=1
    root.version+=1;emit(db,actor,root,'curriculum.team.membership_changed',member_id=str(command.user_id))
    return {'kind':'team',**row_view(root)}


def check_material(db,actor,school_id,content):
    if content.inventory_checked_on and content.inventory_checked_on>school_today(db.get(School,school_id)):raise DomainError('future_inventory','Inventory counts require an actual past check.',409)
    for revision_id in content.presentation_revision_ids:resolve_resource(db,actor,school_id,revision_id,'read')


@mutation('materials.manage')
def create_material(db,actor,school_id,command):
    check_material(db,actor,school_id,command.content)
    values=command.content.model_dump(mode='json');values['inventory_checked_on']=command.content.inventory_checked_on
    row=m.MaterialCatalogItem(school_id=school_id,state='active',**values);db.add(row);emit(db,actor,row,'curriculum.material.created')
    return {'kind':'material',**row_view(row),'availability':'unknown'}


@mutation('materials.manage')
def update_material(db,actor,school_id,identifier,command):
    row=get(db,m.MaterialCatalogItem,school_id,identifier,command.expected_version,True);check_material(db,actor,school_id,command.content)
    for key,value in command.content.model_dump(mode='python').items():setattr(row,key,[str(v) for v in value] if key=='presentation_revision_ids' else value)
    row.version+=1;emit(db,actor,row,'curriculum.material.inventory_updated')
    return {'kind':'material',**row_view(row),'availability':'unknown'}


def material_availability(db,actor,request):
    school_id=str(request.school_id);authority(db,actor,school_id,'materials.read')
    row=get(db,m.MaterialCatalogItem,school_id,request.material_id,request.material_version)
    if request.ends_at<=request.starts_at:raise DomainError('material_interval','A positive reservation interval is required.',422)
    port=db.info.get('curriculum_material_reservation_port')
    if port is None or row.count is None:return MaterialAvailability(request=request,state='unavailable' if port is None else 'unknown')
    result=MaterialAvailability.model_validate(port.availability(db,actor,request))
    if result.request!=request:raise DomainError('reservation_contract','Availability must match the exact material version, count and interval.',409)
    if result.state in {'available','insufficient'} and (result.available_count is None or result.checked_at is None or result.checked_at>utcnow() or not result.reservation_revision or result.available_count>row.count or (result.state=='available')!=(result.available_count>=request.count)):
        raise DomainError('reservation_contract','Known availability requires a dated reservation-ledger revision and a consistent quantity.',409)
    return result


@mutation('curriculum.publish')
def withdraw_class_plan(db,actor,school_id,identifier,command):
    root=get(db,m.ClassLearningPlan,school_id,identifier,command.expected_version,True)
    if root.state=='withdrawn':raise DomainError('invalid_transition','This class plan has already been withdrawn.',409)
    for revision in db.scalars(select(m.ClassPlanRevision).where(m.ClassPlanRevision.school_id==school_id,m.ClassPlanRevision.plan_id==root.id)):
        if revision.state=='published':capture_impacts(db,actor,school_id,'class_plan',revision.id,None)
        revision.state='withdrawn'
    root.state='withdrawn';root.version+=1;emit(db,actor,root,'curriculum.class_plan.withdrawn')
    return {'kind':'class_plan','id':root.id,'version':root.version,'state':root.state}


@mutation('curriculum.publish')
def withdraw_scheme(db,actor,school_id,identifier,command):
    root=get(db,m.CurriculumScheme,school_id,identifier,command.expected_version,True)
    if root.state=='withdrawn':raise DomainError('invalid_transition','This scheme has already been withdrawn.',409)
    revisions=list(db.scalars(select(m.SchemeRevision).where(m.SchemeRevision.school_id==school_id,m.SchemeRevision.scheme_id==root.id)))
    for revision in revisions:
        if revision.state=='reviewed':capture_impacts(db,actor,school_id,'scheme',revision.id,None)
        revision.state='withdrawn'
    root.state='withdrawn';root.version+=1;emit(db,actor,root,'curriculum.scheme.withdrawn',revision_ids=[r.id for r in revisions])
    return {'kind':'scheme','id':root.id,'version':root.version,'state':root.state}


def record_source_correction_impacts(db,actor,school_id,reference):
    """Owner-authorized source-event adapter; caller commits with its correction.

    Only exact source coordinates are inspected here. Original source prose is
    never selected. Consumer projections independently reject stale originals.
    Repeated correction events do not duplicate an already-open dependency.
    """
    authority(db,actor,school_id,'curriculum.manage')
    reference=s.SourceReference.model_validate(reference)
    if reference.case_id:raise access_denied()
    if reference.learner_id:require_learner_access(db,actor,school_id,str(reference.learner_id),'evidence.read')
    db.scalar(select(School).where(School.id==school_id).with_for_update())
    target=reference.model_dump(mode='json')
    recall_key='source-recall:'+digest(target)
    prior=db.scalar(select(m.CommandReceipt).where(m.CommandReceipt.school_id==school_id,m.CommandReceipt.actor_id==actor.user_id,m.CommandReceipt.request_key==recall_key))
    if prior:
        if prior.operation!='source_recall' or prior.request_digest!=digest(target):raise DomainError('idempotency_conflict','The source recall key conflicts with another operation.',409)
        return prior.result
    def matches(refs):return any(s.SourceReference.model_validate(ref).model_dump(mode='json')==target for ref in refs)
    affected=[]
    for model,field,kind in ((m.SchemeRevision,'sources','scheme'),(m.ClassPlanRevision,'imported_sources','class_plan')):
        for row in db.scalars(select(model).where(model.school_id==school_id)):
            if matches(getattr(row,field)):affected.append((kind,row))
    resources=list(db.scalars(select(m.ResourceRevision).where(m.ResourceRevision.school_id==school_id)))
    resource_ids={row.id for row in resources if matches(row.sources)}
    while True:
        expanded=resource_ids|{row.id for row in resources if row.original_revision_id in resource_ids or row.previous_revision_id in resource_ids}
        if expanded==resource_ids:break
        resource_ids=expanded
    affected.extend(('resource',row) for row in resources if row.id in resource_ids)
    for kind,row in affected:
        capture_impacts(db,actor,school_id,kind,row.id,None)
        emit(db,actor,row,'curriculum.source.review_required',source_id=str(reference.source_id),source_revision=reference.revision)
    result={'affected_revisions':len(affected)}
    db.add(m.CommandReceipt(school_id=school_id,actor_id=actor.user_id,request_key=recall_key,operation='source_recall',request_digest=digest(target),result=result))
    db.flush();return result
