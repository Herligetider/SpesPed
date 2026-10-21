"""Synthetic professional review through native authenticated HTTP workflows."""
from datetime import date,timedelta,datetime,time
from zoneinfo import ZoneInfo
from uuid import uuid4
import pytest
from sqlalchemy import select
from assessment_fixtures import assessment_env,curriculum_env,teaching_env,env,login,instrument,planned,started,recorded,reviewed,path as assessment_path
from plans_fixtures import base,retry,expected
from spesped.contexts.identity.models import StaffAssignment,AuthorityGrant
from spesped.contexts.administration.router import router
from spesped.contexts.administration.adapters import NativeAssessmentAuthorityPort,NativeQualificationReadPort
from spesped.db import utcnow

ACTIONS=['professional.read','professional.evidence.manage','professional.evidence.read','professional.evidence.review','professional.responsibility.manage','professional.responsibility.review','professional.policy.manage','professional.policy.review','professional.review.manage',*[f'professional.review.{p}' for p in ['teaching','instrument_administration','result_review','statement_finalize','grade_set']]]
@pytest.fixture
def administration_env(assessment_env):
    client,factory,app,ids=assessment_env
    if not any(getattr(r,'path','').endswith('/professional-authority/records') for r in app.routes):app.include_router(router)
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id.in_([ids['reviewer'],ids['teacher']]))):
            assignment.actions=list(set(assignment.actions)|{'professional.read'});assignment.valid_from=date.today()-timedelta(days=90)
        for action in ACTIONS:
            db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['reviewer'],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    app.state.assessment_authority_port=NativeAssessmentAuthorityPort();app.state.teaching_qualification_port=NativeQualificationReadPort()
    return client,factory,app,ids

def path(ids):return base(ids)+'/professional-authority/records'
def source():return {'system':'Synthetic HR archive','identity':'HR-'+str(uuid4()),'version':'1','digest':'a'*64,'issued_on':(date.today()-timedelta(days=1)).isoformat(),'authority':'Synthetic explicitly delegated school verification','scope':'This named person or pupil and recorded purposes only','limitations':'Human reference check; external system is not automatically monitored'}
def period():
    zone=ZoneInfo('Europe/Oslo')
    return {'effective_from':datetime.combine(date.today()-timedelta(days=60),time.min,zone).isoformat(),'effective_until':datetime.combine(date.today()+timedelta(days=2),time.min,zone).isoformat()}
def create(client,ids,h,content):
    r=client.post(path(ids),headers=h,json=retry(content=content));assert r.status_code==201,r.text
    return r.json()
def approve(client,ids,h,row,outcome='eligible'):
    r=client.post(path(ids)+f'/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic delegated professional checked authoritative original reference, exact scope, limitations and effective bounds',source_checked_on=date.today().isoformat(),outcome=outcome));assert r.status_code==200,r.text
    return r.json()
def ref(row):return {'record_id':row['id'],'revision':row['revision'],'digest':row['content_digest']}
def prerequisites(client,ids,h,person='reviewer'):
    q=create(client,ids,h,{'kind':'qualification','person_id':ids[person],'qualification':'Synthetic teaching and instrument certificate','purposes':['teaching','instrument_administration','result_review','statement_finalize','grade_set'],'source':source(),**period()});q=approve(client,ids,h,q)
    r=create(client,ids,h,{'kind':'responsibility','learner_id':ids['a'],'person_id':ids[person],'subject':'reading','responsibility':'responsible_teaching','source':source(),**period()});r=approve(client,ids,h,r)
    return q,r

def instrument_request(ids,row,person='reviewer'):
    return {'school_id':ids['school'],'learner_id':ids['a'],'person_id':ids[person],'purpose':'instrument_administration','exact_revision_id':row['revision_id'],'exact_digest':row['content_digest'],'starts_on':date.today().isoformat(),'ends_on':date.today().isoformat(),'subject':None,'scheme_revision_id':None}
def professional_review(client,ids,h,request,q,r,policy=None):
    content={'kind':'assessment_review','request':request,'qualification':ref(q),'responsibility':ref(r),'policy':ref(policy) if policy else None,'source':source(),**period()}
    row=create(client,ids,h,content);return approve(client,ids,h,row)
