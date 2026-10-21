"""Teaching application services; every mutation belongs to the caller transaction."""
from datetime import datetime,timedelta,timezone
import json
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from spesped.audit import record_audit
from spesped.auth import Actor,require_authority,require_learner_access,require_school_access,active_at,school_today
from spesped.contexts.identity.models import Learner,School,SchoolMembership,UserAccount
from spesped.contexts.evidence import service as evidence
from spesped.contexts.evidence.projections import confirmed_binding_is_current
from spesped.contexts.evidence.schemas import RegisterDerivative
from spesped.contexts.entitlements import service as entitlements
from spesped.contexts.plans import service as plans
from spesped.contexts.plans.projections import teaching_goal_basis,goal_binding_is_current
from spesped.contexts.platform import service as gateway
from spesped.contexts.platform.contracts import SourceInput,GenerationRequest,SourceRef
from spesped.db import utcnow
from spesped.domain.approval import canonical_content_digest
from spesped.errors import DomainError,access_denied
from .common import conflict,expected,replay,remember,event
from .models import *
from .schemas import SessionContent,ReviseSession


def access(db,actor,school_id,learner_id,action='teaching.read'):
    membership=require_school_access(db,actor,school_id)
    if membership.role in {'assistant','guardian','technical_administrator'}: raise access_denied()
    return require_learner_access(db,actor,school_id,learner_id,action)


def lock_learners(db,school_id,ids):
    for learner_id in sorted(set(ids)):
        if db.scalar(select(Learner).where(Learner.school_id == school_id,Learner.id == learner_id).with_for_update().execution_options(populate_existing=True)) is None: raise access_denied()


def load(db,model,school_id,identity,lock=False):
    query=select(model).where(model.school_id == school_id,model.id == str(identity))
    if lock: query=query.with_for_update()
    row=db.scalar(query.execution_options(populate_existing=True))
    if row is None: raise access_denied()
    return row


def row_json(row,fields): return jsonable_encoder({name:getattr(row,name) for name in fields})


def source_binding(db,actor,school_id,learner_id,value):
    value=jsonable_encoder(value)
    item=evidence.evidence(db,actor,school_id,str(value['evidence_id']),'evidence.read',lock=True)
    revision=evidence.current(db,item)
    if (item.learner_id != learner_id or item.current_revision != value['evidence_revision'] or revision.certainty != 'confirmed' or revision.link_id != str(value['link_id'])):
        raise DomainError('source_changed','The selected evidence binding has changed.',409)
    evidence.excerpt_view(db,actor,school_id,str(value['link_id']))
    if not confirmed_binding_is_current(db,school_id,learner_id,str(value['evidence_id']),value['evidence_revision'],str(value['link_id'])):
        raise DomainError('source_changed','The source was corrected or withdrawn. Select its current confirmed revision.',409)
    return value


def basis_snapshot(row):
    return row_json(row,('planned_at','duration_minutes','learners','theme','arena','materials','missing_information'))


def basis_access(db,actor,basis,action='teaching.read'):
    for learner in basis.learners: access(db,actor,basis.school_id,learner['learner_id'],action)


def basis_current(db,actor,basis,*,curated=False,seen=None):
    """All source/goal/observation bindings are checked transitively on every use."""
    if canonical_content_digest(basis_snapshot(basis)) != basis.digest: return False
    seen=set() if seen is None else seen
    if basis.id in seen: return False
    seen=seen | {basis.id}
    for learner in basis.learners:
        lid=learner['learner_id']
        for goal in learner['goals']:
            if not goal_binding_is_current(db,basis.school_id,lid,goal,basis.planned_at): return False
            if not curated:
                try:
                    current=teaching_goal_basis(db,actor,basis.school_id,lid,goal['goal']['id'],at=basis.planned_at)
                    if canonical_content_digest(current) != canonical_content_digest(goal): return False
                except DomainError: return False
        for binding in learner['source_bindings']:
            if curated:
                if not confirmed_binding_is_current(db,basis.school_id,lid,str(binding['evidence_id']),binding['evidence_revision'],str(binding['link_id'])): return False
            else:
                try: source_binding(db,actor,basis.school_id,lid,binding)
                except DomainError: return False
        if learner['profile'] and not curated:
            try: current_profile=plans.profile_view(db,actor,basis.school_id,lid,limit=100)['items']
            except DomainError: return False
            by_id={p['id']:p for p in current_profile}
            if any(p['id'] not in by_id or canonical_content_digest(by_id[p['id']]) != canonical_content_digest(p) for p in learner['profile']): return False
        # Profile metadata currency is additionally represented in source_bindings;
        # the owning profile port checks revisions and current confirmations.
        if learner['profile'] and curated:
            from spesped.contexts.plans.projections import profile_bindings_are_current
            if not profile_bindings_are_current(db,basis.school_id,lid,learner['profile']): return False
        for observation in learner['observations']:
            rev=db.scalar(select(ObservationRevision).where(ObservationRevision.school_id == basis.school_id,ObservationRevision.id == observation['id']).execution_options(populate_existing=True))
            if rev is None or not observation_current(db,rev,seen=seen): return False
            if not curated:
                try: access(db,actor,basis.school_id,lid)
                except DomainError:return False
    return True


def require_basis_current(db,actor,basis):
    basis_access(db,actor,basis)
    if not basis_current(db,actor,basis): raise DomainError('teaching_basis_stale','The teaching basis needs a new review. Select current sources or continue manually with a new basis.',409)


def create_basis(db,actor,school_id,command):
    for selected in command.learners: access(db,actor,school_id,str(selected.learner_id),'teaching.write')
    lock_learners(db,school_id,[str(x.learner_id) for x in command.learners])
    prior,digest=replay(db,actor,school_id,'teaching.basis',command,None)
    if prior:
        row=load(db,TeachingBasis,school_id,prior);require_basis_current(db,actor,row);return row
    selected_learners=[]
    for selected in command.learners:
        lid=str(selected.learner_id)
        goals=[teaching_goal_basis(db,actor,school_id,lid,str(g),at=command.planned_at) for g in selected.goal_revision_ids]
        profiles=[]
        if selected.profile_statement_ids:
            available={p['id']:p for p in plans.profile_view(db,actor,school_id,lid,limit=100)['items']}
            for pid in selected.profile_statement_ids:
                item=available.get(str(pid))
                if item is None or item['state'] != 'confirmed' or item['source_status'] != 'current': raise DomainError('profile_unavailable','Select a current confirmed support profile statement.',409)
                profiles.append(item)
        observations=[]
        for oid in selected.observation_revision_ids:
            rev=load(db,ObservationRevision,school_id,str(oid))
            load(db,TeachingObservation,school_id,rev.observation_id,True)
            if rev.learner_id != lid or not rev.saved or not observation_current(db,rev): raise DomainError('observation_stale','Select a current saved observation.',409)
            observations.append(observation_snapshot(rev))
        bindings=[source_binding(db,actor,school_id,lid,v.model_dump(mode='json')) for v in selected.sources]
        selected_evidence=[]
        for binding in bindings:
            item=evidence.evidence(db,actor,school_id,str(binding['evidence_id']))
            selected_evidence.append(jsonable_encoder(evidence.evidence_view(db,item)))
        bindings.extend(p['source'] for p in profiles)
        for goal in goals: bindings.extend(goal['source_bindings'])
        bindings=list({canonical_content_digest(b):b for b in bindings}.values())
        selected_learners.append(jsonable_encoder({'learner_id':lid,'goals':goals,'profile':profiles,'observations':observations,'evidence':selected_evidence,'source_bindings':bindings}))
    row=TeachingBasis(school_id=school_id,planned_at=command.planned_at.astimezone(timezone.utc),duration_minutes=command.duration_minutes,learners=selected_learners,theme=command.theme,arena=command.arena,materials=command.materials,missing_information=command.missing_information,created_by=actor.user_id,digest='pending')
    row.digest=canonical_content_digest(basis_snapshot(row));db.add(row);db.flush()
    require_basis_current(db,actor,row)
    event(db,actor,row,'teaching.basis_created')
    remember(db,actor,school_id,'teaching.basis',command,digest,row.id)
    return row


def basis_view(db,actor,row):
    basis_access(db,actor,row)
    valid=basis_current(db,actor,row)
    return {'id':row.id,'digest':row.digest,'source_status':'current' if valid else 'review_required','basis':basis_snapshot(row) if valid else None,'manual_fallback_available':True}


def current_revision(db,row):
    return db.scalar(select(SessionRevision).where(SessionRevision.school_id == row.school_id,SessionRevision.session_id == row.id,SessionRevision.revision == row.current_revision))


def session(db,actor,school_id,session_id,action='teaching.read',lock=False):
    row=load(db,TeachingSession,school_id,session_id)
    basis=load(db,TeachingBasis,school_id,current_revision(db,row).basis_id)
    basis_access(db,actor,basis,action)
    if lock:
        lock_learners(db,school_id,[l['learner_id'] for l in basis.learners])
        row=load(db,TeachingSession,school_id,session_id,True)
        basis_access(db,actor,load(db,TeachingBasis,school_id,current_revision(db,row).basis_id),action)
    return row


