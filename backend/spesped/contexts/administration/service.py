"""Scoped human review, revision and revocation; no authority self escalation."""
from uuid import uuid4
from functools import wraps
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError
from pydantic import TypeAdapter
from spesped.auth import Actor,require_school_access,require_learner_access,require_authority,school_today
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError,access_denied
from spesped.contexts.identity.models import School
from . import models as m,schemas as s,native as n
CONTENT=TypeAdapter(s.Content)

def coordinates(content):
    if hasattr(content,'request'):
        r=content.request
        return str(r.learner_id),str(r.staff_id if hasattr(r,'staff_id') else r.person_id)
    return str(content.learner_id) if hasattr(content,'learner_id') else None,str(content.person_id) if hasattr(content,'person_id') else None

def action(content,verb):
    if content.kind=='qualification':return 'professional.evidence.'+verb
    if content.kind=='responsibility':return 'professional.responsibility.'+verb
    if content.kind=='assessment_policy':return 'professional.policy.'+verb
    purpose='teaching' if content.kind=='teaching_review' else content.request.purpose
    return 'professional.review.'+purpose if verb=='review' else 'professional.review.manage'

def authorize(db,actor,school_id,content,verb):
    learner_id,_=coordinates(content)
    require_authority(db,actor,school_id,action(content,verb),learner_id=learner_id)
    if learner_id:require_learner_access(db,actor,school_id,learner_id,'professional.read')

def get(db,school_id,identifier):
    row=db.scalar(select(m.ProfessionalRecord).where(m.ProfessionalRecord.school_id==school_id,m.ProfessionalRecord.id==str(identifier)).execution_options(populate_existing=True))
    if row is None:raise access_denied()
    return row

def revision(db,row):return db.scalar(select(m.ProfessionalRevision).where(m.ProfessionalRevision.school_id==row.school_id,m.ProfessionalRevision.record_id==row.id,m.ProfessionalRevision.number==row.current_revision))
def content_of(rev):
    if n.digest(rev.content)!=rev.digest:raise n.conflict()
    return CONTENT.validate_python(rev.content)
def check(db,rev):return db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.school_id==rev.school_id,m.ProfessionalCheck.revision_id==rev.id))

def current(db,row,*,eligible=True):
    rev=revision(db,row);content=content_of(rev);review=check(db,rev)
    if row.state!='reviewed' or review is None or review.digest!=rev.digest:raise n.conflict()
    if eligible and review.outcome!='eligible':raise n.conflict()
    authorize(db,Actor(review.reviewer_id),row.school_id,content,'review')
    if review.created_at>utcnow() or review.source_checked_on>school_today(db.get(School,row.school_id)):raise n.conflict()
    return rev,content,review

def referenced(db,school_id,ref,kind,*,eligible=True):
    row=get(db,school_id,ref.record_id);rev,content,review=current(db,row,eligible=eligible)
    if row.kind!=kind or rev.number!=ref.revision or rev.digest!=ref.digest:raise n.conflict()
    if kind in {'responsibility','assessment_policy'}:
        alternatives=db.scalars(select(m.ProfessionalRecord).where(m.ProfessionalRecord.school_id==school_id,m.ProfessionalRecord.kind==kind,m.ProfessionalRecord.learner_id==row.learner_id,m.ProfessionalRecord.person_id==row.person_id,m.ProfessionalRecord.state=='reviewed',m.ProfessionalRecord.id!=row.id)).all()
        for other in alternatives:
            other_rev=revision(db,other);other_content=content_of(other_rev)
            if other_content.subject==content.subject and (kind!='assessment_policy' or other_content.scheme_revision_id==content.scheme_revision_id) and other_content.effective_from<content.effective_until and content.effective_from<other_content.effective_until:
                raise n.conflict('Overlapping professional responsibility or subject determinations need explicit reconciliation.')
    return row,rev,content,review

