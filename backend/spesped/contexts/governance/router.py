from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from spesped.auth import Actor, get_actor, require_school_access
from spesped.db import get_db
from . import models as m, schemas as s, service as svc

router = APIRouter(prefix='/api/v1/schools/{school_id}/governance', tags=['governance'])

def governance_db(request: Request, db: Session = Depends(get_db)):
    db.info['governance_case_scope_resolver'] = getattr(request.app.state, 'governance_case_scope_resolver', None)
    return db



def view(row):
    return {column.name:getattr(row,column.name) for column in row.__table__.columns}


def envelope(db, model, school_id, offset, limit):
    query = select(model).where(model.school_id == school_id)
    items = db.scalars(query.order_by(model.id).offset(offset).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(model).where(model.school_id == school_id))
    return {'items':[view(i) for i in items], 'total':total}


@router.post('/candidate-imports/bundled')
def import_candidates(school_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(governance_db)):
    return svc.import_candidates(db, actor, str(school_id))


@router.get('/candidates')
def candidates(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    svc.authority(db,actor,str(school_id),'rules.manage')
    return envelope(db,m.LegalImportCandidate,str(school_id),offset,limit)


@router.post('/requirements',status_code=201)
def create_requirement(school_id: UUID, command: s.RequirementCreate, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.create_requirement(db,actor,str(school_id),command))


@router.get('/requirements')
def requirements(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id))
    return envelope(db,m.RequirementDefinition,str(school_id),offset,limit)


@router.get('/requirements/{requirement_id}/versions')
def requirement_versions(school_id: UUID, requirement_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id)); svc.get_scoped(db,m.RequirementDefinition,str(school_id),requirement_id)
    rows = list(db.scalars(select(m.RequirementVersion).where(m.RequirementVersion.school_id==str(school_id),m.RequirementVersion.requirement_id==str(requirement_id)).order_by(m.RequirementVersion.revision_number)))
    return {'items':[view(r) for r in rows[offset:offset+limit]],'total':len(rows)}


@router.post('/requirements/{requirement_id}/versions',status_code=201)
def revise_requirement(school_id: UUID, requirement_id: UUID, command: s.RequirementRevision, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.revise_requirement(db,actor,str(school_id),requirement_id,command))


@router.post('/requirement-versions/{version_id}/review')
def review_requirement(school_id: UUID, version_id: UUID, command: s.Review, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.review_requirement(db,actor,str(school_id),version_id,command))


@router.post('/profiles',status_code=201)
def create_profile(school_id: UUID, command: s.ProfileCreate, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.create_profile(db,actor,str(school_id),command))