def revision_valid(db,actor,revision,*,curated=False):
    basis=load(db,TeachingBasis,revision.school_id,revision.basis_id)
    if canonical_content_digest({'basis_digest':basis.digest,'content':revision.content,'field_job_ids':revision.field_job_ids}) != revision.content_digest: return False
    if not basis_current(db,actor,basis,curated=curated): return False
    runtime=(db.info.get('ai_gateway_runtime') or db.info.get('teaching_runtime') or db.info.get('plans_runtime'))
    for job_id in revision.generation_job_ids:
        if curated:
            # Curated access needs only live model/policy/source metadata. Root's
            # gateway predicate must never disclose model output to an assistant.
            from spesped.contexts.platform.service import job_binding_is_current
            if not job_binding_is_current(db,revision.school_id,job_id,runtime): return False
        else:
            if runtime is None: return False
            try: gateway.current_job(db,actor,revision.school_id,job_id,runtime)
            except DomainError: return False
    return True


def approved(db,revision):
    return db.scalar(select(SessionReview).where(SessionReview.school_id == revision.school_id,SessionReview.revision_id == revision.id,SessionReview.kind == 'approve',SessionReview.content_digest == revision.content_digest)) is not None


def follow_up_binding(db,school_id,target_type,target_id,session_revision_id=None):
    delivery_id=None
    if target_type == 'session':
        revision=load(db,SessionRevision,school_id,session_revision_id) if session_revision_id else current_revision(db,load(db,TeachingSession,school_id,target_id))
        session_revision_id=revision.id
    elif target_type == 'brief':session_revision_id=load(db,AssistantBrief,school_id,target_id).session_revision_id
    elif target_type in {'brief_message','assistant_actual_input'}:
        model=BriefMessage if target_type == 'brief_message' else AssistantActualInput
        item=load(db,model,school_id,target_id)
        assigned=load(db,BriefAssignment,school_id,item.assignment_id)
        session_revision_id=load(db,AssistantBrief,school_id,assigned.brief_id).session_revision_id
        if target_type == 'assistant_actual_input':delivery_id=item.delivery_revision_id
    elif target_type == 'delivery_revision':
        actual=load(db,DeliveryRevision,school_id,target_id)
        delivery_id=actual.id;session_revision_id=actual.session_revision_id
    else:return None
    binding={'format':'teaching.follow-up-basis.v1','session_revision_id':session_revision_id,'delivery_revision_id':delivery_id}
    if session_revision_id:
        revision=load(db,SessionRevision,school_id,session_revision_id)
        basis=load(db,TeachingBasis,school_id,revision.basis_id)
        binding.update(session_content_digest=revision.content_digest,basis_id=basis.id,basis_digest=basis.digest)
    return binding


def follow_up(db,actor,school_id,learner_id,target_type,target_id,reason,owner,action,*,session_revision_id=None):
    binding=follow_up_binding(db,school_id,target_type,target_id,session_revision_id)
    dependency_key=canonical_content_digest(binding)
    query=select(TeachingFollowUp).where(TeachingFollowUp.school_id == school_id,TeachingFollowUp.learner_id == learner_id,TeachingFollowUp.target_type == target_type,TeachingFollowUp.target_id == target_id,TeachingFollowUp.reason_code == reason,TeachingFollowUp.dependency_key == dependency_key)
    prior=db.scalar(query)
    if prior:return prior
    row=TeachingFollowUp(school_id=school_id,learner_id=learner_id,target_type=target_type,target_id=target_id,reason_code=reason,owner_id=owner,action=action,state='open',dependency_binding=binding,dependency_key=dependency_key)
    try:
        with db.begin_nested():
            db.add(row);db.flush();event(db,actor,row,'teaching.follow_up_created')
    except IntegrityError as exc:
        unique=getattr(exc.orig,'sqlstate',None) == '23505' or (db.bind.dialect.name == 'sqlite' and 'UNIQUE constraint failed' in str(exc.orig))
        if not unique:raise
        existing=db.scalar(query)
        if existing is None:raise
        return existing
    return row


def session_view(db,actor,row,revision=None):
    revision=revision or current_revision(db,row)
    basis=load(db,TeachingBasis,row.school_id,revision.basis_id);basis_access(db,actor,basis)
    valid=revision_valid(db,actor,revision)
    if not valid:
        for learner in basis.learners: follow_up(db,actor,row.school_id,learner['learner_id'],'session',row.id,'basis_changed',row.owner_id,'Review the affected session and any assigned brief using current sources.',session_revision_id=revision.id)
        for guide in db.scalars(select(AssistantBrief).where(AssistantBrief.school_id == row.school_id,AssistantBrief.session_revision_id == revision.id)):
            follow_up(db,actor,row.school_id,guide.learner_id,'brief',guide.id,'basis_changed',row.owner_id,'Review the affected brief and its dated assignments using current sources.')
    return {'id':row.id,'version':row.version,'state':row.state if valid else 'review_required','owner_id':row.owner_id,'revision_id':revision.id,'revision':revision.revision,'basis_id':basis.id,'content_digest':revision.content_digest,'content':revision.content if valid else None,'source_status':'current' if valid else 'review_required','approved':approved(db,revision) and valid,'planned_at':basis.planned_at,'duration_minutes':basis.duration_minutes,'delivery_state':delivery_status(db,row),'generation_job_id':revision.generation_job_id,'field_job_ids':revision.field_job_ids}


def delivery_status(db,row):
    actual=db.scalar(select(SessionDelivery).where(SessionDelivery.school_id == row.school_id,SessionDelivery.session_id == row.id))
    return actual.state if actual else 'not_recorded'


def depend(db,actor,basis,target_type,target_id,revision):
    for learner in basis.learners:
        for binding in learner['source_bindings']:
            # Register through the evidence owner's API, never through its ORM.
            evidence.register_derivative(db,actor,basis.school_id,str(binding['evidence_id']),RegisterDerivative(evidence_revision=binding['evidence_revision'],target_type=target_type,target_id=target_id,target_revision=revision,state='draft'))


def save_session(db,actor,school_id,command,session_id=None,generation_job_id=None,selected_fields=()):
    basis=load(db,TeachingBasis,school_id,str(command.basis_id));basis_access(db,actor,basis,'teaching.write')
    lock_learners(db,school_id,[l['learner_id'] for l in basis.learners])
    row=session(db,actor,school_id,session_id,'teaching.write',True) if session_id else None
    operation='teaching.session_revise' if row else 'teaching.session_create'
    prior,digest=replay(db,actor,school_id,operation,command,session_id)
    if prior:
        old=session(db,actor,school_id,prior);require_basis_current(db,actor,load(db,TeachingBasis,school_id,current_revision(db,old).basis_id));return old
    require_basis_current(db,actor,basis)
    validate_owner(db,school_id,str(command.owner_id))
    for learner in basis.learners:access(db,Actor(str(command.owner_id)),school_id,learner['learner_id'],'teaching.write')
    if sum(s.minutes for s in command.content.steps) > basis.duration_minutes: raise DomainError('step_duration','The planned steps exceed the available duration.',422)
    if row:
        expected(row,command)
        old_basis=load(db,TeachingBasis,school_id,current_revision(db,row).basis_id)
        if {l['learner_id'] for l in old_basis.learners} != {l['learner_id'] for l in basis.learners}: raise DomainError('session_learners','Create a separate session to change the pupil group.',409)
        row.current_revision+=1;row.state='draft';row.owner_id=str(command.owner_id);row.updated_at=utcnow()
        for brief in db.scalars(select(AssistantBrief).join(SessionRevision,AssistantBrief.session_revision_id == SessionRevision.id).where(SessionRevision.session_id == row.id,AssistantBrief.state == 'approved')):
            brief.state='review_required'
            follow_up(db,actor,school_id,brief.learner_id,'brief',brief.id,'session_changed',row.owner_id,'Review and replace the outdated assigned brief.')
    else:
        row=TeachingSession(school_id=school_id,owner_id=str(command.owner_id),state='draft');db.add(row);db.flush()
    content=command.content.model_dump(mode='json')
    field_jobs={field:[] for field in content}
    if row.current_revision > 1:
        previous=db.scalar(select(SessionRevision).where(SessionRevision.school_id == school_id,SessionRevision.session_id == row.id,SessionRevision.revision == row.current_revision-1))
        field_jobs={field:list(jobs) for field,jobs in previous.field_job_ids.items()}
    for field in getattr(command,'manual_replacements',()):field_jobs[field]=[]
    for field in selected_fields:field_jobs[field]=[generation_job_id]
    previous_jobs=sorted({job for jobs in field_jobs.values() for job in jobs})
    revision=SessionRevision(school_id=school_id,session_id=row.id,revision=row.current_revision,basis_id=basis.id,content=content,content_digest=canonical_content_digest({'basis_digest':basis.digest,'content':content,'field_job_ids':field_jobs}),created_by=actor.user_id,reason=getattr(command,'reason','Initial teaching plan'),generation_job_id=generation_job_id,generation_job_ids=previous_jobs,field_job_ids=field_jobs)
    db.add(revision);db.flush();depend(db,actor,basis,'teaching_session',row.id,row.current_revision)
    event(db,actor,row,operation,revision_id=revision.id)
    remember(db,actor,school_id,operation,command,digest,row.id)
    return row


