"""Authenticated BC07 workflow endpoints. Root assembly owns registration."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor,get_actor,require_school_access
from spesped.audit import record_audit
from spesped.db import get_db
from spesped.errors import DomainError,access_denied
from spesped.contexts.platform.router import runtime,job_view
from . import service
from .common import mutate
from .models import *
from .schemas import *

router=APIRouter(prefix='/api/v1/schools/{school_id}',tags=['Teaching practice'])


def context(request:Request,db:Session=Depends(get_db)):
    db.info['teaching_runtime']=runtime(request)
    db.info['teaching_qualification_port']=getattr(request.app.state,'teaching_qualification_port',None)
    return db


def read(db,actor,school_id,action,target,identity,value):
    record_audit(db,actor,school_id,action,target,identity)
    return mutate(db,lambda:value)


def bounded_dates(*dates):
    if any(d is not None and (d.tzinfo is None or d.utcoffset() is None) for d in dates):raise DomainError('period','Use UTC-aware ISO timestamps.',422)


@router.get('/teaching/brief-templates')
def templates(school_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    require_school_access(db,actor,str(school_id))
    return {'items':[{'id':'practical','focus':'Practical steps, material location and help contact'},{'id':'visual_support','focus':'Visual cues and agreed simplification'},{'id':'guided_practice','focus':'Model, supported practice and when to ask the teacher'}],'total':3,'five_minute_comprehension':'requires_practitioner_usability_test','replaces_training':False}


@router.post('/teaching/bases',status_code=201)
def create_basis(school_id:UUID,command:CreateBasis,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.create_basis(db,actor,str(school_id),command))
    return mutate(db,lambda:service.basis_view(db,actor,row))


@router.get('/teaching/bases/{basis_id}')
def get_basis(school_id:UUID,basis_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.load(db,TeachingBasis,str(school_id),str(basis_id))
    return read(db,actor,str(school_id),'teaching.basis_read','teaching_basis',row.id,service.basis_view(db,actor,row))


@router.post('/teaching/sessions',status_code=201)
def create_session(school_id:UUID,command:SaveSession,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_session(db,actor,str(school_id),command));return mutate(db,lambda:service.session_view(db,actor,row))


@router.get('/teaching/sessions/{session_id}')
def get_session(school_id:UUID,session_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.session(db,actor,str(school_id),str(session_id));value=service.session_view(db,actor,row)
    return read(db,actor,str(school_id),'teaching.session_read','teaching_session',row.id,value)


@router.post('/teaching/sessions/{session_id}/revisions',status_code=201)
def revise_session(school_id:UUID,session_id:UUID,command:ReviseSession,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_session(db,actor,str(school_id),command,str(session_id)));return mutate(db,lambda:service.session_view(db,actor,row))


@router.get('/teaching/sessions/{session_id}/revisions')
def session_history(school_id:UUID,session_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.session(db,actor,str(school_id),str(session_id))
    revisions=list(db.scalars(select(SessionRevision).where(SessionRevision.school_id == str(school_id),SessionRevision.session_id == row.id).order_by(SessionRevision.revision.desc())))
    value={'items':[service.session_view(db,actor,row,r) for r in revisions[offset:offset+limit]],'total':len(revisions)}
    return read(db,actor,str(school_id),'teaching.session_history','teaching_session',row.id,value)


@router.post('/teaching/sessions/{session_id}/review')
def review_session(school_id:UUID,session_id:UUID,command:ReviewSession,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.review_session(db,actor,str(school_id),str(session_id),command,'review'));return mutate(db,lambda:service.session_view(db,actor,row))


@router.post('/teaching/sessions/{session_id}/approve')
def approve_session(school_id:UUID,session_id:UUID,command:ReviewSession,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.review_session(db,actor,str(school_id),str(session_id),command,'approve'));return mutate(db,lambda:service.session_view(db,actor,row))


@router.post('/teaching/sessions/{session_id}/suggestions',status_code=201)
def request_suggestion(school_id:UUID,session_id:UUID,command:RequestSuggestion,request:Request,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    return job_view(service.request_suggestion(db,actor,str(school_id),str(session_id),command,runtime(request)))


@router.get('/teaching/sessions/{session_id}/suggestions/{job_id}/diff')
def suggestion_diff(school_id:UUID,session_id:UUID,job_id:UUID,request:Request,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    value=service.suggestion_diff(db,actor,str(school_id),str(session_id),str(job_id),runtime(request))
    return read(db,actor,str(school_id),'teaching.suggestion_diff','teaching_session',str(session_id),value)


@router.post('/teaching/sessions/{session_id}/suggestions/review')
def review_suggestion(school_id:UUID,session_id:UUID,command:ReviewSuggestion,request:Request,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.review_suggestion(db,actor,str(school_id),str(session_id),command,runtime(request)));return mutate(db,lambda:service.session_view(db,actor,row))


@router.post('/teaching/briefs',status_code=201)
def create_brief(school_id:UUID,command:CreateBrief,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.create_brief(db,actor,str(school_id),command));return mutate(db,lambda:service.brief_view(db,actor,row))


@router.get('/teaching/briefs/{brief_id}')
def get_brief(school_id:UUID,brief_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.brief(db,actor,str(school_id),str(brief_id));return read(db,actor,str(school_id),'teaching.brief_read','teaching_brief',row.id,service.brief_view(db,actor,row))


@router.post('/teaching/briefs/{brief_id}/review')
def review_brief(school_id:UUID,brief_id:UUID,command:ReviewBrief,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.review_brief(db,actor,str(school_id),str(brief_id),command));return mutate(db,lambda:service.brief_view(db,actor,row))


@router.post('/teaching/briefs/{brief_id}/assignments',status_code=201)
def assign_brief(school_id:UUID,brief_id:UUID,command:AssignBrief,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.assign_brief(db,actor,str(school_id),str(brief_id),command));return {'id':row.id,'version':row.version,'state':row.state,'brief_id':row.brief_id,'assistant_id':row.assistant_id,'valid_from':row.valid_from,'valid_until':row.valid_until}


@router.get('/teaching/brief-assignments')
def my_assignments(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    require_school_access(db,actor,str(school_id))
    rows=list(db.scalars(select(BriefAssignment).where(BriefAssignment.school_id == str(school_id),BriefAssignment.assistant_id == actor.user_id,BriefAssignment.state == 'active',BriefAssignment.valid_from <= service.utcnow(),BriefAssignment.valid_until > service.utcnow()).order_by(BriefAssignment.valid_from,BriefAssignment.id)))
    value={'items':[service.assignment_view(db,actor,*service.assignment(db,actor,str(school_id),r.id)) for r in rows[offset:offset+limit]],'total':len(rows)};return mutate(db,lambda:value)


@router.get('/teaching/brief-assignments/{assignment_id}')
def get_assignment(school_id:UUID,assignment_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row,guide=service.assignment(db,actor,str(school_id),str(assignment_id));value=service.assignment_view(db,actor,row,guide);return mutate(db,lambda:value)


@router.post('/teaching/brief-assignments/{assignment_id}/revoke')
def revoke_assignment(school_id:UUID,assignment_id:UUID,command:Expected,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.revoke_assignment(db,actor,str(school_id),str(assignment_id),command));return {'id':row.id,'version':row.version,'state':row.state}


@router.post('/teaching/brief-assignments/{assignment_id}/messages',status_code=201)
def message(school_id:UUID,assignment_id:UUID,command:BriefInteraction,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.interact(db,actor,str(school_id),str(assignment_id),command));return service.row_json(row,('id','author_id','kind','text','responds_to_id','created_at'))


@router.get('/teaching/brief-assignments/{assignment_id}/messages')
def messages(school_id:UUID,assignment_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row,guide=service.assignment(db,actor,str(school_id),str(assignment_id))
    current=service.brief_is_current(db,actor,guide,curated=actor.user_id == row.assistant_id)
    rows=list(db.scalars(select(BriefMessage).where(BriefMessage.school_id == str(school_id),BriefMessage.assignment_id == row.id).order_by(BriefMessage.created_at,BriefMessage.id)))
    value={'items':[service.row_json(r,('id','author_id','kind','text','responds_to_id','created_at')) | {'text':r.text if current else None} for r in rows[offset:offset+limit]],'total':len(rows),'source_status':'current' if current else 'review_required'}
    return read(db,actor,str(school_id),'teaching.brief_messages_read','brief_assignment',row.id,value)


@router.post('/teaching/deliveries',status_code=201)
def create_delivery(school_id:UUID,command:SaveDelivery,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_delivery(db,actor,str(school_id),command));return mutate(db,lambda:service.delivery_view(db,actor,row))


@router.get('/teaching/deliveries/{delivery_id}')
def get_delivery(school_id:UUID,delivery_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.delivery(db,actor,str(school_id),str(delivery_id));return read(db,actor,str(school_id),'teaching.delivery_read','teaching_delivery',row.id,service.delivery_view(db,actor,row))


@router.post('/teaching/deliveries/{delivery_id}/corrections')
def correct_delivery(school_id:UUID,delivery_id:UUID,command:CorrectDelivery,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_delivery(db,actor,str(school_id),command,str(delivery_id)));return mutate(db,lambda:service.delivery_view(db,actor,row))


@router.get('/teaching/deliveries/{delivery_id}/revisions')
def delivery_history(school_id:UUID,delivery_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.delivery(db,actor,str(school_id),str(delivery_id))
    revisions=list(db.scalars(select(DeliveryRevision).where(DeliveryRevision.school_id == str(school_id),DeliveryRevision.delivery_id == row.id).order_by(DeliveryRevision.revision.desc())))
    return read(db,actor,str(school_id),'teaching.delivery_history','teaching_delivery',row.id,{'items':[service.delivery_view(db,actor,row,r) for r in revisions[offset:offset+limit]],'total':len(revisions)})


@router.get('/learners/{learner_id}/teaching-deliveries')
def learner_deliveries(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    sid,lid=str(school_id),str(learner_id);service.access(db,actor,sid,lid)
    rows=list(db.scalars(select(SessionDelivery).join(DeliveryRevision,DeliveryRevision.delivery_id == SessionDelivery.id).join(LearnerParticipation,LearnerParticipation.delivery_revision_id == DeliveryRevision.id).where(SessionDelivery.school_id == sid,DeliveryRevision.revision == SessionDelivery.current_revision,LearnerParticipation.learner_id == lid).order_by(DeliveryRevision.occurred_at.desc(),SessionDelivery.id)).unique())
    return read(db,actor,sid,'teaching.learner_delivery_read','learner',lid,{'items':[service.delivery_view(db,actor,r,learner_id=lid) for r in rows[offset:offset+limit]],'total':len(rows)})


@router.get('/learners/{learner_id}/teaching-summary')
def summary(school_id:UUID,learner_id:UUID,start:datetime,end:datetime,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    bounded_dates(start,end)
    return read(db,actor,str(school_id),'teaching.delivery_summary','learner',str(learner_id),service.delivery_summary(db,actor,str(school_id),str(learner_id),start,end))


@router.post('/teaching/observations',status_code=201)
def create_observation(school_id:UUID,command:SaveObservation,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_observation(db,actor,str(school_id),command));return mutate(db,lambda:service.observation_view(db,actor,row))


@router.get('/teaching/observations/{observation_id}')
def get_observation(school_id:UUID,observation_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.load(db,TeachingObservation,str(school_id),str(observation_id));return read(db,actor,str(school_id),'teaching.observation_read','teaching_observation',row.id,service.observation_view(db,actor,row))


@router.post('/teaching/observations/{observation_id}/corrections')
def correct_observation(school_id:UUID,observation_id:UUID,command:CorrectObservation,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.save_observation(db,actor,str(school_id),command,str(observation_id)));return mutate(db,lambda:service.observation_view(db,actor,row))


@router.get('/teaching/observations/{observation_id}/revisions')
def observation_history(school_id:UUID,observation_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=service.load(db,TeachingObservation,str(school_id),str(observation_id));service.observation_view(db,actor,row)
    rows=list(db.scalars(select(ObservationRevision).where(ObservationRevision.school_id == str(school_id),ObservationRevision.observation_id == row.id).order_by(ObservationRevision.revision.desc())))
    return read(db,actor,str(school_id),'teaching.observation_history','teaching_observation',row.id,{'items':[service.observation_view(db,actor,row,r) for r in rows[offset:offset+limit]],'total':len(rows)})


@router.get('/learners/{learner_id}/teaching-observations')
def observations(school_id:UUID,learner_id:UUID,start:datetime|None=None,end:datetime|None=None,goal_revision_id:UUID|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    bounded_dates(start,end)
    value=service.observations_for_learner(db,actor,str(school_id),str(learner_id),start=start,end=end,goal_revision_id=str(goal_revision_id) if goal_revision_id else None,offset=offset,limit=limit)
    return read(db,actor,str(school_id),'teaching.observations_read','learner',str(learner_id),value)


@router.get('/learners/{learner_id}/teaching-sessions')
def learner_sessions(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    sid,lid=str(school_id),str(learner_id);service.access(db,actor,sid,lid)
    rows=[]
    for row in db.scalars(select(TeachingSession).where(TeachingSession.school_id == sid).order_by(TeachingSession.created_at.desc(),TeachingSession.id)):
        basis=service.load(db,TeachingBasis,sid,service.current_revision(db,row).basis_id)
        if any(l['learner_id'] == lid for l in basis.learners):
            try:service.basis_access(db,actor,basis)
            except DomainError:continue
            rows.append(row)
    value={'items':[service.session_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    return read(db,actor,sid,'teaching.sessions_read','learner',lid,value)


@router.get('/learners/{learner_id}/teaching-follow-ups')
def follow_ups(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    service.access(db,actor,str(school_id),str(learner_id))
    rows=list(db.scalars(select(TeachingFollowUp).where(TeachingFollowUp.school_id == str(school_id),TeachingFollowUp.learner_id == str(learner_id)).order_by(TeachingFollowUp.created_at.desc(),TeachingFollowUp.id)))
    value={'items':[service.follow_up_view(db,actor,r) for r in rows[offset:offset+limit]],'total':len(rows)}
    return read(db,actor,str(school_id),'teaching.follow_ups_read','learner',str(learner_id),value)


@router.post('/teaching/follow-ups/{follow_up_id}/resolve')
def resolve(school_id:UUID,follow_up_id:UUID,command:ResolveFollowUp,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.resolve_follow_up(db,actor,str(school_id),str(follow_up_id),command));return mutate(db,lambda:service.follow_up_view(db,actor,row))


@router.post('/teaching/brief-assignments/{assignment_id}/actual-inputs',status_code=201)
def submit_actual(school_id:UUID,assignment_id:UUID,command:SubmitActualInput,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.submit_actual_input(db,actor,str(school_id),str(assignment_id),command))
    return service.row_json(row,('id','version','state','author_id','occurred_at','created_at','content')) | {'counts_as_delivery':False}


@router.get('/teaching/brief-assignments/{assignment_id}/actual-inputs')
def actual_inputs(school_id:UUID,assignment_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    assigned,guide=service.assignment(db,actor,str(school_id),str(assignment_id))
    rows=list(db.scalars(select(AssistantActualInput).where(AssistantActualInput.school_id == str(school_id),AssistantActualInput.assignment_id == assigned.id).order_by(AssistantActualInput.created_at.desc(),AssistantActualInput.id)))
    current=service.brief_is_current(db,actor,guide,curated=actor.user_id == assigned.assistant_id)
    value={'items':[service.actual_input_view(db,actor,r,guide) for r in rows[offset:offset+limit]],'total':len(rows),'counts_as_delivery':False}
    return read(db,actor,str(school_id),'teaching.actual_inputs_read','brief_assignment',assigned.id,value)


@router.post('/teaching/actual-inputs/{input_id}/review')
def review_actual(school_id:UUID,input_id:UUID,command:ReviewActualInput,actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    row=mutate(db,lambda:service.review_actual_input(db,actor,str(school_id),str(input_id),command));return service.actual_input_view(db,actor,row,service.load(db,AssistantBrief,str(school_id),service.load(db,BriefAssignment,str(school_id),row.assignment_id).brief_id))


@router.get('/teaching/sessions/{session_id}/briefs')
def session_briefs(school_id:UUID,session_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    parent=service.session(db,actor,str(school_id),str(session_id))
    rows=list(db.scalars(select(AssistantBrief).join(SessionRevision,AssistantBrief.session_revision_id == SessionRevision.id).where(AssistantBrief.school_id == str(school_id),SessionRevision.session_id == parent.id).order_by(AssistantBrief.created_at.desc(),AssistantBrief.id)))
    value={'items':[service.brief_view(db,actor,row) for row in rows[offset:offset+limit]],'total':len(rows)}
    return read(db,actor,str(school_id),'teaching.session_briefs_read','teaching_session',parent.id,value)


@router.get('/teaching/briefs/{brief_id}/assignments')
def brief_assignments(school_id:UUID,brief_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(context)):
    guide=service.brief(db,actor,str(school_id),str(brief_id))
    rows=list(db.scalars(select(BriefAssignment).where(BriefAssignment.school_id == str(school_id),BriefAssignment.brief_id == guide.id).order_by(BriefAssignment.created_at.desc(),BriefAssignment.id)))
    value={'items':[service.row_json(row,('id','version','state','assistant_id','valid_from','valid_until','assigned_by')) for row in rows[offset:offset+limit]],'total':len(rows)}
    return read(db,actor,str(school_id),'teaching.assignments_read','teaching_brief',guide.id,value)
