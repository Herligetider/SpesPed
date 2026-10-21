"""Transactional native assessment workflows and currently authorized projections."""
from datetime import datetime,timedelta,time,timezone,date
from decimal import Decimal,InvalidOperation
from functools import wraps
from uuid import UUID
import json
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError
from spesped.auth import require_school_access,require_learner_access,require_authority,school_today
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError,access_denied
from spesped.contexts.identity.models import School,UserAccount
from . import models as m,schemas as s,adapters as a
from .ports import AuthorityRequest,authority_basis

def local_day(db,school_id,instant):
    from zoneinfo import ZoneInfo
    return instant.astimezone(ZoneInfo(db.get(School,school_id).timezone)).date()

def encode(value):return json.loads(a.canonical(value))
def row_json(row):return encode({c.name:getattr(row,c.name) for c in row.__table__.columns})
def conflict(message='Reload the current exact assessment revision before retrying.'):
    return DomainError('assessment_conflict',message,409)
def school_access(db,actor,school_id,action):
    member=require_school_access(db,actor,school_id)
    if member.role in {'guardian','technical_administrator'}:raise access_denied()
    require_authority(db,actor,school_id,action)
def pupil_access(db,actor,school_id,learner_id,action='assessment.read'):
    require_learner_access(db,actor,school_id,learner_id,action)
def get(db,model,school_id,identifier,expected=None):
    with db.no_autoflush:row=db.scalar(select(model).where(model.school_id==school_id,model.id==str(identifier)).execution_options(populate_existing=True))
    if row is None:raise access_denied()
    if expected is not None and row.version!=expected:raise conflict()
    return row

def event(db,actor,row,action,**payload):
    db.flush();record_audit(db,actor,row.school_id,action,row.__tablename__,row.id)
    db.add(m.AssessmentEvent(school_id=row.school_id,aggregate_id=row.id,aggregate_version=getattr(row,'version',1),actor_id=actor.user_id,event_type=action,payload=encode(payload),causation_id=db.info['assessment_request_key']))
    db.flush()

def mutation(action,kind):
    def decorate(fn):
        @wraps(fn)
        def wrapped(db,actor,school_id,*args):
            previous=db.info.get('assessment_request_key')
            try:
                # All BC09 writers lock the same tenant before reading revisions
                # or request keys. PostgreSQL serializes competing commands.
                require_school_access(db,actor,school_id)
                db.scalar(select(School.id).where(School.id==school_id).with_for_update())
                command=args[-1];db.info['assessment_request_key']=command.request_key
                fingerprint=a.digest({'operation':fn.__name__,'target':[str(v) for v in args[:-1]],'command':command.model_dump(mode='json')})
                receipt=db.scalar(select(m.AssessmentCommand).where(m.AssessmentCommand.school_id==school_id,m.AssessmentCommand.actor_id==actor.user_id,m.AssessmentCommand.request_key==command.request_key))
                # Reauthorize the exact command scope even when replaying.
                if kind=='instrument':school_access(db,actor,school_id,action)
                else:
                    model={'administration':m.Administration,'progress':m.ProgressReview,'statement':m.Statement,'follow_up':m.FollowUp}[kind]
                    if hasattr(command,'learner_id'):learner_id=str(command.learner_id)
                    elif args[:-1]:
                        target=get(db,model,school_id,args[0])
                        if kind=='follow_up':target=get(db,m.Administration,school_id,target.administration_id)
                        learner_id=target.learner_id
                    else:raise access_denied()
                    pupil_access(db,actor,school_id,learner_id,action)
                    if action=='assessment.finalize':
                        require_authority(db,actor,school_id,'assessment.finalize',learner_id=learner_id)
                        if command.grade is not None:require_authority(db,actor,school_id,'assessment.grade',learner_id=learner_id)
                if receipt:
                    if receipt.digest!=fingerprint:raise DomainError('idempotency_conflict','This request key identifies different assessment content or scope.',409)
                    result=view(db,actor,school_id,receipt.target_kind,receipt.target_id)
                    db.commit();return result
                result=fn(db,actor,school_id,*args)
                db.add(m.AssessmentCommand(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,operation=fn.__name__,digest=fingerprint,target_kind=kind,target_id=result.id))
                db.flush();value=view(db,actor,school_id,kind,result.id)
                db.commit();return value
            except (StaleDataError,DBAPIError) as exc:
                db.rollback()
                if isinstance(exc,StaleDataError) or getattr(getattr(exc,'orig',None),'sqlstate',None) in {'40001','40P01','55P03','23505'} or 'UNIQUE constraint failed' in str(getattr(exc,'orig','')):raise conflict('A concurrent command changed this assessment. Retry the same request key.') from None
                raise
            except Exception:db.rollback();raise
            finally:
                if previous is None:db.info.pop('assessment_request_key',None)
                else:db.info['assessment_request_key']=previous
        return wrapped
    return decorate

def current_instrument(db,actor,school_id,revision_id,on_date=None,use=False):
    school_access(db,actor,school_id,'assessment.instrument.read')
    revision=get(db,m.InstrumentRevision,school_id,revision_id);root=get(db,m.Instrument,school_id,revision.instrument_id)
    if a.digest(revision.content)!=revision.digest:raise conflict('The instrument content differs from its immutable digest.')
    a.school_sources(db,actor,school_id,revision.content['sources'])
    reviewed=db.scalar(select(m.InstrumentReview).where(m.InstrumentReview.school_id==school_id,m.InstrumentReview.revision_id==revision.id))
    if use:
        if root.state!='active' or root.current_revision!=revision.number or reviewed is None or reviewed.digest!=revision.digest:raise DomainError('instrument_unreviewed','Use the current exact reviewed instrument version.',409)
        day=on_date or school_today(db.get(School,school_id));content=s.InstrumentContent.model_validate(revision.content)
        if not content.permitted_use or not content.license_from<=day<=content.license_until:raise DomainError('instrument_license','Reviewed instrument use is unavailable for this date.',409)
    return root,revision,reviewed