def validate_owner(db,school_id,user_id):
    person=db.get(UserAccount,user_id,populate_existing=True)
    today=school_today(db.get(School,school_id))
    membership=db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id,SchoolMembership.user_id == user_id,*active_at(SchoolMembership,today)).execution_options(populate_existing=True))
    if person is None or person.state != 'active' or membership is None or membership.role in {'guardian','technical_administrator'}: raise DomainError('owner_unavailable','Choose an active school staff member.',409)


def staff_choices(db,actor,school_id,learner_id,purpose,*,offset=0,limit=50):
    # These are the same active staff candidates accepted by validate_owner.
    # The list never asserts teaching qualifications or grants pupil access.
    access(db,actor,school_id,learner_id,'teaching.write')
    if purpose == 'assistant':require_authority(db,actor,school_id,'teaching.assign',learner_id)
    today=school_today(db.get(School,school_id))
    query=select(UserAccount.id,UserAccount.display_name).join(SchoolMembership,SchoolMembership.user_id == UserAccount.id).where(
        SchoolMembership.school_id == school_id,*active_at(SchoolMembership,today),
        UserAccount.state == 'active',SchoolMembership.role.not_in(['guardian','technical_administrator']))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.execute(query.order_by(UserAccount.display_name,UserAccount.id).offset(offset).limit(limit)).mappings()
    return {'items':[dict(row) for row in rows],'total':total}


def review_session(db,actor,school_id,identity,command,kind):
    row=session(db,actor,school_id,identity,'teaching.write',True)
    basis=load(db,TeachingBasis,school_id,current_revision(db,row).basis_id)
    grants=[]
    if kind == 'approve':
        for learner in basis.learners: grants.append(require_authority(db,actor,school_id,'teaching.approve',learner['learner_id']).id)
    prior,digest=replay(db,actor,school_id,'teaching.session_'+kind,command,identity)
    revision=current_revision(db,row)
    if not revision_valid(db,actor,revision): raise DomainError('teaching_basis_stale','Review the changed source basis before approving this session.',409)
    if prior:return row
    expected(row,command)
    if revision.id != str(command.revision_id) or revision.content_digest != command.content_digest: raise conflict('Approval must bind the exact current session content and basis.')
    if row.state != ('draft' if kind == 'review' else 'in_review'): raise conflict('The session is not in the required review state.')
    row.state='in_review' if kind == 'review' else 'approved';row.updated_at=utcnow()
    db.add(SessionReview(school_id=school_id,revision_id=revision.id,kind=kind,content_digest=revision.content_digest,reviewer_id=actor.user_id,authority_id=json.dumps(grants) if grants else None,reason=command.reason))
    event(db,actor,row,'teaching.session_'+kind,revision_id=revision.id);remember(db,actor,school_id,'teaching.session_'+kind,command,digest,row.id)
    return row


def brief(db,actor,school_id,identity,lock=False):
    row=load(db,AssistantBrief,school_id,identity,lock)
    access(db,actor,school_id,row.learner_id)
    return row


def brief_is_current(db,actor,row,*,curated=False):
    revision=load(db,SessionRevision,row.school_id,row.session_revision_id)
    parent=load(db,TeachingSession,row.school_id,revision.session_id)
    digest=canonical_content_digest({'session_revision_id':row.session_revision_id,'learner_id':row.learner_id,'template':row.template,'content':row.content})
    return row.state == 'approved' and row.reviewed_at is not None and digest == row.content_digest and parent.current_revision == revision.revision and parent.state == 'approved' and approved(db,revision) and revision_valid(db,actor,revision,curated=curated)


def create_brief(db,actor,school_id,command):
    revision=load(db,SessionRevision,school_id,str(command.session_revision_id))
    parent=session(db,actor,school_id,revision.session_id,'teaching.write',True)
    basis=load(db,TeachingBasis,school_id,revision.basis_id)
    if str(command.learner_id) not in {l['learner_id'] for l in basis.learners}: raise access_denied()
    prior,digest=replay(db,actor,school_id,'teaching.brief_create',command,revision.id)
    if prior:
        old=brief(db,actor,school_id,prior)
        if not revision_valid(db,actor,revision):raise DomainError('teaching_basis_stale','The source basis needs review.',409)
        return old
    if parent.current_revision != revision.revision or not approved(db,revision) or parent.state != 'approved' or not revision_valid(db,actor,revision): raise DomainError('approved_session_required','A current exact approved session is required for a brief.',409)
    if command.replaces_brief_id:
        previous=brief(db,actor,school_id,str(command.replaces_brief_id))
        if previous.learner_id != str(command.learner_id) or load(db,SessionRevision,school_id,previous.session_revision_id).session_id != parent.id:raise access_denied()
    content=command.content.model_dump(mode='json')
    row=AssistantBrief(school_id=school_id,session_revision_id=revision.id,learner_id=str(command.learner_id),template=command.template,content=content,content_digest=canonical_content_digest({'session_revision_id':revision.id,'learner_id':str(command.learner_id),'template':command.template,'content':content}),replaces_brief_id=str(command.replaces_brief_id) if command.replaces_brief_id else None,created_by=actor.user_id,state='draft')
    db.add(row);db.flush();depend(db,actor,basis,'assistant_brief',row.id,1);event(db,actor,row,'teaching.brief_created');remember(db,actor,school_id,'teaching.brief_create',command,digest,row.id)
    return row


def review_brief(db,actor,school_id,identity,command):
    row=brief(db,actor,school_id,identity,True)
    access(db,actor,school_id,row.learner_id,'teaching.write')
    authority=require_authority(db,actor,school_id,'teaching.brief.approve',row.learner_id)
    revision=load(db,SessionRevision,school_id,row.session_revision_id)
    parent=session(db,actor,school_id,revision.session_id)
    prior,digest=replay(db,actor,school_id,'teaching.brief_review',command,identity)
    if not revision_valid(db,actor,revision) or current_revision(db,parent).id != revision.id or not approved(db,revision):raise DomainError('teaching_basis_stale','The session changed. Prepare a new brief for the current approved revision.',409)
    if prior:return row
    expected(row,command)
    if row.state != 'draft' or command.content_digest != row.content_digest:raise conflict('Review the exact new brief content.')
    row.state='approved';row.reviewed_at=utcnow();row.reviewed_by=actor.user_id;row.authority_id=authority.id;row.review_reason=command.reason
    event(db,actor,row,'teaching.brief_reviewed');remember(db,actor,school_id,'teaching.brief_review',command,digest,row.id)
    return row


def brief_view(db,actor,row):
    access(db,actor,row.school_id,row.learner_id)
    revision=load(db,SessionRevision,row.school_id,row.session_revision_id)
    current=revision_valid(db,actor,revision) and load(db,TeachingSession,row.school_id,revision.session_id).current_revision == revision.revision
    if not current:
        owner=load(db,TeachingSession,row.school_id,revision.session_id).owner_id
        follow_up(db,actor,row.school_id,row.learner_id,'brief',row.id,'basis_changed',owner,'Review the stale brief and its dated assignments.')
    return {'id':row.id,'version':row.version,'state':row.state if current else 'review_required','session_revision_id':row.session_revision_id,'learner_id':row.learner_id,'template':row.template,'content':row.content if current else None,'content_digest':row.content_digest,'reviewed_by':row.reviewed_by,'reviewed_at':row.reviewed_at}


def assign_brief(db,actor,school_id,identity,command):
    row=brief(db,actor,school_id,identity,True)
    access(db,actor,school_id,row.learner_id,'teaching.write')
    require_authority(db,actor,school_id,'teaching.assign',row.learner_id)
    validate_owner(db,school_id,str(command.assistant_id))
    prior,digest=replay(db,actor,school_id,'teaching.brief_assign',command,identity)
    if not brief_is_current(db,actor,row):raise DomainError('brief_stale','Only a current reviewed brief can be assigned.',409)
    if prior:return load(db,BriefAssignment,school_id,prior)
    expected(row,command)
    basis=load(db,TeachingBasis,school_id,load(db,SessionRevision,school_id,row.session_revision_id).basis_id)
    if not command.valid_from <= basis.planned_at < command.valid_until:raise DomainError('assignment_period','The assignment must cover the planned session.',422)
    assignment=BriefAssignment(school_id=school_id,brief_id=row.id,assistant_id=str(command.assistant_id),valid_from=command.valid_from,valid_until=command.valid_until,role=command.role,assigned_by=actor.user_id,state='active')
    db.add(assignment);db.flush();event(db,actor,assignment,'teaching.brief_assigned');remember(db,actor,school_id,'teaching.brief_assign',command,digest,assignment.id)
    return assignment


