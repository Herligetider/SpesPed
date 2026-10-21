from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor, get_actor
from spesped.audit import record_audit
from spesped.db import get_db
from spesped.errors import DomainError, access_denied
from spesped.contexts.entitlements.common import commit,mutate,source_status
from . import service
from .models import IndividualEducationPlan, PlanRevision, PlanImpact, GoalRevision, PlanApproval, ProfileStatement, ProfileReview
from .schemas import ProfileInput,ProfileReviewInput,CreatePlan,RevisePlan,PlanLifecycle

def bind_runtime(request:Request,db:Session=Depends(get_db)):
    try:db.info['plans_runtime']=gateway_runtime(request)
    except DomainError:db.info['plans_runtime']=None


router=APIRouter(prefix='/api/v1/schools/{school_id}',tags=['learning profiles and plans'],dependencies=[Depends(bind_runtime)])


def plan_view(db,actor,row,revision=None):
    service.check_access(db,actor,row.school_id,row.learner_id,'plans.read')
    revision=revision or service.current_revision(db,row)
    value={'id':row.id,'learner_id':row.learner_id,'kind':row.kind,'version':row.version,'state':row.state,'current_revision':row.current_revision,'active_revision_id':row.active_revision_id,'revision_state':revision.state,'content_digest':revision.content_digest,'approved_by':revision.approved_by,'approved_at':revision.approved_at,'activated_at':revision.activated_at,'activation_until':revision.activation_until}
    status=source_status(db,actor,row.school_id,row.learner_id,service.projection_bindings(db,actor,row,revision))
    from .generation import lineage_status
    if lineage_status(db,actor,row,revision) != 'current': status='review_required'
    issues=[]
    try: service.validate_plan_basis(db,actor,row,revision,historical=revision.state == 'historical')
    except DomainError as exc:
        if exc.status_code == 403: raise
        issues.append({'code':exc.code,'message':exc.message})
    value['source_status']=status
    value['content']=service.snapshot(db,revision) if status == 'current' else {'id':revision.id,'revision':revision.revision,'issue':'source_review_required'}
    value['clarifications']=issues
    value['approval_binding']=revision.approval_binding
    return value


