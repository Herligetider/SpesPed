"""Native, transactional document workflows. Content approval never sends mail."""
import calendar
from datetime import date,datetime,timedelta,timezone
from functools import wraps
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError
from spesped.auth import Actor,require_school_access,require_learner_access,require_authority,school_today,active_at
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError,access_denied
from spesped.contexts.identity.models import School,UserAccount,GuardianRelationship
from . import models as m,schemas as s,adapters as a

def conflict(message='Reload the current document revision before retrying.'):
    return DomainError('document_conflict',message,409)
def get(db,model,school_id,identity,expected=None):
    with db.no_autoflush:row=db.scalar(select(model).where(model.school_id==school_id,model.id==str(identity)).execution_options(populate_existing=True))
    if row is None:raise access_denied()
    if expected is not None and row.version!=expected:raise conflict()
    return row
def access(db,actor,school_id,learner_id,action='documents.read'):
    require_learner_access(db,actor,school_id,learner_id,action)
def school_access(db,actor,school_id,action):
    member=require_school_access(db,actor,school_id)
    if member.role in {'guardian','technical_administrator'}:raise access_denied()
    return require_authority(db,actor,school_id,action)
def row_json(row):return a.encode({c.name:getattr(row,c.name) for c in row.__table__.columns})
def current(db,row,model=m.DocumentRevision,field='document_id'):
    return db.scalar(select(model).where(model.school_id==row.school_id,getattr(model,field)==row.id,model.number==row.current_revision))
def event(db,actor,row,action,**payload):
    now=utcnow();db.flush();record_audit(db,actor,row.school_id,action,row.__tablename__,row.id)
    db.add(m.DocumentEvent(school_id=row.school_id,aggregate_id=row.id,aggregate_version=row.version,actor_id=actor.user_id,event_type=action,payload=a.encode(payload),causation_id=db.info['documents_request_key'],correlation_id=db.info['documents_correlation_id'],occurred_at=now,recorded_at=now,created_at=now,schema_version=1));db.flush()
def mutation(action,kind):
    def decorator(fn):
        @wraps(fn)
        def wrapped(db,actor,school_id,*args):
            previous={k:db.info.get(k) for k in ('documents_request_key','documents_correlation_id')}
            try:
                # One tenant lock gives deterministic receipt/revision/schedule dedup
                # under PostgreSQL, including first commands with no row to lock yet.
                require_school_access(db,actor,school_id)
                db.scalar(select(School.id).where(School.id==school_id).with_for_update())
                command=args[-1];db.info['documents_request_key']=command.request_key;db.info['documents_correlation_id']=str(uuid4())
                fingerprint=a.digest({'operation':fn.__name__,'target':[str(v) for v in args[:-1]],'command':command.model_dump(mode='json')})
                if kind=='template':school_access(db,actor,school_id,action)
                else:
                    if hasattr(command,'learner_id'):learner=str(command.learner_id)
                    elif hasattr(command,'settings'):learner=str(command.settings.learner_id)
                    else:learner=get(db,m.EmailDraftSchedule if kind=='schedule' else m.DocumentCase,school_id,args[0]).learner_id
                    access(db,actor,school_id,learner,action)
                prior=db.scalar(select(m.DocumentCommand).where(m.DocumentCommand.school_id==school_id,m.DocumentCommand.actor_id==actor.user_id,m.DocumentCommand.request_key==command.request_key))
                if prior:
                    if prior.digest!=fingerprint:raise DomainError('idempotency_conflict','This request key identifies different document content or scope.',409)
                    if fn.__name__=='transition_document' and command.action=='approve':approval_authority(db,actor,get(db,m.DocumentCase,school_id,prior.target_id),current(db,get(db,m.DocumentCase,school_id,prior.target_id)),required=True)
                    value=contribution_workspace(db,actor,school_id,prior.target_id) if action=='documents.contribute' else view(db,actor,school_id,kind,prior.target_id)
                    db.commit();return value
                row=fn(db,actor,school_id,*args)
                db.add(m.DocumentCommand(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,operation=fn.__name__,digest=fingerprint,target_kind=kind,target_id=row.id));db.flush()
                value=contribution_workspace(db,actor,school_id,row.id) if action=='documents.contribute' else view(db,actor,school_id,kind,row.id)
                db.commit();return value
            except (StaleDataError,DBAPIError) as exc:
                db.rollback()
                if isinstance(exc,StaleDataError) or getattr(getattr(exc,'orig',None),'sqlstate',None) in {'40001','40P01','55P03','23505'} or 'UNIQUE constraint failed' in str(getattr(exc,'orig','')):raise conflict('A concurrent document command won. Retry the same request key.') from None
                raise
            except Exception:db.rollback();raise
            finally:
                for k,v in previous.items():
                    if v is None:db.info.pop(k,None)
                    else:db.info[k]=v
        return wrapped
    return decorator

def read_contract(fn):
    @wraps(fn)
    def wrapped(db,*args,**kwargs):
        # Separate owner identities prevent populate_existing authorization reads
        # from altering cached caller state. No flush/commit/rollback on reads.
        with a.owner_reader(db) as reader:return fn(reader,*args,**kwargs)
    return wrapped

def template_basis(db,actor,school_id,identity,kind,starts_on,ends_on):
    rev=get(db,m.TemplateRevision,school_id,identity);root=get(db,m.Template,school_id,rev.template_id)
    a.school_sources(db,actor,school_id,rev.content['sources'])
    if a.digest(rev.content)!=rev.digest:raise conflict('Template digest differs from its immutable content.')
    review=db.scalar(select(m.TemplateReview).where(m.TemplateReview.school_id==school_id,m.TemplateReview.revision_id==rev.id))
    c=rev.content
    valid=(root.state=='active' and root.current_revision==rev.number and review is not None and review.digest==rev.digest and c['kind']==kind and date.fromisoformat(c['effective_from'])<=starts_on<=ends_on<=date.fromisoformat(c['effective_until']))
    return {'revision_id':rev.id,'digest':rev.digest,'content':c,'state':'reviewed_current' if valid else 'unresolved','review_id':review.id if review else None}
