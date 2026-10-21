"""Current rewrite coordinates do not release recalled text or source material."""
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from documents_fixtures import (documents_env,generated_documents,document_wire,assessment_env,curriculum_env,
    teaching_env,env,login,path,base,create,evidence,revised,expected,key)
from test_documents_generation import generate,diff,selection
from spesped.auth import Actor
from spesped.contexts.documents import service as svc,models as m
from spesped.contexts.identity.models import StaffAssignment,AuthorityGrant,UserAccount
from spesped.contexts.platform.models import ModelRelease
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.db import utcnow
from spesped.errors import DomainError
from spesped.main import create_app

FIELDS={'document_id','learner_id','kind','state','version','revision_id','revision','content_digest','section_keys','generated_fields'}

def selected(e):
    job=generate(e);proposal=diff(e,job)
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=selection(e,proposal))
    assert response.status_code==200,response.text
    e.row=response.json()
    return job

def recovery(client,ids,row):
    response=client.get(path(ids)+f'/cases/{row["id"]}/recovery')
    assert response.status_code==200,response.text
    data=response.json();assert set(data)==FIELDS
    return data

@pytest.mark.parametrize('recall',['model','source'])
def test_recalled_content_yields_coordinates_only_to_current_writer(generated_documents,recall):
    e=generated_documents
    binding,item=evidence(e.client,e.ids,e.h,text='Synthetic withheld source canary, never recovery metadata')
    e.row=revised(e.client,e.ids,e.h,e.row)
    job=selected(e)
    with e.factory.begin() as db:
        if recall=='model': db.get(ModelRelease,e.release).state='revoked'
        else: db.get(SourceSubjectLink,binding['link_id']).revoked_at=utcnow()
    unavailable=e.client.get(path(e.ids)+f'/cases/{e.row["id"]}').json()['revision']
    assert unavailable['content'] is None and unavailable['snapshot'] is None and 'lineage' not in unavailable
    data=recovery(e.client,e.ids,e.row)
    assert data['version']==e.row['version'] and data['revision_id']==e.row['revision_id'] and data['content_digest']==e.row['content_digest']
    assert data['section_keys']==['body','next_steps'] and data['generated_fields']==['body','subject']
    encoded=json.dumps(data)
    for forbidden in ('Synthetic withheld source','Synthetic source-backed review text','Synthetic editable period email',job['id'],item['id'],binding['link_id']):
        assert forbidden not in encoded
    # A writer needs neither generation nor source reading authority just to
    # discover edit coordinates. Those rights remain required by their owners.
    with e.factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==e.ids['reviewer'])):
            assignment.actions=['documents.write']
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==e.ids['reviewer'],AuthorityGrant.action=='ai.guardian_email_drafting')):
            grant.state='revoked'
    assert recovery(e.client,e.ids,e.row)==data
    assert e.client.get(path(e.ids)+f'/cases/{e.row["id"]}').status_code==403
    assert e.client.get(path(e.ids)+f'/cases/{e.row["id"]}/suggestions/{job["id"]}/diff').status_code==403
    # Native fresh application registration; no fixture source/model adapters
    # are needed or installed in this metadata-only application.
    fresh=create_app(e.app.state.settings,e.factory)
    assert '/api/v1/schools/{school_id}/documents/cases/{identity}/recovery' in fresh.openapi()['paths']
    with TestClient(fresh) as client:
        login(client)
        assert recovery(client,e.ids,e.row)==data

def test_recovery_rejects_reader_approver_contributor_wrong_pupil_and_school(documents_env):
    client,factory,app,ids=documents_env;h=login(client);row=create(client,ids,h)
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a']))
        assignment.actions=['documents.read','documents.review','documents.contribute']
    login(client,'teacher')
    route=path(ids)+f'/cases/{row["id"]}/recovery'
    assert client.get(path(ids)+f'/cases/{row["id"]}').status_code==200
    assert client.get(route).status_code==403  # Approval authority is not write authority.
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a']))
        assignment.actions=['documents.write'];assignment.learner_id=ids['b']
    assert client.get(route).status_code==403
    login(client)
    assert client.get(f'/api/v1/schools/{ids["other_school"]}/documents/cases/{row["id"]}/recovery').status_code==403
    assert client.get(path(ids)+f'/cases/{uuid4()}/recovery').status_code==403
    assert recovery(client,ids,row)['generated_fields']==[]

