"""Transaction-owning protected workflows. No external delivery or AI decisions."""
from functools import wraps
import hashlib
import json
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from spesped.auth import Actor, require_school_access, require_authority, active_at, school_today
from spesped.audit import record_audit
from spesped.contexts.identity.models import School, SchoolMembership, UserAccount, Learner
from spesped.contexts.governance.ports import ValidatedEvidenceReference
from spesped.db import utcnow
from spesped.errors import DomainError, access_denied
from . import models as m
from .ports import ReviewedRuleContext


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def view(row):
    return json.loads(json.dumps({c.name:getattr(row,c.name) for c in row.__table__.columns},default=str))


def transaction(fn):
    @wraps(fn)
    def run(db,*args,**kwargs):
        try:
            result=fn(db,*args,**kwargs)
            db.commit()
            return result
        except (StaleDataError,IntegrityError,OperationalError) as exc:
            db.rollback()
            raise DomainError('write_conflict','A concurrent change occurred. Reload and retry the same request key.',409) from exc
        except Exception:
            db.rollback()
            raise
    return run


def staff_membership(db,actor,school_id):
    member=require_school_access(db,actor,school_id)
    if member.role=='guardian':raise access_denied()
    return member


def authority(db,actor,school_id,action):
    staff_membership(db,actor,school_id)
    return require_authority(db,actor,school_id,'safeguarding.'+action)


def reporting_access(db,actor,school_id):
    staff_membership(db,actor,school_id)
    authority(db,actor,school_id,'report')


def person_valid(db,school_id,user_id):
    school=db.get(School,school_id)
    user=db.get(UserAccount,str(user_id))
    member=db.scalar(select(SchoolMembership).where(SchoolMembership.school_id==school_id,SchoolMembership.user_id==str(user_id),*active_at(SchoolMembership,school_today(school))))
    if user is None or user.state!='active' or member is None or member.role=='guardian':
        raise DomainError('invalid_owner','Select an active staff member in this school.')


def case_access(db,actor,school_id,case_id,action='read',lock=False):
    staff_membership(db,actor,school_id)
    query=select(m.CaseRecord).where(m.CaseRecord.school_id==school_id,m.CaseRecord.id==str(case_id)).execution_options(populate_existing=True)
    if lock: query=query.with_for_update()
    case=db.scalar(query)
    if case is None or actor.user_id in case.excluded_user_ids: raise access_denied()
    # Scope is always exact. Neither school administration, learner access,
    # author identity nor owner metadata is a dossier permission.
    require_authority(db,actor,school_id,'safeguarding.case.read',learner_id=case.learner_id,case_id=case.id)
    if action!='read': require_authority(db,actor,school_id,'safeguarding.case.'+action,learner_id=case.learner_id,case_id=case.id)
    return case


def personal_access(db,actor,school_id,case_id,lock=False):
    reporting_access(db,actor,school_id)
    query=select(m.CaseRecord).where(m.CaseRecord.school_id==school_id,m.CaseRecord.id==str(case_id)).execution_options(populate_existing=True)
    if lock: query=query.with_for_update()
    case=db.scalar(query)
    if case is None or case.author_id!=actor.user_id or actor.user_id in case.excluded_user_ids: raise access_denied()
    return case


def participant_access(db,actor,school_id,case_id,lock=False):
    staff_membership(db,actor,school_id)
    query=select(m.CaseRecord).where(m.CaseRecord.school_id==school_id,m.CaseRecord.id==str(case_id)).execution_options(populate_existing=True)
    if lock:query=query.with_for_update()
    case=db.scalar(query)
    if case is None or actor.user_id in case.excluded_user_ids:raise access_denied()
    require_authority(db,actor,school_id,'safeguarding.case.contribute',learner_id=case.learner_id,case_id=case.id)
    return case


def owner_valid(db,case,user_id,full=False):
    person_valid(db,case.school_id,user_id)
    try:case_access(db,Actor(str(user_id)),case.school_id,case.id,'write')
    except DomainError:
        if full:raise
        participant_access(db,Actor(str(user_id)),case.school_id,case.id)


def scoped_child(db,model,case,identifier):
    row=db.scalar(select(model).where(model.school_id==case.school_id,model.case_id==case.id,model.id==str(identifier)))
    if row is None: raise access_denied()
    return row


def all_children(db,model,case):
    return list(db.scalars(select(model).where(model.school_id==case.school_id,model.case_id==case.id).order_by(*([model.recorded_at,model.id] if hasattr(model,'recorded_at') else [model.id]))))