def validate(db,actor,school_id,content,*,reviewing=False):
    learner_id,person_id=coordinates(content)
    if learner_id:require_learner_access(db,actor,school_id,learner_id,'professional.read')
    if person_id:n.person(db,school_id,person_id)
    if content.source.issued_on>school_today(db.get(School,school_id)):raise n.conflict('A source cannot have a future issue date.')
    if content.kind=='responsibility':
        n.person(db,school_id,person_id,learner_id,content.effective_from,content.effective_until)
    elif content.kind=='assessment_policy':n.policy_target(db,actor,school_id,content)
    elif content.kind in {'teaching_review','assessment_review'}:
        r=content.request
        if str(r.school_id)!=school_id:raise access_denied()
        target=n.teaching_target(db,actor,r) if content.kind=='teaching_review' else n.assessment_target(db,actor,r)
        start,end=n.bounds(db,school_id,r)
        if not content.effective_from<=start<end<=content.effective_until:raise n.conflict('The exact review must cover the whole requested interval.')
        n.person(db,school_id,person_id,learner_id,start,end)
        _,_,qual,_=referenced(db,school_id,content.qualification,'qualification')
        _,_,resp,_=referenced(db,school_id,content.responsibility,'responsibility')
        purpose='teaching' if content.kind=='teaching_review' else r.purpose
        if str(qual.person_id)!=person_id or purpose not in qual.purposes or str(resp.person_id)!=person_id or str(resp.learner_id)!=learner_id or resp.responsibility!='responsible_teaching':raise n.conflict()
        if target['subject'] is not None and resp.subject!=target['subject']:raise n.conflict()
        for basis in (qual,resp):
            if not basis.effective_from<=content.effective_from<content.effective_until<=basis.effective_until:raise n.conflict('The source records must cover the entire reviewed interval.')
        if content.kind=='assessment_review' and content.policy:
            _,_,policy,_=referenced(db,school_id,content.policy,'assessment_policy')
            if str(policy.learner_id)!=learner_id or policy.subject!=r.subject or str(policy.scheme_revision_id)!=str(r.scheme_revision_id) or not policy.effective_from<=content.effective_from<content.effective_until<=policy.effective_until:raise n.conflict()
            n.policy_target(db,actor,school_id,policy)
            if reviewing and ('unresolved' in (policy.completion,policy.exemption,policy.grade_policy)):raise n.conflict('Resolve subject completion, exemption and grading policy before approval.')
    return content

def view(db,actor,school_id,identifier,*,private=False):
    row=get(db,school_id,identifier);rev=revision(db,row);content=content_of(rev)
    learner_id,_=coordinates(content)
    if learner_id:require_learner_access(db,actor,school_id,learner_id,'professional.read')
    else:require_authority(db,actor,school_id,'professional.read')
    review=check(db,rev)
    value={'id':row.id,'kind':row.kind,'learner_id':row.learner_id,'person_id':row.person_id,'version':row.version,'state':row.state,'revision_id':rev.id,'revision':rev.number,'content_digest':rev.digest,'review':None,'source_verification':'human_reference_only'}
    if review:value['review']={'id':review.id,'reviewed_by':review.reviewer_id,'reviewed_at':review.created_at,'outcome':review.outcome,'source_checked_on':review.source_checked_on}
    try:
        _,_,current_review=current(db,row,eligible=False)
        validate(db,actor,school_id,content,reviewing=current_review.outcome=='eligible')
        if row.kind in {'responsibility','assessment_policy'}:referenced(db,school_id,s.Reference(record_id=row.id,revision=rev.number,digest=rev.digest),row.kind,eligible=False)
        value['eligibility']={'eligible':'reviewed_current','ineligible':'ineligible','unresolved':'unresolved'}[current_review.outcome]
    except DomainError as exc:
        value['eligibility']='unresolved'
        value['eligibility_reason']=exc.code
    value['effective_from']=content.effective_from;value['effective_until']=content.effective_until
    now=utcnow()
    value['effective_status']='future' if now<content.effective_from else 'elapsed' if now>=content.effective_until else 'current'
    if row.state=='revoked':value['eligibility']='revoked'
    elif content.kind not in {'teaching_review','assessment_review'} and value['effective_status']!='current' and value['eligibility']=='reviewed_current':value['eligibility']='unresolved'
    revocation=db.scalar(select(m.ProfessionalRevocation).where(m.ProfessionalRevocation.school_id==school_id,m.ProfessionalRevocation.record_id==row.id))
    if revocation:value['revocation']={'revoked_by':revocation.revoked_by,'revoked_at':revocation.created_at,'revision_id':revocation.revision_id}
    if private:
        authorize(db,actor,school_id,content,'read' if content.kind=='qualification' else 'manage')
        if revocation:value['revocation']['reason']=revocation.reason
        value['content']=rev.content
        if review:value['review']['reason']=review.reason
    return n.encode(value)

