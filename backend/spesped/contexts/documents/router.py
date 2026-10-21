"""Session authenticated document APIs. No endpoint dispatches external messages."""
from uuid import UUID
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor,get_actor
from spesped.db import get_db
from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
from . import service as svc,schemas as s,models as m,generation as gen,choices as picks
router=APIRouter(prefix='/api/v1/schools/{school_id}/documents',tags=['documents'])
def documents_db(request:Request,db:Session=Depends(get_db)):
    db.info['curriculum_source_port']=getattr(request.app.state,'curriculum_source_port',None) or EvidenceSourceReadPort(getattr(request.app.state,'evidence_storage',None))
    db.info['documents_runtime']=getattr(request.app.state,'ai_gateway',None)
    db.info['plans_runtime']=db.info['documents_runtime'];db.info['teaching_runtime']=db.info['documents_runtime']
    for name in ('document_dispatch_history_port','assessment_authority_port','teaching_qualification_port','governance_case_scope_resolver'):
        db.info[name]=getattr(request.app.state,name,None)
    return db
D=Depends(documents_db);A=Depends(get_actor)
@router.post('/templates',status_code=201)
def create_template(school_id:UUID,command:s.TemplateCreate,db:Session=D,actor:Actor=A):return svc.create_template(db,actor,str(school_id),command)
@router.get('/templates/{identity}')
def read_template(school_id:UUID,identity:UUID,db:Session=D,actor:Actor=A):return svc.template_view(db,actor,str(school_id),identity)
@router.post('/templates/{identity}/revisions',status_code=201)
def revise_template(school_id:UUID,identity:UUID,command:s.TemplateRevise,db:Session=D,actor:Actor=A):return svc.revise_template(db,actor,str(school_id),identity,command)
@router.post('/templates/{identity}/review')
def review_template(school_id:UUID,identity:UUID,command:s.Exact,db:Session=D,actor:Actor=A):return svc.review_template(db,actor,str(school_id),identity,command)
@router.post('/templates/{identity}/recall')
def recall_template(school_id:UUID,identity:UUID,command:s.Exact,db:Session=D,actor:Actor=A):return svc.recall_template(db,actor,str(school_id),identity,command)
@router.post('/period-resolution')
def resolve_period(school_id:UUID,command:s.PeriodResolve,db:Session=D,actor:Actor=A):return svc.resolve_period(db,actor,str(school_id),command)
@router.post('/cases',status_code=201)
def create(school_id:UUID,command:s.DocumentCreate,db:Session=D,actor:Actor=A):return svc.create_document(db,actor,str(school_id),command)
@router.get('/cases/{identity}')
def read(school_id:UUID,identity:UUID,db:Session=D,actor:Actor=A):return svc.document_view(db,actor,str(school_id),identity)
@router.get('/cases/{identity}/revisions')
def history(school_id:UUID,identity:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):return svc.revision_history(db,actor,str(school_id),identity,offset,limit)
@router.post('/cases/{identity}/revisions',status_code=201)
def revise(school_id:UUID,identity:UUID,command:s.DocumentRevise,db:Session=D,actor:Actor=A):return svc.revise_document(db,actor,str(school_id),identity,command)
@router.post('/cases/{identity}/review')
def review(school_id:UUID,identity:UUID,command:s.Transition,db:Session=D,actor:Actor=A):return svc.transition_document(db,actor,str(school_id),identity,command)
@router.post('/cases/{identity}/assignments',status_code=201)
def assign(school_id:UUID,identity:UUID,command:s.AssignContribution,db:Session=D,actor:Actor=A):return svc.assign_contribution(db,actor,str(school_id),identity,command)
@router.post('/cases/{identity}/contributions',status_code=201)
def contribute(school_id:UUID,identity:UUID,command:s.Contribute,db:Session=D,actor:Actor=A):return svc.contribute(db,actor,str(school_id),identity,command)
@router.post('/cases/{identity}/suggestions',status_code=201)
def suggest(school_id:UUID,identity:UUID,command:s.Suggest,request:Request,db:Session=D,actor:Actor=A):return gen.request_suggestion(db,actor,str(school_id),str(identity),command,request.app.state.ai_gateway)
@router.get('/cases/{identity}/suggestions/{job_id}/diff')
def diff(school_id:UUID,identity:UUID,job_id:UUID,request:Request,db:Session=D,actor:Actor=A):return gen.diff(db,actor,str(school_id),str(identity),str(job_id),request.app.state.ai_gateway)
@router.post('/cases/{identity}/suggestion-review')
def select_proposal(school_id:UUID,identity:UUID,command:s.ApplySuggestion,db:Session=D,actor:Actor=A):return gen.apply(db,actor,str(school_id),str(identity),command)
@router.post('/schedules',status_code=201)
def create_schedule(school_id:UUID,command:s.ScheduleCreate,db:Session=D,actor:Actor=A):return svc.create_schedule(db,actor,str(school_id),command)
@router.get('/schedules/{identity}')
def read_schedule(school_id:UUID,identity:UUID,db:Session=D,actor:Actor=A):return svc.schedule_view(db,actor,str(school_id),identity)
@router.post('/schedules/{identity}/revisions',status_code=201)
def change_schedule(school_id:UUID,identity:UUID,command:s.ScheduleChange,db:Session=D,actor:Actor=A):return svc.change_schedule(db,actor,str(school_id),identity,command)
@router.post('/schedules/{identity}/state')
def state_schedule(school_id:UUID,identity:UUID,command:s.ScheduleTransition,db:Session=D,actor:Actor=A):return svc.transition_schedule(db,actor,str(school_id),identity,command)
@router.post('/schedules/{identity}/run')
def run_schedule(school_id:UUID,identity:UUID,command:s.ScheduleRun,db:Session=D,actor:Actor=A):return svc.run_schedule(db,actor,str(school_id),identity,command)
@router.get('/learners/{learner_id}/workspace')
def workspace(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):return svc.workspace(db,actor,str(school_id),str(learner_id),offset,limit)
@router.get('/cases/{identity}/contribution-workspace')
def contribution_workspace(school_id:UUID,identity:UUID,db:Session=D,actor:Actor=A):return svc.contribution_workspace(db,actor,str(school_id),str(identity))