@read_contract
def template_view(db,actor,school_id,identity):
    require_school_access(db,actor,school_id)
    row=get(db,m.Template,school_id,identity);rev=current(db,row,m.TemplateRevision,'template_id')
    a.school_sources(db,actor,school_id,rev.content['sources'])
    return {**row_json(row),'revision_id':rev.id,'content':rev.content,'content_digest':rev.digest,'reviewed':bool(db.scalar(select(m.TemplateReview.id).where(m.TemplateReview.school_id==school_id,m.TemplateReview.revision_id==rev.id)))}
@mutation('documents.templates.manage','template')
def create_template(db,actor,school_id,command):
    a.school_sources(db,actor,school_id,command.content.sources)
    row=m.Template(school_id=school_id,state='active');db.add(row);db.flush()
    content=command.content.model_dump(mode='json');db.add(m.TemplateRevision(school_id=school_id,template_id=row.id,number=1,content=content,digest=a.digest(content),author_id=actor.user_id));event(db,actor,row,'documents.template.created');return row
@mutation('documents.templates.manage','template')
def revise_template(db,actor,school_id,identity,command):
    row=get(db,m.Template,school_id,identity,command.expected_version);a.school_sources(db,actor,school_id,command.content.sources)
    row.current_revision+=1;row.version+=1;row.state='active';content=command.content.model_dump(mode='json')
    db.add(m.TemplateRevision(school_id=school_id,template_id=row.id,number=row.current_revision,content=content,digest=a.digest(content),author_id=actor.user_id));event(db,actor,row,'documents.template.revised');return row
@mutation('documents.templates.review','template')
def review_template(db,actor,school_id,identity,command):
    row=get(db,m.Template,school_id,identity,command.expected_version);rev=current(db,row,m.TemplateRevision,'template_id')
    if rev.id!=str(command.revision_id) or rev.digest!=command.content_digest:raise conflict()
    a.school_sources(db,actor,school_id,rev.content['sources'])
    if db.scalar(select(m.TemplateReview.id).where(m.TemplateReview.school_id==school_id,m.TemplateReview.revision_id==rev.id)):raise conflict('This exact template already has a human review.')
    db.add(m.TemplateReview(school_id=school_id,revision_id=rev.id,digest=rev.digest,reviewer_id=actor.user_id,reason=command.reason));row.version+=1;event(db,actor,row,'documents.template.reviewed');return row
@mutation('documents.templates.review','template')
def recall_template(db,actor,school_id,identity,command):
    row=get(db,m.Template,school_id,identity,command.expected_version);rev=current(db,row,m.TemplateRevision,'template_id')
    if rev.id!=str(command.revision_id) or rev.digest!=command.content_digest:raise conflict()
    row.state='recalled';row.version+=1;event(db,actor,row,'documents.template.recalled');return row

def recipient(db,actor,school_id,learner_id,identity,action='documents.read'):
    access(db,actor,school_id,learner_id,action)
    relationship=get(db,GuardianRelationship,school_id,identity)
    school=db.get(School,school_id);today=school_today(school)
    user=db.get(UserAccount,relationship.guardian_user_id,populate_existing=True)
    valid=(relationship.learner_id==learner_id and relationship.state=='active' and relationship.valid_from<=today and (relationship.valid_until is None or today<=relationship.valid_until) and relationship.parental_responsibility and relationship.information_rights in {'full','allowed','yes'} and not relationship.restrictions and relationship.source_reference and user and user.state=='active')
    if relationship.learner_id!=learner_id:raise access_denied()
    return {'relationship_id':relationship.id,'version':relationship.version,'state':'eligible_proposal' if valid else 'unresolved','disclosure':'not_authorized'}

def item_key(ref):return f"{ref['kind']}:{ref['id']}:{ref['revision']}"
def entry(ref,value,classification='confirmed'):
    return {'key':item_key(ref),'reference':ref,'digest':a.digest(value),'classification':classification,'value':value}
