"""Synthetic BC06 HTTP fixtures using real evidence/plans/teaching owners."""
from datetime import date,timedelta
from uuid import uuid4
from sqlalchemy import select
import pytest
from teaching_fixtures import teaching_env,env,login,ordinary_goal,basis,session,actual
from plans_fixtures import base,key,retry,expected,evidence
from spesped.contexts.curriculum.router import router
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.contexts.curriculum.ports import FutureSession
from spesped.db import utcnow


class SyntheticFutureSessions:
    """An explicit test dependency index over actual BC07 rows; no production claim."""
    def __init__(self):self.dependencies={};self.mode='current'
    def upcoming(self,db,actor,request):
        from spesped.contexts.teaching import models as t,service as teaching
        result=[]
        for revision_id in self.dependencies.get(str(request.old_revision_id),[]):
            revision=db.get(t.SessionRevision,revision_id)
            root=teaching.session(db,actor,str(request.school_id),revision.session_id)
            basis=db.get(t.TeachingBasis,revision.basis_id)
            if basis.planned_at<=request.changed_at or root.current_revision!=revision.revision:continue
            result.append(FutureSession(request=request,session_id=root.id,session_revision_id=revision.id,owner_id=root.owner_id,planned_at=basis.planned_at,learner_ids=[l['learner_id'] for l in basis.learners]))
        return result
    def validate_decision(self,db,actor,value,decision,replacement):
        from spesped.contexts.teaching import models as t,service as teaching
        revision=db.get(t.SessionRevision,str(value.session_revision_id))
        root=teaching.session(db,actor,str(value.request.school_id),revision.session_id)
        basis=db.get(t.TeachingBasis,revision.basis_id)
        return self.mode=='current' and root.owner_id==actor.user_id and root.current_revision==revision.revision and basis.planned_at==value.planned_at and (decision=='keep' or bool(replacement))


@pytest.fixture
def curriculum_env(teaching_env):
    client,factory,app,ids=teaching_env
    if not any(getattr(r,'path','').endswith('/curriculum/resources') for r in app.routes):app.include_router(router)
    with factory.begin() as db:
        for name in ('reviewer','teacher'):
            for action in ('curriculum.read','curriculum.manage','curriculum.publish','curriculum.source.read','resources.read','resources.manage','materials.read','materials.manage','evidence.intake'):
                exists=db.scalar(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids[name],AuthorityGrant.action==action))
                if not exists:db.add(AuthorityGrant(school_id=ids['school'],user_id=ids[name],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    app.state.curriculum_future_session_port=SyntheticFutureSessions()
    return client,factory,app,ids


def path(ids):return base(ids)+'/curriculum'


def source(client,ids,h,text='Synthetic school curriculum original'):
    response=client.post(base(ids)+'/intake/notes',headers=h,json=retry(external_scope='synthetic_curriculum',external_id=key(),sender='Synthetic school professional',document_type='curriculum',received_at=utcnow().isoformat(),text=text))
    assert response.status_code==201,response.text
    row=response.json()
    return {'kind':'curriculum_document','source_id':row['id'],'revision':row['revision'],'digest':row['digest']},row


def resource_content(**changes):
    value={'title':'Synthetic bead presentation','author':'Synthetic author','original_provenance':'Synthetic original presentation A','method':'Montessori presentation','preparation':'Prepare one tray','instructions':['Present the bead sequence','Offer independent practice'],'subjects':['mathematics'],'skills':['counting'],'tags':['beads'],'age_min':6,'age_max':12,'duration_minutes':30,'group_min':1,'group_max':4,'prerequisites':['Recognises the first three quantities'],'material_ids':[],'sources':[],'rights':{'license_name':'Synthetic school owned','rights_basis':'Synthetic documented authorship','valid_from':'2026-01-01','valid_until':None,'read':True,'use':True,'copy':True,'ai':False,'share_team':True,'share_school':True}}
    value.update(changes);return value


def resource(client,ids,h,**changes):
    response=client.post(path(ids)+'/resources',headers=h,json=retry(content=resource_content(**changes)))
    assert response.status_code==201,response.text
    return response.json()


def share(client,ids,h,row,visibility='school',**changes):
    payload=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic sharing and license checked',visibility=visibility,**changes)
    response=client.post(path(ids)+f'/resources/{row["id"]}/sharing',headers=h,json=payload)
    assert response.status_code==200,response.text
    return response.json()


def scheme(client,ids,h,pedagogy='public'):
    ref,_=source(client,ids,h)
    content={'title':'Synthetic approved scheme','pedagogy':pedagogy,'valid_from':'2026-01-01','valid_until':'2027-12-31','goals':[{'code':'READ1','subject':'reading','description':'Read meaningful words','age_min':6,'age_max':12}],'subject_allocations':[{'subject':'reading','minutes':180,'period_description':'Synthetic week'}],'assessment_rules':[{'subject':'reading','assessment_form':'Dated observation','scale_description':'Narrative without numeric grade','completion_rule':'Human-reviewed documented development','exception_basis':'Synthetic approved Montessori assessment reference' if pedagogy=='montessori' else None}],'sources':[ref]}
    response=client.post(path(ids)+'/schemes',headers=h,json=retry(content=content));assert response.status_code==201,response.text
    row=response.json();payload=expected(row,revision_id=row['content']['id'],content_digest=row['content']['content_digest'],reason='Synthetic original and assessment scheme checked',approval_reference='Synthetic dated school approval record',approved_on=date.today().isoformat())
    response=client.post(path(ids)+f'/schemes/{row["id"]}/review',headers=h,json=payload);assert response.status_code==200,response.text
    return response.json(),content


def plan_content(scheme_row,**changes):
    value={'title':'Synthetic mixed-age continents theme','group_name':'Synthetic ages 6–12','school_year':'2026-2027','age_min':6,'age_max':12,'valid_from':'2026-08-01','valid_until':'2027-06-30','themes':[{'id':key(),'title':'Continents','valid_from':'2026-10-01','valid_until':'2026-11-30','learning_objectives':['Explore continents'],'curriculum_references':[{'scheme_revision_id':scheme_row['content']['id'],'goal_code':'READ1'}],'activities':['Read adapted continent cards'],'material_ids':[]}],'imported_sources':[],'import_notes':None}
    value.update(changes);return value


def class_plan(client,ids,h,content):
    response=client.post(path(ids)+'/class-plans',headers=h,json=retry(content=content));assert response.status_code==201,response.text
    return response.json()


def publish(client,ids,h,row):
    response=client.post(path(ids)+f'/class-plans/{row["id"]}/publish',headers=h,json=expected(row,revision_id=row['content']['id'],content_digest=row['content']['content_digest'],periods_checked=True,references_checked=True,reason='Synthetic periods and exact goals checked'))
    assert response.status_code==200,response.text
    return response.json()