@router.get('/learners/{learner_id}/choices/{category}',response_model=picks.ChoicePage)
def choices(school_id:UUID,learner_id:UUID,category:picks.Category,kind:s.Kind,starts_on:date,ends_on:date,
            offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),requirement_version_id:UUID|None=None,
            source_mode:Literal['interval','background']='interval',source_starts_on:date|None=None,source_ends_on:date|None=None,
            query:str|None=Query(None,min_length=1,max_length=100),
            db:Session=D,actor:Actor=A):
    return picks.choices(db,actor,str(school_id),str(learner_id),category,kind,starts_on,ends_on,offset=offset,limit=limit,
        requirement_version_id=requirement_version_id,source_mode=source_mode,source_starts_on=source_starts_on,source_ends_on=source_ends_on,query=query)

@router.get('/cases/{identity}/suggestions',response_model=picks.SuggestionPage)
def suggestions(school_id:UUID,identity:UUID,request:Request,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    return picks.suggestions(db,actor,str(school_id),str(identity),request.app.state.ai_gateway,offset,limit)

@router.get('/cases/{identity}/recovery',response_model=picks.RecoveryMetadata)
def recovery_metadata(school_id:UUID,identity:UUID,db:Session=D,actor:Actor=A):
    return svc.recovery_metadata(db,actor,str(school_id),str(identity))

@router.get('/learners/{learner_id}/contribution-inbox',response_model=picks.ContributionPage)
def contribution_inbox(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),db:Session=D,actor:Actor=A):
    return picks.contribution_inbox(db,actor,str(school_id),str(learner_id),offset,limit)