def collect(db,actor,school_id,command,cutoff,recipient_action='documents.read'):
    learner_id=str(command.learner_id);start,end,tz=a.period(db,school_id,command.starts_on,command.ends_on)
    entries={};gaps=[]
    for selected in command.selection.goals:
        if not start<=selected.applicable_at<end:raise DomainError('goal_period','The goal applicability instant must lie in the chosen interval.',422)
        value=a.goal(db,actor,school_id,learner_id,selected)
        ref={'kind':'goal','id':str(selected.goal_revision_id),'revision':1,'applicable_at':selected.applicable_at.isoformat()}
        entries[item_key(ref)]=entry(ref,value,'historical_goal_basis')
    refs=list(command.selection.references)
    if command.selection.discover_evidence:
        for v in a.evidence(db,actor,school_id,learner_id,start,end):
            refs.append(s.EvidenceRef.model_validate(v['reference']))
    if command.selection.discover_observations:
        for v in a.observations(db,actor,school_id,learner_id,start,end):
            refs.append(s.EvidenceRef(kind='observation',id=v['revision_id'],revision=v['revision']))
    for ref in refs:
        resolved=a.reference(db,actor,school_id,learner_id,ref);value=resolved['value']
        occurred=value.get('occurred_at')
        if not occurred or not start<=datetime.fromisoformat(occurred.replace('Z','+00:00'))<end:raise DomainError('source_period','Selected factual sources must occur in the chosen inclusive calendar interval.',422)
        recorded=value.get('recorded_at') or value.get('created_at')
        if recorded and datetime.fromisoformat(recorded.replace('Z','+00:00'))>cutoff:continue
        entries[item_key(resolved['reference'])]=entry(resolved['reference'],value)
    for ref in command.selection.background_references:
        resolved=a.reference(db,actor,school_id,learner_id,ref);value=resolved['value'];occurred=value.get('occurred_at')
        if not occurred or datetime.fromisoformat(occurred.replace('Z','+00:00'))>=start:raise DomainError('background_period','Background references must predate the chosen interval; choose interval facts separately.',422)
        entries[item_key(resolved['reference'])]=entry(resolved['reference'],value,'background_reference_not_interval_fact')
    for identity in command.selection.actual_revision_ids:
        value=a.actual(db,actor,school_id,learner_id,identity)
        if not start<=datetime.fromisoformat(value['occurred_at'].replace('Z','+00:00'))<end:raise DomainError('actual_period','Actual delivery lies outside the chosen interval.',422)
        ref={'kind':'actual','id':str(identity),'revision':1};entries[item_key(ref)]=entry(ref,value,'actual_delivery_not_learning_progress')
    for identity in command.selection.future_plan_revision_ids:
        value=a.future_plan(db,actor,school_id,learner_id,identity)
        if datetime.fromisoformat(value['planned_at'].replace('Z','+00:00'))<end:raise DomainError('future_plan_period','Future plans must follow the summary period.',422)
        ref={'kind':'future_plan','id':str(identity),'revision':1};entries[item_key(ref)]=entry(ref,value,'future_plan_not_actual')
    observed=[v for v in entries.values() if v['classification']=='confirmed' and (v['reference']['kind'] in {'observation','assessment_result','progress_review','assessment_statement'} or (v['reference']['kind']=='evidence' and v['value'].get('claim_type')=='observation'))]
    if not observed:gaps.append('no_confirmed_observations_in_selected_period')
    if command.kind=='annual_ito_evaluation':
        if not any(v['classification']=='historical_goal_basis' and v['value']['goal']['kind']=='individual_education' for v in entries.values()):gaps.append('historical_ito_goal_basis_missing')
        if not any(v['reference']['kind']=='actual' for v in entries.values()):gaps.append('actual_delivery_not_selected')
        if not any(v['reference']['kind']=='progress_review' for v in entries.values()):gaps.append('professional_progress_review_not_selected')
    template=None;rule=None
    if command.template_revision_id:
        template=template_basis(db,actor,school_id,command.template_revision_id,command.kind,command.starts_on,command.ends_on)
        if template['state']!='reviewed_current':gaps.append('template_review_unresolved')
    elif command.kind!='guardian_email':gaps.append('template_unknown_manual_working_draft')
    if template and template['content']['requirement_version_id']:
        if command.obligation_id:
            rule=a.obligation(db,actor,school_id,learner_id,command.obligation_id,command.kind,command.starts_on,command.ends_on)
            if rule['state']!='applicable' or rule['requirement_version_id']!=template['content']['requirement_version_id']:gaps.append('rule_applicability_unresolved')
        else:gaps.append('rule_applicability_unresolved')
    recipients=[recipient(db,actor,school_id,learner_id,v,recipient_action) for v in command.recipient_relationship_ids]
    return a.encode({'period':{'starts_on':command.starts_on,'ends_on':command.ends_on,'timezone':tz,'starts_at':start,'ends_at_exclusive':end},'cutoff':cutoff,'purpose':command.purpose,'kind':command.kind,'language':command.language,'length':command.length,'topics':command.topics,'selection':command.selection.model_dump(mode='json'),'entries':sorted(entries.values(),key=lambda v:v['key']),'gaps':gaps,'template':template,'rule':rule,'recipients':recipients,'planned_activity_is_delivery':False,'missing_evidence_is_progress':False})

def configuration(command):
    return command.model_dump(mode='json',exclude={'request_key','content'})
def make_revision(db,actor,row,command,reason,lineage=None,existing_snapshot=None):
    snap=existing_snapshot
    if snap is None:
        cutoff=utcnow();data=collect(db,actor,row.school_id,command,cutoff)
        snap=m.EvidenceSnapshot(school_id=row.school_id,document_id=row.id,learner_id=row.learner_id,cutoff=cutoff,content=data,digest=a.digest(data));db.add(snap);db.flush()
    data=snap.content
    if command.content is None:
        specs=data['template']['content']['sections'] if data['template'] else ([{'key':'body'},{'key':'next_steps'}] if row.kind=='guardian_email' else [{'key':'summary'},{'key':'actual_delivery'},{'key':'human_evaluation'}])
        content=s.Content(subject=None,sections=[s.Section(key=v['key'],missing_inputs=data['gaps'] if i==0 else []) for i,v in enumerate(specs)]).model_dump(mode='json')
    else:content=command.content.model_dump(mode='json')
    validate_content(content,data)
    config=configuration(command)
    digest=a.digest({'configuration':config,'content':content,'snapshot_digest':snap.digest,'lineage':lineage or {}})
    rev=m.DocumentRevision(school_id=row.school_id,document_id=row.id,snapshot_id=snap.id,number=row.current_revision,configuration=config,content=content,digest=digest,author_id=actor.user_id,reason=reason,lineage=lineage or {})
    db.add(rev);db.flush()
    if row.current_revision>1:
        previous=db.scalar(select(m.DocumentRevision).where(m.DocumentRevision.school_id==row.school_id,m.DocumentRevision.document_id==row.id,m.DocumentRevision.number==row.current_revision-1))
        if previous:
            for assignment in db.scalars(select(m.ContributionAssignment).where(m.ContributionAssignment.school_id==row.school_id,m.ContributionAssignment.revision_id==previous.id)):
                db.add(m.ContributionAssignment(school_id=row.school_id,revision_id=rev.id,section_key=assignment.section_key,contributor_id=assignment.contributor_id,required=assignment.required,assigned_by=actor.user_id))
    db.flush();return rev

def validate_content(content,snapshot):
    keys={v['key'] for v in snapshot['entries']}
    if any(not set(v['source_keys'])<=keys for v in content['sections']):raise DomainError('source_key_scope','A section cites a source outside its immutable snapshot.',422)
    if snapshot['template']:
        allowed={v['key'] for v in snapshot['template']['content']['sections']}
        if not {v['key'] for v in content['sections']}<=allowed:raise DomainError('template_section','Sections must belong to the selected template.',422)

@mutation('documents.write','document')
def create_document(db,actor,school_id,command):
    access(db,Actor(str(command.owner_id)),school_id,str(command.learner_id),'documents.write')
    if command.kind=='guardian_email' and not command.recipient_relationship_ids:raise DomainError('recipient_selection','Select proposed guardian recipients for this purpose.',422)
    row=m.DocumentCase(school_id=school_id,learner_id=str(command.learner_id),owner_id=str(command.owner_id),kind=command.kind,state='draft');db.add(row);db.flush()
    make_revision(db,actor,row,command,'Initial human-selected document basis');event(db,actor,row,'documents.created');return row
