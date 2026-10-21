from datetime import date,timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select,event,text
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.errors import DomainError
from spesped.contexts.administration import models as m
from spesped.contexts.administration.adapters import NativeAssessmentAuthorityPort
from spesped.contexts.assessment.ports import AuthorityRequest,authority_basis
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment,AuditRecord
from administration_fixtures import *

def bound(db,app):
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    db.info['curriculum_source_port']=EvidenceSourceReadPort(app.state.evidence_storage)
    db.info['assessment_authority_port']=NativeAssessmentAuthorityPort()
    return db


def test_native_http_instrument_result_review_and_metadata_privacy(administration_env):
    client,factory,app,ids=administration_env;h=login(client)
    inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    request=instrument_request(ids,inst)
    with factory() as db:
        bound(db,app)
        assert NativeAssessmentAuthorityPort().resolve(db,Actor(ids['reviewer']),AuthorityRequest(**request)).state=='unresolved'
    review=professional_review(client,ids,h,request,q,r)
    assert review['eligibility']=='reviewed_current'
    assert 'content' not in review and 'reason' not in review['review']
    assert client.get(path(ids)+f'/{q["id"]}?private=true').json()['source_verification']=='human_reference_only'
    row=planned(client,ids,h,inst);row=started(client,ids,h,row);row=recorded(client,ids,h,row)
    result_request={**request,'purpose':'result_review','exact_revision_id':row['result']['id'],'exact_digest':row['result']['digest']}
    professional_review(client,ids,h,result_request,q,r)
    row=reviewed(client,ids,h,row)
    assert row['state']=='professionally_reviewed' and row['review_authority_status']=='reviewed_current'
    # A fresh application port instance resolves persisted records without fixtures.
    with factory() as db:
        bound(db,app)
        basis=authority_basis(db,Actor(ids['reviewer']),AuthorityRequest(**result_request),required=True)
        assert basis['state']=='reviewed_current' and len(basis['sources'])==3
        events=db.scalars(select(m.ProfessionalEvent)).all()
        assert events and all(e.schema_version==1 and e.correlation_id and e.causation_id and e.occurred_at<=e.recorded_at for e in events)
        assert all(set(e.payload)=={'kind','revision','state'} for e in events)
    teacher=login(client,'teacher')
    assert client.get(path(ids)+f'/{q["id"]}?private=true').status_code==403
    assert client.get(path(ids)+f'/{review["id"]}').status_code==200

def test_revocation_current_cache_pending_changes_and_historic_review(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    req=AuthorityRequest(**instrument_request(ids,inst));review=professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    port=NativeAssessmentAuthorityPort()
    with factory() as db:
        bound(db,app)
        assert port.resolve(db,Actor(ids['reviewer']),req).state=='reviewed_current'
        cached=db.get(m.ProfessionalRecord,q['id']);cached.state='revoked'
        with pytest.raises(DomainError,match='pending'):port.resolve(db,Actor(ids['reviewer']),req)
        assert cached in db.dirty and cached.state=='revoked';db.rollback()
        cached=db.get(m.ProfessionalRecord,q['id'])
        response=client.post(path(ids)+f'/{q["id"]}/revoke',headers=h,json=expected(q,reason='Synthetic HR evidence recalled'));assert response.status_code==200,response.text
        assert port.resolve(db,Actor(ids['reviewer']),req).state=='unresolved'
        # The reader neither refreshes nor overwrites retained caller identities.
        assert cached.state=='reviewed'
        historical=client.get(path(ids)+f'/{review["id"]}/history').json()['items'][0]
        assert historical['review']['outcome']=='eligible'

def test_exact_scope_conflicts_and_unauthorized_replay(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    req=AuthorityRequest(**instrument_request(ids,inst));review=professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    with factory() as db:
        bound(db,app)
        port=NativeAssessmentAuthorityPort();actor=Actor(ids['reviewer'])
        assert port.resolve(db,actor,req.model_copy(update={'person_id':uuid4()})).state=='unresolved'
        assert port.resolve(db,actor,req.model_copy(update={'learner_id':__import__('uuid').UUID(ids['b'])})).state=='unresolved'
        assert port.resolve(db,actor,req.model_copy(update={'exact_digest':'b'*64})).state=='unresolved'
        with pytest.raises(DomainError):port.resolve(db,Actor(ids['teacher']),req.model_copy(update={'school_id':__import__('uuid').UUID(ids['other_school'])}))
    # Multiple active determinations cannot be resolved by last-write-wins.
    other=professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='unresolved'
    response=client.post(path(ids)+f'/{other["id"]}/revoke',headers=h,json=expected(other,reason='Synthetic duplicate explicitly withdrawn'));assert response.status_code==200
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='reviewed_current'
    content={'kind':'qualification','person_id':ids['reviewer'],'qualification':'Synthetic certificate','purposes':['teaching'],'source':source(),**period()};command=retry(content=content)
    response=client.post(path(ids),headers=h,json=command);assert response.status_code==201
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='professional.evidence.manage')):grant.state='revoked'
    assert client.post(path(ids),headers=h,json=command).status_code==403

def test_assignment_and_reviewer_revocation_invalidate_current_projection(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    req=AuthorityRequest(**instrument_request(ids,inst));professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    with factory() as retained:
        bound(retained,app)
        retained.scalars(select(AuthorityGrant)).all()
        assert NativeAssessmentAuthorityPort().resolve(retained,Actor(ids['reviewer']),req).state=='reviewed_current'
        with factory.begin() as db:
            for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='professional.evidence.review')):grant.state='revoked'
        assert NativeAssessmentAuthorityPort().resolve(retained,Actor(ids['reviewer']),req).state=='unresolved'
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='professional.evidence.review')):grant.state='active'
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a'])):assignment.valid_until=date.today()-timedelta(days=1)
    with factory() as db:
        bound(db,app)
        with pytest.raises(DomainError):NativeAssessmentAuthorityPort().resolve(db,Actor(ids['reviewer']),req)
