from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from spesped.auth import Actor, get_actor
from spesped.db import get_db
from . import schemas as s, service as svc

router=APIRouter(prefix='/api/v1/schools/{school_id}/safeguarding',tags=['safeguarding'])


def safeguarding_db(request:Request,db:Session=Depends(get_db)):
    db.info['safeguarding_rule_context']=getattr(request.app.state,'safeguarding_rule_context',None)
    return db


@router.get('/cases')
def cases(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),learner_id:UUID|None=None,kind:s.Kind|None=None,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.list_cases(db,actor,str(school_id),offset,limit,learner_id,kind)


@router.get('/submissions')
def submissions(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.list_personal(db,actor,str(school_id),offset,limit)


@router.get('/submissions/{case_id}')
def submission(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.personal_projection(db,actor,str(school_id),case_id)


@router.post('/submissions/{case_id}/personal-actions',status_code=201)
def personal_action(school_id:UUID,case_id:UUID,command:s.ActualAction,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_action(db,actor,str(school_id),case_id,command,personal=True)


@router.post('/submissions/{case_id}/personal-contacts',status_code=201)
def personal_contact(school_id:UUID,case_id:UUID,command:s.Contact,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_contact(db,actor,str(school_id),case_id,command,personal=True)


@router.get('/contact-routes')
def routes(school_id:UUID,purpose:s.Kind,about:s.About='pupil',actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.contact_routes(db,actor,str(school_id),purpose,about)


@router.get('/route-configurations')
def route_configurations(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.route_configurations(db,actor,str(school_id),offset,limit)


@router.post('/route-configurations',status_code=201)
def create_route(school_id:UUID,command:s.RouteCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_route(db,actor,str(school_id),command)


@router.post('/route-configurations/{route_id}/review')
def review_route(school_id:UUID,route_id:UUID,command:s.RouteReview,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.review_route(db,actor,str(school_id),route_id,command)


@router.get('/learners/{learner_id}/repeated-physical-events')
def repeated(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.repeated_events(db,actor,str(school_id),learner_id,offset,limit)


@router.post('/environment-cases',status_code=201)
def create_environment(school_id:UUID,command:s.EnvironmentCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_environment(db,actor,str(school_id),command)


@router.post('/concern-reports',status_code=201)
def create_concern(school_id:UUID,command:s.ConcernCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_concern(db,actor,str(school_id),command)


@router.post('/physical-interventions',status_code=201)
def create_physical(school_id:UUID,command:s.PhysicalCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_physical(db,actor,str(school_id),command)


@router.get('/cases/{case_id}')
def detail(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.detail(db,actor,str(school_id),case_id)


@router.get('/cases/{case_id}/export')
def export(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.detail(db,actor,str(school_id),case_id,export=True)


@router.get('/cases/{case_id}/history')
def history(school_id:UUID,case_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.revision_history(db,actor,str(school_id),case_id,offset,limit)


@router.get('/cases/{case_id}/contact-routes')
def case_routes(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.contact_routes(db,actor,str(school_id),None,None,case_id)


@router.post('/cases/{case_id}/accounts',status_code=201)
def account(school_id:UUID,case_id:UUID,command:s.AddAccount,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.add_account(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/pupil-views',status_code=201)
def pupil_view(school_id:UUID,case_id:UUID,command:s.AddPupilView,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.add_pupil_view(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/action-plans',status_code=201)
def plan(school_id:UUID,case_id:UUID,command:s.PlanCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_plan(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/performed-actions',status_code=201)
def action(school_id:UUID,case_id:UUID,command:s.ActualAction,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_action(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/drafts',status_code=201)
def draft(school_id:UUID,case_id:UUID,command:s.DraftCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_draft(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/drafts/{draft_id}/review')
def draft_review(school_id:UUID,case_id:UUID,draft_id:UUID,command:s.DraftReview,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.review_draft(db,actor,str(school_id),case_id,draft_id,command)


@router.post('/cases/{case_id}/actual-contacts',status_code=201)
def contact(school_id:UUID,case_id:UUID,command:s.Contact,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_contact(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/actual-contacts/{contact_id}/reconcile')
def reconcile(school_id:UUID,case_id:UUID,contact_id:UUID,command:s.ReconcileContact,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.reconcile_contact(db,actor,str(school_id),case_id,contact_id,command)


@router.post('/cases/{case_id}/followups',status_code=201)
def followup(school_id:UUID,case_id:UUID,command:s.FollowupCreate,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.create_followup(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/followups/{followup_id}/completion')
def followup_complete(school_id:UUID,case_id:UUID,followup_id:UUID,command:s.FollowupComplete,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.complete_followup(db,actor,str(school_id),case_id,followup_id,command)


@router.post('/cases/{case_id}/assignment')
def assignment(school_id:UUID,case_id:UUID,command:s.Assign,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.assign_owner(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/review')
def review(school_id:UUID,case_id:UUID,command:s.Review,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.review_case(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/corrections/environment')
def correct_environment(school_id:UUID,case_id:UUID,command:s.EnvironmentCorrection,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.correct_record(db,actor,str(school_id),case_id,command,'environment')


@router.post('/cases/{case_id}/corrections/concern')
def correct_concern(school_id:UUID,case_id:UUID,command:s.ConcernCorrection,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.correct_record(db,actor,str(school_id),case_id,command,'concern')


@router.post('/cases/{case_id}/corrections/physical')
def correct_physical(school_id:UUID,case_id:UUID,command:s.PhysicalCorrection,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.correct_record(db,actor,str(school_id),case_id,command,'physical')


@router.get('/contributions')
def contributions(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.list_contributions(db,actor,str(school_id),offset,limit)


@router.get('/contributions/{case_id}')
def contribution(school_id:UUID,case_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.contribution_projection(db,actor,str(school_id),case_id)


@router.post('/contributions/{case_id}/accounts',status_code=201)
def contribute_account(school_id:UUID,case_id:UUID,command:s.AddAccount,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.add_account(db,actor,str(school_id),case_id,command,participant=True)


@router.post('/contributions/{case_id}/pupil-views',status_code=201)
def contribute_pupil_view(school_id:UUID,case_id:UUID,command:s.AddPupilView,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.add_pupil_view(db,actor,str(school_id),case_id,command,participant=True)


@router.post('/submissions/{case_id}/pupil-views',status_code=201)
def personal_pupil_view(school_id:UUID,case_id:UUID,command:s.AddPupilView,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.add_pupil_view(db,actor,str(school_id),case_id,command,personal=True)


@router.post('/contributions/{case_id}/performed-actions',status_code=201)
def contribute_action(school_id:UUID,case_id:UUID,command:s.ActualAction,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_action(db,actor,str(school_id),case_id,command,participant=True)


@router.post('/contributions/{case_id}/actual-contacts',status_code=201)
def contribute_contact(school_id:UUID,case_id:UUID,command:s.Contact,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.record_contact(db,actor,str(school_id),case_id,command,participant=True)


@router.post('/contributions/{case_id}/followups/{followup_id}/completion')
def contribute_followup_complete(school_id:UUID,case_id:UUID,followup_id:UUID,command:s.FollowupComplete,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.complete_followup(db,actor,str(school_id),case_id,followup_id,command,participant=True)


@router.post('/cases/{case_id}/protection')
def protection(school_id:UUID,case_id:UUID,command:s.ProtectionChange,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.update_protection(db,actor,str(school_id),case_id,command)


@router.post('/cases/{case_id}/followups/{followup_id}/assignment')
def followup_assignment(school_id:UUID,case_id:UUID,followup_id:UUID,command:s.Assign,actor:Actor=Depends(get_actor),db:Session=Depends(safeguarding_db)):
    return svc.reassign_followup(db,actor,str(school_id),case_id,followup_id,command)
