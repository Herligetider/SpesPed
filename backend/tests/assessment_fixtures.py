"""Synthetic BC09 fixtures over real BC02/05/06/07 owner workflows."""
from datetime import date,timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from curriculum_fixtures import curriculum_env,teaching_env,env,login,ordinary_goal,scheme,source
from plans_fixtures import base,key,retry,expected,evidence
from spesped.contexts.assessment.router import router
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.db import utcnow

class SyntheticAssessmentAuthority:
    """Future J19 contract fixture; deliberately never a production adapter."""
    def __init__(self):
        self.state='reviewed_current';self.exemption='not_exempt';self.completion='ongoing';self.grade_policy='optional';self.values=['A','B','C'];self.wrong=False;self.calls=[]
        self.review_id=uuid4();self.source_id=uuid4();self.reviewed_at=utcnow()
    def resolve(self,db,actor,request):
        from spesped.contexts.assessment.ports import AuthorityResult,AuthoritySource
        self.calls.append(request)
        if self.wrong:request=request.model_copy(update={'person_id':uuid4()})
        return AuthorityResult(request=request,state=self.state,review_id=self.review_id,reviewed_by=actor.user_id,reviewed_at=self.reviewed_at,effective_from=date(2020,1,1),effective_until=date(2035,12,31),sources=[AuthoritySource(record_id=self.source_id,revision=1,digest='a'*64)],exemption=self.exemption,completion=self.completion,grade_policy=self.grade_policy,grade_values=self.values)

@pytest.fixture
def assessment_env(curriculum_env):
    client,factory,app,ids=curriculum_env
    if not any(getattr(r,'path','').endswith('/assessment/instruments') for r in app.routes):app.include_router(router)
    with factory.begin() as db:
        for name in ('reviewer','teacher'):
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids[name])):
                assignment.actions=list(set(assignment.actions)|{'assessment.read','assessment.write','assessment.review','assessment.contribute','assessment.finalize','assessment.grade','assessment.communicate'})
            for action in ('assessment.instrument.read','assessment.instrument.manage','assessment.instrument.review','assessment.finalize','assessment.grade'):
                db.add(AuthorityGrant(school_id=ids['school'],user_id=ids[name],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    app.state.assessment_authority_port=SyntheticAssessmentAuthority()
    return client,factory,app,ids

def path(ids):return base(ids)+'/assessment'
def conditions(**changes):
    return {'method':'Synthetic timed word reading','language':'Norwegian','support':'Synthetic visual cue','adaptations':[],'context':'Synthetic quiet room','condition_codes':['instruction_reviewed'],**changes}
def instrument(client,ids,h,guidance=True):
    ref,_=source(client,ids,h,'Synthetic instrument manual, scale and interval guidance')
    content={'title':'Synthetic reading instrument','publisher_version':'synthetic-1','instructions':'Synthetic instruction; no real norm claims','scales':[{'code':'raw','label':'Correct synthetic words','kind':'numeric','minimum':'0','maximum':'20'}],'eligible_conditions':['instruction_reviewed'],'qualification_requirement':'Synthetic reviewed practitioner qualification required','license_basis':'Synthetic school-owned test','license_from':'2020-01-01','license_until':'2035-12-31','permitted_use':True,'sources':[ref],'reassessment':{'minimum_days':30,'rationale':'Synthetic manual minimum interval','source':ref} if guidance else None}
    result=client.post(path(ids)+'/instruments',headers=h,json=retry(content=content));assert result.status_code==201,result.text
    row=result.json();result=client.post(path(ids)+f'/instruments/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact version, scale, license and manual checked'));assert result.status_code==200,result.text
    return result.json(),content

def planned(client,ids,h,instrument_row,**changes):
    result=client.post(path(ids)+'/administrations',headers=h,json=retry(learner_id=ids['a'],instrument_revision_id=instrument_row['revision_id'],planned_on=date.today().isoformat(),purpose='Synthetic reading follow-up',conditions=conditions(),**changes));assert result.status_code==201,result.text
    return result.json()
def started(client,ids,h,row):
    result=client.post(path(ids)+f'/administrations/{row["id"]}/start',headers=h,json=expected(row,occurred_at=(utcnow()-timedelta(hours=2)).isoformat()));assert result.status_code==200,result.text
    return result.json()
def recorded(client,ids,h,row,**changes):
    result=client.post(path(ids)+f'/administrations/{row["id"]}/results',headers=h,json=expected(row,occurred_at=(utcnow()-timedelta(hours=1)).isoformat(),raw={'raw':'12'},conditions=conditions(),**changes));assert result.status_code==201,result.text
    return result.json()
def reviewed(client,ids,h,row,**changes):
    result=client.post(path(ids)+f'/administrations/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['result']['id'],content_digest=row['result']['digest'],reason='Synthetic exact raw record reviewed',interpretation='Synthetic result only, with recorded support',comparison='separate',comparison_reason='No direct comparison claimed',**changes));assert result.status_code==200,result.text
    return result.json()
def observation(client,ids,h,goal_id,**changes):
    content={'learner_id':ids['a'],'goal_revision_id':goal_id,'occurred_at':(utcnow()-timedelta(hours=1)).isoformat(),'observation':'Synthetic observed one independent word','support':'Synthetic visual cue','interpretation':None,'next_step':None,'input_method':'manual','transcript_reviewed':False,**changes}
    result=client.post(base(ids)+'/teaching/observations',headers=h,json=retry(save=True,content=content));assert result.status_code==201,result.text
    return result.json()
def finding(**changes):return {'judgement':'Synthetic cautious human judgement from the selected sources','outcome':'continue','missing_evidence':[],'contradictory_evidence':[],'comparison_limitations':[],'tasks':[],**changes}
def progress(client,ids,h,goal_id,**changes):
    result=client.post(path(ids)+'/progress-reviews',headers=h,json=retry(**{'learner_id':ids['a'],'goal_revision_id':goal_id,'starts_at':(utcnow()-timedelta(days=1)).isoformat(),'ends_at':utcnow().isoformat(),'finding':finding(),**changes}));assert result.status_code==201,result.text
    return result.json()
def statement_content(**changes):return {'judgement':'Synthetic subject competence judgement','next_work':'Practise synthetic words','basis':[],'missing_evidence':[],'completion':'ongoing','exemption':'not_exempt','expected_contributors':[],**changes}
def statement(client,ids,h,sc,**changes):
    result=client.post(path(ids)+'/statements',headers=h,json=retry(**{'learner_id':ids['a'],'scheme_revision_id':sc['content']['id'] if sc else None,'subject':'reading','assessment_type':'half_year','starts_on':'2026-10-01','ends_on':'2026-10-21','content':statement_content(),**changes}));assert result.status_code==201,result.text
    return result.json()