def assignment(db,actor,school_id,identity,*,write=False,teacher=False):
    require_school_access(db,actor,school_id)
    row=load(db,BriefAssignment,school_id,identity,write)
    guide=load(db,AssistantBrief,school_id,row.brief_id)
    if actor.user_id != row.assistant_id or teacher:
        access(db,actor,school_id,guide.learner_id,'teaching.write' if write else 'teaching.read')
    else:
        # This explicit dated assignment is the sole curated-content grant. No
        # schoolwide intake/dossier permission is required or inferred.
        member=require_school_access(db,actor,school_id)
        if member.role in {'guardian','technical_administrator'}:raise access_denied()
        if row.state != 'active' or not row.valid_from <= utcnow() < row.valid_until:raise access_denied()
        learner=db.scalar(select(Learner).where(Learner.school_id == school_id,Learner.id == guide.learner_id,Learner.state == 'active'))
        if learner is None:raise access_denied()
    return row,guide


def assignment_labels(db,row,guide):
    """Call only after the teacher/dated-assignee access gate, without dossier access."""
    revision=load(db,SessionRevision,row.school_id,guide.session_revision_id)
    owner=load(db,TeachingSession,row.school_id,revision.session_id).owner_id
    learner_name=db.scalar(select(Learner.display_name).where(Learner.school_id == row.school_id,Learner.id == guide.learner_id))
    names=dict(db.execute(select(UserAccount.id,UserAccount.display_name).where(UserAccount.id.in_([row.assistant_id,owner]))).all())
    return {'learner_name':learner_name,'assistant_name':names.get(row.assistant_id),'follow_up_owner_name':names.get(owner)}


def assignment_view(db,actor,row,guide):
    own=actor.user_id == row.assistant_id
    current=brief_is_current(db,actor,guide,curated=own)
    revision=load(db,SessionRevision,row.school_id,guide.session_revision_id)
    basis=load(db,TeachingBasis,row.school_id,revision.basis_id)
    owner=load(db,TeachingSession,row.school_id,revision.session_id).owner_id
    if not current:follow_up(db,actor,row.school_id,guide.learner_id,'brief',guide.id,'basis_changed',owner,'Review the stale assistant brief and contact the assigned assistant.')
    record_audit(db,actor,row.school_id,'teaching.brief_opened','brief_assignment',row.id)
    return {'id':row.id,'version':row.version,'state':row.state,'brief_state':'assigned' if current else 'review_required','learner_id':guide.learner_id,'role':row.role if current else None,'valid_from':row.valid_from,'valid_until':row.valid_until,'planned_at':basis.planned_at,'arena':basis.arena if current else None,'content':guide.content if current else None,'opened_is_completion':False,'understanding_confirmed':False,'follow_up_owner_id':owner} | assignment_labels(db,row,guide)


def interact(db,actor,school_id,identity,command):
    assignment_row,guide=assignment(db,actor,school_id,identity,write=True)
    own=actor.user_id == assignment_row.assistant_id
    if own and command.kind not in {'question','feedback'}:raise access_denied()
    if not own and command.kind not in {'answer','guidance'}:raise access_denied()
    if not brief_is_current(db,actor,guide,curated=own):raise DomainError('brief_stale','Contact the responsible teacher for a reviewed brief.',409)
    prior,digest=replay(db,actor,school_id,'teaching.brief_message',command,identity)
    if prior:return load(db,BriefMessage,school_id,prior)
    if command.responds_to_id:
        previous=load(db,BriefMessage,school_id,str(command.responds_to_id))
        if previous.assignment_id != assignment_row.id or (command.kind == 'answer' and previous.kind != 'question'):raise access_denied()
    if command.kind == 'answer' and not command.responds_to_id:raise DomainError('question_required','An answer must identify the question.',422)
    row=BriefMessage(school_id=school_id,assignment_id=identity,author_id=actor.user_id,kind=command.kind,text=command.text,responds_to_id=str(command.responds_to_id) if command.responds_to_id else None);db.add(row);db.flush()
    if command.kind == 'question' or command.needs_follow_up:
        revision=load(db,SessionRevision,school_id,guide.session_revision_id);owner=load(db,TeachingSession,school_id,revision.session_id).owner_id
        follow_up(db,actor,school_id,guide.learner_id,'brief_message',row.id,'guidance_required',owner,'Review the assistant question or feedback and give guidance for this assignment.')
    event(db,actor,row,'teaching.brief_message_created');remember(db,actor,school_id,'teaching.brief_message',command,digest,row.id)
    return row


def revoke_assignment(db,actor,school_id,identity,command):
    row,guide=assignment(db,actor,school_id,identity,write=True,teacher=True)
    require_authority(db,actor,school_id,'teaching.assign',guide.learner_id)
    prior,digest=replay(db,actor,school_id,'teaching.assignment_revoke',command,identity)
    if prior:return row
    expected(row,command);row.state='revoked';row.updated_at=utcnow()
    event(db,actor,row,'teaching.assignment_revoked');remember(db,actor,school_id,'teaching.assignment_revoke',command,digest,row.id);return row


def delivery_revision(db,row):
    return db.scalar(select(DeliveryRevision).where(DeliveryRevision.school_id == row.school_id,DeliveryRevision.delivery_id == row.id,DeliveryRevision.revision == row.current_revision))


def participation_rows(db,revision):
    return list(db.scalars(select(LearnerParticipation).where(LearnerParticipation.school_id == revision.school_id,LearnerParticipation.delivery_revision_id == revision.id).order_by(LearnerParticipation.learner_id)))


def staff_rows(db,revision):
    return list(db.scalars(select(StaffParticipation).where(StaffParticipation.school_id == revision.school_id,StaffParticipation.delivery_revision_id == revision.id).order_by(StaffParticipation.staff_id)))


def delivery(db,actor,school_id,identity,action='teaching.read',lock=False):
    row=load(db,SessionDelivery,school_id,identity)
    participants=participation_rows(db,delivery_revision(db,row))
    for p in participants: access(db,actor,school_id,p.learner_id,action)
    if lock:
        lock_learners(db,school_id,[p.learner_id for p in participants]);row=load(db,SessionDelivery,school_id,identity,True)
        for p in participation_rows(db,delivery_revision(db,row)):access(db,actor,school_id,p.learner_id,action)
    return row


def qualification_request(school_id,pupil,staff_id,occurred_at,duration_minutes,provision):
    from .ports import QualificationRequest
    ref=pupil.provision
    # No finer staff/pupil placement within this event is recorded. Never invent
    # a qualified subinterval from a minute total; require full event coverage.
    return QualificationRequest(school_id=school_id,learner_id=str(pupil.learner_id),staff_id=str(staff_id),decision_id=ref['decision_id'] if isinstance(ref,dict) else ref.decision_id,decision_revision_id=ref['decision_revision_id'] if isinstance(ref,dict) else ref.decision_revision_id,provision_id=ref['provision_id'] if isinstance(ref,dict) else ref.provision_id,occurred_at=occurred_at,ended_at=occurred_at+timedelta(minutes=duration_minutes),provision_digest=canonical_content_digest(row_json(provision,('id','decision_revision_id','category','organization','competence','effective_from','effective_until','source'))))


