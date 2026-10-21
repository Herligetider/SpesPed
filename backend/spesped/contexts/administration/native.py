"""Read native owner contracts on the caller's transaction, with fresh identities.

External HR documents are human checked references, never fetched or represented
as live source-system verification. Their withdrawal requires an attributed native
revocation/revision; effective bounds and verifier authority are rechecked here.
"""
from contextlib import contextmanager
from datetime import datetime,time,timedelta,date
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor,require_school_access,require_learner_access,require_authority,school_today
from spesped.errors import DomainError
from spesped.domain import canonical_content_digest,SummaryPeriod
from spesped.contexts.identity.models import School,StaffAssignment
from spesped.contexts.curriculum.adapters import canonical
import json
from . import models as m

def encode(value):return json.loads(canonical(value))
def digest(value):return canonical_content_digest(encode(value))
def conflict(message='Recheck the exact current professional record and source.'):
    return DomainError('professional_source_changed',message,409)
@contextmanager
def reader(db):
    excluded=(m.ProfessionalCommand,m.ProfessionalEvent)
    if any(type(r).__module__.startswith('spesped.contexts.') and not isinstance(r,excluded) for r in db.new|db.dirty|db.deleted):
        raise DomainError('dependency_pending','Flush or roll back pending source or authority changes before resolving professional authority.',409)
    with db.no_autoflush:
        fresh=Session(bind=db.connection(),join_transaction_mode='rollback_only',autoflush=False,expire_on_commit=False)
        fresh.info.update(db.info)
        try:yield fresh
        finally:fresh.close()

def bounds(db,school_id,request):
    if hasattr(request,'occurred_at'):return request.occurred_at,request.ended_at
    try:
        period=SummaryPeriod(request.starts_on,request.ends_on,db.get(School,school_id).timezone).to_utc()
    except ValueError:raise conflict('The selected assessment dates must contain a real interval in the school timezone.') from None
    return period.start,period.end

def person(db,school_id,person_id,learner_id=None,start=None,end=None):
    person_actor=Actor(str(person_id));require_school_access(db,person_actor,school_id)
    if learner_id:
        # Employment/responsibility does not grant content access. An explicit
        # current pupil assignment is required independently, including its full
        # historical service interval when qualification is requested for actuals.
        today=school_today(db.get(School,school_id))
        rows=list(db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==school_id,StaffAssignment.user_id==str(person_id),StaffAssignment.learner_id==str(learner_id),StaffAssignment.state=='active',StaffAssignment.valid_from<=today)))
        zone=ZoneInfo(db.get(School,school_id).timezone)
        rows=[r for r in rows if (r.valid_until is None or r.valid_until>=today) and r.actions]
        if start is not None:
            rows=[r for r in rows if datetime.combine(r.valid_from,time.min,zone)<=start and (r.valid_until is None or end<=datetime.combine(r.valid_until+timedelta(days=1),time.min,zone))]
        if not rows:raise conflict('The person needs a current dated assignment covering the whole service period.')
    return person_actor

def teaching_target(db,actor,request):
    from spesped.contexts.entitlements.service import resolve_provision
    from spesped.contexts.entitlements.projections import provision_binding_is_current
    school_id=str(request.school_id);learner_id=str(request.learner_id)
    require_learner_access(db,actor,school_id,learner_id,'teaching.read')
    _,_,revision,provision=resolve_provision(db,actor,school_id,learner_id,str(request.decision_id),str(request.decision_revision_id),str(request.provision_id),at=request.occurred_at,historical=True)
    fields=('id','decision_revision_id','category','organization','competence','effective_from','effective_until','source')
    from fastapi.encoders import jsonable_encoder
    actual_digest=canonical_content_digest(jsonable_encoder({f:getattr(provision,f) for f in fields}))
    binding=request.model_dump(mode='json')
    if actual_digest!=request.provision_digest or not provision_binding_is_current(db,school_id,learner_id,binding,request.occurred_at,historical=True) or not (revision.effective_from<=request.occurred_at<request.ended_at<=revision.effective_until and provision.effective_from<=request.occurred_at<request.ended_at<=provision.effective_until):raise conflict()
    return {'subject':provision.subject,'target_digest':actual_digest}

def assessment_target(db,actor,request):
    from spesped.contexts.assessment import service as svc,models as am
    from spesped.contexts.assessment.adapters import scheme
    school_id=str(request.school_id);learner_id=str(request.learner_id)
    require_learner_access(db,actor,school_id,learner_id,'assessment.read')
    if request.starts_on>request.ends_on:raise conflict('An ordered assessment period is required.')
    if request.purpose=='instrument_administration':
        _,rev,_=svc.current_instrument(db,actor,school_id,str(request.exact_revision_id),on_date=request.starts_on,use=True)
        content=rev.content
        if request.ends_on>date.fromisoformat(content['license_until']):raise conflict()
        if request.subject is not None or request.scheme_revision_id is not None:raise conflict()
        if rev.digest!=request.exact_digest:raise conflict()
        return {'subject':None,'target_digest':rev.digest}
    if request.purpose=='result_review':
        rev=svc.get(db,am.ResultRevision,school_id,request.exact_revision_id)
        row=svc.get(db,am.Administration,school_id,rev.administration_id)
        if row.learner_id!=learner_id or row.current_result!=rev.number or rev.digest!=request.exact_digest or svc.local_day(db,school_id,rev.occurred_at)!=request.starts_on or request.starts_on!=request.ends_on or request.subject is not None or request.scheme_revision_id is not None:raise conflict()
        svc.administration_sources(db,actor,row,use=True)
        from spesped.contexts.assessment.schemas import RecordResult
        exact=RecordResult(request_key='verification',expected_version=1,occurred_at=rev.occurred_at,raw=rev.raw,conditions=rev.conditions,correction_reason=rev.correction_reason).model_dump(mode='json',exclude={'request_key','expected_version'})
        if svc.a.digest(exact)!=rev.digest:raise conflict()
        return {'subject':None,'target_digest':rev.digest}
    rev=svc.get(db,am.StatementRevision,school_id,request.exact_revision_id)
    row=svc.get(db,am.Statement,school_id,rev.statement_id)
    if row.learner_id!=learner_id or row.current_revision!=rev.number or rev.digest!=request.exact_digest or svc.a.digest(rev.content)!=rev.digest or row.starts_on!=request.starts_on or row.ends_on!=request.ends_on or row.subject!=request.subject or row.scheme_revision_id!=str(request.scheme_revision_id):raise conflict()
    sc,sources,unresolved=svc.statement_basis(db,actor,row,rev.content)
    if sc is None or svc.a.digest(sc)!=svc.a.digest(rev.content['scheme_binding']) or svc.a.digest(sources)!=svc.a.digest(rev.content['source_snapshot']):raise conflict()
    return {'subject':row.subject,'target_digest':rev.digest,'scheme_digest':sc['basis_digest']}

def policy_target(db,actor,school_id,content):
    from spesped.contexts.curriculum.projections import reviewed_assessment_scheme
    zone=ZoneInfo(db.get(School,school_id).timezone)
    start=content.effective_from.astimezone(zone).date();end=(content.effective_until-timedelta(microseconds=1)).astimezone(zone).date()
    require_learner_access(db,actor,school_id,str(content.learner_id),'assessment.read')
    sc=reviewed_assessment_scheme(db,actor,school_id,str(content.scheme_revision_id),starts_on=start,ends_on=end)
    if len([r for r in sc['assessment_rules'] if r['subject']==content.subject])!=1:raise conflict('The reviewed scheme must identify one exact subject rule.')
    return sc['basis_digest']