COLLECTIONS={'accounts':m.AttributedAccount,'pupil_views':m.PupilPerspective,'plans':m.ActionPlan,'measures':m.PlanMeasure,
    'performed_actions':m.PerformedAction,'drafts':m.ConcernDraft,'actual_contacts':m.ActualContact,
    'contact_reconciliations':m.ContactReconciliation,'followups':m.Followup,'reviews':m.CaseReview,'corrections':m.RecordCorrection}
TYPED={'environment':m.EnvironmentCase,'concern':m.ConcernReport,'physical':m.PhysicalInterventionRecord}


def case_content(db,case):
    result=view(case)
    result['record']=view(db.scalar(select(TYPED[case.kind]).where(TYPED[case.kind].case_id==case.id,TYPED[case.kind].school_id==case.school_id)))
    for key,model in COLLECTIONS.items(): result[key]=[view(r) for r in all_children(db,model,case)]
    result['classification']='protected_safeguarding'
    missing=[]
    if case.kind in ('environment','physical') and (not result['pupil_views'] or result['pupil_views'][-1]['statement'] is None):missing.append('pupil_perspective_pending')
    if case.kind=='environment' and not any(a['kind']=='investigation' for a in result['accounts']):missing.append('investigation_not_recorded')
    if case.kind=='environment' and not result['plans']:missing.append('action_plan_not_recorded')
    if case.kind=='concern' and not result['accounts']:missing.append('fact_basis_not_recorded')
    if case.kind=='physical' and result['record']['duration_seconds'] is None:missing.append('duration_unknown')
    result['workflow_checks']={'missing_documentation':missing,'notification_execution':'recorded' if result['actual_contacts'] else 'not_recorded','legal_completeness':'requires_reviewed_rule_context'}
    return result


def current_snapshot(db,case):
    row=db.scalar(select(m.CaseSnapshot).where(m.CaseSnapshot.school_id==case.school_id,m.CaseSnapshot.case_id==case.id,m.CaseSnapshot.revision==case.version))
    if row is None: raise DomainError('snapshot_unavailable','The current protected revision is unavailable.',503)
    return row


def detail(db,actor,school_id,case_id,export=False):
    case=case_access(db,actor,school_id,case_id,'export' if export else 'read')
    row=current_snapshot(db,case)
    result={**row.content,'evidence_reference':{'reference_id':row.id,'revision':row.revision,'digest':row.digest}}
    result['rule_context']=rule_context(db,actor,case)
    return result


def rule_context(db,actor,case):
    resolver=db.info.get('safeguarding_rule_context')
    if resolver is None:
        return {'state':'unavailable','reason':'No reviewed school rule adapter is configured. Use established manual contact procedures; no duty or notification is marked fulfilled.'}
    context=resolver(db,actor,case.school_id,case.learner_id,case.id)
    if not isinstance(context,ReviewedRuleContext) or not context.profile_id or context.profile_revision<1:
        raise DomainError('rule_context_unavailable','The reviewed rule context could not be validated.',503)
    return {'state':'reviewed','profile_id':context.profile_id,'profile_revision':context.profile_revision,
        'obligation_ids':list(context.obligation_ids),'documentation_requirements':list(context.documentation_requirements),
        'notification_requirements':list(context.notification_requirements)}


def list_cases(db,actor,school_id,offset=0,limit=50,learner_id=None,kind=None):
    require_school_access(db,actor,school_id)
    query=select(m.CaseRecord).where(m.CaseRecord.school_id==school_id)
    if learner_id: query=query.where(m.CaseRecord.learner_id==str(learner_id))
    if kind: query=query.where(m.CaseRecord.kind==kind)
    visible=[]
    for case in db.scalars(query.order_by(m.CaseRecord.recorded_at,m.CaseRecord.id)):
        try: case_access(db,actor,school_id,case.id)
        except DomainError: continue
        visible.append(view(case))
    return {'items':visible[offset:offset+limit],'total':len(visible)}


def personal_projection(db,actor,school_id,case_id):
    case=personal_access(db,actor,school_id,case_id)
    # Only the initial, author's own submitted facts and their own subsequent
    # contacts/actions; no state/owner/review/other contributor metadata leaks.
    initial=db.scalar(select(m.CaseSnapshot).where(m.CaseSnapshot.case_id==case.id,m.CaseSnapshot.school_id==school_id,m.CaseSnapshot.revision==1))
    result={'id':case.id,'kind':case.kind,'version':case.version,'submitted_at':str(case.recorded_at),'original_submission':initial.content['record']}
    for key in ('accounts','pupil_views'):
        result['original_'+key]=initial.content[key]
    result['own_pupil_views']=[view(r) for r in all_children(db,m.PupilPerspective,case) if r.author_id==actor.user_id]
    result['own_contacts']=[view(r) for r in all_children(db,m.ActualContact,case) if r.author_id==actor.user_id]
    result['own_actions']=[view(r) for r in all_children(db,m.PerformedAction,case) if r.actor_id==actor.user_id]
    return result


