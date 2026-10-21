"""Authenticated BC09 workflows; factual communication recording never sends."""
from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor,get_actor
from spesped.db import get_db
from . import models as m,schemas as s,service as svc
from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
router=APIRouter(prefix='/api/v1/schools/{school_id}/assessment',tags=['assessment'])
def assessment_db(request:Request,db:Session=Depends(get_db)):
    db.info['curriculum_source_port']=getattr(request.app.state,'curriculum_source_port',None) or EvidenceSourceReadPort(getattr(request.app.state,'evidence_storage',None))
    for name in ('assessment_authority_port','teaching_qualification_port'):
        db.info[name]=getattr(request.app.state,name,None)
    db.info['plans_runtime']=getattr(request.app.state,'ai_gateway',None)
    db.info['teaching_runtime']=getattr(request.app.state,'ai_gateway',None)
    return db
D=Depends(assessment_db);A=Depends(get_actor)

@router.post('/instruments',status_code=201)
def instrument_create(school_id:UUID,command:s.InstrumentCreate,db:Session=D,actor:Actor=A):return svc.create_instrument(db,actor,str(school_id),command)
@router.get('/instruments')
def instruments(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id);svc.school_access(db,actor,school_id,'assessment.instrument.read')
    rows=list(db.scalars(select(m.Instrument).where(m.Instrument.school_id==school_id).order_by(m.Instrument.created_at,m.Instrument.id)))
    return {'items':[svc.instrument_view(db,actor,school_id,r.id) for r in rows[offset:offset+limit]],'total':len(rows)}
@router.get('/instruments/{identifier}')
def instrument_read(school_id:UUID,identifier:UUID,db:Session=D,actor:Actor=A):return svc.instrument_view(db,actor,str(school_id),identifier)
@router.post('/instruments/{identifier}/revisions',status_code=201)
def instrument_revise(school_id:UUID,identifier:UUID,command:s.InstrumentRevise,db:Session=D,actor:Actor=A):return svc.revise_instrument(db,actor,str(school_id),identifier,command)
@router.post('/instruments/{identifier}/review')
def instrument_review(school_id:UUID,identifier:UUID,command:s.InstrumentReview,db:Session=D,actor:Actor=A):return svc.review_instrument(db,actor,str(school_id),identifier,command)
@router.get('/instruments/{identifier}/revisions')
def instrument_history(school_id:UUID,identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id);svc.instrument_view(db,actor,school_id,identifier)
    rows=list(db.scalars(select(m.InstrumentRevision).where(m.InstrumentRevision.school_id==school_id,m.InstrumentRevision.instrument_id==str(identifier)).order_by(m.InstrumentRevision.number)))
    for r in rows[offset:offset+limit]:svc.current_instrument(db,actor,school_id,r.id)
    return {'items':[svc.row_json(r) for r in rows[offset:offset+limit]],'total':len(rows)}
@router.post('/administrations',status_code=201)
def administration_plan(school_id:UUID,command:s.AdministrationPlan,db:Session=D,actor:Actor=A):return svc.plan_administration(db,actor,str(school_id),command)
@router.get('/administrations/{identifier}')
def administration_read(school_id:UUID,identifier:UUID,db:Session=D,actor:Actor=A):return svc.administration_view(db,actor,str(school_id),identifier)
@router.post('/administrations/{identifier}/start')
def administration_start(school_id:UUID,identifier:UUID,command:s.AdministrationStart,db:Session=D,actor:Actor=A):return svc.start_administration(db,actor,str(school_id),identifier,command)
@router.post('/administrations/{identifier}/abort')
def administration_abort(school_id:UUID,identifier:UUID,command:s.AdministrationAbort,db:Session=D,actor:Actor=A):return svc.abort_administration(db,actor,str(school_id),identifier,command)
@router.post('/administrations/{identifier}/results',status_code=201)
def administration_record(school_id:UUID,identifier:UUID,command:s.RecordResult,db:Session=D,actor:Actor=A):return svc.record_result(db,actor,str(school_id),identifier,command)
@router.post('/administrations/{identifier}/review')
def administration_review(school_id:UUID,identifier:UUID,command:s.ReviewResult,db:Session=D,actor:Actor=A):return svc.review_result(db,actor,str(school_id),identifier,command)
@router.get('/administrations/{identifier}/results')
def result_history(school_id:UUID,identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id);v=svc.administration_view(db,actor,school_id,identifier)
    if v['source_status']=='unavailable':return {'items':[],'total':0,'source_status':'unavailable'}
    rows=list(db.scalars(select(m.ResultRevision).where(m.ResultRevision.school_id==school_id,m.ResultRevision.administration_id==str(identifier)).order_by(m.ResultRevision.number)))
    return {'items':[svc.row_json(r) for r in rows[offset:offset+limit]],'total':len(rows)}