def write(db,actor,school_id,operation,command,identifier=None):
    if any(type(r).__module__.startswith('spesped.contexts.') and not isinstance(r,(m.ProfessionalCommand,m.ProfessionalEvent)) for r in db.new|db.dirty|db.deleted):raise DomainError('dependency_pending','Flush or roll back pending business changes before a professional command.',409)
    try:
        require_school_access(db,actor,school_id)
        db.scalar(select(School.id).where(School.id==school_id).with_for_update())
        row=get(db,school_id,identifier) if identifier else None
        old=content_of(revision(db,row)) if row else None
        content=command.content if hasattr(command,'content') else old
        if operation=='review':
            # A receipt authorizes no signing operation. Resolve its original
            # immutable revision even after the current record changes purpose.
            reviewed_revision=db.scalar(select(m.ProfessionalRevision).where(m.ProfessionalRevision.school_id==school_id,m.ProfessionalRevision.record_id==row.id,m.ProfessionalRevision.id==str(command.revision_id)))
            if reviewed_revision is None:raise access_denied()
            content=content_of(reviewed_revision)
            authorize(db,actor,school_id,content,'review')
        else:
            authorize(db,actor,school_id,content,'manage')
            if old:authorize(db,actor,school_id,old,'manage')
        fingerprint=n.digest({'operation':operation,'target':identifier,'command':command.model_dump(mode='json')})
        receipt=db.scalar(select(m.ProfessionalCommand).where(m.ProfessionalCommand.school_id==school_id,m.ProfessionalCommand.actor_id==actor.user_id,m.ProfessionalCommand.request_key==command.request_key))
        if receipt:
            if receipt.digest!=fingerprint:raise DomainError('idempotency_conflict','The request key identifies different professional content.',409)
            result=view(db,actor,school_id,receipt.target_id);db.commit();return result
        if row and row.version!=command.expected_version:raise n.conflict('Reload the current professional record version.')
        if operation in {'create','revise'}:
            validate(db,actor,school_id,content)
            learner_id,person_id=coordinates(content)
            if row:
                if row.kind!=content.kind or (row.learner_id,row.person_id)!=(learner_id,person_id):raise n.conflict('Record kind, learner and person cannot change; create a new record.')
                if row.state=='revoked':raise n.conflict('A revoked record cannot be revived.')
                row.current_revision+=1;row.version+=1;row.state='draft'
            else:
                row=m.ProfessionalRecord(school_id=school_id,kind=content.kind,learner_id=learner_id,person_id=person_id,state='draft');db.add(row);db.flush()
            data=content.model_dump(mode='json')
            db.add(m.ProfessionalRevision(school_id=school_id,record_id=row.id,number=row.current_revision,content=data,digest=n.digest(data),authored_by=actor.user_id))
        elif operation=='review':
            rev=revision(db,row)
            if row.state!='draft' or rev.id!=str(command.revision_id) or rev.digest!=command.content_digest or check(db,rev):raise n.conflict()
            if command.source_checked_on>school_today(db.get(School,school_id)) or command.source_checked_on<content.source.issued_on:raise n.conflict('Record an actual source verification date after issue.')
            validate(db,actor,school_id,content,reviewing=command.outcome=='eligible')
            db.add(m.ProfessionalCheck(school_id=school_id,revision_id=rev.id,digest=rev.digest,reviewer_id=actor.user_id,authority_action=action(content,'review'),reason=command.reason,source_checked_on=command.source_checked_on,outcome=command.outcome));row.state='reviewed';row.version+=1
        else:
            if row.state=='revoked':raise n.conflict()
            db.add(m.ProfessionalRevocation(school_id=school_id,record_id=row.id,revision_id=revision(db,row).id,revoked_by=actor.user_id,reason=command.reason))
            row.state='revoked';row.version+=1
        db.flush();now=utcnow();record_audit(db,actor,school_id,'professional.'+operation,row.__tablename__,row.id)
        # Only metadata crosses the outbox; private reference/reason stays owned.
        db.add(m.ProfessionalEvent(school_id=school_id,aggregate_id=row.id,aggregate_version=row.version,actor_id=actor.user_id,event_type='professional.'+operation,payload={'kind':row.kind,'revision':row.current_revision,'state':row.state},occurred_at=now,recorded_at=now,correlation_id=str(uuid4()),causation_id=command.request_key,schema_version=1))
        db.add(m.ProfessionalCommand(school_id=school_id,actor_id=actor.user_id,request_key=command.request_key,digest=fingerprint,target_id=row.id));db.flush()
        result=view(db,actor,school_id,row.id);db.commit();return result
    except (StaleDataError,DBAPIError) as exc:
        db.rollback()
        if isinstance(exc,StaleDataError) or getattr(getattr(exc,'orig',None),'sqlstate',None) in {'40001','40P01','55P03','23505'} or 'UNIQUE constraint failed' in str(exc):raise n.conflict('A concurrent command changed this record; retry the same key.') from None
        raise
    except Exception:db.rollback();raise