def validate_actual(db,actor,school_id,content):
    from .ports import resolve_qualification
    if content.occurred_at + timedelta(minutes=content.duration_minutes) > utcnow():raise DomainError('future_delivery','Record actual work only after it occurred; keep future work as a plan.',422)
    qualifications={}
    for staff in content.staff:validate_owner(db,school_id,str(staff.staff_id))
    for p in content.participants:
        lid=str(p.learner_id);access(db,actor,school_id,lid,'teaching.write')
        for gid in p.goal_revision_ids:plans.goal_reference(db,actor,school_id,lid,str(gid),at=content.occurred_at,historical=True)
        provision=None
        if p.provision:
            case,decision,revision,provision=entitlements.resolve_provision(db,actor,school_id,lid,str(p.provision.decision_id),str(p.provision.decision_revision_id),str(p.provision.provision_id),at=content.occurred_at,historical=True)
            if provision.category != p.category or provision.counting_basis != p.counting_basis:raise DomainError('delivery_provision','Actual support must use the exact decision category and counting basis.',409)
            if content.occurred_at + timedelta(minutes=p.minutes) > provision.effective_until:raise DomainError('decision_period','Actual participation extends outside the provision period.',409)
        bindings=[]
        if p.category == 'individually_adapted_education' and p.minutes and p.support_status == 'assessed':
            if provision is None:raise DomainError('ito_staffing_unassessed','ITO counting requires its exact provision and reviewed staffing competence. Record unassessed actual work with an owned deviation when the basis is unavailable.',409)
            qualified_minutes=0
            for staff in content.staff:
                if staff.category != p.category:continue
                request=qualification_request(school_id,p,staff.staff_id,content.occurred_at,content.duration_minutes,provision)
                result=resolve_qualification(db,actor,request)
                if result.state == 'reviewed_current':
                    bindings.append(result.model_dump(mode='json'));qualified_minutes+=staff.minutes
            required=p.attributed_staff_minutes if p.counting_basis == 'staff_time' else p.minutes
            if qualified_minutes < required:raise DomainError('ito_staffing_unassessed','The actual staffing lacks a current reviewed competence and responsibility basis for these ITO minutes. Record unassessed work with an owned deviation.',409)
        qualifications[(lid,p.category)]=bindings or None
    for pupil in content.participants:
        possible=sum(min(s.minutes,pupil.minutes) for s in content.staff if s.category == pupil.category)
        if (pupil.attributed_staff_minutes or 0) > possible:raise DomainError('staff_allocation','Delivered staff support exceeds the possible support during actual pupil participation. Record other staff expenditure separately.',422)
    if sum(p.attributed_staff_minutes or 0 for p in content.participants) > sum(s.minutes for s in content.staff):raise DomainError('staff_allocation','Allocated staff minutes exceed actual staff resource time.',422)
    for category in {p.category for p in content.participants}:
        allocated=sum(p.attributed_staff_minutes or 0 for p in content.participants if p.category == category)
        actual=sum(s.minutes for s in content.staff if s.category == category)
        if allocated > actual:raise DomainError('staff_allocation','Allocated staff minutes exceed actual staff time in this support category.',422)
    if content.follow_up_owner_id:validate_owner(db,school_id,str(content.follow_up_owner_id))
    return qualifications


def support_assessment_current(db,actor,revision,pupil):
    if pupil.status == 'absent':return pupil.minutes == 0 and pupil.attributed_staff_minutes in {None,0}
    if pupil.support_status != 'assessed':return False
    if pupil.category != 'individually_adapted_education':return True
    if not pupil.provision or not pupil.qualification_binding:return False
    from .ports import QualificationResult,resolve_qualification
    try:
        ref=pupil.provision
        _,_,_,provision=entitlements.resolve_provision(db,actor,pupil.school_id,pupil.learner_id,ref['decision_id'],ref['decision_revision_id'],ref['provision_id'],at=revision.occurred_at,historical=True)
        actual_staff={s.staff_id:s for s in staff_rows(db,revision) if s.category == pupil.category}
        total=0;seen=set()
        for saved in pupil.qualification_binding:
            stored=QualificationResult.model_validate(saved)
            staff_id=str(stored.request.staff_id)
            if staff_id in seen or staff_id not in actual_staff:return False
            seen.add(staff_id)
            request=qualification_request(pupil.school_id,pupil,staff_id,revision.occurred_at,revision.duration_minutes,provision)
            if stored.request != request or resolve_qualification(db,actor,request) != stored:return False
            total+=actual_staff[staff_id].minutes
        required=pupil.attributed_staff_minutes if pupil.counting_basis == 'staff_time' else pupil.minutes
        return total >= required
    except (DomainError,ValueError,TypeError,KeyError):return False


def save_delivery(db,actor,school_id,command,identity=None):
    content=command.content
    for p in content.participants: access(db,actor,school_id,str(p.learner_id),'teaching.write')
    lock_learners(db,school_id,[str(p.learner_id) for p in content.participants])
    parent=None
    if content.session_revision_id:
        sr=load(db,SessionRevision,school_id,str(content.session_revision_id));parent=session(db,actor,school_id,sr.session_id,'teaching.write',True)
        basis=load(db,TeachingBasis,school_id,sr.basis_id)
        if {str(p.learner_id) for p in content.participants} != {l['learner_id'] for l in basis.learners}:raise DomainError('delivery_learners','Include the exact planned pupils, recording absence explicitly.',422)
        if not approved(db,sr):raise DomainError('approved_session_required','Use an approved session revision or register an unplanned actual session.',409)
    row=delivery(db,actor,school_id,identity,'teaching.write',True) if identity else None
    operation='teaching.delivery_correct' if row else 'teaching.delivery_create'
    prior,digest=replay(db,actor,school_id,operation,command,identity)
    if prior:
        return delivery(db,actor,school_id,prior)
    qualifications=validate_actual(db,actor,school_id,content)
    if row:
        expected(row,command)
        old=delivery_revision(db,row)
        if row.session_id != (parent.id if parent else None):raise DomainError('delivery_session','Correct within the same actual session; a new event needs a separate entry.',409)
        if {p.learner_id for p in participation_rows(db,old)} != {str(p.learner_id) for p in content.participants}:raise DomainError('delivery_learners','An actual correction preserves the recorded group; record an absence or separate event explicitly.',409)
        row.current_revision+=1;row.state=content.status;row.updated_at=utcnow()
    else:
        if parent and db.scalar(select(SessionDelivery).where(SessionDelivery.school_id == school_id,SessionDelivery.session_id == parent.id)) is not None:raise conflict('This session already has actual delivery. Correct the existing record instead of counting it twice.')
        row=SessionDelivery(school_id=school_id,session_id=parent.id if parent else None,state=content.status);db.add(row);db.flush()
    rev=DeliveryRevision(school_id=school_id,delivery_id=row.id,revision=row.current_revision,session_revision_id=str(content.session_revision_id) if content.session_revision_id else None,occurred_at=content.occurred_at,duration_minutes=content.duration_minutes,status=content.status,activity=content.activity,cause=content.cause,cause_detail=content.cause_detail,reason=getattr(command,'reason','Actual event recorded'),recorded_by=actor.user_id)
    db.add(rev);db.flush()
    for p in content.participants:
        values=p.model_dump(mode='json');values['goal_revision_ids']=[str(g) for g in p.goal_revision_ids]
        db.add(LearnerParticipation(school_id=school_id,delivery_revision_id=rev.id,qualification_binding=qualifications[(str(p.learner_id),p.category)],**values))
    for s in content.staff:db.add(StaffParticipation(school_id=school_id,delivery_revision_id=rev.id,**s.model_dump(mode='json')))
    db.flush()
    if identity:
        old_ids=select(DeliveryRevision.id).where(DeliveryRevision.school_id == school_id,DeliveryRevision.delivery_id == row.id,DeliveryRevision.id != rev.id)
        for item in db.scalars(select(AssistantActualInput).where(AssistantActualInput.school_id == school_id,AssistantActualInput.state == 'recorded',AssistantActualInput.delivery_revision_id.in_(old_ids)).with_for_update().execution_options(populate_existing=True)):
            item.state='needs_clarification';item.invalidated_by_revision_id=rev.id;item.updated_at=utcnow()
            assigned=load(db,BriefAssignment,school_id,item.assignment_id)
            guide=load(db,AssistantBrief,school_id,assigned.brief_id)
            owner=load(db,TeachingSession,school_id,load(db,SessionRevision,school_id,guide.session_revision_id).session_id).owner_id
            follow_up(db,actor,school_id,guide.learner_id,'assistant_actual_input',item.id,'actual_revision_changed',owner,'Review the assistant input against the corrected current actual record; the prior reconciliation is historical.')
            event(db,actor,item,'teaching.actual_reconciliation_invalidated',delivery_revision_id=rev.id)
    if content.follow_up:
        for p in content.participants:follow_up(db,actor,school_id,str(p.learner_id),'delivery_revision',rev.id,'delivery_deviation',str(content.follow_up_owner_id),content.follow_up)
    event(db,actor,row,operation,revision_id=rev.id);remember(db,actor,school_id,operation,command,digest,row.id)
    return row


def ensure_staffing_follow_up(db,actor,revision,pupil,assessed):
    if pupil.category != 'individually_adapted_education' or not pupil.minutes or pupil.support_status != 'assessed' or assessed:return
    owner=revision.recorded_by
    if revision.session_revision_id:
        planned=load(db,SessionRevision,revision.school_id,revision.session_revision_id)
        owner=load(db,TeachingSession,revision.school_id,planned.session_id).owner_id
    follow_up(db,actor,revision.school_id,pupil.learner_id,'delivery_revision',revision.id,'staffing_basis_changed',owner,'Review the original staffing competence and responsibility basis; claimed support is currently unassessed and actual staff expenditure remains separate.')


def delivery_follow_up_view(db,actor,revision,*,learner_scoped=False):
    hidden={'follow_up_owner_id':None,'follow_up':None,'follow_up_source_status':'not_exposed'}
    if learner_scoped:return hidden
    rows=list(db.scalars(select(TeachingFollowUp).where(
        TeachingFollowUp.school_id == revision.school_id,
        TeachingFollowUp.target_type == 'delivery_revision',
        TeachingFollowUp.target_id == revision.id,
        TeachingFollowUp.reason_code == 'delivery_deviation')))
    if not rows:return hidden | {'follow_up_source_status':'none'}
    views=[follow_up_view(db,actor,row) for row in rows]
    values={(v['owner_id'],v['action']) for v in views}
    if any(v['source_status'] != 'current' for v in views) or len(values) != 1:
        return hidden | {'follow_up_source_status':'review_required'}
    owner,action=next(iter(values))
    return {'follow_up_owner_id':owner,'follow_up':action,'follow_up_source_status':'current'}