def list_personal(db,actor,school_id,offset=0,limit=50):
    reporting_access(db,actor,school_id)
    rows=list(db.scalars(select(m.CaseRecord).where(m.CaseRecord.school_id==school_id,m.CaseRecord.author_id==actor.user_id).order_by(m.CaseRecord.recorded_at,m.CaseRecord.id)))
    rows=[r for r in rows if actor.user_id not in r.excluded_user_ids]
    return {'items':[{'id':r.id,'kind':r.kind,'submitted_at':str(r.recorded_at)} for r in rows[offset:offset+limit]],'total':len(rows)}


def repeated_events(db,actor,school_id,learner_id,offset=0,limit=50):
    # A repeated-event grant never expands per-case permissions. Only fully
    # authorized physical records participate, with no hidden-event count.
    staff_membership(db,actor,school_id)
    require_authority(db,actor,school_id,'safeguarding.repeated_events',learner_id=str(learner_id))
    result=list_cases(db,actor,school_id,0,100000,str(learner_id),'physical')
    visible=[]
    for row in result['items']:
        case=case_access(db,actor,school_id,row['id'])
        visible.append({'id':case.id,'occurred_at':str(case.occurred_at),'state':case.state,'version':case.version})
    return {'items':visible[offset:offset+limit],'total':len(visible)}


def resolve_case_learner(db,actor,school_id,case_id):
    return case_access(db,actor,school_id,case_id).learner_id


def validate_evidence_reference(db,actor,school_id,learner_id,case_id,reference_id):
    if case_id is None or learner_id is None: raise access_denied()
    case=case_access(db,actor,school_id,case_id)
    if case.learner_id!=str(learner_id): raise access_denied()
    row=current_snapshot(db,case)
    if row.id!=str(reference_id) or row.digest!=digest(row.content): raise access_denied()
    return ValidatedEvidenceReference(row.id,school_id,case.learner_id,case.id,row.revision,row.digest)


def check_time(at):
    if at>utcnow(): raise DomainError('future_actual_time','Actual events cannot be recorded in the future.')


def receipt(db,actor,school_id,command,operation,case_id=None):
    fingerprint=digest({'operation':operation,'case_id':case_id,'command':command.model_dump(mode='json')})
    row=db.scalar(select(m.CommandReceipt).where(m.CommandReceipt.school_id==school_id,m.CommandReceipt.actor_id==actor.user_id,m.CommandReceipt.request_key==command.request_key))
    if row and row.request_digest!=fingerprint:
        raise DomainError('idempotency_conflict','This request key was used for different content.',409)
    return row,fingerprint


def emit(db,actor,school_id,aggregate_id,version,operation,occurred_at,target_type='SafeguardingCase'):
    record_audit(db,actor,school_id,'safeguarding.'+operation,target_type,aggregate_id)
    db.add(m.SafeguardingEvent(school_id=school_id,aggregate_id=aggregate_id,aggregate_version=version,event_type='safeguarding.'+operation,actor_id=actor.user_id,occurred_at=occurred_at))


def finalize(db,actor,case,command,operation,fingerprint,personal=False,new=False,participant=False):
    if not new: case.version+=1
    if case.state=='closed' and operation!='review':case.review_required=True
    db.flush()
    content=case_content(db,case)
    row=m.CaseSnapshot(school_id=case.school_id,case_id=case.id,revision=case.version,content=content,digest=digest(content))
    db.add(row);db.flush()
    emit(db,actor,case.school_id,case.id,case.version,operation,getattr(command,'occurred_at',utcnow()))
    result=contribution_projection(db,actor,case.school_id,case.id) if participant else personal_projection(db,actor,case.school_id,case.id) if personal else {**content,'evidence_reference':{'reference_id':row.id,'revision':row.revision,'digest':row.digest}}
    db.add(m.CommandReceipt(school_id=case.school_id,actor_id=actor.user_id,request_key=command.request_key,request_digest=fingerprint,case_id=case.id,result=result))
    db.flush()
    return result