def instrument_view(db,actor,school_id,identifier):
    school_access(db,actor,school_id,'assessment.instrument.read')
    root=get(db,m.Instrument,school_id,identifier)
    revision=db.scalar(select(m.InstrumentRevision).where(m.InstrumentRevision.school_id==school_id,m.InstrumentRevision.instrument_id==root.id,m.InstrumentRevision.number==root.current_revision))
    _,revision,review=current_instrument(db,actor,school_id,revision.id)
    return {'kind':'instrument',**row_json(root),'revision_id':revision.id,'content_digest':revision.digest,'content':revision.content,'review':row_json(review) if review else None}

@mutation('assessment.instrument.manage','instrument')
def create_instrument(db,actor,school_id,command):
    a.school_sources(db,actor,school_id,command.content.sources)
    root=m.Instrument(school_id=school_id,owner_id=actor.user_id,state='active');db.add(root);db.flush()
    data=command.content.model_dump(mode='json')
    db.add(m.InstrumentRevision(school_id=school_id,instrument_id=root.id,number=1,content=data,digest=a.digest(data),authored_by=actor.user_id));event(db,actor,root,'assessment.instrument.created');return root

@mutation('assessment.instrument.manage','instrument')
def revise_instrument(db,actor,school_id,identifier,command):
    root=get(db,m.Instrument,school_id,identifier,command.expected_version)
    a.school_sources(db,actor,school_id,command.content.sources)
    root.current_revision+=1;root.version+=1;data=command.content.model_dump(mode='json')
    db.add(m.InstrumentRevision(school_id=school_id,instrument_id=root.id,number=root.current_revision,content=data,digest=a.digest(data),authored_by=actor.user_id));event(db,actor,root,'assessment.instrument.revised');return root

@mutation('assessment.instrument.review','instrument')
def review_instrument(db,actor,school_id,identifier,command):
    root=get(db,m.Instrument,school_id,identifier,command.expected_version)
    _,revision,prior=current_instrument(db,actor,school_id,command.revision_id)
    if revision.instrument_id!=root.id or revision.number!=root.current_revision or revision.digest!=command.content_digest or prior:raise conflict()
    db.add(m.InstrumentReview(school_id=school_id,revision_id=revision.id,digest=revision.digest,reviewer_id=actor.user_id,reason=command.reason));root.version+=1
    event(db,actor,root,'assessment.instrument.reviewed',revision_id=revision.id);return root

def authority_request(actor,row,revision,purpose,starts_on,ends_on,**kwargs):
    return AuthorityRequest(school_id=row.school_id,learner_id=row.learner_id,person_id=actor.user_id,purpose=purpose,exact_revision_id=revision.id,exact_digest=revision.digest,starts_on=starts_on,ends_on=ends_on,**kwargs)
def conditions_check(instrument,conditions):
    if set(conditions.condition_codes)!=set(instrument.content['eligible_conditions']):raise DomainError('instrument_conditions','Every reviewed eligible condition must be explicitly recorded; unknown conditions require clarification.',409)

def administration_sources(db,actor,row,use=False,on_date=None):
    pupil_access(db,actor,row.school_id,row.learner_id)
    return current_instrument(db,actor,row.school_id,row.instrument_revision_id,on_date=on_date or row.planned_on,use=use)

def current_result(db,row):
    return db.scalar(select(m.ResultRevision).where(m.ResultRevision.school_id==row.school_id,m.ResultRevision.administration_id==row.id,m.ResultRevision.number==row.current_result)) if row.current_result else None

def authority_current(db,actor,binding):
    if not binding:return False
    try:
        request=AuthorityRequest.model_validate(binding['request'])
        with a.owner_reader(db) as reader:current=authority_basis(reader,actor,request)
        return current['state']=='reviewed_current' and a.digest(current)==a.digest(binding)
    except DomainError:
        return False

def administration_view(db,actor,school_id,identifier):
    row=get(db,m.Administration,school_id,identifier);pupil_access(db,actor,school_id,row.learner_id)
    try:
        root,instrument,review=administration_sources(db,actor,row)
        stale=root.current_revision!=instrument.number or root.state!='active' or review is None
        today=school_today(db.get(School,school_id));license_current=instrument.content['permitted_use'] and date.fromisoformat(instrument.content['license_from'])<=today<=date.fromisoformat(instrument.content['license_until'])
    except DomainError as exc:
        if exc.status_code not in {403,409}:raise
        return {'kind':'administration','id':row.id,'version':row.version,'state':row.state,'learner_id':row.learner_id,'source_status':'unavailable','result':None,'interpretation':None}
    result=current_result(db,row)
    review=db.scalar(select(m.ResultReview).where(m.ResultReview.school_id==school_id,m.ResultReview.result_revision_id==result.id)) if result else None
    qualification_status='reviewed_current' if authority_current(db,actor,row.eligibility) else 'unassessed'
    if row.state not in {'planned','aborted'} and qualification_status!='reviewed_current':stale=True
    authority_status='reviewed_current' if review and authority_current(db,actor,review.competence) else 'unassessed'
    if review and authority_status!='reviewed_current':stale=True
    return {'kind':'administration',**row_json(row),'source_status':'review_required' if stale or not license_current else 'current','instrument':instrument.content,'result':row_json(result) if result else None,'interpretation':row_json(review) if review else None,'comparison_key':a.digest({'instrument_revision_id':instrument.id,'conditions':result.conditions if result else row.conditions}),'universal_score':None,'qualification_status':qualification_status if row.eligibility['state']=='reviewed_current' else row.eligibility['state'],'review_authority_status':authority_status}

