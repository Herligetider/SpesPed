from datetime import datetime,timedelta,date
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from spesped.domain import canonical_content_digest
from spesped.contexts.administration import models as m
from spesped.contexts.entitlements.models import DecisionProvision
from spesped.auth import Actor
from spesped.contexts.teaching.ports import QualificationRequest
from administration_fixtures import *
from plans_fixtures import evidence,support_case,confirmed_decision
from teaching_fixtures import actual,ordinary_goal
from assessment_fixtures import statement,statement_content
from curriculum_fixtures import scheme

def test_native_teaching_actual_full_interval_exact_decision_and_source_recall(administration_env):
    client,factory,app,ids=administration_env;h=login(client)
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h);decision=confirmed_decision(client,ids,h,case,binding)
    goal,_=ordinary_goal(client,ids,h);payload=actual(ids,{'a':goal});q,r=prerequisites(client,ids,h)
    reference={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']}
    payload['participants'][0].update(category='individually_adapted_education',provision=reference,counting_basis='learner_time')
    payload['staff'][0]['category']='individually_adapted_education'
    with factory() as db:
        provision=db.get(DecisionProvision,reference['provision_id'])
        fields=('id','decision_revision_id','category','organization','competence','effective_from','effective_until','source')
        provision_digest=canonical_content_digest(jsonable_encoder({f:getattr(provision,f) for f in fields}))
    req=QualificationRequest(school_id=ids['school'],learner_id=ids['a'],staff_id=ids['reviewer'],**reference,provision_digest=provision_digest,occurred_at=payload['occurred_at'],ended_at=datetime.fromisoformat(payload['occurred_at'])+timedelta(minutes=30))
    url=base(ids)+'/teaching/deliveries'
    assert client.post(url,headers=h,json=retry(content=payload)).status_code==409
    row=create(client,ids,h,{'kind':'teaching_review','request':req.model_dump(mode='json'),'qualification':ref(q),'responsibility':ref(r),'source':source(),**period()});row=approve(client,ids,h,row)
    response=client.post(url,headers=h,json=retry(content=payload));assert response.status_code==201,response.text
    delivery=response.json();assert delivery['participants'][0]['support_assessment']=='assessed'
    with factory() as db:
        port=NativeQualificationReadPort()
        assert port.resolve(db,Actor(ids['reviewer']),req).state=='reviewed_current'
        assert port.resolve(db,Actor(ids['reviewer']),req.model_copy(update={'ended_at':req.ended_at+timedelta(minutes=1)})).state=='unresolved'
    # Replacing a current responsibility revision invalidates exact prior proofs;
    # source history and the recorded actual remain immutable.
    private=client.get(path(ids)+f'/{r["id"]}?private=true').json()
    response=client.post(path(ids)+f'/{r["id"]}/revisions',headers=h,json=expected(r,content={**private['content'],'responsibility':'assistant_support'}));assert response.status_code==200,response.text
    fresh=client.get(url+'/'+delivery['id']).json()
    assert fresh['participants'][0]['support_assessment']=='unassessed'
    assert fresh['occurred_at']==delivery['occurred_at']
    with factory() as db:assert db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==row['revision_id'])).outcome=='eligible'

def policy(client,ids,h,sc,**changes):
    content={'kind':'assessment_policy','learner_id':ids['a'],'subject':'reading','scheme_revision_id':sc['content']['id'],'completion':'ongoing','exemption':'not_exempt','grade_policy':'optional','grade_values':['A','B','C'],'source':source(),**period(),**changes}
    return approve(client,ids,h,create(client,ids,h,content))

def test_native_subject_policy_distinct_finalize_grade_and_recall(administration_env):
    client,factory,app,ids=administration_env;h=login(client);sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    q,r=prerequisites(client,ids,h);p=policy(client,ids,h,sc)
    competence={'reference':{'kind':'evidence','id':binding['evidence_id'],'revision':binding['evidence_revision'],'link_id':binding['link_id']},'curriculum_goal_code':'READ1','role':'subject_competence','relevance':'Synthetic human selected evidence'}
    row=statement(client,ids,h,sc,content=statement_content(basis=[competence]))
    req={'school_id':ids['school'],'learner_id':ids['a'],'person_id':ids['reviewer'],'purpose':'statement_finalize','exact_revision_id':row['revision_id'],'exact_digest':row['content_digest'],'starts_on':row['starts_on'],'ends_on':row['ends_on'],'subject':'reading','scheme_revision_id':sc['content']['id']}
    final=professional_review(client,ids,h,req,q,r,p)
    command=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic qualified subject teacher finalizes selected exact subject basis',contribution_ids=[],grade='B')
    url=assessment_path(ids)+f'/statements/{row["id"]}/finalize'
    assert client.post(url,headers=h,json=command).status_code==409
    grade=professional_review(client,ids,h,{**req,'purpose':'grade_set'},q,r,p)
    invalid={**command,'request_key':str(uuid4()),'grade':'Z'}
    assert client.post(url,headers=h,json=invalid).status_code==409
    response=client.post(url,headers=h,json=command);assert response.status_code==200,response.text
    finalized=response.json();assert finalized['finalization']['grade']=='B' and finalized['finalization_authority_status']=='reviewed_current'
    # Revoking the reviewed subject policy preserves final historical approval.
    response=client.post(path(ids)+f'/{p["id"]}/revoke',headers=h,json=expected(p,reason='Synthetic subject decision recalled'));assert response.status_code==200
    current=client.get(assessment_path(ids)+f'/statements/{row["id"]}').json()
    assert current['state']=='finalized' and current['finalization']==finalized['finalization']
    assert current['finalization_authority_status']=='unassessed'