def create_case(db,actor,school_id,command,kind):
    reporting_access(db,actor,school_id)
    # Serialize school-level logical request identities on production PostgreSQL.
    db.scalar(select(School).where(School.id==school_id).with_for_update())
    old,fingerprint=receipt(db,actor,school_id,command,'create_'+kind)
    if old:
        personal_access(db,actor,school_id,old.case_id)
        return old.result
    learner=db.scalar(select(Learner).where(Learner.school_id==school_id,Learner.id==str(command.learner_id),Learner.state=='active'))
    if learner is None: raise access_denied()
    if actor.user_id in {str(v) for v in command.excluded_user_ids}: raise access_denied()
    for uid in command.excluded_user_ids: person_valid(db,school_id,uid)
    check_time(command.occurred_at)
    case=m.CaseRecord(school_id=school_id,learner_id=str(command.learner_id),kind=kind,author_id=actor.user_id,about=command.about,excluded_user_ids=[str(v) for v in command.excluded_user_ids],occurred_at=command.occurred_at,state='registered' if kind!='environment' else 'received')
    db.add(case);db.flush()
    values=command.model_dump(mode='json',exclude={'request_key','learner_id','about','excluded_user_ids','occurred_at','accounts','pupil_view'})
    db.add(TYPED[kind](school_id=school_id,case_id=case.id,**values))
    if kind=='concern':
        for account in command.accounts: add_account_row(db,actor,case,account)
    if kind=='physical': add_pupil_row(db,actor,case,command.pupil_view,personal=True)
    return finalize(db,actor,case,command,'create_'+kind,fingerprint,personal=True,new=True)


create_environment=transaction(lambda db,actor,school_id,command:create_case(db,actor,school_id,command,'environment'))
create_concern=transaction(lambda db,actor,school_id,command:create_case(db,actor,school_id,command,'concern'))
create_physical=transaction(lambda db,actor,school_id,command:create_case(db,actor,school_id,command,'physical'))


def prepare(db,actor,school_id,case_id,command,operation,personal=False,action='write',participant=False):
    case=participant_access(db,actor,school_id,case_id,True) if participant else personal_access(db,actor,school_id,case_id,True) if personal else case_access(db,actor,school_id,case_id,action,True)
    old,fingerprint=receipt(db,actor,school_id,command,operation,case.id)
    if old: return case,old,fingerprint
    if case.version!=command.expected_version: raise DomainError('version_conflict','This case changed. Reload before retrying.',409)
    closed_metadata=operation in {'review','assignment','protection'} or operation.startswith('followup_assignment:')
    if case.state=='closed' and not closed_metadata and not (personal or participant):raise DomainError('case_closed','Reopen this case before changing it.')
    return case,None,fingerprint


def add_account_row(db,actor,case,command):
    check_time(command.occurred_at)
    if command.corrects_id: scoped_child(db,m.AttributedAccount,case,command.corrects_id)
    values=command.model_dump(mode='python',exclude={'request_key','expected_version'})
    values['corrects_id']=str(command.corrects_id) if command.corrects_id else None
    db.add(m.AttributedAccount(school_id=case.school_id,case_id=case.id,author_id=actor.user_id,**values))


@transaction
def add_account(db,actor,school_id,case_id,command,participant=False):
    case,old,key=prepare(db,actor,school_id,case_id,command,'participant_account' if participant else 'account',participant=participant)
    if old:return old.result
    if participant and command.corrects_id and scoped_child(db,m.AttributedAccount,case,command.corrects_id).author_id!=actor.user_id:raise access_denied()
    add_account_row(db,actor,case,command)
    if not participant and command.kind=='investigation' and case.kind=='environment':case.state='investigating'
    return finalize(db,actor,case,command,'participant_account' if participant else 'account',key,participant=participant)


def add_pupil_row(db,actor,case,command,personal=False):
    check_time(command.occurred_at)
    if command.followup_owner_id:
        if personal:
            if str(command.followup_owner_id)!=actor.user_id:raise access_denied()
            person_valid(db,case.school_id,actor.user_id)
        else:owner_valid(db,case,command.followup_owner_id)
    values=command.model_dump(mode='python',exclude={'request_key','expected_version'})
    values['followup_owner_id']=str(command.followup_owner_id) if command.followup_owner_id else None
    db.add(m.PupilPerspective(school_id=case.school_id,case_id=case.id,author_id=actor.user_id,**values))


@transaction
def add_pupil_view(db,actor,school_id,case_id,command,participant=False,personal=False):
    operation='participant_pupil_view' if participant else 'personal_pupil_view' if personal else 'pupil_view'
    case,old,key=prepare(db,actor,school_id,case_id,command,operation,personal,participant=participant)
    if old:return old.result
    add_pupil_row(db,actor,case,command,personal=personal or participant)
    return finalize(db,actor,case,command,operation,key,personal=personal,participant=participant)