@mutation('documents.write','document')
def revise_document(db,actor,school_id,identity,command):
    row=get(db,m.DocumentCase,school_id,identity,command.expected_version);data=command.document
    if str(data.learner_id)!=row.learner_id or data.kind!=row.kind:raise conflict('A revision cannot move a document to another pupil or report type.')
    access(db,Actor(str(data.owner_id)),school_id,row.learner_id,'documents.write')
    old=current(db,row);lineage=dict(old.lineage)
    before={v['key']:v['text'] for v in old.content['sections']}|{'subject':old.content['subject']}
    after={v.key:v.text for v in data.content.sections}|{'subject':data.content.subject} if data.content else {}
    for key in command.sever_generation_fields:
        if key not in lineage or key not in after or after[key]==before.get(key):raise DomainError('independent_replacement_required','Severing AI lineage requires a changed independently authored field.',422)
        lineage.pop(key)
    row.owner_id=str(data.owner_id);row.current_revision+=1;row.version+=1;row.state='draft'
    db.flush();make_revision(db,actor,row,data,command.reason,lineage=lineage);event(db,actor,row,'documents.revised');return row

def snapshot_status(db,actor,row,rev,recipient_action='documents.read'):
    snap=get(db,m.EvidenceSnapshot,row.school_id,rev.snapshot_id)
    if a.digest(snap.content)!=snap.digest:raise conflict('Snapshot content differs from its immutable digest.')
    if a.digest({'configuration':rev.configuration,'content':rev.content,'snapshot_digest':snap.digest,'lineage':rev.lineage})!=rev.digest:raise conflict('Saved content differs from its exact immutable revision digest.')
    command=s.DocumentCreate.model_validate({**rev.configuration,'request_key':'read','content':rev.content})
    # Resolve original refs even when discovery now omits corrected/withdrawn rows.
    for v in snap.content['entries']:
        ref=v['reference'];kind=ref['kind']
        if kind=='goal':value=a.goal(db,actor,row.school_id,row.learner_id,s.GoalSelection(goal_revision_id=ref['id'],applicable_at=ref['applicable_at']))
        elif kind=='actual':value=a.actual(db,actor,row.school_id,row.learner_id,ref['id'])
        elif kind=='future_plan':value=a.future_plan(db,actor,row.school_id,row.learner_id,ref['id'])
        else:value=a.reference(db,actor,row.school_id,row.learner_id,s.EvidenceRef.model_validate(ref))['value']
        if a.digest(value)!=v['digest']:raise conflict('Selected source content or authority changed; review a new revision.')
    from .generation import validate_lineage
    validate_lineage(db,actor,row,rev)
    current_data=collect(db,actor,row.school_id,command,utcnow(),recipient_action)
    original={v['key'] for v in snap.content['entries']};late=[{'key':v['key'],'digest':v['digest']} for v in current_data['entries'] if v['key'] not in original]
    basis_changed=any(current_data[k]!=snap.content[k] for k in ('template','rule','recipients','period'))
    return snap,{'state':'review_required' if late or basis_changed else 'current','late_sources':late,'basis_changed':basis_changed}

def missing_contributions(db,row,rev):
    assignments=list(db.scalars(select(m.ContributionAssignment).where(m.ContributionAssignment.school_id==row.school_id,m.ContributionAssignment.revision_id==rev.id)))
    contributions=list(db.scalars(select(m.Contribution).where(m.Contribution.school_id==row.school_id,m.Contribution.revision_id==rev.id)))
    missing=[{'section_key':v.section_key,'contributor_id':v.contributor_id} for v in assignments if v.required and not any(c.section_key==v.section_key and c.author_id==v.contributor_id and c.kind in {'submitted','checked'} for c in contributions)]
    snap=get(db,m.EvidenceSnapshot,row.school_id,rev.snapshot_id)
    if snap.content['template']:
        for v in snap.content['template']['content']['sections']:
            if v.get('contribution_required') and not any(c.section_key==v['key'] and c.kind in {'submitted','checked'} for c in contributions):missing.append({'section_key':v['key'],'contributor_id':None})
    return missing

def approval_authority(db,actor,row,rev,required=False):
    snap=get(db,m.EvidenceSnapshot,row.school_id,rev.snapshot_id);template=snap.content['template'];action=template['content']['approval_action'] if template else 'documents.approve'
    try:
        grant=require_authority(db,actor,row.school_id,action,learner_id=row.learner_id)
        return {'id':grant.id,'version':grant.version,'action':grant.action,'learner_id':grant.learner_id,'valid_from':grant.valid_from.isoformat(),'valid_until':grant.valid_until.isoformat() if grant.valid_until else None,'person_id':actor.user_id,'revision_id':rev.id,'digest':rev.digest}
    except DomainError:
        if required:raise
        return None

def ready(db,actor,row,rev):
    snap,status=snapshot_status(db,actor,row,rev)
    if status['state']!='current':raise conflict('New or changed source basis requires a new reviewed document revision.')
    data=snap.content
    access(db,Actor(row.owner_id),row.school_id,row.learner_id,'documents.write')
    if row.kind!='guardian_email' and (not data['template'] or data['template']['state']!='reviewed_current' or 'rule_applicability_unresolved' in data['gaps']):raise DomainError('template_unresolved','Use an exact reviewed applicable template before report finalization. The manual working draft remains available.',409)
    if any(v['state']!='eligible_proposal' for v in data['recipients']):raise DomainError('recipient_unresolved','The proposed guardian relationship requires current rights review.',409)
    if row.kind=='guardian_email' and not rev.content['subject']:raise DomainError('subject_missing','Provide an email subject before approval.',409)
    spec=data['template']['content']['sections'] if data['template'] else [{'key':v['key'],'required':True} for v in rev.content['sections']]
    bykey={v['key']:v for v in rev.content['sections']}
    missing=[v['key'] for v in spec if v.get('required',True) and (v['key'] not in bykey or not bykey[v['key']]['text'])]
    unresolved=set(data['gaps'])|{g for v in rev.content['sections'] for g in v['missing_inputs']}
    unresolved-=set(rev.content['handled_gaps'])
    if missing or unresolved:raise DomainError('document_inputs_missing','Required section text and explicit handling of every evidence gap are needed before approval.',409)
    if missing_contributions(db,row,rev):raise DomainError('document_contributions_missing','Required section contributors must submit or check this exact revision.',409)
    return snap