@router.get('/learners/{learner_id}/support-profile')
def profile(school_id:UUID,learner_id:UUID,history:bool=False,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=service.profile_view(db,actor,str(school_id),str(learner_id),history,offset=offset,limit=limit);commit(db);return value


@router.get('/learners/{learner_id}/support-profile/brief')
def brief(school_id:UUID,learner_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=service.profile_view(db,actor,str(school_id),str(learner_id),brief=True);commit(db);return value


@router.post('/learners/{learner_id}/support-profile/statements',status_code=201)
def propose(school_id:UUID,learner_id:UUID,command:ProfileInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.propose_profile(db,actor,str(school_id),str(learner_id),command));return {'id':row.id,'version':row.version,'state':row.state}


@router.post('/learners/{learner_id}/support-profile/statements/{statement_id}/review')
def review_profile(school_id:UUID,learner_id:UUID,statement_id:UUID,command:ProfileReviewInput,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.review_profile(db,actor,str(school_id),str(learner_id),str(statement_id),command));return {'id':row.id,'version':row.version,'state':row.state}


@router.post('/learners/{learner_id}/education-plans',status_code=201)
def create_plan(school_id:UUID,learner_id:UUID,command:CreatePlan,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.save_plan(db,actor,str(school_id),str(learner_id),command));return plan_view(db,actor,row)


@router.get('/learners/{learner_id}/education-plans')
def plans(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    service.check_access(db,actor,str(school_id),str(learner_id))
    rows=db.scalars(select(IndividualEducationPlan).where(IndividualEducationPlan.school_id == str(school_id),IndividualEducationPlan.learner_id == str(learner_id)).order_by(IndividualEducationPlan.created_at,IndividualEducationPlan.id)).all()
    value={'items':[plan_view(db,actor,row) for row in rows[offset:offset+limit]],'total':len(rows)}
    record_audit(db,actor,str(school_id),'plan.list_read','learner',str(learner_id));commit(db);return value


@router.get('/education-plans/{plan_id}')
def get_plan(school_id:UUID,plan_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=service.plan(db,actor,str(school_id),str(plan_id));value=plan_view(db,actor,row)
    record_audit(db,actor,str(school_id),'plan.read','education_plan',row.id);commit(db);return value


@router.post('/education-plans/{plan_id}/revisions',status_code=201)
def revise(school_id:UUID,plan_id:UUID,command:RevisePlan,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=service.plan(db,actor,str(school_id),str(plan_id),'plans.write')
    row=mutate(db,lambda:service.save_plan(db,actor,str(school_id),row.learner_id,command,str(plan_id)));return plan_view(db,actor,row)


@router.get('/education-plans/{plan_id}/revisions')
def revisions(school_id:UUID,plan_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=service.plan(db,actor,str(school_id),str(plan_id))
    items=db.scalars(select(PlanRevision).where(PlanRevision.school_id == str(school_id),PlanRevision.plan_id == row.id).order_by(PlanRevision.revision.desc())).all()
    value={'items':[plan_view(db,actor,row,r) for r in items[offset:offset+limit]],'total':len(items)}
    record_audit(db,actor,str(school_id),'plan.history_read','education_plan',row.id);commit(db);return value


@router.get('/education-plans/{plan_id}/compare')
def compare(school_id:UUID,plan_id:UUID,old_revision_id:UUID,new_revision_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=service.plan(db,actor,str(school_id),str(plan_id))
    old=db.scalar(select(PlanRevision).where(PlanRevision.school_id == str(school_id),PlanRevision.plan_id == row.id,PlanRevision.id == str(old_revision_id)))
    new=db.scalar(select(PlanRevision).where(PlanRevision.school_id == str(school_id),PlanRevision.plan_id == row.id,PlanRevision.id == str(new_revision_id)))
    if old is None or new is None: raise access_denied()
    record_audit(db,actor,str(school_id),'plan.comparison_read','education_plan',row.id);commit(db)
    return {'items':service.compare(db,row,old,new),'impact':'Future session consumers must revalidate exact goal revision and plan basis.'}


@router.post('/education-plans/{plan_id}/review')
def review(school_id:UUID,plan_id:UUID,command:PlanLifecycle,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.lifecycle(db,actor,str(school_id),str(plan_id),command,'review'));return plan_view(db,actor,row)


@router.post('/education-plans/{plan_id}/approve')
def approve(school_id:UUID,plan_id:UUID,command:PlanLifecycle,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.lifecycle(db,actor,str(school_id),str(plan_id),command,'approve'));return plan_view(db,actor,row)


@router.post('/education-plans/{plan_id}/activate')
def activate(school_id:UUID,plan_id:UUID,command:PlanLifecycle,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:service.lifecycle(db,actor,str(school_id),str(plan_id),command,'activate'));return plan_view(db,actor,row)


@router.get('/learners/{learner_id}/learning-goals')
def goals(school_id:UUID,learner_id:UUID,at:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    from datetime import datetime
    try:
        instant=datetime.fromisoformat(at) if at else None
        if instant and (instant.tzinfo is None or instant.utcoffset() is None): raise ValueError()
    except ValueError: raise DomainError('period','Use an aware ISO timestamp.',422) from None
    items=service.active_goals(db,actor,str(school_id),str(learner_id),instant)
    record_audit(db,actor,str(school_id),'goal.list_read','learner',str(learner_id));commit(db)
    return {'items':items[offset:offset+limit],'total':len(items)}


@router.get('/learners/{learner_id}/learning-goals/{goal_revision_id}')
def goal(school_id:UUID,learner_id:UUID,goal_revision_id:UUID,historical:bool=False,actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=service.goal_reference(db,actor,str(school_id),str(learner_id),str(goal_revision_id),historical=historical)
    record_audit(db,actor,str(school_id),'goal.read','goal_revision',str(goal_revision_id));commit(db);return value


@router.get('/learners/{learner_id}/plan-change-impacts')
def impacts(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    service.check_access(db,actor,str(school_id),str(learner_id))
    items=db.scalars(select(PlanImpact).where(PlanImpact.school_id == str(school_id),PlanImpact.learner_id == str(learner_id)).order_by(PlanImpact.created_at.desc(),PlanImpact.id)).all()
    record_audit(db,actor,str(school_id),'plan.impacts_read','learner',str(learner_id));commit(db)
    return {'items':[service.content_row(r,('id','version','state','plan_id','plan_revision_id','kind','old_reference','new_reference','resolved_by_revision_id')) for r in items[offset:offset+limit]],'total':len(items)}


@router.get('/learners/{learner_id}/support-profile/statements/{statement_id}/history')
def statement_history(school_id:UUID,learner_id:UUID,statement_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    profile=service.profile(db,actor,str(school_id),str(learner_id))
    row=db.scalar(select(ProfileStatement).where(ProfileStatement.school_id == str(school_id),ProfileStatement.profile_id == (profile.id if profile else None),ProfileStatement.id == str(statement_id)))
    if row is None: raise access_denied()
    reviews=db.scalars(select(ProfileReview).where(ProfileReview.school_id == str(school_id),ProfileReview.statement_id == row.id).order_by(ProfileReview.reviewed_at,ProfileReview.id)).all()
    record_audit(db,actor,str(school_id),'profile.history_read','profile_statement',row.id);commit(db)
    items=[service.profile_review_projection(db,actor,str(school_id),str(learner_id),row,service.content_row(r,('id','outcome','reason','reviewer_id','reviewed_at')),('reason',)) for r in reviews[offset:offset+limit]]
    return {'items':items,'total':len(reviews)}


from . import generation
from .schemas import GenerationBasisInput,PlanSuggestionRequest,PlanSuggestionReview
from spesped.contexts.platform.router import runtime as gateway_runtime,job_view


def generation_runtime(request:Request,db:Session=Depends(get_db)):
    configured=gateway_runtime(request)
    db.info['plans_runtime']=configured
    return configured


@router.post('/education-plans/{plan_id}/generation-bases',status_code=201)
def generation_basis(school_id:UUID,plan_id:UUID,command:GenerationBasisInput,runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    basis=mutate(db,lambda:generation.create_basis(db,actor,str(school_id),str(plan_id),command))
    return generation.basis_view(db,actor,str(school_id),basis.id)


@router.get('/plan-generation-bases/{basis_id}')
def read_generation_basis(school_id:UUID,basis_id:UUID,runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=generation.basis_view(db,actor,str(school_id),str(basis_id))
    record_audit(db,actor,str(school_id),'plan.generation_basis_read','plan_generation_basis',str(basis_id));commit(db);return value


@router.post('/education-plans/{plan_id}/suggestions',status_code=201)
def suggest_plan(school_id:UUID,plan_id:UUID,command:PlanSuggestionRequest,runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    return job_view(generation.request_suggestion(db,actor,str(school_id),str(plan_id),command,runtime))


@router.get('/education-plans/{plan_id}/suggestions')
def plan_suggestions(school_id:UUID,plan_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=generation.suggestion_history(db,actor,str(school_id),str(plan_id),runtime,offset=offset,limit=limit)
    record_audit(db,actor,str(school_id),'plan.suggestions_read','education_plan',str(plan_id));commit(db);return value


@router.get('/education-plans/{plan_id}/suggestions/{job_id}')
def plan_suggestion(school_id:UUID,plan_id:UUID,job_id:UUID,basis_id:UUID,runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=generation.diff(db,actor,str(school_id),str(plan_id),str(basis_id),str(job_id),runtime)
    record_audit(db,actor,str(school_id),'plan.suggestion_read','education_plan',str(plan_id));commit(db);return value


@router.post('/education-plans/{plan_id}/suggestion-reviews')
def review_plan_suggestion(school_id:UUID,plan_id:UUID,command:PlanSuggestionReview,runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    row=mutate(db,lambda:generation.review(db,actor,str(school_id),str(plan_id),command,runtime))
    return plan_view(db,actor,row)


@router.get('/education-plans/{plan_id}/suggestion-reviews')
def plan_suggestion_reviews(school_id:UUID,plan_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),runtime=Depends(generation_runtime),actor:Actor=Depends(get_actor),db:Session=Depends(get_db)):
    value=generation.review_history(db,actor,str(school_id),str(plan_id),offset,limit)
    record_audit(db,actor,str(school_id),'plan.suggestion_reviews_read','education_plan',str(plan_id));commit(db);return value