@transaction
def create_plan(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'plan')
    if old:return old.result
    if case.kind!='environment':raise DomainError('wrong_case_type','Action plans belong to school environment cases.')
    revision=1+int(db.scalar(select(func.count()).select_from(m.ActionPlan).where(m.ActionPlan.case_id==case.id)))
    row=m.ActionPlan(school_id=school_id,case_id=case.id,revision=revision,problem_assessment=command.problem_assessment,evaluation_date=command.evaluation_date,author_id=actor.user_id)
    db.add(row);db.flush()
    for measure in command.measures:
        owner_valid(db,case,measure.owner_id)
        db.add(m.PlanMeasure(school_id=school_id,case_id=case.id,plan_id=row.id,**{**measure.model_dump(),'owner_id':str(measure.owner_id)}))
    case.state='measures_active'
    return finalize(db,actor,case,command,'plan',key)


@transaction
def record_action(db,actor,school_id,case_id,command,personal=False,participant=False):
    operation='participant_action' if participant else 'personal_action' if personal else 'performed_action'
    case,old,key=prepare(db,actor,school_id,case_id,command,operation,personal,participant=participant)
    if old:return old.result
    check_time(command.occurred_at)
    if command.measure_id:
        if personal:raise DomainError('case_permission_required','Linking a plan measure needs current case permission.',403)
        measure=scoped_child(db,m.PlanMeasure,case,command.measure_id)
        if participant and measure.owner_id!=actor.user_id:raise access_denied()
    values=command.model_dump(exclude={'request_key','expected_version'})
    values['measure_id']=str(command.measure_id) if command.measure_id else None
    db.add(m.PerformedAction(school_id=school_id,case_id=case.id,actor_id=actor.user_id,**values))
    return finalize(db,actor,case,command,operation,key,personal,participant=participant)


@transaction
def create_draft(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'draft')
    if old:return old.result
    if case.kind!='concern':raise DomainError('wrong_case_type','Message drafts belong to concern reports.')
    # A responsible author prepares human text. There is no generated legal
    # determination and no recipient/guardian automatically copied.
    revision=1+int(db.scalar(select(func.count()).select_from(m.ConcernDraft).where(m.ConcernDraft.case_id==case.id)))
    fields=command.model_dump(exclude={'request_key','expected_version'})
    db.add(m.ConcernDraft(school_id=school_id,case_id=case.id,revision=revision,author_id=actor.user_id,digest=digest(fields),**fields))
    case.state='message_prepared'
    return finalize(db,actor,case,command,'draft',key)


@transaction
def review_draft(db,actor,school_id,case_id,draft_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'draft_review:'+str(draft_id))
    if old:return old.result
    row=scoped_child(db,m.ConcernDraft,case,draft_id)
    latest=db.scalar(select(func.max(m.ConcernDraft.revision)).where(m.ConcernDraft.case_id==case.id))
    if row.revision!=latest or row.digest!=command.draft_digest:raise DomainError('draft_changed','Review the exact current draft.',409)
    if actor.user_id!=row.author_id:raise access_denied()
    if row.reviewed_at:raise DomainError('already_reviewed','This exact draft already has the responsible author review.',409)
    row.reviewed_by=actor.user_id;row.reviewed_at=utcnow();row.review_rationale=command.rationale
    return finalize(db,actor,case,command,'draft_review:'+str(draft_id),key)


def route_available(db,row,case=None):
    today=school_today(db.get(School,row.school_id))
    if row.state!='approved' or not row.reviewed_by or not row.reviewed_at or not row.valid_from<=today<=row.valid_until:return False
    if case and (row.about!=case.about or row.purpose!=case.kind or row.recipient_user_id in case.excluded_user_ids):return False
    # Revoked route owners cannot leave apparently supported contact paths.
    try:person_valid(db,row.school_id,row.owner_id)
    except DomainError:return False
    return True


def contact_routes(db,actor,school_id,purpose,about,case_id=None):
    case=case_access(db,actor,school_id,case_id) if case_id else None
    if case:purpose=case.kind;about=case.about
    else:reporting_access(db,actor,school_id)
    rows=list(db.scalars(select(m.ContactRoute).where(m.ContactRoute.school_id==school_id,m.ContactRoute.purpose==purpose,m.ContactRoute.about==about)))
    valid=[r for r in rows if route_available(db,r,case)]
    return {'items':[view(r) for r in valid],'total':len(valid),'state':'available' if valid else 'unavailable',
        'manual_guidance':'Use established manual contact procedures when urgent or a route is unavailable. Necessary personal action does not require a draft or headteacher approval.'}