@mutation('assessment.write','administration')
def plan_administration(db,actor,school_id,command):
    _,instrument,_=current_instrument(db,actor,school_id,command.instrument_revision_id,on_date=command.planned_on,use=True)
    conditions_check(instrument,command.conditions)
    row=m.Administration(school_id=school_id,learner_id=str(command.learner_id),instrument_revision_id=instrument.id,planned_on=command.planned_on,purpose=command.purpose,conditions=command.conditions.model_dump(mode='json'),state='planned')
    row.eligibility=authority_basis(db,actor,authority_request(actor,row,instrument,'instrument_administration',command.planned_on,command.planned_on))
    db.add(row);event(db,actor,row,'assessment.administration.planned');return row

@mutation('assessment.write','administration')
def start_administration(db,actor,school_id,identifier,command):
    row=get(db,m.Administration,school_id,identifier,command.expected_version)
    _,instrument,_=administration_sources(db,actor,row,use=True,on_date=local_day(db,school_id,command.occurred_at))
    if row.state!='planned' or command.occurred_at>utcnow():raise conflict('Only a planned administration can start at an actual recorded instant.')
    row.eligibility=authority_basis(db,actor,authority_request(actor,row,instrument,'instrument_administration',local_day(db,school_id,command.occurred_at),local_day(db,school_id,command.occurred_at)),required=True)
    row.started_at=command.occurred_at;row.state='started';row.version+=1;event(db,actor,row,'assessment.administration.started');return row

@mutation('assessment.write','administration')
def abort_administration(db,actor,school_id,identifier,command):
    row=get(db,m.Administration,school_id,identifier,command.expected_version)
    if row.state not in {'planned','started'}:raise conflict('An aborted attempt must be separate from a recorded result.')
    row.state='aborted';row.abort_reason=command.reason;row.version+=1;event(db,actor,row,'assessment.administration.aborted');return row

def validate_raw(instrument,raw):
    scales={v['code']:s.Scale.model_validate(v) for v in instrument.content['scales']}
    if set(raw)!=set(scales):raise DomainError('assessment_scale','Supply precisely the instrument version’s explicit scales.',422)
    for code,value in raw.items():
        scale=scales[code]
        if scale.kind=='numeric':
            try:number=Decimal(value)
            except (InvalidOperation,ValueError):raise DomainError('assessment_scale','The raw result must use the recorded numeric scale.',422) from None
            if not number.is_finite() or not scale.minimum<=number<=scale.maximum:raise DomainError('assessment_scale','The raw result lies outside the instrument scale.',422)
        elif value not in scale.categories:raise DomainError('assessment_scale','The raw result must use a recorded categorical value.',422)

@mutation('assessment.write','administration')
def record_result(db,actor,school_id,identifier,command):
    row=get(db,m.Administration,school_id,identifier,command.expected_version)
    _,instrument,_=administration_sources(db,actor,row,use=True,on_date=local_day(db,school_id,command.occurred_at))
    if row.state not in {'started','recorded','professionally_reviewed'} or command.occurred_at>utcnow() or row.started_at is None or command.occurred_at<row.started_at:raise conflict('Record an actual result after the administration began.')
    if row.current_result and not command.correction_reason:raise DomainError('assessment_correction_reason','An append-only result correction requires its reason.',422)
    validate_raw(instrument,command.raw);conditions_check(instrument,command.conditions)
    authority_basis(db,actor,authority_request(actor,row,instrument,'instrument_administration',local_day(db,school_id,command.occurred_at),local_day(db,school_id,command.occurred_at)),required=True)
    row.current_result+=1;row.state='recorded';row.version+=1
    content=command.model_dump(mode='json',exclude={'request_key','expected_version'})
    result=m.ResultRevision(school_id=school_id,administration_id=row.id,number=row.current_result,occurred_at=command.occurred_at,raw=command.raw,conditions=command.conditions.model_dump(mode='json'),recorded_by=actor.user_id,correction_reason=command.correction_reason,digest=a.digest(content));db.add(result)
    db.flush();event(db,actor,row,'assessment.result.recorded',result_revision_id=result.id);return row

@mutation('assessment.review','administration')
def review_result(db,actor,school_id,identifier,command):
    row=get(db,m.Administration,school_id,identifier,command.expected_version)
    _,instrument,_=administration_sources(db,actor,row,use=True)
    result=current_result(db,row)
    if row.state!='recorded' or not result or result.id!=str(command.revision_id) or result.digest!=command.content_digest:raise conflict()
    competence=authority_basis(db,actor,authority_request(actor,row,result,'result_review',local_day(db,school_id,result.occurred_at),local_day(db,school_id,result.occurred_at)),required=True)
    db.add(m.ResultReview(school_id=school_id,result_revision_id=result.id,reviewer_id=actor.user_id,interpretation=command.interpretation,comparison=command.comparison,comparison_reason=command.comparison_reason,competence=competence))
    guidance=instrument.content.get('reassessment')
    day=local_day(db,school_id,result.occurred_at)+timedelta(days=guidance['minimum_days']) if guidance else None
    db.add(m.FollowUp(school_id=school_id,administration_id=row.id,result_revision_id=result.id,proposed_on=day,selected_on=None,guidance=guidance or {},state='proposed' if guidance else 'open_professional_question',reason=guidance['rationale'] if guidance else 'No reviewed source-backed reassessment interval is available.'))
    row.state='professionally_reviewed';row.version+=1;event(db,actor,row,'assessment.result.reviewed',result_revision_id=result.id);return row