def delivery_view(db,actor,row,revision=None,learner_id=None):
    revision=revision or delivery_revision(db,row)
    participants=participation_rows(db,revision)
    if learner_id:
        access(db,actor,row.school_id,learner_id)
        participants=[p for p in participants if p.learner_id == learner_id]
        if not participants:raise access_denied()
    else:
        for p in participants:access(db,actor,row.school_id,p.learner_id)
    assessments={p.id:support_assessment_current(db,actor,revision,p) for p in participants}
    for p in participants:ensure_staffing_follow_up(db,actor,revision,p,assessments[p.id])
    # A learner-scoped projection contains no other child's participation or
    # group narrative. Staff totals are exposed only through the group read.
    return {'id':row.id,'version':row.version,'revision':revision.revision,'revision_id':revision.id,'session_revision_id':revision.session_revision_id,'state':revision.status,'occurred_at':revision.occurred_at,'recorded_at':revision.created_at,'recorded_by':revision.recorded_by,'duration_minutes':revision.duration_minutes,'activity':revision.activity if not learner_id else None,'cause':revision.cause,'cause_detail':revision.cause_detail if not learner_id else None,'correction_reason':revision.reason if not learner_id else None,'participants':[row_json(p,('learner_id','goal_revision_ids','status','minutes','category','support','provision','counting_basis','attributed_staff_minutes','support_status')) | {'support_assessment':'assessed' if assessments[p.id] else 'unassessed'} for p in participants],'staff':[row_json(s,('staff_id','minutes','role','category')) for s in staff_rows(db,revision)] if not learner_id else None,'staff_minutes':sum(s.minutes for s in staff_rows(db,revision)) if not learner_id else None,'staff_labels_are_reported':True,'staff_labels_prove_qualification':False} | delivery_follow_up_view(db,actor,revision,learner_scoped=learner_id is not None)


def observation_snapshot(rev):
    return row_json(rev,('id','observation_id','revision','learner_id','occurred_at','created_at','author_id','session_revision_id','assignment_id','goal_revision_id','observation','support','interpretation','next_step','input_method','saved'))


def observation_current(db,rev,*,seen=None):
    root=load(db,TeachingObservation,rev.school_id,rev.observation_id)
    if root.current_revision != rev.revision or root.learner_id != rev.learner_id or not rev.saved:return False
    # Actual observations remain attributed facts, independently of whether a
    # prior pedagogical plan is still current. They never inherit its prose.
    return rev.input_method != 'unconfirmed_transcript'


def observation_authorize(db,actor,school_id,content,*,write=False):
    if content.assignment_id:
        row,guide=assignment(db,actor,school_id,str(content.assignment_id),write=write)
        if guide.learner_id != str(content.learner_id) or (content.session_revision_id and str(content.session_revision_id) != guide.session_revision_id):raise access_denied()
        if actor.user_id == row.assistant_id:
            if not row.valid_from <= content.occurred_at < row.valid_until:raise access_denied()
            # Saving an actual observation after a source correction is allowed:
            # only its own typed input is exposed, never stale brief prose.
            return
    access(db,actor,school_id,str(content.learner_id),'teaching.write' if write else 'teaching.read')


def save_observation(db,actor,school_id,command,identity=None):
    content=command.content
    observation_authorize(db,actor,school_id,content,write=True)
    lock_learners(db,school_id,[str(content.learner_id)])
    old=None
    if identity:
        row=load(db,TeachingObservation,school_id,identity,True)
        if row.author_id != actor.user_id:raise access_denied()
        old=db.scalar(select(ObservationRevision).where(ObservationRevision.school_id == school_id,ObservationRevision.observation_id == row.id,ObservationRevision.revision == row.current_revision))
        # A wrong-pupil correction needs both original and new scope; an assistant
        # cannot move an observation between pupil assignments.
        if row.learner_id != str(content.learner_id):
            access(db,actor,school_id,row.learner_id,'teaching.write');access(db,actor,school_id,str(content.learner_id),'teaching.write')
    else: row=None
    operation='teaching.observation_correct' if row else 'teaching.observation_create'
    prior,digest=replay(db,actor,school_id,operation,command,identity)
    if prior:return load(db,TeachingObservation,school_id,prior)
    if content.occurred_at > utcnow():raise DomainError('future_observation','An observation must already have occurred.',422)
    if content.session_revision_id:
        sr=load(db,SessionRevision,school_id,str(content.session_revision_id));basis=load(db,TeachingBasis,school_id,sr.basis_id)
        allowed=next((l for l in basis.learners if l['learner_id'] == str(content.learner_id)),None)
        if allowed is None:raise access_denied()
        if content.goal_revision_id and str(content.goal_revision_id) not in {g['goal']['id'] for g in allowed['goals']}:raise DomainError('observation_goal','Use a goal from this learner’s exact session basis.',409)
    if content.goal_revision_id and not content.assignment_id:
        plans.goal_reference(db,actor,school_id,str(content.learner_id),str(content.goal_revision_id),at=content.occurred_at,historical=True)
    if content.assignment_id and content.goal_revision_id:
        _,guide=assignment(db,actor,school_id,str(content.assignment_id))
        sr=load(db,SessionRevision,school_id,guide.session_revision_id);basis=load(db,TeachingBasis,school_id,sr.basis_id)
        allowed=next(l for l in basis.learners if l['learner_id'] == str(content.learner_id))
        if str(content.goal_revision_id) not in {g['goal']['id'] for g in allowed['goals']}:raise access_denied()
    if row:
        expected(row,command)
        if old.saved and not command.save:raise DomainError('observation_state','A saved fact cannot become an unconfirmed draft. Save an attributed correction.',409)
        row.current_revision+=1;row.learner_id=str(content.learner_id);row.state='corrected' if command.save else 'draft';row.updated_at=utcnow()
    else:
        row=TeachingObservation(school_id=school_id,learner_id=str(content.learner_id),author_id=actor.user_id,state='saved' if command.save else 'draft');db.add(row);db.flush()
    values=content.model_dump(exclude={'transcript_reviewed'},mode='python')
    for name in ('learner_id','session_revision_id','assignment_id','goal_revision_id'):
        if values[name] is not None:values[name]=str(values[name])
    rev=ObservationRevision(school_id=school_id,observation_id=row.id,revision=row.current_revision,**values,saved=command.save,author_id=actor.user_id,reason=getattr(command,'reason','Author confirmed short observation') if command.save else 'Unconfirmed author draft')
    db.add(rev);db.flush();event(db,actor,row,operation,revision_id=rev.id)
    remember(db,actor,school_id,operation,command,digest,row.id)
    # Existing bases bind the exact observation revision. A correction makes
    # active derived prose stale immediately through observation_current.
    return row


def observation_view(db,actor,row,revision=None):
    rev=revision or db.scalar(select(ObservationRevision).where(ObservationRevision.school_id == row.school_id,ObservationRevision.observation_id == row.id,ObservationRevision.revision == row.current_revision))
    if row.learner_id != rev.learner_id:
        # Historical wrong-pupil text is never an access bridge back to that pupil.
        access(db,actor,row.school_id,row.learner_id);access(db,actor,row.school_id,rev.learner_id)
    elif rev.assignment_id and row.author_id == actor.user_id:
        assignment(db,actor,row.school_id,rev.assignment_id)
    else:access(db,actor,row.school_id,row.learner_id)
    if not rev.saved and row.author_id != actor.user_id:raise access_denied()
    return {**observation_snapshot(rev),'id':row.id,'revision_id':rev.id,'version':row.version,'state':row.state,'current':row.current_revision == rev.revision and row.learner_id == rev.learner_id,'confirmed':rev.saved and rev.input_method != 'unconfirmed_transcript','correction_reason':rev.reason}


def read_observation(db,actor,school_id,learner_id,revision_id):
    """Actor-aware public read/provenance port for timeline/reporting consumers."""
    access(db,actor,school_id,learner_id)
    rev=load(db,ObservationRevision,school_id,revision_id)
    row=load(db,TeachingObservation,school_id,rev.observation_id)
    if row.learner_id != learner_id or rev.learner_id != learner_id or not observation_current(db,rev):raise DomainError('observation_unavailable','The saved observation was corrected or is unavailable.',409)
    return observation_view(db,actor,row,rev)