@transaction
def record_contact(db,actor,school_id,case_id,command,personal=False,participant=False):
    operation='participant_contact' if participant else 'personal_contact' if personal else 'contact'
    case,old,key=prepare(db,actor,school_id,case_id,command,operation,personal,participant=participant)
    if old:return old.result
    check_time(command.occurred_at)
    if command.draft_id:
        if personal or participant:raise DomainError('case_permission_required','A protected draft reference needs case permission; personal action can be recorded without a draft.',403)
        draft=scoped_child(db,m.ConcernDraft,case,command.draft_id)
        latest=db.scalar(select(func.max(m.ConcernDraft.revision)).where(m.ConcernDraft.case_id==case.id))
        if draft.digest!=command.draft_digest or not draft.reviewed_at or draft.reviewed_by!=draft.author_id or draft.revision!=latest:
            raise DomainError('unreviewed_draft','The exact current draft needs responsible author review.',409)
        if draft.recipient!=command.recipient:raise DomainError('recipient_mismatch','The recorded recipient differs from the reviewed draft.',409)
        if draft.body!=command.information_shared:raise DomainError('draft_content_mismatch','The actual content differs from the reviewed draft. Record the actual contact without this draft reference, or review the corrected draft.',409)
    route=db.get(m.ContactRoute,str(command.route_id)) if command.route_id else None
    valid=route is not None and route.school_id==school_id and route_available(db,route,case)
    if not valid and not command.route_deviation_reason:raise DomainError('manual_route_reason_required','Record the actual contact route and why an approved route was unavailable or unsuitable. Personal action needs no prior approval.')
    if route and route.school_id!=school_id:raise access_denied()
    if valid and (command.recipient!=route.recipient or command.channel!=route.channel) and not command.route_deviation_reason:
        raise DomainError('route_mismatch','Record why the actual recipient/channel differed from the reviewed route.')
    values=command.model_dump(exclude={'request_key','expected_version'})
    for name in ('draft_id','route_id'):values[name]=str(values[name]) if values[name] else None
    db.add(m.ActualContact(school_id=school_id,case_id=case.id,author_id=actor.user_id,**values))
    # A notification requirement, prepared text, failed attempt or unknown
    # outcome never becomes an actual performed notification.
    if command.outcome=='performed' and case.state!='closed':
        if case.kind=='environment' and case.state=='received' and command.contact_kind=='notification':case.state='notified'
        elif case.kind=='concern':case.state='actual_contact'
    return finalize(db,actor,case,command,operation,key,personal,participant=participant)


@transaction
def reconcile_contact(db,actor,school_id,case_id,contact_id,command):
    operation='contact_reconciliation:'+str(contact_id)
    case,old,key=prepare(db,actor,school_id,case_id,command,operation)
    if old:return old.result
    contact=scoped_child(db,m.ActualContact,case,contact_id)
    check_time(command.occurred_at)
    if command.occurred_at<contact.occurred_at:raise DomainError('invalid_chronology','Reconciliation cannot precede the contact.')
    db.add(m.ContactReconciliation(school_id=school_id,case_id=case.id,contact_id=contact.id,author_id=actor.user_id,**command.model_dump(exclude={'request_key','expected_version'})))
    if command.outcome=='performed':
        if case.kind=='environment' and case.state=='received' and contact.contact_kind=='notification':case.state='notified'
        elif case.kind=='concern':case.state='actual_contact'
    return finalize(db,actor,case,command,operation,key)


@transaction
def create_followup(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'followup')
    if old:return old.result
    owner_valid(db,case,command.owner_id)
    fields=command.model_dump(exclude={'request_key','expected_version'});fields['owner_id']=str(command.owner_id)
    db.add(m.Followup(school_id=school_id,case_id=case.id,**fields))
    if case.kind=='concern':case.state='followup'
    return finalize(db,actor,case,command,'followup',key)


@transaction
def complete_followup(db,actor,school_id,case_id,followup_id,command,participant=False):
    operation=('participant_' if participant else '')+'followup_completion:'+str(followup_id)
    case,old,key=prepare(db,actor,school_id,case_id,command,operation,participant=participant)
    if old:return old.result
    row=scoped_child(db,m.Followup,case,followup_id)
    owner_valid(db,case,row.owner_id)
    if row.owner_id!=actor.user_id:raise access_denied()
    check_time(command.occurred_at)
    row.state=command.state;row.outcome=command.outcome;row.completed_at=command.occurred_at
    return finalize(db,actor,case,command,operation,key,participant=participant)


