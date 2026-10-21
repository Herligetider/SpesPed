"""Current negative determinations and exact-purpose replay regression proofs."""
from datetime import date,timedelta
import pytest
from sqlalchemy import select,func
from fastapi.encoders import jsonable_encoder
from spesped.auth import Actor
from spesped.domain import canonical_content_digest
from spesped.contexts.administration import models as m
from spesped.contexts.identity.models import AuthorityGrant,AuditRecord
from spesped.contexts.assessment.ports import AuthorityRequest
from spesped.contexts.teaching.ports import QualificationRequest
from spesped.contexts.entitlements.models import DecisionProvision
from administration_fixtures import *
from test_professional_authority_native import bound
from plans_fixtures import evidence,support_case,confirmed_decision
from assessment_fixtures import statement
from curriculum_fixtures import scheme
from test_professional_authority_consumers import policy


def negative_review(client,factory,ids,h,kind,q,r):
    if kind=='assessment':
        instrument_row,_=instrument(client,ids,h)
        request=AuthorityRequest(**instrument_request(ids,instrument_row,person='teacher'))
        content={'kind':'assessment_review','request':request.model_dump(mode='json'),'qualification':ref(q),'responsibility':ref(r),'policy':None,'source':source(),**period()}
        return request,approve(client,ids,h,create(client,ids,h,content),outcome='ineligible'),NativeAssessmentAuthorityPort()
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h);decision=confirmed_decision(client,ids,h,case,binding)
    occurred=utcnow()-timedelta(hours=1)
    with factory() as db:
        provision=db.get(DecisionProvision,decision['provisions'][0]['id'])
        fields=('id','decision_revision_id','category','organization','competence','effective_from','effective_until','source')
        digest=canonical_content_digest(jsonable_encoder({f:getattr(provision,f) for f in fields}))
    request=QualificationRequest(school_id=ids['school'],learner_id=ids['a'],staff_id=ids['teacher'],decision_id=decision['id'],decision_revision_id=decision['content']['id'],provision_id=decision['provisions'][0]['id'],provision_digest=digest,occurred_at=occurred,ended_at=occurred+timedelta(minutes=30))
    content={'kind':'teaching_review','request':request.model_dump(mode='json'),'qualification':ref(q),'responsibility':ref(r),'source':source(),**period()}
    return request,approve(client,ids,h,create(client,ids,h,content),outcome='ineligible'),NativeQualificationReadPort()


@pytest.mark.parametrize('kind',['assessment','teaching'])
@pytest.mark.parametrize('withdrawal',['source_revision','reviewer'])
def test_negative_binding_requires_current_exact_dependencies(administration_env,kind,withdrawal):
    client,factory,app,ids=administration_env;h=login(client);q,r=prerequisites(client,ids,h,person='teacher')
    request,row,port=negative_review(client,factory,ids,h,kind,q,r)
    with factory() as db:
        assert port.resolve(bound(db,app),Actor(ids['reviewer']),request).state=='ineligible'
        historical=db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==row['revision_id']))
        original={c.name:getattr(historical,c.name) for c in historical.__table__.columns}
    assert client.get(path(ids)+f'/{row["id"]}').json()['eligibility']=='ineligible'
    if withdrawal=='source_revision':
        content=client.get(path(ids)+f'/{q["id"]}?private=true').json()['content']
        response=client.post(path(ids)+f'/{q["id"]}/revisions',headers=h,json=expected(q,content={**content,'qualification':'Synthetic corrected qualification source'}));assert response.status_code==200,response.text
    else:
        action='professional.review.teaching' if kind=='teaching' else 'professional.review.instrument_administration'
        with factory.begin() as db:
            for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action==action)):grant.state='revoked'
    with factory() as db:
        assert port.resolve(bound(db,app),Actor(ids['reviewer']),request).state=='unresolved'
        historical=db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==row['revision_id']))
        assert {c.name:getattr(historical,c.name) for c in historical.__table__.columns}==original
    metadata=client.get(path(ids)+f'/{row["id"]}').json()
    assert metadata['review']['outcome']=='ineligible' and metadata['eligibility']=='unresolved'


def counts(factory,record_id):
    with factory() as db:
        row=db.get(m.ProfessionalRecord,record_id)
        # A refused replay can add a security denial audit; it must never add
        # another successful professional action or any business artifact.
        return (row.version,row.state,row.current_revision,*(db.scalar(select(func.count()).select_from(model)) for model in (m.ProfessionalRevision,m.ProfessionalCheck,m.ProfessionalCommand,m.ProfessionalEvent)),db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action.like('professional.%'),AuditRecord.outcome=='success')))


@pytest.mark.parametrize('revoked_purpose',['statement_finalize','grade_set'])
def test_review_replay_authorizes_original_revision_purpose_only(administration_env,revoked_purpose):
    client,factory,app,ids=administration_env;h=login(client);sc,_=scheme(client,ids,h);q,r=prerequisites(client,ids,h);p=policy(client,ids,h,sc)
    target=statement(client,ids,h,sc)
    request={'school_id':ids['school'],'learner_id':ids['a'],'person_id':ids['reviewer'],'purpose':'statement_finalize','exact_revision_id':target['revision_id'],'exact_digest':target['content_digest'],'starts_on':target['starts_on'],'ends_on':target['ends_on'],'subject':'reading','scheme_revision_id':sc['content']['id']}
    content={'kind':'assessment_review','request':request,'qualification':ref(q),'responsibility':ref(r),'policy':ref(p),'source':source(),**period()}
    row=create(client,ids,h,content)
    command=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic original statement authority review',source_checked_on=date.today().isoformat(),outcome='eligible')
    endpoint=path(ids)+f'/{row["id"]}/review'
    response=client.post(endpoint,headers=h,json=command);assert response.status_code==200,response.text
    reviewed_row=response.json()
    response=client.post(path(ids)+f'/{row["id"]}/revisions',headers=h,json=expected(reviewed_row,content={**content,'request':{**request,'purpose':'grade_set'}}));assert response.status_code==200,response.text
    current=response.json();before=counts(factory,row['id'])
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.school_id==ids['school'],AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='professional.review.'+revoked_purpose)):grant.state='revoked'
    replay=client.post(endpoint,headers=h,json=command)
    assert replay.status_code==(403 if revoked_purpose=='statement_finalize' else 200),replay.text
    if replay.status_code==200:
        assert replay.json()['revision_id']==current['revision_id'] and replay.json()['state']=='draft'
    assert counts(factory,row['id'])==before
    with factory() as db:
        original=db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==row['revision_id']))
        assert original.outcome=='eligible' and original.authority_action=='professional.review.statement_finalize'