@mutation('assessment.write','follow_up')
def decide_follow_up(db,actor,school_id,identifier,command):
    row=get(db,m.FollowUp,school_id,identifier,command.expected_version);administration=get(db,m.Administration,school_id,row.administration_id)
    administration_sources(db,actor,administration,use=command.decision!='rejected',on_date=command.selected_on or row.proposed_on)
    result=current_result(db,administration)
    if not result or result.id!=row.result_revision_id:raise conflict('The proposed follow-up belongs to a superseded result; review the correction first.')
    if command.decision!='rejected':
        if not row.guidance:raise DomainError('reassessment_unresolved','A date cannot be inferred without reviewed source-backed interval guidance.',409)
        chosen=command.selected_on or row.proposed_on
        if chosen is None or chosen<row.proposed_on:raise DomainError('reassessment_interval','The selected date must respect the reviewed minimum interval.',409)
        if command.decision=='accepted' and chosen!=row.proposed_on:raise conflict('Use moved when choosing a different eligible date.')
        row.selected_on=chosen
    elif command.selected_on:raise DomainError('reassessment_date','A rejected proposal has no chosen date.',422)
    row.state=command.decision;row.reason=command.reason;row.decided_by=actor.user_id;row.version+=1;event(db,actor,row,'assessment.follow_up.decided');return row

def follow_up_view(db,actor,school_id,identifier):
    row=get(db,m.FollowUp,school_id,identifier);admin=administration_view(db,actor,school_id,row.administration_id)
    if admin['source_status']=='unavailable':return {'kind':'follow_up','id':row.id,'version':row.version,'state':row.state,'source_status':'unavailable'}
    return {'kind':'follow_up',**row_json(row),'source_status':admin['source_status'],'result_current':bool(admin['result'] and admin['result']['id']==row.result_revision_id)}

def resolve_reference(db,actor,school_id,learner_id,ref,seen=None):
    ref=s.EvidenceRef.model_validate(ref)
    if ref.kind=='evidence':value=a.evidence(db,actor,school_id,learner_id,ref)
    elif ref.kind=='observation':
        value=a.observation(db,actor,school_id,learner_id,ref.id)
        if value['revision']!=ref.revision:raise conflict('The observation revision differs from the selected source.')
    elif ref.kind=='assessment_result':
        result=get(db,m.ResultRevision,school_id,ref.id);admin=get(db,m.Administration,school_id,result.administration_id)
        if admin.learner_id!=learner_id:raise access_denied()
        current=administration_view(db,actor,school_id,admin.id)
        if current['source_status']!='current' or current['state']!='professionally_reviewed' or current['result']['id']!=result.id or result.number!=ref.revision:raise conflict('The exact assessment result requires current professional review.')
        value={'result':current['result'],'interpretation':current['interpretation'],'instrument_revision_id':admin.instrument_revision_id,'comparison_key':current['comparison_key'],'learner_id':learner_id,'occurred_at':result.occurred_at,'recorded_at':result.created_at}
    else:
        row=get(db,m.ProgressReview,school_id,ref.id)
        if row.learner_id!=learner_id:raise access_denied()
        seen=set() if seen is None else set(seen)
        if row.id in seen:raise conflict('Cyclic progress evidence is unavailable.')
        current=progress_view(db,actor,school_id,row.id,seen=seen|{row.id})
        if current['source_status']!='current' or current['state']!='confirmed' or current['content']['number']!=ref.revision:raise conflict('The exact previous professional review is no longer a current source.')
        value={'review_id':row.id,'snapshot_digest':row.snapshot_digest,'content':current['content'],'occurred_at':current['content']['created_at'],'recorded_at':current['content']['created_at']}
    value=encode(value)
    if ref.digest and a.digest(value)!=ref.digest:raise conflict('The selected exact source digest changed.')
    return {'reference':ref.model_dump(mode='json'),'digest':a.digest(value),'value':value}

def validate_tasks(db,school_id,learner_id,finding):
    from spesped.auth import Actor
    for task in finding.tasks:
        # An owner choice cannot create access for another staff member.
        pupil_access(db,Actor(str(task.owner_id)),school_id,learner_id,'assessment.write')