@transaction
def assign_owner(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'assignment',action='review')
    if old:return old.result
    owner_valid(db,case,command.owner_id,full=True)
    case.owner_id=str(command.owner_id)
    db.add(m.CaseReview(school_id=school_id,case_id=case.id,decision='assignment',assessment=command.reason,pupil_situation='Assignment only; no pupil situation assessment.',reviewer_id=actor.user_id,occurred_at=utcnow()))
    return finalize(db,actor,case,command,'assignment',key)


@transaction
def review_case(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'review',action='review')
    if old:return old.result
    check_time(command.occurred_at)
    if case.owner_id is None:raise DomainError('owner_required','Assign a currently authorized responsible owner before reviewing.')
    owner_valid(db,case,case.owner_id,full=True)
    if command.decision=='reopen':
        if case.state!='closed':raise DomainError('not_closed','Only a closed case can be reopened.')
        case.state='investigating' if case.kind=='environment' else 'under_review'
    elif case.state=='closed':raise DomainError('case_closed','An explicit reopening assessment is required.')
    elif command.decision=='close':
        if actor.user_id!=case.owner_id:raise access_denied()
        if case.kind=='environment':
            if not all_children(db,m.ActionPlan,case) or not any(a.kind=='investigation' for a in all_children(db,m.AttributedAccount,case)) or not all_children(db,m.PupilPerspective,case):
                raise DomainError('incomplete_case','Record investigation, pupil perspective or owned reason, and action plan before reviewed closure.')
        case.state='closed'
    elif command.decision=='investigating':case.state='investigating'
    elif command.decision=='evaluating':case.state='evaluating'
    elif command.decision=='checked':case.state='under_review'
    elif command.decision=='corrected':case.state='corrected'
    elif command.decision=='continue':case.state='measures_active' if case.kind=='environment' else 'followup'
    case.review_required=False
    db.add(m.CaseReview(school_id=school_id,case_id=case.id,reviewer_id=actor.user_id,**command.model_dump(exclude={'request_key','expected_version'})))
    return finalize(db,actor,case,command,'review',key)


@transaction
def correct_record(db,actor,school_id,case_id,command,kind):
    operation='correct_'+kind
    case,old,key=prepare(db,actor,school_id,case_id,command,operation)
    if old:return old.result
    if case.kind!=kind:raise DomainError('wrong_case_type','Use the correction command for this case type.')
    if kind=='concern' and actor.user_id!=case.author_id:raise DomainError('responsible_author_required','Only the responsible report author can correct their assessment. Other contributors record their own attributed assessment.',403)
    row=db.scalar(select(TYPED[kind]).where(TYPED[kind].case_id==case.id,TYPED[kind].school_id==school_id))
    for field,value in command.model_dump(mode='json',exclude={'request_key','expected_version','correction_reason'}).items():setattr(row,field,value)
    db.add(m.RecordCorrection(school_id=school_id,case_id=case.id,prior_revision=case.version,correction_reason=command.correction_reason,author_id=actor.user_id))
    case.state='corrected'
    return finalize(db,actor,case,command,operation,key)


@transaction
def create_route(db,actor,school_id,command):
    authority(db,actor,school_id,'routes.manage')
    db.scalar(select(School).where(School.id==school_id).with_for_update())
    old,key=receipt(db,actor,school_id,command,'route_create')
    if old:return old.result
    person_valid(db,school_id,command.owner_id)
    if command.recipient_user_id:person_valid(db,school_id,command.recipient_user_id)
    if command.supersedes_id:
        previous=db.get(m.ContactRoute,str(command.supersedes_id))
        if previous is None or previous.school_id!=school_id or previous.purpose!=command.purpose or previous.about!=command.about:raise access_denied()
    fields=command.model_dump(exclude={'request_key'})
    for name in ('owner_id','recipient_user_id','supersedes_id'):fields[name]=str(fields[name]) if fields[name] else None
    row=m.ContactRoute(school_id=school_id,digest=digest(fields),**fields)
    db.add(row);db.flush()
    emit(db,actor,school_id,row.id,row.version,'route_create',utcnow(),'SafeguardingContactRoute')
    result=view(row)
    db.add(m.CommandReceipt(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,request_digest=key,result=result))
    return result