@mutation('documents.review','document')
def transition_document(db,actor,school_id,identity,command):
    row=get(db,m.DocumentCase,school_id,identity,command.expected_version);rev=current(db,row)
    if rev.id!=str(command.revision_id) or rev.digest!=command.content_digest:raise conflict()
    if command.action=='approve':
        if db.scalar(select(m.ContentApproval.id).where(m.ContentApproval.school_id==school_id,m.ContentApproval.revision_id==rev.id)):raise conflict('This revision was already approved or recalled; create a new revision for renewed approval.')
        if row.state!='in_review':raise conflict('Submit this exact revision for review before approving it.')
        ready(db,actor,row,rev);binding=approval_authority(db,actor,row,rev,required=True)
        db.add(m.ContentApproval(school_id=school_id,revision_id=rev.id,digest=rev.digest,approver_id=actor.user_id,action=binding['action'],authority=binding,reason=command.reason));row.state='approved'
    elif command.action=='review':
        if row.state not in {'draft','waiting_contributions'}:raise conflict()
        snapshot_status(db,actor,row,rev);row.state='waiting_contributions' if missing_contributions(db,row,rev) else 'in_review'
    elif command.action=='recall':
        approval_authority(db,actor,row,rev,required=True)
        if row.state!='approved':raise conflict()
        row.state='draft'
    else:row.state='discarded'
    row.version+=1;db.add(m.ReviewRecord(school_id=school_id,revision_id=rev.id,action=command.action,actor_id=actor.user_id,reason=command.reason));event(db,actor,row,'documents.'+command.action,revision_id=rev.id);return row

@mutation('documents.write','document')
def assign_contribution(db,actor,school_id,identity,command):
    row=get(db,m.DocumentCase,school_id,identity,command.expected_version);rev=current(db,row)
    if row.state=='approved' or rev.id!=str(command.revision_id) or command.section_key not in {v['key'] for v in rev.content['sections']}:raise conflict()
    access(db,Actor(str(command.contributor_id)),school_id,row.learner_id,'documents.contribute')
    db.add(m.ContributionAssignment(school_id=school_id,revision_id=rev.id,section_key=command.section_key,contributor_id=str(command.contributor_id),required=command.required,assigned_by=actor.user_id));row.state='waiting_contributions';row.version+=1;event(db,actor,row,'documents.contributor.assigned',revision_id=rev.id);return row
@mutation('documents.contribute','document')
def contribute(db,actor,school_id,identity,command):
    row=get(db,m.DocumentCase,school_id,identity,command.expected_version);rev=current(db,row)
    if row.state in {'approved','discarded'} or rev.id!=str(command.revision_id):raise conflict()
    assigned=db.scalar(select(m.ContributionAssignment).where(m.ContributionAssignment.school_id==school_id,m.ContributionAssignment.revision_id==rev.id,m.ContributionAssignment.contributor_id==actor.user_id,m.ContributionAssignment.section_key==command.section_key))
    if assigned is None:raise access_denied()
    snap,status=snapshot_status(db,actor,row,rev,'documents.contribute')
    if not set(command.source_keys)<={v['key'] for v in snap.content['entries']}:raise access_denied()
    db.add(m.Contribution(school_id=school_id,revision_id=rev.id,section_key=command.section_key,author_id=actor.user_id,kind=command.kind,text=command.text,source_keys=command.source_keys));row.version+=1;db.flush()
    if row.state=='waiting_contributions' and not missing_contributions(db,row,rev):row.state='draft'
    event(db,actor,row,'documents.contribution.recorded',revision_id=rev.id);return row

def approval_status(db,actor,row,rev):
    approval=db.scalar(select(m.ContentApproval).where(m.ContentApproval.school_id==row.school_id,m.ContentApproval.revision_id==rev.id))
    if approval is None:return None
    if row.state!='approved' or current(db,row).id!=rev.id:return {'id':approval.id,'state':'superseded_or_recalled'}
    binding=approval_authority(db,Actor(approval.approver_id),row,rev)
    return {'id':approval.id,'state':'current' if binding==approval.authority and approval.digest==rev.digest else 'authority_review_required','approver_id':approval.approver_id,'revision_id':rev.id,'digest':approval.digest}

def revision_view(db,actor,row,rev):
    metadata={'id':rev.id,'number':rev.number,'digest':rev.digest,'created_at':rev.created_at,'author_id':rev.author_id,'snapshot_id':rev.snapshot_id,'configuration':rev.configuration}
    try:snap,status=snapshot_status(db,actor,row,rev)
    except DomainError as exc:
        if exc.status_code not in {403,409}:raise
        return {**a.encode(metadata),'content':None,'source_status':'unavailable','review_required':True,'snapshot':None,'approval':None,'source_changes':{'state':'unavailable','reason_code':exc.code,'content_withheld':True}}
    approval=approval_status(db,actor,row,rev)
    if approval and approval['state']!='current':status['state']='review_required'
    return {**a.encode(metadata),'content':rev.content,'source_status':status['state'],'review_required':status['state']!='current','source_changes':status,'snapshot':{'id':snap.id,'cutoff':snap.cutoff,'digest':snap.digest,'manifest':snap.content},'approval':approval,'missing_contributions':missing_contributions(db,row,rev),'lineage':rev.lineage}
@read_contract
def document_view(db,actor,school_id,identity):
    row=get(db,m.DocumentCase,school_id,identity);access(db,actor,school_id,row.learner_id)
    rev=current(db,row);value=revision_view(db,actor,row,rev)
    contributions=[]
    if value['content'] is not None:contributions=[row_json(v) for v in db.scalars(select(m.Contribution).where(m.Contribution.school_id==school_id,m.Contribution.revision_id==rev.id).order_by(m.Contribution.created_at,m.Contribution.id))]
    owner_state='active'
    try:access(db,Actor(row.owner_id),school_id,row.learner_id,'documents.write')
    except DomainError:owner_state='inactive_or_scope_revoked'
    return {**row_json(row),'owner_state':owner_state,'revision_id':rev.id,'content_digest':rev.digest,'revision':value,'contributions':contributions,'dispatch':{'state':'not_requested','automatic_send':False},'legal_finalization':'reviewed_report' if row.kind!='guardian_email' and row.state=='approved' and value['source_status']=='current' else 'not_finalized'}