def snapshot(db,actor,school_id,command):
    learner_id=str(command.learner_id)
    if command.ends_at>utcnow():raise DomainError('progress_period','A progress review period must already have elapsed.',422)
    g=a.goal(db,actor,school_id,learner_id,command.goal_revision_id,command.starts_at)
    a.goal(db,actor,school_id,learner_id,command.goal_revision_id,command.ends_at-timedelta(microseconds=1))
    refs=[resolve_reference(db,actor,school_id,learner_id,ref) for ref in command.references]
    for ref in refs:
        value=ref['value'];occurred=value.get('occurred_at')
        if occurred is None:raise DomainError('progress_source_period','Every selected source requires its actual occurrence.',409)
        instant=datetime.fromisoformat(occurred.replace('Z','+00:00'))
        if not command.starts_at<=instant<command.ends_at:raise DomainError('progress_source_period','Select sources that occurred within the chosen half-open review period.',409)
        if ref['reference']['kind']=='evidence' and value.get('goal_revision_id') not in {None,str(command.goal_revision_id)}:raise DomainError('progress_source_goal','Evidence refers to a different goal revision.',409)
        if ref['reference']['kind']=='observation' and value.get('goal_revision_id')!=str(command.goal_revision_id):raise DomainError('progress_source_goal','The observation must refer to the exact selected goal revision.',409)
    observed=a.observations(db,actor,school_id,learner_id,command.goal_revision_id,command.starts_at,command.ends_at)
    goal_evidence=a.goal_evidence(db,actor,school_id,learner_id,command.goal_revision_id,command.starts_at,command.ends_at)
    actuals=[]
    for identity in command.delivery_revision_ids:
        value=a.actual(db,actor,school_id,learner_id,identity)
        occurred=datetime.fromisoformat(value['occurred_at'].replace('Z','+00:00'))
        if not command.starts_at<=occurred<command.ends_at:raise DomainError('progress_delivery_period','The actual delivery occurred outside the review period.',409)
        if not any(str(command.goal_revision_id) in p['goal_revision_ids'] for p in value['participation']):raise DomainError('progress_delivery_goal','Actual participation must reference the exact goal revision.',409)
        actuals.append(value)
    methods={v['input_method'] for v in observed};supports={v['support'] for v in observed}
    assessments=[r['value'] for r in refs if r['reference']['kind']=='assessment_result']
    comparable={v['comparison_key'] for v in assessments}
    gaps=[]
    if not observed and not refs and not goal_evidence['items']:gaps.append('insufficient_documented_learning_evidence')
    if not actuals:gaps.append('actual_delivery_not_selected')
    limits=[]
    if len(methods)>1 or len(comparable)>1:limits.append('changed_method_or_instrument_conditions')
    if len(supports)>1:limits.append('varied_recorded_support')
    if any(v['interpretation']['comparison']=='incomparable' for v in assessments):limits.append('professionally_marked_incomparable_results')
    return encode({'goal':g,'references':refs,'goal_evidence':goal_evidence,'observations':observed,'actual_deliveries':actuals,'gaps':gaps,'comparison_limitations':limits,'planned_activity_is_evidence':False,'universal_pupil_score':None,'drafting':'manual_grounded_source_review','ai_generation':'not_integrated'})

def progress_revision(db,row):
    return db.scalar(select(m.ProgressRevision).where(m.ProgressRevision.school_id==row.school_id,m.ProgressRevision.review_id==row.id,m.ProgressRevision.number==row.current_revision))
def evidence_sufficient(snap,finding):
    if 'insufficient_documented_learning_evidence' in snap['gaps'] and finding.outcome!='more_information':raise DomainError('insufficient_progress_basis','Missing learning evidence requires an explicit need for more information.',409)
    if snap['comparison_limitations'] and not finding.comparison_limitations:raise DomainError('progress_comparison_limitations','Address the recorded method/support comparison limitations explicitly.',409)

def progress_dependencies(db,actor,row,seen):
    original=row.snapshot
    if a.digest(original)!=row.snapshot_digest:raise conflict('The historical evidence snapshot no longer matches its digest.')
    current_goal=a.goal(db,actor,row.school_id,row.learner_id,row.goal_revision_id,row.starts_at)
    stale=a.digest(current_goal)!=a.digest(original['goal']) or not a.current_goal_binding(db,row.school_id,row.learner_id,original['goal'],row.starts_at)
    for entry in original['references']+original.get('goal_evidence',{}).get('items',[]):
        current=resolve_reference(db,actor,row.school_id,row.learner_id,entry['reference'],seen=seen)
        if current['digest']!=entry['digest']:stale=True
    for value in original['observations']:
        current=a.observation(db,actor,row.school_id,row.learner_id,value['revision_id'])
        if a.digest(current)!=a.digest(value):stale=True
    for value in original['actual_deliveries']:
        current=a.actual(db,actor,row.school_id,row.learner_id,value['delivery_revision_id'])
        if a.digest(current)!=a.digest(value):stale=True
    observed=a.observations(db,actor,row.school_id,row.learner_id,row.goal_revision_id,row.starts_at,row.ends_at)
    late=sorted({v['revision_id'] for v in observed}-{v['revision_id'] for v in original['observations']})
    evidence=a.goal_evidence(db,actor,row.school_id,row.learner_id,row.goal_revision_id,row.starts_at,row.ends_at)
    prior={(r['reference']['id'],r['reference']['revision']) for r in original.get('goal_evidence',{}).get('items',[])}
    late.extend('evidence:'+r['reference']['id']+':'+str(r['reference']['revision']) for r in evidence['items'] if (r['reference']['id'],r['reference']['revision']) not in prior)
    return stale,late

def progress_view(db,actor,school_id,identifier,seen=None):
    row=get(db,m.ProgressReview,school_id,identifier);pupil_access(db,actor,school_id,row.learner_id)
    try:stale,late=progress_dependencies(db,actor,row,set() if seen is None else seen)
    except DomainError as exc:
        if exc.status_code not in {403,409}:raise
        return {'kind':'progress','id':row.id,'learner_id':row.learner_id,'version':row.version,'state':row.state,'source_status':'unavailable','review_required':True,'snapshot':None,'content':None,'reason':exc.code}
    return {'kind':'progress',**row_json(row),'source_status':'review_required' if stale else 'current','review_required':stale or bool(late),'late_evidence_revision_ids':late,'content':row_json(progress_revision(db,row)),'historical_review_immutable':True}