@router.get('/profiles')
def profiles(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    svc.authority(db,actor,str(school_id),'rules.manage')
    return envelope(db,m.SchoolRuleProfile,str(school_id),offset,limit)


@router.get('/profiles/{profile_id}/impact')
def profile_impact(school_id: UUID, profile_id: UUID, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return svc.profile_impact(db,actor,str(school_id),profile_id)


@router.post('/profiles/{profile_id}/activate')
def activate_profile(school_id: UUID, profile_id: UUID, command: s.ProfileActivation, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.activate_profile(db,actor,str(school_id),profile_id,command))


@router.post('/triggers',status_code=201)
def trigger(school_id: UUID, command: s.Trigger, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    rows = svc.trigger_obligations(db,actor,str(school_id),command)
    return {'items':[task_view(db,r) for r in rows], 'total':len(rows)}


def task_view(db, task, detailed=True):
    rule = db.get(m.RequirementVersion,task.requirement_version_id)
    definition = db.get(m.RequirementDefinition,rule.requirement_id)
    result = {'id':task.id,'version':task.version,'requirement_version_id':rule.id,'requirement_title':definition.title,
        'source_type':definition.source_type,'source_reference':definition.source_reference,
        'deadline_kind':task.deadline_kind,'deadline_date':task.deadline_date,'deadline_at':task.deadline_at,
        'deadline_reasons':task.deadline_reasons,'legal_timing':rule.deadline_rule,
        'internal_planned_date':task.internal_planned_date,'owner_id':task.owner_id,'status':svc.task_status(db,task)}
    if detailed: result.update(view(task)); result['required_action']=rule.required_action; result['required_document_types']=rule.required_document_types
    return result


@router.get('/obligations')
def obligations(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id))
    try: svc.authority(db,actor,str(school_id),'tasks.manage'); manager=True
    except svc.DomainError: manager=False
    query = select(m.ObligationInstance).where(m.ObligationInstance.school_id==str(school_id))
    if not manager: query=query.where(m.ObligationInstance.owner_id==actor.user_id)
    # Authorization happens before pagination. Even administrative task authority
    # does not expand learner/case content access.
    rows = list(db.scalars(query.order_by(m.ObligationInstance.id)))
    visible = [r for r in rows if r.owner_id==actor.user_id or svc.can_scope(db,actor,r)]
    return {'items':[task_view(db,r,detailed=svc.can_scope(db,actor,r)) for r in visible[offset:offset+limit]],'total':len(visible)}


@router.get('/obligations/{obligation_id}')
def obligation(school_id: UUID, obligation_id: UUID, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    task=svc.get_scoped(db,m.ObligationInstance,str(school_id),obligation_id); svc.task_access(db,actor,task)
    result = task_view(db,task)
    for key, model in (('actions',m.ObligationAction),('assignments',m.ObligationAssignment),('applicability_history',m.ApplicabilityDecision),('reviews',m.ObligationReview)):
        result[key] = [view(a) for a in db.scalars(select(model).where(model.school_id==str(school_id),model.obligation_id==task.id).order_by(model.recorded_at,model.id))]
    return result


@router.post('/obligations/{obligation_id}/assignment')
def assign(school_id: UUID, obligation_id: UUID, command: s.Assignment, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return task_view(db,svc.assign_task(db,actor,str(school_id),obligation_id,command))


@router.post('/obligations/{obligation_id}/inputs')
def resolve_inputs(school_id: UUID, obligation_id: UUID, command: s.ResolveInputs, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return task_view(db,svc.resolve_task_inputs(db,actor,str(school_id),obligation_id,command))


@router.post('/obligations/{obligation_id}/actions',status_code=201)
def submit_action(school_id: UUID, obligation_id: UUID, command: s.ActionSubmission, request: Request, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    action,task=svc.submit_action(db,actor,str(school_id),obligation_id,command,getattr(request.app.state,'governance_evidence_validator',None))
    return {'action':view(action),'obligation':task_view(db,task)}


@router.post('/obligations/{obligation_id}/review')
def review_task(school_id: UUID, obligation_id: UUID, command: s.TaskReview, request: Request, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return task_view(db,svc.review_task(db,actor,str(school_id),obligation_id,command,getattr(request.app.state,'governance_evidence_validator',None)))


@router.post('/deviations',status_code=201)
def create_deviation(school_id: UUID, command: s.DeviationCreate, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.create_deviation(db,actor,str(school_id),command))


@router.get('/deviations')
def deviations(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id))
    try: svc.authority(db,actor,str(school_id),'tasks.manage'); manager=True
    except svc.DomainError: manager=False
    query=select(m.ComplianceDeviation).where(m.ComplianceDeviation.school_id==str(school_id))
    if not manager: query=query.where(m.ComplianceDeviation.owner_id==actor.user_id)
    rows=list(db.scalars(query.order_by(m.ComplianceDeviation.id)))
    visible=[r for r in rows if svc.can_scope(db,actor,svc.get_scoped(db,m.ObligationInstance,str(school_id),r.obligation_id))]
    return {'items':[view(r) for r in visible[offset:offset+limit]],'total':len(visible)}


@router.get('/deviations/{deviation_id}')
def deviation(school_id: UUID, deviation_id: UUID, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    row=svc.get_scoped(db,m.ComplianceDeviation,str(school_id),deviation_id)
    svc.deviation_access(db,actor,row)
    return {**view(row),'followups':[view(r) for r in db.scalars(select(m.DeviationFollowup).where(m.DeviationFollowup.school_id==str(school_id),m.DeviationFollowup.deviation_id==row.id))]}


@router.post('/deviations/{deviation_id}/followups')
def follow_deviation(school_id: UUID, deviation_id: UUID, command: s.DeviationAction, request: Request, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.follow_deviation(db,actor,str(school_id),deviation_id,command,getattr(request.app.state,'governance_evidence_validator',None)))


@router.get('/overview')
def overview(school_id: UUID, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return svc.leadership_overview(db,actor,str(school_id))


@router.post('/workload-studies',status_code=201)
def create_study(school_id: UUID, command: s.StudyCreate, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.create_study(db,actor,str(school_id),command))


@router.get('/workload-studies')
def studies(school_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id))
    return envelope(db,m.WorkloadStudy,str(school_id),offset,limit)


@router.post('/workload-studies/{study_id}/participation')
def participate(school_id: UUID, study_id: UUID, command: s.StudyParticipation, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return svc.participate(db,actor,str(school_id),study_id,command)


@router.post('/workload-studies/{study_id}/measurements',status_code=201)
def measure(school_id: UUID, study_id: UUID, command: s.Measurement, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    row=svc.measure(db,actor,str(school_id),study_id,command)
    return view(row)


@router.get('/workload-studies/{study_id}/my-measurements')
def own_measurements(school_id: UUID, study_id: UUID, offset: int=Query(0,ge=0), limit: int=Query(50,ge=1,le=200), actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    require_school_access(db,actor,str(school_id)); svc.get_scoped(db,m.WorkloadStudy,str(school_id),study_id)
    participant=db.scalar(select(m.WorkloadParticipant).where(m.WorkloadParticipant.school_id==str(school_id),m.WorkloadParticipant.study_id==str(study_id),m.WorkloadParticipant.user_id==actor.user_id))
    rows=list(db.scalars(select(m.WorkloadMeasurement).where(m.WorkloadMeasurement.school_id==str(school_id),m.WorkloadMeasurement.participant_id==participant.id).order_by(m.WorkloadMeasurement.id))) if participant else []
    return {'items':[view(r) for r in rows[offset:offset+limit]],'total':len(rows)}


@router.get('/workload-studies/{study_id}/results')
def results(school_id: UUID, study_id: UUID, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return svc.study_results(db,actor,str(school_id),study_id)


@router.post('/requirement-versions/{version_id}/withdraw')
def withdraw_rule(school_id: UUID, version_id: UUID, command: s.Review, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.withdraw_rule(db,actor,str(school_id),version_id,command))


@router.post('/profiles/{profile_id}/revoke')
def revoke_profile(school_id: UUID, profile_id: UUID, command: s.Review, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.revoke_profile(db,actor,str(school_id),profile_id,command))


@router.post('/workload-studies/{study_id}/close')
def close_study(school_id: UUID, study_id: UUID, command: s.Review, actor: Actor=Depends(get_actor), db: Session=Depends(governance_db)):
    return view(svc.close_study(db,actor,str(school_id),study_id,command))


from . import report_periods


@router.get('/obligations/{obligation_id}/report-period-reviews')
def report_period_reviews(school_id: UUID, obligation_id: UUID, document_kind: str = Query(min_length=1, max_length=100), actor: Actor = Depends(get_actor), db: Session = Depends(governance_db)):
    return report_periods.report_period_history(db, actor, str(school_id), str(obligation_id), document_kind)


@router.post('/obligations/{obligation_id}/report-period-reviews')
def review_report_period(school_id: UUID, obligation_id: UUID, command: report_periods.ReportPeriodCommand, actor: Actor = Depends(get_actor), db: Session = Depends(governance_db)):
    return report_periods.review_report_period(db, actor, str(school_id), str(obligation_id), command)