@read_contract
def revision_history(db,actor,school_id,identity,offset=0,limit=50):
    row=get(db,m.DocumentCase,school_id,identity);access(db,actor,school_id,row.learner_id)
    rows=list(db.scalars(select(m.DocumentRevision).where(m.DocumentRevision.school_id==school_id,m.DocumentRevision.document_id==row.id).order_by(m.DocumentRevision.number)))
    return {'items':[revision_view(db,actor,row,r) for r in rows[offset:offset+limit]],'total':len(rows)}
@read_contract
def frozen_revision(db,actor,school_id,learner_id,revision_id,purpose):
    rev=get(db,m.DocumentRevision,school_id,revision_id);row=get(db,m.DocumentCase,school_id,rev.document_id);access(db,actor,school_id,learner_id,'documents.read')
    if row.learner_id!=learner_id or rev.configuration['purpose']!=purpose or row.state!='approved' or current(db,row).id!=rev.id:raise access_denied()
    snap,status=snapshot_status(db,actor,row,rev);approval=approval_status(db,actor,row,rev)
    if status['state']!='current' or not approval or approval['state']!='current':raise conflict('Exact content approval or source currency requires renewed review.')
    return {'document_id':row.id,'revision_id':rev.id,'revision_digest':rev.digest,'learner_id':learner_id,'purpose':purpose,'kind':row.kind,'period':snap.content['period'],'content':rev.content,'recipient_relationship_ids':rev.configuration['recipient_relationship_ids'],'approval':approval,'snapshot_digest':snap.digest,'disclosure_authorized':False}

def confirmed_periods(db,actor,school_id,learner_id,relationship_id,purpose):
    from .ports import SentPeriod
    proposal=recipient(db,actor,school_id,learner_id,relationship_id)
    if proposal['state']!='eligible_proposal':raise DomainError('recipient_unresolved','Choose a current eligible guardian relationship before resolving sent periods.',409)
    port=db.info.get('document_dispatch_history_port')
    if port is None:return None
    with a.owner_reader(db) as reader:values=[SentPeriod.model_validate(v) for v in port.confirmed_periods(reader,actor,school_id,learner_id,str(relationship_id),purpose)]
    if any(str(v.school_id)!=school_id or str(v.learner_id)!=learner_id or str(v.recipient_relationship_id)!=str(relationship_id) or v.purpose!=purpose or v.ends_on<v.starts_on for v in values):raise DomainError('dispatch_history_scope','Confirmed dispatch history returned an invalid recipient, purpose or interval binding.',503)
    return values
@read_contract
def resolve_period(db,actor,school_id,command):
    learner=str(command.learner_id);access(db,actor,school_id,learner,'documents.write');today=school_today(db.get(School,school_id));start,end=command.starts_on,command.ends_on
    history=None
    if command.recipient_relationship_id:history=confirmed_periods(db,actor,school_id,learner,command.recipient_relationship_id,command.purpose)
    if command.shortcut=='last_14_days':start,end=today-timedelta(days=13),today
    elif command.shortcut=='previous_month':
        end=today.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif command.shortcut=='since_last_sent':
        if not command.recipient_relationship_id or not history:return {'state':'unresolved','reason':'confirmed_sent_period_required','period':None,'dispatch_history':'unavailable' if history is None else 'no_confirmed_sent_period','choose_dates_required':True}
        start=max(v.ends_on for v in history)+timedelta(days=1);end=today
        if start>end:return {'state':'unresolved','reason':'last_confirmed_period_has_no_following_dates','period':None,'choose_dates_required':True}
    astart,aend,tz=a.period(db,school_id,start,end)
    overlap=[v.model_dump(mode='json') for v in history or [] if v.starts_on<=end and start<=v.ends_on]
    return a.encode({'state':'resolved','period':{'starts_on':start,'ends_on':end,'timezone':tz,'starts_at':astart,'ends_at_exclusive':aend},'overlaps':overlap,'dispatch_history':'unavailable' if history is None else 'confirmed_records_only','holes_and_corrections':'human_review_required'})

def schedule_settings(db,actor,school_id,settings):
    learner=str(settings.learner_id);owner=Actor(str(settings.owner_id))
    if settings.timezone is not None and settings.timezone!=db.get(School,school_id).timezone:raise DomainError('schedule_timezone','Draft schedules use the reviewed current school timezone.',422)
    access(db,owner,school_id,learner,'documents.write')
    for identity in settings.recipient_relationship_ids:
        if recipient(db,actor,school_id,learner,identity)['state']!='eligible_proposal':raise DomainError('recipient_unresolved','A draft plan requires current proposed guardian relationships.',409)
    if settings.generation_mode=='local_ai':
        from .generation import configured_generation
        configured_generation(db,owner,school_id,learner,settings.policy_id,settings.release_id,db.info.get('documents_runtime'))
    a.period(db,school_id,school_today(db.get(School,school_id)),school_today(db.get(School,school_id)))
@mutation('documents.schedule','schedule')
def create_schedule(db,actor,school_id,command):
    schedule_settings(db,actor,school_id,command.settings);settings=command.settings.model_dump(mode='json');settings['timezone']=db.get(School,school_id).timezone
    row=m.EmailDraftSchedule(school_id=school_id,learner_id=str(command.settings.learner_id),owner_id=str(command.settings.owner_id),state='inactive',next_run_at=command.settings.first_run_at);db.add(row);db.flush()
    db.add(m.ScheduleRevision(school_id=school_id,schedule_id=row.id,number=1,settings=settings,digest=a.digest(settings),author_id=actor.user_id,reason='Optional plan created inactive; explicit activation required'));event(db,actor,row,'documents.schedule.created');return row
@mutation('documents.schedule','schedule')
def change_schedule(db,actor,school_id,identity,command):
    row=get(db,m.EmailDraftSchedule,school_id,identity,command.expected_version)
    if row.state=='ended' or row.learner_id!=str(command.settings.learner_id):raise conflict()
    schedule_settings(db,actor,school_id,command.settings)
    row.owner_id=str(command.settings.owner_id);row.current_revision+=1;row.version+=1;row.state='inactive';row.pause_reason=None;row.next_run_at=command.settings.first_run_at;settings=command.settings.model_dump(mode='json');settings['timezone']=db.get(School,school_id).timezone
    db.add(m.ScheduleRevision(school_id=school_id,schedule_id=row.id,number=row.current_revision,settings=settings,digest=a.digest(settings),author_id=actor.user_id,reason=command.reason));event(db,actor,row,'documents.schedule.changed');return row