@mutation('assessment.write','progress')
def create_progress(db,actor,school_id,command):
    snap=snapshot(db,actor,school_id,command);evidence_sufficient(snap,command.finding);validate_tasks(db,school_id,str(command.learner_id),command.finding)
    row=m.ProgressReview(school_id=school_id,learner_id=str(command.learner_id),goal_revision_id=str(command.goal_revision_id),starts_at=command.starts_at,ends_at=command.ends_at,snapshot=snap,snapshot_digest=a.digest(snap),state='draft');db.add(row);db.flush()
    finding=command.finding.model_dump(mode='json')
    db.add(m.ProgressRevision(school_id=school_id,review_id=row.id,number=1,finding=finding,digest=a.digest({'snapshot_digest':row.snapshot_digest,'finding':finding}),author_id=actor.user_id,status='draft'))
    event(db,actor,row,'assessment.progress.created');return row

@mutation('assessment.write','progress')
def revise_progress(db,actor,school_id,identifier,command):
    row=get(db,m.ProgressReview,school_id,identifier,command.expected_version)
    if row.state=='confirmed':raise conflict('A confirmed historical review is immutable. Create a new review with the new evidence.')
    current=progress_view(db,actor,school_id,row.id)
    if current['source_status']!='current':raise conflict('Rebuild the source snapshot before continuing this review.')
    evidence_sufficient(row.snapshot,command.finding);validate_tasks(db,school_id,row.learner_id,command.finding)
    row.current_revision+=1;row.version+=1;row.state='draft';finding=command.finding.model_dump(mode='json')
    db.add(m.ProgressRevision(school_id=school_id,review_id=row.id,number=row.current_revision,finding=finding,digest=a.digest({'snapshot_digest':row.snapshot_digest,'finding':finding}),author_id=actor.user_id,status='draft'))
    event(db,actor,row,'assessment.progress.revised');return row

@mutation('assessment.review','progress')
def transition_progress(db,actor,school_id,identifier,command):
    row=get(db,m.ProgressReview,school_id,identifier,command.expected_version);rev=progress_revision(db,row)
    if rev.id!=str(command.revision_id) or rev.digest!=command.content_digest:raise conflict()
    current=progress_view(db,actor,school_id,row.id)
    if current['source_status']!='current' or current['review_required']:raise conflict('New or changed evidence requires a new source snapshot and review.')
    expected_state='draft' if command.transition=='submit' else 'in_review'
    if row.state!=expected_state:raise conflict()
    state='in_review' if command.transition=='submit' else 'confirmed'
    row.current_revision+=1;row.version+=1;row.state=state
    # Status transitions append an exact human binding instead of rewriting it.
    finding={**rev.finding,'review_reason':command.reason}
    db.add(m.ProgressRevision(school_id=school_id,review_id=row.id,number=row.current_revision,finding=finding,digest=a.digest({'snapshot_digest':row.snapshot_digest,'finding':finding,'status':state}),author_id=actor.user_id,status=state))
    event(db,actor,row,'assessment.progress.'+state);return row

def statement_revision(db,row):
    return db.scalar(select(m.StatementRevision).where(m.StatementRevision.school_id==row.school_id,m.StatementRevision.statement_id==row.id,m.StatementRevision.number==row.current_revision))
def statement_basis(db,actor,row,content,seen=None):
    sc=a.scheme(db,actor,row.school_id,row.scheme_revision_id,row.starts_on,row.ends_on)
    if sc is None:return None,[],['assessment_scheme_unresolved']
    rules=[r for r in sc['assessment_rules'] if r['subject']==row.subject]
    if len(rules)!=1:raise DomainError('assessment_subject_unresolved','The reviewed scheme must identify one explicit assessment rule for this subject.',409)
    codes={g['code'] for g in sc['goals'] if g['subject']==row.subject}
    sources=[]
    for entry in content['basis']:
        basis=s.CompetenceBasis.model_validate(entry)
        if basis.curriculum_goal_code not in codes:raise DomainError('assessment_curriculum_goal','Select an exact subject competence goal from this reviewed scheme.',409)
        value=resolve_reference(db,actor,row.school_id,row.learner_id,basis.reference,seen=seen)
        if basis.role=='subject_competence':
            if basis.reference.kind=='progress_review' or value['value'].get('goal_revision_id') is not None:raise DomainError('iop_not_subject_grade_basis','An IOP progress source cannot silently become the subject competence or grade basis.',409)
        occurred=value['value'].get('occurred_at')
        if occurred:
            day=local_day(db,row.school_id,datetime.fromisoformat(occurred.replace('Z','+00:00')))
            if not row.starts_on<=day<=row.ends_on:raise DomainError('assessment_source_period','Subject evidence must occur within the selected school-local assessment period.',409)
        sources.append({**entry,'resolved':value})
    unresolved=[]
    if content['completion']=='unresolved':unresolved.append('subject_completion_unresolved')
    if content['exemption']=='unresolved':unresolved.append('assessment_exemption_unresolved')
    if not any(v['role']=='subject_competence' for v in sources):unresolved.append('subject_competence_basis_missing')
    return sc,sources,unresolved

def statement_content(db,actor,row,content):
    values=content.model_dump(mode='json')
    scheme,sources,unresolved=statement_basis(db,actor,row,values)
    return {**values,'scheme_binding':scheme,'source_snapshot':sources,'unresolved':unresolved,'drafting':'manual_grounded_source_review','ai_generation':'not_integrated'}