@router.get('/follow-ups/{identifier}')
def follow_up_read(school_id:UUID,identifier:UUID,db:Session=D,actor:Actor=A):return svc.follow_up_view(db,actor,str(school_id),identifier)
@router.post('/follow-ups/{identifier}/decision')
def follow_up_decide(school_id:UUID,identifier:UUID,command:s.DecideFollowUp,db:Session=D,actor:Actor=A):return svc.decide_follow_up(db,actor,str(school_id),identifier,command)
@router.post('/progress-reviews',status_code=201)
def progress_create(school_id:UUID,command:s.ProgressCreate,db:Session=D,actor:Actor=A):return svc.create_progress(db,actor,str(school_id),command)
@router.get('/progress-reviews/{identifier}')
def progress_read(school_id:UUID,identifier:UUID,db:Session=D,actor:Actor=A):return svc.progress_view(db,actor,str(school_id),identifier)
@router.post('/progress-reviews/{identifier}/revisions',status_code=201)
def progress_revise(school_id:UUID,identifier:UUID,command:s.ProgressRevise,db:Session=D,actor:Actor=A):return svc.revise_progress(db,actor,str(school_id),identifier,command)
@router.post('/progress-reviews/{identifier}/review')
def progress_transition(school_id:UUID,identifier:UUID,command:s.ProgressTransition,db:Session=D,actor:Actor=A):return svc.transition_progress(db,actor,str(school_id),identifier,command)
@router.post('/statements',status_code=201)
def statement_create(school_id:UUID,command:s.StatementCreate,db:Session=D,actor:Actor=A):return svc.create_statement(db,actor,str(school_id),command)
@router.get('/statements/{identifier}')
def statement_read(school_id:UUID,identifier:UUID,db:Session=D,actor:Actor=A):return svc.statement_view(db,actor,str(school_id),identifier)
@router.post('/statements/{identifier}/revisions',status_code=201)
def statement_revise(school_id:UUID,identifier:UUID,command:s.StatementRevise,db:Session=D,actor:Actor=A):return svc.revise_statement(db,actor,str(school_id),identifier,command)
@router.post('/statements/{identifier}/contributions',status_code=201)
def statement_contribute(school_id:UUID,identifier:UUID,command:s.Contribute,db:Session=D,actor:Actor=A):return svc.contribute(db,actor,str(school_id),identifier,command)
@router.post('/statements/{identifier}/finalize')
def statement_finalize(school_id:UUID,identifier:UUID,command:s.FinalizeStatement,db:Session=D,actor:Actor=A):return svc.finalize_statement(db,actor,str(school_id),identifier,command)
@router.post('/statements/{identifier}/communications',status_code=201)
def statement_communicate(school_id:UUID,identifier:UUID,command:s.RecordCommunication,db:Session=D,actor:Actor=A):return svc.record_communication(db,actor,str(school_id),identifier,command)
@router.get('/learners/{learner_id}/{collection}')
def learner_collection(school_id:UUID,learner_id:UUID,collection:str,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    school_id=str(school_id);learner_id=str(learner_id);svc.pupil_access(db,actor,school_id,learner_id)
    kinds={'administrations':('administration',m.Administration),'progress-reviews':('progress',m.ProgressReview),'statements':('statement',m.Statement)}
    if collection=='follow-ups':
        rows=list(db.scalars(select(m.FollowUp).join(m.Administration,m.Administration.id==m.FollowUp.administration_id).where(m.FollowUp.school_id==school_id,m.Administration.school_id==school_id,m.Administration.learner_id==learner_id).order_by(m.FollowUp.created_at,m.FollowUp.id)));kind='follow_up'
    elif collection in kinds:
        kind,model=kinds[collection];rows=list(db.scalars(select(model).where(model.school_id==school_id,model.learner_id==learner_id).order_by(model.created_at,model.id)))
    else:raise svc.DomainError('assessment_collection','Unknown assessment collection.',404)
    return {'items':[svc.view(db,actor,school_id,kind,r.id) for r in rows[offset:offset+limit]],'total':len(rows)}

@router.get('/progress-reviews/{identifier}/revisions')
def progress_history(school_id:UUID,identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    return svc.revision_history(db,actor,str(school_id),'progress',identifier,offset,limit)
@router.get('/statements/{identifier}/revisions')
def statement_history(school_id:UUID,identifier:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    return svc.revision_history(db,actor,str(school_id),'statement',identifier,offset,limit)