@pytest.mark.parametrize('recall',['model','source'])
def test_independent_rewrite_uses_exact_coordinates_and_metadata_follows_supersession(generated_documents,recall):
    e=generated_documents
    binding,_=evidence(e.client,e.ids,e.h,text='Synthetic old source is never copied into independent recovery')
    e.row=revised(e.client,e.ids,e.h,e.row);selected(e)
    with e.factory.begin() as db:
        if recall=='model': db.get(ModelRelease,e.release).state='revoked'
        else: db.get(SourceSubjectLink,binding['link_id']).revoked_at=utcnow()
    previous=recovery(e.client,e.ids,e.row)
    content={'subject':'Synthetic newly authored independent subject',
        'sections':[{'key':field,'text':'Synthetic new independent human account; missing evidence is explicitly unresolved',
            'source_keys':[],'missing_inputs':[]} for field in previous['section_keys']],
        'handled_gaps':{}}
    document={**e.row['revision']['configuration'],'request_key':key(),'content':content,
        'selection':{'discover_evidence':False,'discover_observations':False}}
    with e.factory() as caller:
        cached=caller.get(m.DocumentCase,e.row['id'])
        old_number=cached.current_revision
        response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/revisions',headers=e.h,json=expected(e.row,
            document=document,reason='Human independently replaces each exact generated field after processing recall',
            sever_generation_fields=previous['generated_fields']))
        assert response.status_code==201,response.text
        row=response.json();assert row['revision']['lineage']=={} and row['revision']['content']==content
        assert row['state']=='draft' and row['revision']['approval'] is None and row['legal_finalization']=='not_finalized'
        direct=svc.recovery_metadata(caller,Actor(e.ids['reviewer']),e.ids['school'],row['id'])
        assert direct['revision_id']==row['revision_id'] and direct['version']==row['version']
        assert direct['revision']==old_number+1 and direct['generated_fields']==[]
        assert cached.current_revision==old_number and caller.in_transaction()
    current=recovery(e.client,e.ids,row)
    assert current['revision_id']!=previous['revision_id'] and current['content_digest']!=previous['content_digest']
    assert current['section_keys']==previous['section_keys'] and current['generated_fields']==[]
    historical=e.client.get(path(e.ids)+f'/cases/{row["id"]}/revisions').json()['items']
    assert next(v for v in historical if v['id']==previous['revision_id'])['content'] is None

def test_recovery_preserves_caller_pending_flushed_state_and_rechecks_cached_authority(documents_env):
    client,factory,app,ids=documents_env;h=login(client);row=create(client,ids,h)
    actor=Actor(ids['reviewer'])
    with factory() as caller:
        events=[]
        event.listen(caller,'before_flush',lambda *_:events.append('flush'))
        event.listen(caller,'after_commit',lambda *_:events.append('commit'))
        event.listen(caller,'after_rollback',lambda *_:events.append('rollback'))
        user=caller.get(UserAccount,ids['reviewer']);user.display_name='Synthetic staged caller value'
        with pytest.raises(DomainError) as error:svc.recovery_metadata(caller,actor,ids['school'],row['id'])
        assert error.value.code=='dependency_pending'
        assert user in caller.dirty and user.display_name=='Synthetic staged caller value' and events==[]
        caller.rollback()
        user=caller.get(UserAccount,ids['reviewer']);user.display_name='Synthetic flushed caller value';caller.flush();events.clear()
        assert svc.recovery_metadata(caller,actor,ids['school'],row['id'])['revision_id']==row['revision_id']
        assert user.display_name=='Synthetic flushed caller value' and caller.in_transaction() and events==[]
        caller.rollback()
    with factory() as caller:
        assert caller.get(UserAccount,ids['reviewer']).display_name=='Synthetic reviewer'
        cached=caller.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a']))
        with factory.begin() as db:
            assignment=db.get(StaffAssignment,cached.id);assignment.actions=[v for v in assignment.actions if v!='documents.write']
        with pytest.raises(DomainError) as error:svc.recovery_metadata(caller,actor,ids['school'],row['id'])
        assert error.value.status_code==403 and 'documents.write' in cached.actions and caller.in_transaction()