def statement_view(db,actor,school_id,identifier):
    row=get(db,m.Statement,school_id,identifier);pupil_access(db,actor,school_id,row.learner_id)
    rev=statement_revision(db,row)
    try:
        if a.digest(rev.content)!=rev.digest:raise conflict('The statement content differs from its immutable digest.')
        sc,sources,unresolved=statement_basis(db,actor,row,rev.content)
        stale=a.digest(sc)!=a.digest(rev.content['scheme_binding']) or a.digest(sources)!=a.digest(rev.content['source_snapshot'])
        contributions=list(db.scalars(select(m.Contribution).where(m.Contribution.school_id==school_id,m.Contribution.statement_revision_id==rev.id).order_by(m.Contribution.created_at,m.Contribution.id)))
        for entry in contributions:
            for ref in entry.sources:resolve_reference(db,actor,school_id,row.learner_id,ref)
        final=db.scalar(select(m.StatementFinalization).where(m.StatementFinalization.school_id==school_id,m.StatementFinalization.statement_revision_id==rev.id))
    except DomainError as exc:
        if exc.status_code not in {403,409}:raise
        return {'kind':'statement','id':row.id,'learner_id':row.learner_id,'version':row.version,'state':row.state,'source_status':'unavailable','content':None,'contributions':[],'finalization':None,'reason':exc.code}
    final_authority_current=bool(final and authority_current(db,actor,final.authority_binding) and (not final.grade_authority or authority_current(db,actor,final.grade_authority)))
    if final and not final_authority_current:stale=True
    contributed={c.author_id for c in contributions if c.kind=='staff'}
    missing=sorted(set(rev.content['expected_contributors'])-contributed)
    communications=list(db.scalars(select(m.Communication).where(m.Communication.school_id==school_id,m.Communication.statement_revision_id==rev.id)))
    return {'kind':'statement',**row_json(row),'source_status':'review_required' if stale else 'current','revision_id':rev.id,'content_digest':rev.digest,'content':rev.content,'scheme':sc,'unresolved':unresolved,'missing_contributor_ids':missing,'contributions':[row_json(c) for c in contributions],'finalization':row_json(final) if final else None,'communications':[row_json(c) for c in communications],'external_send_performed':False,'finalization_authority_status':'reviewed_current' if final_authority_current else 'unassessed'}

@mutation('assessment.write','statement')
def create_statement(db,actor,school_id,command):
    row=m.Statement(school_id=school_id,learner_id=str(command.learner_id),scheme_revision_id=str(command.scheme_revision_id) if command.scheme_revision_id else None,subject=command.subject,assessment_type=command.assessment_type,starts_on=command.starts_on,ends_on=command.ends_on,state='under_work')
    content=statement_content(db,actor,row,command.content)
    if content['unresolved']:row.state='needs_basis'
    db.add(row);db.flush();db.add(m.StatementRevision(school_id=school_id,statement_id=row.id,number=1,content=content,digest=a.digest(content),author_id=actor.user_id));event(db,actor,row,'assessment.statement.created');return row

@mutation('assessment.write','statement')
def revise_statement(db,actor,school_id,identifier,command):
    row=get(db,m.Statement,school_id,identifier,command.expected_version)
    if row.state=='finalized':raise conflict('A finalized historical statement is immutable. Create a new statement.')
    if command.scheme_revision_id is not None:row.scheme_revision_id=str(command.scheme_revision_id)
    content=statement_content(db,actor,row,command.content)
    row.current_revision+=1;row.version+=1;row.state='needs_basis' if content['unresolved'] else 'under_work'
    db.add(m.StatementRevision(school_id=school_id,statement_id=row.id,number=row.current_revision,content=content,digest=a.digest(content),author_id=actor.user_id));event(db,actor,row,'assessment.statement.revised');return row

@mutation('assessment.contribute','statement')
def contribute(db,actor,school_id,identifier,command):
    row=get(db,m.Statement,school_id,identifier,command.expected_version)
    if row.state=='finalized' or command.occurred_at>utcnow():raise conflict('Record dated contributions while the statement is under review.')
    rev=statement_revision(db,row)
    for ref in command.sources:
        value=resolve_reference(db,actor,school_id,row.learner_id,ref)['value']
        if command.kind=='learner_self_assessment' and (ref.kind!='evidence' or (value.get('source_type')!='reported_information' or value.get('claim_type')!='report' or not value.get('reporter'))):raise DomainError('learner_voice_source','Learner self-assessment requires an attributed confirmed report of the learner’s own account.',409)
    db.add(m.Contribution(school_id=school_id,statement_id=row.id,statement_revision_id=rev.id,author_id=actor.user_id,kind=command.kind,occurred_at=command.occurred_at,content=command.content,sources=[r.model_dump(mode='json') for r in command.sources]))
    row.version+=1;event(db,actor,row,'assessment.statement.contribution_recorded');return row