@mutation('documents.schedule','schedule')
def transition_schedule(db,actor,school_id,identity,command):
    row=get(db,m.EmailDraftSchedule,school_id,identity,command.expected_version)
    if row.state=='ended':raise conflict('An ended draft schedule cannot be reactivated.')
    settings=s.ScheduleSettings.model_validate(current(db,row,m.ScheduleRevision,'schedule_id').settings)
    if command.action=='activate':schedule_settings(db,actor,school_id,settings);row.state='active';row.pause_reason=None
    elif command.action=='pause':row.state='paused';row.pause_reason='human_paused'
    else:row.state='ended';row.pause_reason='human_ended'
    row.version+=1;event(db,actor,row,'documents.schedule.'+command.action);return row

def next_run(instant,settings,tz):
    local=instant.astimezone(ZoneInfo(tz));anchor=settings.first_run_at.astimezone(ZoneInfo(tz))
    if settings.recurrence=='days':local+=timedelta(days=settings.recurrence_count)
    else:
        idx=local.year*12+local.month-1+settings.recurrence_count;year,month=divmod(idx,12);month+=1
        local=local.replace(year=year,month=month,day=min(anchor.day,calendar.monthrange(year,month)[1]))
    local=local.replace(hour=anchor.hour,minute=anchor.minute,second=anchor.second,microsecond=anchor.microsecond)
    # Preserve a calendar wall time across DST; canonicalize nonexistent local times.
    return local.astimezone(timezone.utc)
def scheduled_period(instant,settings,tz):
    end=instant.astimezone(ZoneInfo(tz)).date()-timedelta(days=1)
    if settings.period_rule=='previous_month':end=end.replace(day=1)-timedelta(days=1) if end.month==instant.astimezone(ZoneInfo(tz)).month else end;start=end.replace(day=1)
    else:start=end-timedelta(days=settings.period_days-1)
    return start,end
@mutation('documents.schedule.run','schedule')
def run_schedule(db,actor,school_id,identity,command):
    row=get(db,m.EmailDraftSchedule,school_id,identity,command.expected_version)
    if row.state!='active':raise conflict('Only an explicitly active draft plan can run.')
    rev=current(db,row,m.ScheduleRevision,'schedule_id');settings=s.ScheduleSettings.model_validate(rev.settings);now=utcnow();tz=settings.timezone or db.get(School,school_id).timezone
    if tz!=db.get(School,school_id).timezone:
        row.state='paused';row.pause_reason='school_timezone_changed';row.version+=1;event(db,actor,row,'documents.schedule.timezone_changed');return row
    try:access(db,Actor(row.owner_id),school_id,row.learner_id,'documents.write')
    except DomainError:
        row.state='paused';row.pause_reason='owner_inactive_or_scope_revoked';row.version+=1;event(db,actor,row,'documents.schedule.owner_unavailable');return row
    if now<row.next_run_at:return row
    due=row.next_run_at;following=next_run(due,settings,tz)
    if due>settings.ends_at:row.state='ended';row.version+=1;event(db,actor,row,'documents.schedule.ended');return row
    start,end=scheduled_period(due,settings,tz);period_key=f'{start.isoformat()}:{end.isoformat()}'
    existing=db.scalar(select(m.DraftRun).where(m.DraftRun.school_id==school_id,m.DraftRun.schedule_revision_id==rev.id,m.DraftRun.learner_id==row.learner_id,m.DraftRun.period_key==period_key))
    if existing:row.next_run_at=following;row.version+=1;event(db,actor,row,'documents.schedule.deduplicated');return row
    missed=0;last_due=due
    while following<=now and following<=settings.ends_at:
        missed+=1;last_due=following;following=next_run(following,settings,tz)
    if missed:
        # A single durable reconciliation outcome replaces a batch of letters.
        last_start,last_end=scheduled_period(last_due,settings,tz)
        db.add(m.DraftRun(school_id=school_id,schedule_revision_id=rev.id,learner_id=row.learner_id,period_key=period_key,status='reconciliation_required',summary={'missed_execution_count':missed+1,'first_due_at':due.isoformat(),'last_due_at':last_due.isoformat(),'first_period':{'starts_on':str(start),'ends_on':str(end)},'last_period':{'starts_on':str(last_start),'ends_on':str(last_end)},'drafts_created':0},document_id=None));row.state='paused';row.pause_reason='missed_execution_reconciliation'
    else:
        data=s.DocumentCreate(request_key='scheduled',learner_id=row.learner_id,kind='guardian_email',purpose=settings.purpose,starts_on=start,ends_on=end,owner_id=row.owner_id,recipient_relationship_ids=settings.recipient_relationship_ids,language=settings.language,length=settings.length,topics=settings.topics,selection=settings.selection)
        # Resolving sources happens before adding a document, so a useful failure
        # can be recorded without accidentally persisting a partial aggregate.
        try:
            snapshot_data=collect(db,Actor(row.owner_id),school_id,data,now)
        except DomainError as exc:
            if exc.status_code not in {403,409,422,503}:raise
            db.add(m.DraftRun(school_id=school_id,schedule_revision_id=rev.id,learner_id=row.learner_id,period_key=period_key,status='failed',summary={'reason_code':exc.code,'manual_review_required':True},document_id=None));row.state='paused';row.pause_reason='draft_basis_unavailable'
        else:
            document=m.DocumentCase(school_id=school_id,learner_id=row.learner_id,owner_id=row.owner_id,kind='guardian_email',state='draft');db.add(document);db.flush()
            snap=m.EvidenceSnapshot(school_id=school_id,document_id=document.id,learner_id=row.learner_id,cutoff=now,content=snapshot_data,digest=a.digest(snapshot_data));db.add(snap);db.flush()
            make_revision(db,Actor(row.owner_id),document,data,'Optional schedule prepared a manual editable draft',existing_snapshot=snap);event(db,actor,document,'documents.scheduled_draft.created',schedule_revision_id=rev.id)
            run=m.DraftRun(school_id=school_id,schedule_revision_id=rev.id,learner_id=row.learner_id,period_key=period_key,status='draft_created',summary={'automatic_send':False,'ai_generation':'requested' if settings.generation_mode=='local_ai' else 'not_requested','human_review_required':True},document_id=document.id)
            db.add(run);db.flush()
            if settings.generation_mode=='local_ai':
                from .generation import configured_generation
                request_state='pending';reason_code=None
                try:binding=configured_generation(db,Actor(row.owner_id),school_id,row.learner_id,settings.policy_id,settings.release_id,db.info.get('documents_runtime'))
                except DomainError as exc:binding={};request_state='blocked';reason_code=exc.code
                document_revision=current(db,document)
                request=m.ScheduledGenerationRequest(school_id=school_id,run_id=run.id,document_id=document.id,revision_id=document_revision.id,snapshot_id=snap.id,owner_id=row.owner_id,policy_id=str(settings.policy_id),release_id=str(settings.release_id),configuration_binding=binding,logical_key='draft-run:'+run.id,state=request_state,reason_code=reason_code)
                db.add(request);db.flush();event(db,actor,request,'documents.scheduled_generation.requested',run_id=run.id,document_id=document.id,revision_id=document_revision.id,policy_id=request.policy_id,release_id=request.release_id)

    row.next_run_at=following
    if following>settings.ends_at and row.state=='active':row.state='ended';row.pause_reason='natural_schedule_end'
    row.version+=1;event(db,actor,row,'documents.schedule.ran',schedule_revision_id=rev.id);return row
