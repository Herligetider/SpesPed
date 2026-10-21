"""Named commands and pagination for the BC06 workspace and teaching consumers."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from spesped.auth import Actor,get_actor,require_learner_access
from spesped.db import get_db
from spesped.errors import DomainError
from . import schemas as s,models as m,service as svc
from .adapters import EvidenceSourceReadPort
from .ports import AvailabilityRequest

router=APIRouter(prefix='/api/v1/schools/{school_id}/curriculum',tags=['curriculum'])


def curriculum_db(request:Request,db:Session=Depends(get_db)):
    db.info['curriculum_source_port']=getattr(request.app.state,'curriculum_source_port',None) or EvidenceSourceReadPort(getattr(request.app.state,'evidence_storage',None))
    for name in ('future_session_port','material_reservation_port'):
        db.info['curriculum_'+name]=getattr(request.app.state,'curriculum_'+name,None)
    return db


def paginate(rows,offset,limit):return {'items':rows[offset:offset+limit],'total':len(rows)}


def visible_views(db,actor,school_id,model,view):
    result=[]
    for row in db.scalars(select(model).where(model.school_id==school_id).order_by(model.created_at,model.id)):
        try:result.append(view(db,actor,school_id,row.id))
        except DomainError as exc:
            if exc.status_code not in {403,409}:raise
    return result


@router.post('/schemes',status_code=201)
def create_scheme(school_id:UUID,command:s.SchemeCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.create_scheme(db,actor,str(school_id),command)


@router.get('/schemes')
def schemes(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'curriculum.read')
    return paginate(visible_views(db,actor,str(school_id),m.CurriculumScheme,svc.scheme_view),offset,limit)


@router.get('/schemes/{scheme_id}')
def scheme(school_id:UUID,scheme_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.scheme_view(db,actor,str(school_id),scheme_id)


@router.post('/schemes/{scheme_id}/revisions',status_code=201)
def revise_scheme(school_id:UUID,scheme_id:UUID,command:s.SchemeRevision,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.revise_scheme(db,actor,str(school_id),scheme_id,command)


@router.post('/schemes/{scheme_id}/review')
def review_scheme(school_id:UUID,scheme_id:UUID,command:s.SchemeReview,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.review_scheme(db,actor,str(school_id),scheme_id,command)


@router.get('/scheme-revisions/{revision_id}')
def scheme_revision(school_id:UUID,revision_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    row=svc.scheme_current(db,actor,str(school_id),revision_id)
    assessment=db.scalar(select(m.AssessmentScheme).where(m.AssessmentScheme.school_id==str(school_id),m.AssessmentScheme.scheme_revision_id==row.id))
    return {'content':svc.row_view(row),'assessment':svc.row_view(assessment)}


@router.post('/class-plans',status_code=201)
def create_plan(school_id:UUID,command:s.ClassPlanCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.create_class_plan(db,actor,str(school_id),command)


@router.get('/class-plans')
def plans(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'curriculum.read')
    return paginate(visible_views(db,actor,str(school_id),m.ClassLearningPlan,svc.class_view),offset,limit)


@router.get('/class-plans/{plan_id}')
def plan(school_id:UUID,plan_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.class_view(db,actor,str(school_id),plan_id)


@router.get('/class-plans/{plan_id}/revisions')
def plan_revisions(school_id:UUID,plan_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.class_view(db,actor,str(school_id),plan_id)
    result=[]
    for row in db.scalars(select(m.ClassPlanRevision).where(m.ClassPlanRevision.school_id==str(school_id),m.ClassPlanRevision.plan_id==str(plan_id)).order_by(m.ClassPlanRevision.number)):
        svc.sources(db,actor,str(school_id),row.imported_sources);result.append(svc.row_view(row))
    return paginate(result,offset,limit)


@router.post('/class-plans/{plan_id}/revisions',status_code=201)
def revise_plan(school_id:UUID,plan_id:UUID,command:s.ClassPlanRevision,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.revise_class_plan(db,actor,str(school_id),plan_id,command)


@router.post('/class-plans/{plan_id}/publish')
def publish_plan(school_id:UUID,plan_id:UUID,command:s.PublishPlan,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.publish_class_plan(db,actor,str(school_id),plan_id,command)


@router.get('/class-context/{revision_id}')
def class_context(school_id:UUID,revision_id:UUID,on_date:date,learner_id:UUID|None=None,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.current_class_context(db,actor,str(school_id),revision_id,on_date,str(learner_id) if learner_id else None)


@router.post('/theme-goal-bindings',status_code=201)
def bind_goal(school_id:UUID,command:s.GoalBindingCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.bind_goal(db,actor,str(school_id),command)


@router.get('/theme-goal-bindings')
def bindings(school_id:UUID,learner_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'curriculum.read');require_learner_access(db,actor,str(school_id),str(learner_id),'plans.read')
    rows=[]
    for row in db.scalars(select(m.ThemeGoalBinding).where(m.ThemeGoalBinding.school_id==str(school_id),m.ThemeGoalBinding.learner_id==str(learner_id)).order_by(m.ThemeGoalBinding.created_at,m.ThemeGoalBinding.id)):
        try:rows.append({'kind':'binding',**svc.binding_view(db,actor,row)})
        except DomainError as exc:
            if exc.status_code!=409:raise
            rows.append({'kind':'binding','id':row.id,'state':'review_required','goal_revision_id':row.goal_revision_id,'theme_id':row.theme_id})
    return paginate(rows,offset,limit)


@router.get('/session-impacts')
def impacts(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'curriculum.read');rows=[]
    for row in db.scalars(select(m.SessionImpact).where(m.SessionImpact.school_id==str(school_id),m.SessionImpact.owner_id==actor.user_id).order_by(m.SessionImpact.created_at,m.SessionImpact.id)):
        try:svc.impact_access(db,actor,row);rows.append(svc.row_view(row))
        except DomainError as exc:
            if exc.status_code!=403:raise
    return paginate(rows,offset,limit)


@router.post('/session-impacts/{impact_id}/decision')
def decide(school_id:UUID,impact_id:UUID,command:s.ImpactDecision,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.decide_impact(db,actor,str(school_id),impact_id,command)


@router.post('/resources',status_code=201)
def create_resource(school_id:UUID,command:s.ResourceCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.create_resource(db,actor,str(school_id),command)


@router.get('/resources')
def resources(school_id:UUID,q:str|None=Query(None,max_length=200),subject:str|None=None,skill:str|None=None,level:str|None=None,tag:str|None=None,age:int|None=Query(None,ge=0,le=30),duration_max:int|None=Query(None,ge=1),group_size:int|None=Query(None,ge=1),material_id:UUID|None=None,prerequisite:str|None=None,purpose:str=Query('read',pattern='^(read|use|copy|ai)$'),prefer_institutional:bool=True,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'resources.read');rows=[]
    for root in db.scalars(select(m.TeachingResource).where(m.TeachingResource.school_id==str(school_id),m.TeachingResource.state!='withdrawn').order_by(m.TeachingResource.id)):
        revision=db.scalar(select(m.ResourceRevision).where(m.ResourceRevision.resource_id==root.id,m.ResourceRevision.number==root.current_revision))
        if subject and subject not in revision.subjects:continue
        if skill and skill not in revision.skills:continue
        if level and level!=revision.level:continue
        if tag and tag not in revision.tags:continue
        if age is not None and not revision.age_min<=age<=revision.age_max:continue
        if duration_max is not None and revision.duration_minutes>duration_max:continue
        if group_size is not None and not revision.group_min<=group_size<=revision.group_max:continue
        if material_id and str(material_id) not in revision.material_ids:continue
        if prerequisite and not any(prerequisite.casefold() in p.casefold() for p in revision.prerequisites):continue
        if q and not any(q.casefold() in value.casefold() for value in [revision.title,revision.method,*revision.tags,*revision.skills,*revision.subjects]):continue
        try:value=svc.resolve_resource(db,actor,str(school_id),revision.id,purpose)
        except DomainError as exc:
            if exc.status_code in {403,409}:continue
            raise
        value['match_reasons']=[name for name,chosen in [('subject',subject),('skill',skill),('level',level),('tag',tag),('age_range',age is not None),('duration',duration_max),('group_size',group_size),('material',material_id),('prerequisite_text',prerequisite),('search_text',q)] if chosen]
        value['institutional_preference']=root.visibility in {'school','team'};rows.append(value)
    rows.sort(key=lambda r:(not r['institutional_preference'] if prefer_institutional else False,r['title'].casefold(),r['id']))
    return paginate(rows,offset,limit)


@router.get('/resources/{resource_id}')
def resource(school_id:UUID,resource_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.resource_view(db,actor,str(school_id),resource_id)


@router.get('/resources/{resource_id}/revisions')
def resource_revisions(school_id:UUID,resource_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.resource_view(db,actor,str(school_id),resource_id)
    rows=[]
    for revision in db.scalars(select(m.ResourceRevision).where(m.ResourceRevision.school_id==str(school_id),m.ResourceRevision.resource_id==str(resource_id)).order_by(m.ResourceRevision.number)):
        try:rows.append(svc.resolve_resource(db,actor,str(school_id),revision.id))
        except DomainError as exc:
            if exc.status_code not in {403,409}:raise
    return paginate(rows,offset,limit)


@router.get('/resource-revisions/{revision_id}')
def resource_revision(school_id:UUID,revision_id:UUID,purpose:str=Query('read',pattern='^(read|use|copy|ai)$'),learner_id:UUID|None=None,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.resolve_resource(db,actor,str(school_id),revision_id,purpose,str(learner_id) if learner_id else None)


@router.post('/resources/{resource_id}/revisions',status_code=201)
def revise_resource(school_id:UUID,resource_id:UUID,command:s.ResourceRevision,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.revise_resource(db,actor,str(school_id),resource_id,command)


@router.post('/resources/{resource_id}/sharing')
def share(school_id:UUID,resource_id:UUID,command:s.ShareResource,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.share_resource(db,actor,str(school_id),resource_id,command)


@router.post('/resources/{resource_id}/withdraw')
def withdraw(school_id:UUID,resource_id:UUID,command:s.Reason,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.withdraw_resource(db,actor,str(school_id),resource_id,command)


@router.post('/resource-experiences',status_code=201)
def experience(school_id:UUID,command:s.ExperienceCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.record_experience(db,actor,str(school_id),command)


@router.get('/resource-experiences')
def experiences(school_id:UUID,learner_id:UUID,resource_revision_id:UUID|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'resources.read');require_learner_access(db,actor,str(school_id),str(learner_id),'teaching.read')
    rows=[]
    for row in db.scalars(select(m.ResourceExperience).where(m.ResourceExperience.school_id==str(school_id),m.ResourceExperience.learner_id==str(learner_id)).order_by(m.ResourceExperience.created_at,m.ResourceExperience.id)):
        if resource_revision_id and row.resource_revision_id!=str(resource_revision_id):continue
        rows.append(svc.experience_view(db,actor,row))
    return paginate(rows,offset,limit)


@router.post('/resource-teams',status_code=201)
def create_team(school_id:UUID,command:s.TeamCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.create_team(db,actor,str(school_id),command)


@router.get('/resource-teams')
def teams(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'resources.manage')
    return paginate([svc.row_view(r) for r in db.scalars(select(m.ResourceTeam).where(m.ResourceTeam.school_id==str(school_id)).order_by(m.ResourceTeam.id))],offset,limit)


@router.post('/resource-teams/{team_id}/membership')
def membership(school_id:UUID,team_id:UUID,command:s.TeamMembership,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.set_team_member(db,actor,str(school_id),team_id,command)


@router.post('/materials',status_code=201)
def create_material(school_id:UUID,command:s.MaterialCreate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.create_material(db,actor,str(school_id),command)


@router.get('/materials')
def materials(school_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'materials.read')
    rows=[{'kind':'material',**svc.row_view(r),'availability':'unknown'} for r in db.scalars(select(m.MaterialCatalogItem).where(m.MaterialCatalogItem.school_id==str(school_id)).order_by(m.MaterialCatalogItem.title,m.MaterialCatalogItem.id))]
    return paginate(rows,offset,limit)


@router.patch('/materials/{material_id}')
def update_material(school_id:UUID,material_id:UUID,command:s.MaterialUpdate,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.update_material(db,actor,str(school_id),material_id,command)


@router.post('/material-availability')
def availability(school_id:UUID,command:AvailabilityRequest,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    if command.school_id!=school_id:raise DomainError('material_scope','Availability request must match the selected school.',403)
    return svc.material_availability(db,actor,command)


@router.post('/class-plans/{plan_id}/withdraw')
def withdraw_plan(school_id:UUID,plan_id:UUID,command:s.Reason,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.withdraw_class_plan(db,actor,str(school_id),plan_id,command)


@router.post('/schemes/{scheme_id}/withdraw')
def withdraw_scheme(school_id:UUID,scheme_id:UUID,command:s.Reason,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.withdraw_scheme(db,actor,str(school_id),scheme_id,command)


@router.get('/schemes/{scheme_id}/revisions')
def scheme_revisions(school_id:UUID,scheme_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.scheme_view(db,actor,str(school_id),scheme_id);rows=[]
    for revision in db.scalars(select(m.SchemeRevision).where(m.SchemeRevision.school_id==str(school_id),m.SchemeRevision.scheme_id==str(scheme_id)).order_by(m.SchemeRevision.number)):
        svc.sources(db,actor,str(school_id),revision.sources)
        assessment=db.scalar(select(m.AssessmentScheme).where(m.AssessmentScheme.school_id==str(school_id),m.AssessmentScheme.scheme_revision_id==revision.id))
        rows.append({'content':svc.row_view(revision),'assessment':svc.row_view(assessment)})
    return paginate(rows,offset,limit)


@router.get('/resource-teams/{team_id}/members')
def team_members(school_id:UUID,team_id:UUID,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'resources.manage');team=svc.get(db,m.ResourceTeam,str(school_id),team_id)
    rows=[svc.row_view(row) for row in db.scalars(select(m.TeamMember).where(m.TeamMember.school_id==str(school_id),m.TeamMember.team_id==team.id).order_by(m.TeamMember.user_id))]
    return {'team_version':team.version,**paginate(rows,offset,limit)}


@router.get('/materials/{material_id}')
def material(school_id:UUID,material_id:UUID,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    svc.authority(db,actor,str(school_id),'materials.read')
    return {'kind':'material',**svc.row_view(svc.get(db,m.MaterialCatalogItem,str(school_id),material_id)),'availability':'unknown'}


@router.post('/theme-goal-bindings/{binding_id}/corrections',status_code=201)
def correct_binding(school_id:UUID,binding_id:UUID,command:s.GoalBindingCorrection,actor:Actor=Depends(get_actor),db:Session=Depends(curriculum_db)):
    return svc.correct_goal_binding(db,actor,str(school_id),binding_id,command)