def observations_for_learner(db,actor,school_id,learner_id,*,start=None,end=None,goal_revision_id=None,offset=0,limit=50):
    access(db,actor,school_id,learner_id)
    query=select(ObservationRevision).join(TeachingObservation,TeachingObservation.id == ObservationRevision.observation_id).where(TeachingObservation.school_id == school_id,TeachingObservation.learner_id == learner_id,ObservationRevision.learner_id == learner_id,ObservationRevision.revision == TeachingObservation.current_revision,ObservationRevision.saved.is_(True))
    if start:query=query.where(ObservationRevision.occurred_at >= start)
    if end:query=query.where(ObservationRevision.occurred_at < end)
    if goal_revision_id:query=query.where(ObservationRevision.goal_revision_id == goal_revision_id)
    rows=list(db.scalars(query.order_by(ObservationRevision.occurred_at.desc(),ObservationRevision.id)))
    return {'items':[observation_view(db,actor,load(db,TeachingObservation,school_id,r.observation_id),r) for r in rows[offset:offset+limit]],'total':len(rows)}


def resolve_generation_source(db,actor,school_id,learner_id,purpose,reference):
    """Server-owned immutable AI input; callers cannot submit evidence prose."""
    if purpose != 'session_planning' or reference.kind != 'teaching_basis' or reference.revision != 1:raise access_denied()
    basis=load(db,TeachingBasis,school_id,str(reference.source_id))
    # Current bounded generation is one pupil/one session. Group actual teaching
    # remains explicitly supported through manual reviewed session commands.
    if len(basis.learners) != 1 or basis.learners[0]['learner_id'] != learner_id:raise access_denied()
    access(db,actor,school_id,learner_id,'teaching.write');require_basis_current(db,actor,basis)
    return SourceInput(reference=reference,school_id=school_id,learner_id=learner_id,purpose=purpose,content=json.dumps(basis_snapshot(basis),sort_keys=True,separators=(',',':'),ensure_ascii=False),media_type='text/plain',provenance='school_data')


def suggestion_job(db,actor,school_id,session_id,job_id,runtime):
    row=session(db,actor,school_id,session_id,'teaching.write',True)
    revision=current_revision(db,row);basis=load(db,TeachingBasis,school_id,revision.basis_id)
    job=gateway.current_job(db,actor,school_id,job_id,runtime,lock=True)
    refs=[s['reference'] for s in job.source_manifest]
    if (job.purpose != 'session_planning' or len(basis.learners) != 1 or job.learner_id != basis.learners[0]['learner_id'] or refs != [{'kind':'teaching_basis','source_id':basis.id,'revision':1}]):raise access_denied()
    if job.state != 'succeeded' or not job.output:raise DomainError('suggestion_unavailable','The model result is not available. Continue in the manual session editor.',409)
    require_basis_current(db,actor,basis)
    return row,revision,basis,job


def request_suggestion(db,actor,school_id,identity,command,runtime):
    row=session(db,actor,school_id,identity,'teaching.write')
    basis=load(db,TeachingBasis,school_id,current_revision(db,row).basis_id)
    require_basis_current(db,actor,basis)
    if len(basis.learners) != 1:raise DomainError('group_generation_scope','Generate a pupil-specific suggestion from a single-pupil basis, or edit this group session manually.',409)
    request=GenerationRequest(learner_id=basis.learners[0]['learner_id'],purpose='session_planning',policy_id=command.policy_id,release_id=command.release_id,logical_request_key=command.request_key,sources=[SourceRef(kind='teaching_basis',source_id=basis.id,revision=1)])
    return gateway.create_job(db,actor,school_id,request,runtime)


def suggestion_diff(db,actor,school_id,identity,job_id,runtime):
    row,revision,basis,job=suggestion_job(db,actor,school_id,identity,job_id,runtime)
    candidate=SessionContent.model_validate(job.output['content']).model_dump(mode='json')
    return {'session_id':row.id,'expected_version':row.version,'current_revision_id':revision.id,'job_id':job.id,'unconfirmed':True,'requires_human_review':True,'changes':[{ 'field':field,'before':revision.content[field],'proposed':candidate[field],'changed':revision.content[field] != candidate[field]} for field in candidate],'missing_evidence':job.output['missing_evidence'],'source_manifest':job.source_manifest}


def review_suggestion(db,actor,school_id,identity,command,runtime):
    row,revision,basis,job=suggestion_job(db,actor,school_id,identity,str(command.job_id),runtime)
    prior,digest=replay(db,actor,school_id,'teaching.suggestion_review',command,identity)
    if prior:return row
    expected(row,command)
    candidate=SessionContent.model_validate(job.output['content']).model_dump(mode='json') if command.content is None else command.content.model_dump(mode='json')
    reviewed_revision=revision
    if command.outcome != 'rejected':
        merged=dict(revision.content)
        for field in command.selected_fields:merged[field]=candidate[field]
        content=SessionContent.model_validate(merged)
        # A fresh internal request identity does not create a second external
        # logical command. The outer review is atomically persisted below.
        revise=ReviseSession(request_key='suggestion:'+canonical_content_digest({'key':command.request_key,'actor':actor.user_id}),expected_version=row.version,basis_id=basis.id,owner_id=row.owner_id,content=content,reason=command.reason or 'Selected fields from reviewed AI suggestion')
        row=save_session(db,actor,school_id,revise,row.id,generation_job_id=job.id,selected_fields=command.selected_fields)
        reviewed_revision=current_revision(db,row)
    db.add(ProposalReview(school_id=school_id,session_id=row.id,session_revision_id=reviewed_revision.id,job_id=job.id,job_digest=canonical_content_digest({'source_manifest':job.source_manifest,'release_digest':job.release_digest,'policy_version':job.policy_version,'output':job.output}),outcome=command.outcome,selected_fields=command.selected_fields,reviewer_id=actor.user_id,reason=command.reason))
    event(db,actor,row,'teaching.suggestion_reviewed',outcome=command.outcome,job_id=job.id)
    remember(db,actor,school_id,'teaching.suggestion_review',command,digest,row.id)
    return row


def resolve_follow_up(db,actor,school_id,identity,command):
    row=load(db,TeachingFollowUp,school_id,identity,True)
    access(db,actor,school_id,row.learner_id,'teaching.write')
    if actor.user_id != row.owner_id:require_authority(db,actor,school_id,'teaching.follow_up',row.learner_id)
    prior,digest=replay(db,actor,school_id,'teaching.follow_up_resolve',command,identity)
    if prior:return row
    expected(row,command)
    if row.state != 'open':raise conflict('The follow-up is already resolved.')
    row.state='resolved';row.resolution=command.resolution;row.updated_at=utcnow()
    event(db,actor,row,'teaching.follow_up_resolved');remember(db,actor,school_id,'teaching.follow_up_resolve',command,digest,row.id);return row


def delivery_summary(db,actor,school_id,learner_id,start,end):
    access(db,actor,school_id,learner_id)
    if start >= end:raise DomainError('summary_period','Use a nonempty UTC-aware half-open interval.',422)
    rows=list(db.scalars(select(LearnerParticipation).join(DeliveryRevision,LearnerParticipation.delivery_revision_id == DeliveryRevision.id).join(SessionDelivery,SessionDelivery.id == DeliveryRevision.delivery_id).where(LearnerParticipation.school_id == school_id,LearnerParticipation.learner_id == learner_id,DeliveryRevision.revision == SessionDelivery.current_revision,DeliveryRevision.occurred_at >= start,DeliveryRevision.occurred_at < end)))
    categories={};assessed_categories={};unassessed_categories={}
    provisions={}
    for row in rows:
        categories[row.category]=categories.get(row.category,0)+row.minutes
        actual_revision=load(db,DeliveryRevision,school_id,row.delivery_revision_id)
        assessed=support_assessment_current(db,actor,actual_revision,row)
        ensure_staffing_follow_up(db,actor,actual_revision,row,assessed)
        amounts=assessed_categories if assessed else unassessed_categories
        amounts[row.category]=amounts.get(row.category,0)+row.minutes
        if row.provision:
            key=canonical_content_digest(row.provision)
            bucket=provisions.setdefault(key,{'reference':row.provision,'counting_basis':row.counting_basis,'recorded_minutes':0,'assessed_recorded_minutes':0,'unassessed_claimed_minutes':0,'actual_revision_ids':[],'entitlement':None,'comparison':'unassessed'})
            amount=0 if row.status == 'absent' else (row.minutes if row.counting_basis == 'learner_time' else row.attributed_staff_minutes or 0)
            if assessed:bucket['assessed_recorded_minutes']+=amount
            else:bucket['unassessed_claimed_minutes']+=amount
            bucket['recorded_minutes']=None if bucket['unassessed_claimed_minutes'] else bucket['assessed_recorded_minutes']
            bucket['actual_revision_ids'].append(row.delivery_revision_id)
    for bucket in provisions.values():
        ref=bucket['reference']
        try:
            case,decision,revision,provision=entitlements.resolve_provision(db,actor,school_id,learner_id,ref['decision_id'],ref['decision_revision_id'],ref['provision_id'],historical=True)
            quantity=entitlements.entitlement_quantity(case,decision,revision,provision)
            if quantity:
                bucket['entitlement']={'amount':str(provision.amount),'unit':provision.unit,'counting_basis':provision.counting_basis,'effective_from':provision.effective_from,'effective_until':provision.effective_until}
                bucket['comparison']='recorded_support_only' if (start,end) == (provision.effective_from,provision.effective_until) else 'different_reference_period'
            else:bucket['comparison']='non_quantitative'
        except DomainError:bucket['comparison']='basis_unavailable'
        if bucket['unassessed_claimed_minutes'] and bucket['comparison'] != 'basis_unavailable':bucket['comparison']='support_unassessed'
    return {'learner_id':learner_id,'start':start,'end':end,'actual_minutes_by_category':categories,'assessed_minutes_by_category':assessed_categories,'unassessed_claimed_minutes_by_category':unassessed_categories,'provisions':list(provisions.values()),'category_totals_are_actual_claims':True,'entitlement_fulfilment':'unassessed','missing_records_are_zero':False,'staff_time_is_learner_time':False}