@transaction
def review_route(db,actor,school_id,route_id,command):
    authority(db,actor,school_id,'routes.review')
    row=db.scalar(select(m.ContactRoute).where(m.ContactRoute.school_id==school_id,m.ContactRoute.id==str(route_id)).with_for_update().execution_options(populate_existing=True))
    if row is None:raise access_denied()
    old,key=receipt(db,actor,school_id,command,'route_review:'+str(route_id))
    if old:return old.result
    if row.version!=command.expected_version or row.digest!=command.digest:raise DomainError('version_conflict','Review the exact current route.',409)
    if command.decision=='approve':
        if row.state!='unreviewed':raise DomainError('route_not_unreviewed','A reviewed/revoked route requires a new configuration revision.')
        person_valid(db,school_id,row.owner_id)
        if row.recipient_user_id:person_valid(db,school_id,row.recipient_user_id)
        if row.supersedes_id:
            previous=db.scalar(select(m.ContactRoute).where(m.ContactRoute.id==row.supersedes_id).with_for_update())
            previous.state='superseded'
        row.state='approved';row.reviewed_by=actor.user_id;row.reviewed_at=utcnow();row.review_rationale=command.rationale
    else:row.state='revoked';row.review_rationale=command.rationale
    row.version+=1;db.flush()
    emit(db,actor,school_id,row.id,row.version,'route_review',utcnow(),'SafeguardingContactRoute')
    result=view(row)
    db.add(m.CommandReceipt(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,request_digest=key,result=result))
    return result


def route_configurations(db,actor,school_id,offset=0,limit=50):
    authority(db,actor,school_id,'routes.manage')
    rows=list(db.scalars(select(m.ContactRoute).where(m.ContactRoute.school_id==school_id).order_by(m.ContactRoute.recorded_at,m.ContactRoute.id)))
    return {'items':[view(r) for r in rows[offset:offset+limit]],'total':len(rows)}


def revision_history(db,actor,school_id,case_id,offset=0,limit=50):
    case=case_access(db,actor,school_id,case_id)
    rows=list(db.scalars(select(m.CaseSnapshot).where(m.CaseSnapshot.school_id==school_id,m.CaseSnapshot.case_id==case.id).order_by(m.CaseSnapshot.revision)))
    return {'items':[{'id':r.id,'revision':r.revision,'digest':r.digest,'recorded_at':str(r.recorded_at),'content':r.content} for r in rows[offset:offset+limit]],'total':len(rows)}


def contribution_projection(db,actor,school_id,case_id):
    case=participant_access(db,actor,school_id,case_id)
    result={'id':case.id,'kind':case.kind,'version':case.version}
    for key,model,field in [('own_accounts',m.AttributedAccount,'author_id'),('own_pupil_views',m.PupilPerspective,'author_id'),('own_actions',m.PerformedAction,'actor_id'),('own_contacts',m.ActualContact,'author_id'),('assigned_followups',m.Followup,'owner_id'),('assigned_measures',m.PlanMeasure,'owner_id')]:
        result[key]=[view(r) for r in all_children(db,model,case) if getattr(r,field)==actor.user_id]
    return result


def list_contributions(db,actor,school_id,offset=0,limit=50):
    require_school_access(db,actor,school_id)
    visible=[]
    for case in db.scalars(select(m.CaseRecord).where(m.CaseRecord.school_id==school_id).order_by(m.CaseRecord.recorded_at,m.CaseRecord.id)):
        try:participant_access(db,actor,school_id,case.id)
        except DomainError:continue
        visible.append({'id':case.id,'kind':case.kind})
    return {'items':visible[offset:offset+limit],'total':len(visible)}


@transaction
def update_protection(db,actor,school_id,case_id,command):
    case,old,key=prepare(db,actor,school_id,case_id,command,'protection',action='review')
    if old:return old.result
    additions={str(uid) for uid in command.excluded_user_ids}
    if actor.user_id in additions:raise DomainError('independent_case_reviewer_required','Another currently authorized case reviewer must record your exclusion.',403)
    for uid in additions:person_valid(db,school_id,uid)
    case.excluded_user_ids=sorted(set(case.excluded_user_ids)|additions)
    case.about=command.about
    if case.owner_id in case.excluded_user_ids:case.owner_id=None
    db.add(m.CaseReview(school_id=school_id,case_id=case.id,decision='protection',assessment=command.reason,pupil_situation='Protection change only; no pupil situation assessment.',reviewer_id=actor.user_id,occurred_at=utcnow()))
    return finalize(db,actor,case,command,'protection',key)


@transaction
def reassign_followup(db,actor,school_id,case_id,followup_id,command):
    operation='followup_assignment:'+str(followup_id)
    case,old,key=prepare(db,actor,school_id,case_id,command,operation,action='review')
    if old:return old.result
    row=scoped_child(db,m.Followup,case,followup_id)
    owner_valid(db,case,command.owner_id)
    row.owner_id=str(command.owner_id)
    db.add(m.CaseReview(school_id=school_id,case_id=case.id,decision='followup_assignment',assessment=command.reason,pupil_situation='Followup assignment only; no pupil situation assessment.',reviewer_id=actor.user_id,occurred_at=utcnow()))
    return finalize(db,actor,case,command,operation,key)