@read_contract
def schedule_view(db,actor,school_id,identity):
    row=get(db,m.EmailDraftSchedule,school_id,identity);access(db,actor,school_id,row.learner_id,'documents.schedule')
    rev=current(db,row,m.ScheduleRevision,'schedule_id');settings=s.ScheduleSettings.model_validate(rev.settings);start,end=scheduled_period(row.next_run_at,settings,settings.timezone or db.get(School,school_id).timezone)
    owner_state='active'
    try:access(db,Actor(row.owner_id),school_id,row.learner_id,'documents.write')
    except DomainError:owner_state='inactive_or_scope_revoked'
    runs=list(db.scalars(select(m.DraftRun).join(m.ScheduleRevision,m.ScheduleRevision.id==m.DraftRun.schedule_revision_id).where(m.DraftRun.school_id==school_id,m.ScheduleRevision.schedule_id==row.id).order_by(m.DraftRun.created_at,m.DraftRun.id)))
    return {**row_json(row),'effective_state':'paused' if row.state=='active' and (owner_state!='active' or (settings.timezone and settings.timezone!=db.get(School,school_id).timezone)) else row.state,'owner_state':owner_state,'settings':rev.settings,'revision_id':rev.id,'next_period':{'starts_on':str(start),'ends_on':str(end)},'runs':[row_json(v)|{'generation_requests':[row_json(q) for q in db.scalars(select(m.ScheduledGenerationRequest).where(m.ScheduledGenerationRequest.school_id==school_id,m.ScheduledGenerationRequest.run_id==v.id))]} for v in runs],'automatic_send':False,'generation_mode':'editable_manual_draft_ai_optional'}
def view(db,actor,school_id,kind,identity):return {'document':document_view,'template':template_view,'schedule':schedule_view}[kind](db,actor,school_id,identity)

@read_contract
def workspace(db,actor,school_id,learner_id,offset=0,limit=50):
    """Native consumer list, authorized before pagination; no global dossier search."""
    access(db,actor,school_id,learner_id)
    rows=list(db.scalars(select(m.DocumentCase).where(m.DocumentCase.school_id==school_id,m.DocumentCase.learner_id==learner_id).order_by(m.DocumentCase.created_at.desc(),m.DocumentCase.id)))
    documents=[document_view(db,actor,school_id,r.id) for r in rows[offset:offset+limit]]
    schedules=[]
    try:
        access(db,actor,school_id,learner_id,'documents.schedule')
        schedules=[schedule_view(db,actor,school_id,r.id) for r in db.scalars(select(m.EmailDraftSchedule).where(m.EmailDraftSchedule.school_id==school_id,m.EmailDraftSchedule.learner_id==learner_id).order_by(m.EmailDraftSchedule.created_at.desc()).limit(limit))]
    except DomainError as exc:
        if exc.status_code!=403:raise
    templates=[]
    for r in db.scalars(select(m.Template).where(m.Template.school_id==school_id,m.Template.state=='active').order_by(m.Template.created_at.desc()).limit(limit)):
        try:templates.append(template_view(db,actor,school_id,r.id))
        except DomainError as exc:
            if exc.status_code not in {403,409}:raise
    return {'documents':{'items':documents,'total':len(rows)},'schedules':schedules,'templates':templates,'dispatch_history':'unavailable' if db.info.get('document_dispatch_history_port') is None else 'connected_confirmed_records_only'}
@read_contract
def contribution_workspace(db,actor,school_id,identity):
    row=get(db,m.DocumentCase,school_id,identity);access(db,actor,school_id,row.learner_id,'documents.contribute');rev=current(db,row)
    assigned=list(db.scalars(select(m.ContributionAssignment).where(m.ContributionAssignment.school_id==school_id,m.ContributionAssignment.revision_id==rev.id,m.ContributionAssignment.contributor_id==actor.user_id)))
    if not assigned:raise access_denied()
    keys={v.section_key for v in assigned};snap,status=snapshot_status(db,actor,row,rev,'documents.contribute')
    sections=[v for v in rev.content['sections'] if v['key'] in keys];sources={k for v in sections for k in v['source_keys']}
    contributions=[row_json(v) for v in db.scalars(select(m.Contribution).where(m.Contribution.school_id==school_id,m.Contribution.revision_id==rev.id,m.Contribution.section_key.in_(keys)))]
    return {'id':row.id,'learner_id':row.learner_id,'version':row.version,'revision_id':rev.id,'content_digest':rev.digest,'assigned_sections':sections,'sources':[v for v in snap.content['entries'] if v['key'] in sources],'source_status':status,'contributions':contributions,'whole_document_access':'requires_documents.read'}