@mutation('assessment.finalize','statement')
def finalize_statement(db,actor,school_id,identifier,command):
    row=get(db,m.Statement,school_id,identifier,command.expected_version);rev=statement_revision(db,row)
    require_authority(db,actor,school_id,'assessment.finalize',learner_id=row.learner_id)
    if row.state=='finalized' or rev.id!=str(command.revision_id) or rev.digest!=command.content_digest:raise conflict()
    if row.ends_on>school_today(db.get(School,school_id)):raise DomainError('assessment_period','Finalization requires an elapsed assessment period.',409)
    current=statement_view(db,actor,school_id,row.id)
    if current['source_status']!='current' or current['unresolved'] or current['missing_contributor_ids']:raise DomainError('assessment_basis_unresolved','Resolve scheme, completion, exemption, subject evidence and outstanding contributions before finalization.',409)
    requested=[str(v) for v in command.contribution_ids]
    actual=[c['id'] for c in current['contributions']]
    if len(set(requested))!=len(requested) or set(requested)!=set(actual):raise conflict('Finalization binds every exact current contribution.')
    basis=authority_basis(db,actor,authority_request(actor,row,rev,'statement_finalize',row.starts_on,row.ends_on,subject=row.subject,scheme_revision_id=row.scheme_revision_id),required=True)
    if basis['completion']!=rev.content['completion'] or basis['exemption']!=rev.content['exemption'] or basis['grade_policy']=='unresolved':raise DomainError('assessment_authority_unresolved','The reviewed authority must resolve this exact completion, exemption and grading policy.',409)
    if basis['exemption']=='assessment_exempt':raise DomainError('assessment_exempt','The recorded exemption does not authorize this assessment statement.',409)
    if row.assessment_type=='final' and basis['completion']!='completes_in_period':raise DomainError('subject_completion','A final subject assessment requires reviewed completion in this period.',409)
    grade_basis=None
    if command.grade is not None:
        require_authority(db,actor,school_id,'assessment.grade',learner_id=row.learner_id)
        grade_basis=authority_basis(db,actor,authority_request(actor,row,rev,'grade_set',row.starts_on,row.ends_on,subject=row.subject,scheme_revision_id=row.scheme_revision_id),required=True)
        if grade_basis['completion']!=basis['completion'] or grade_basis['exemption']!=basis['exemption'] or grade_basis['grade_policy']!=basis['grade_policy'] or grade_basis['grade_policy'] not in {'optional','required'} or command.grade not in grade_basis['grade_values'] or grade_basis['exemption']!='not_exempt':raise DomainError('assessment_grade_unresolved','Only the reviewed subject scale and non-exempt grade authority permit this human-entered grade.',409)
    elif basis['grade_policy']=='required' and basis['exemption']!='grade_exempt':raise DomainError('assessment_grade_required','An authorized subject teacher must explicitly enter the grade required by the reviewed scheme.',409)
    db.add(m.StatementFinalization(school_id=school_id,statement_revision_id=rev.id,revision_digest=rev.digest,authorized_person_id=actor.user_id,authority_binding=basis,grade=command.grade,grade_authority=grade_basis,contribution_ids=sorted(requested),reason=command.reason));row.state='finalized';row.version+=1;event(db,actor,row,'assessment.statement.finalized',statement_revision_id=rev.id);return row

@mutation('assessment.communicate','statement')
def record_communication(db,actor,school_id,identifier,command):
    row=get(db,m.Statement,school_id,identifier,command.expected_version);rev=statement_revision(db,row)
    if row.state!='finalized' or rev.id!=str(command.revision_id) or command.occurred_at>utcnow():raise conflict('Record factual communication for an exact finalized statement after it happened.')
    current=statement_view(db,actor,school_id,row.id)
    if current['source_status']!='current':raise conflict('Recheck the statement sources before recording communication.')
    db.add(m.Communication(school_id=school_id,statement_revision_id=rev.id,recorded_by=actor.user_id,occurred_at=command.occurred_at,destination=command.destination,method=command.method,factual_reference=command.factual_reference));row.version+=1;event(db,actor,row,'assessment.communication.recorded',destination=command.destination);return row

def view(db,actor,school_id,kind,identifier):
    return {'instrument':instrument_view,'administration':administration_view,'follow_up':follow_up_view,'progress':progress_view,'statement':statement_view}[kind](db,actor,school_id,identifier)


def read_contract(fn):
    @wraps(fn)
    def wrapped(db,*args,**kwargs):
        watched=('spesped.contexts.identity.','spesped.contexts.evidence.','spesped.contexts.plans.','spesped.contexts.teaching.','spesped.contexts.curriculum.','spesped.contexts.assessment.','spesped.contexts.entitlements.','spesped.contexts.platform.')
        excluded=(m.AssessmentCommand,m.AssessmentEvent)
        if any(type(row).__module__.startswith(watched) and not isinstance(row,excluded) for row in db.new|db.dirty|db.deleted):
            raise DomainError('dependency_pending','Flush or roll back pending assessment/source/permission changes before reading.',409)
        with db.no_autoflush:return fn(db,*args,**kwargs)
    return wrapped

instrument_view=read_contract(instrument_view)
administration_view=read_contract(administration_view)
follow_up_view=read_contract(follow_up_view)
progress_view=read_contract(progress_view)
statement_view=read_contract(statement_view)

@read_contract
def revision_history(db,actor,school_id,kind,identifier,offset=0,limit=50):
    """Recover authored versions without widening any original-source access."""
    model=m.ProgressReview if kind=='progress' else m.Statement
    row=get(db,model,school_id,identifier);pupil_access(db,actor,school_id,row.learner_id)
    revision_model=m.ProgressRevision if kind=='progress' else m.StatementRevision
    column=revision_model.review_id if kind=='progress' else revision_model.statement_id
    rows=list(db.scalars(select(revision_model).where(revision_model.school_id==school_id,column==row.id).order_by(revision_model.number)))
    if kind=='progress':
        current=progress_view(db,actor,school_id,row.id)
        if current['source_status']=='unavailable':return {'items':[],'total':len(rows),'source_status':'unavailable'}
        return {'items':[row_json(r) for r in rows[offset:offset+limit]],'total':len(rows),'source_status':current['source_status']}
    from types import SimpleNamespace
    values=[]
    for revision in rows[offset:offset+limit]:
        sc=revision.content.get('scheme_binding')
        historical=SimpleNamespace(**{**row_json(row),'scheme_revision_id':sc['scheme_revision_id'] if sc else None,'starts_on':row.starts_on,'ends_on':row.ends_on})
        try:
            statement_basis(db,actor,historical,revision.content)
            values.append({**row_json(revision),'source_status':'current'})
        except DomainError as exc:
            if exc.status_code not in {403,409}:raise
            values.append({'id':revision.id,'number':revision.number,'source_status':'unavailable','content':None})
    return {'items':values,'total':len(rows)}