def submit_actual_input(db,actor,school_id,identity,command):
    assigned,guide=assignment(db,actor,school_id,identity,write=True)
    if actor.user_id != assigned.assistant_id:raise access_denied()
    prior,digest=replay(db,actor,school_id,'teaching.actual_input',command,identity)
    if prior:return load(db,AssistantActualInput,school_id,prior)
    if not assigned.valid_from <= command.content.occurred_at < assigned.valid_until:raise access_denied()
    if command.content.occurred_at+timedelta(minutes=command.content.duration_minutes) > utcnow():raise DomainError('future_delivery','Record input only after the actual work occurred.',422)
    row=AssistantActualInput(school_id=school_id,assignment_id=assigned.id,author_id=actor.user_id,occurred_at=command.content.occurred_at,content=command.content.model_dump(mode='json'),state='submitted');db.add(row);db.flush()
    revision=load(db,SessionRevision,school_id,guide.session_revision_id);owner=load(db,TeachingSession,school_id,revision.session_id).owner_id
    follow_up(db,actor,school_id,guide.learner_id,'assistant_actual_input',row.id,'actual_input_review',owner,'Review assistant actual input against the actual session record; input alone does not count delivered entitlement minutes.')
    event(db,actor,row,'teaching.actual_input_submitted');remember(db,actor,school_id,'teaching.actual_input',command,digest,row.id);return row


def matching_current_actual(db,actor,row,guide,revision_id,*,lock=False):
    rev=load(db,DeliveryRevision,row.school_id,revision_id)
    actual=delivery(db,actor,row.school_id,rev.delivery_id,'teaching.write',lock)
    parent=load(db,TeachingSession,row.school_id,load(db,SessionRevision,row.school_id,guide.session_revision_id).session_id)
    pupil=next((p for p in participation_rows(db,rev) if p.learner_id == guide.learner_id and p.category == row.content['category']),None)
    if (actual.current_revision != rev.revision or actual.session_id != parent.id or rev.status not in {'delivered','partial'} or pupil is None or pupil.status == 'absent' or pupil.minutes <= 0 or not support_assessment_current(db,actor,rev,pupil) or rev.occurred_at != row.occurred_at or pupil.minutes != row.content['duration_minutes'] or pupil.status != row.content['status']):
        raise DomainError('actual_input_mismatch','Link the eligible exact current actual record or request clarification.',409)
    return rev


def review_actual_input(db,actor,school_id,identity,command):
    # Match delivery's learner -> delivery -> input lock order, preventing an
    # actual correction from racing a review into a stale reconciliation.
    preview=load(db,AssistantActualInput,school_id,identity)
    assigned,guide=assignment(db,actor,school_id,preview.assignment_id,teacher=True)
    if command.delivery_revision_id:
        candidate=load(db,DeliveryRevision,school_id,str(command.delivery_revision_id))
        actual=delivery(db,actor,school_id,candidate.delivery_id,'teaching.write')
        lock_learners(db,school_id,[p.learner_id for p in participation_rows(db,delivery_revision(db,actual))])
    else:lock_learners(db,school_id,[guide.learner_id])
    rev=matching_current_actual(db,actor,preview,guide,str(command.delivery_revision_id),lock=True) if command.delivery_revision_id else None
    row=load(db,AssistantActualInput,school_id,identity,True)
    access(db,actor,school_id,guide.learner_id,'teaching.write')
    prior,digest=replay(db,actor,school_id,'teaching.actual_input_review',command,identity)
    if prior:return row
    expected(row,command)
    if row.state != 'submitted' and not (row.state == 'needs_clarification' and row.invalidated_by_revision_id):raise conflict('This actual input has already been reviewed; submit a separate clarification or correction.')
    row.delivery_revision_id=rev.id if rev else None;row.invalidated_by_revision_id=None
    row.state=command.outcome;row.reviewed_by=actor.user_id;row.review_reason=command.reason;row.updated_at=utcnow()
    db.add(ActualInputReview(school_id=school_id,input_id=row.id,outcome=command.outcome,delivery_revision_id=rev.id if rev else None,reason=command.reason,reviewed_by=actor.user_id,reviewed_at=utcnow()))
    event(db,actor,row,'teaching.actual_input_reviewed');remember(db,actor,school_id,'teaching.actual_input_review',command,digest,row.id);return row


def actual_input_view(db,actor,row,guide):
    current=brief_is_current(db,actor,guide,curated=actor.user_id != row.reviewed_by and actor.user_id == load(db,BriefAssignment,row.school_id,row.assignment_id).assistant_id)
    value=row_json(row,('id','version','state','author_id','occurred_at','created_at','content','delivery_revision_id','review_reason','invalidated_by_revision_id'))
    # A historical link is shown as history, never as current reconciled work.
    reconciled=False
    if row.state == 'recorded' and row.delivery_revision_id:
        rev=load(db,DeliveryRevision,row.school_id,row.delivery_revision_id)
        actual=load(db,SessionDelivery,row.school_id,rev.delivery_id)
        reconciled=actual.current_revision == rev.revision and actual.state in {'delivered','partial'}
    if row.state == 'recorded' and not reconciled:value['state']='needs_clarification'
    value['currently_reconciled']=reconciled
    if not current:value['review_reason']=None
    history=list(db.scalars(select(ActualInputReview).where(ActualInputReview.school_id == row.school_id,ActualInputReview.input_id == row.id).order_by(ActualInputReview.created_at,ActualInputReview.id)))
    value['review_history']=[row_json(h,('id','outcome','delivery_revision_id','reviewed_by','reviewed_at')) | {'reason':h.reason if current else None,'historical':h.delivery_revision_id != row.delivery_revision_id or not reconciled} for h in history]
    return value


def follow_up_dependencies_current(db,actor,row):
    binding=row.dependency_binding
    if not isinstance(binding,dict) or binding.get('format') != 'teaching.follow-up-basis.v1' or canonical_content_digest(binding) != row.dependency_key:return False
    try:
        if binding.get('session_revision_id'):
            revision=load(db,SessionRevision,row.school_id,binding['session_revision_id'])
            basis=load(db,TeachingBasis,row.school_id,revision.basis_id)
            if revision.content_digest != binding['session_content_digest'] or basis.id != binding['basis_id'] or basis.digest != binding['basis_digest']:return False
            basis_access(db,actor,basis)
            if not revision_valid(db,actor,revision):return False
        if binding.get('delivery_revision_id'):
            revision=load(db,DeliveryRevision,row.school_id,binding['delivery_revision_id'])
            for pupil in participation_rows(db,revision):
                access(db,actor,row.school_id,pupil.learner_id)
                for goal in pupil.goal_revision_ids:plans.goal_reference(db,actor,row.school_id,pupil.learner_id,goal,at=revision.occurred_at,historical=True)
                if pupil.category == 'individually_adapted_education' and pupil.minutes and not support_assessment_current(db,actor,revision,pupil):return False
                if pupil.provision:
                    ref=pupil.provision
                    entitlements.resolve_provision(db,actor,row.school_id,pupil.learner_id,ref['decision_id'],ref['decision_revision_id'],ref['provision_id'],at=revision.occurred_at,historical=True)
        return bool(binding.get('session_revision_id') or binding.get('delivery_revision_id'))
    except (DomainError,KeyError,TypeError):return False


def follow_up_view(db,actor,row):
    access(db,actor,row.school_id,row.learner_id)
    value=row_json(row,('id','version','state','target_type','target_id','reason_code','owner_id','action','resolution','dependency_binding'))
    current=follow_up_dependencies_current(db,actor,row)
    if not current:
        value['resolution']=None
        # Delivery actions are user-authored group prose. Generic source-change
        # actions remain actionable without disclosing the withdrawn material.
        if row.target_type == 'delivery_revision' and row.reason_code == 'delivery_deviation':value['action']=None
    value['source_status']='current' if current else 'review_required'
    return value
