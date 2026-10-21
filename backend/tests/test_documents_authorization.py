"""Derivative content uses native reader/approver/assigned-section scope."""
import pytest
from sqlalchemy import select
from documents_fixtures import generated_documents,document_wire,documents_env,assessment_env,curriculum_env,teaching_env,env,login,path,expected,revised,transition,evidence
from test_documents_generation import generate,diff,selection
from spesped.contexts.identity.models import StaffAssignment,AuthorityGrant
from spesped.contexts.platform.models import ModelRelease

def selected(e):
    job=generate(e);proposal=diff(e,job)
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=selection(e,proposal));assert response.status_code==200,response.text
    e.row=response.json();return e.row

def narrow(e,*,write=False,read=True,ai=False):
    with e.factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==e.ids['teacher'])):
            assignment.actions=[v for v in assignment.actions if not ((not write and v=='documents.write') or (not read and v=='documents.read'))]
        if not ai:
            for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==e.ids['teacher'],AuthorityGrant.action=='ai.guardian_email_drafting')):grant.state='revoked'

@pytest.mark.parametrize('scope',['read_no_ai_or_write','read_no_write','approve_no_ai_or_write','assigned_section_only'])
def test_selected_generated_content_obeys_consumer_scope_without_generation(generated_documents,scope):
    e=generated_documents;row=selected(e)
    if scope=='approve_no_ai_or_write':
        row=revised(e.client,e.ids,e.h,row);row=transition(e.client,e.ids,e.h,row,'review')
    elif scope=='assigned_section_only':
        response=e.client.post(path(e.ids)+f'/cases/{row["id"]}/assignments',headers=e.h,json=expected(row,revision_id=row['revision_id'],section_key='body',contributor_id=e.ids['teacher']));assert response.status_code==201,response.text;row=response.json()
    narrow(e,read=scope!='assigned_section_only',ai=scope=='read_no_write');h=login(e.client,'teacher')
    if scope=='approve_no_ai_or_write':
        row=transition(e.client,e.ids,h,row,'approve');assert row['revision']['approval']['state']=='current'
    elif scope=='assigned_section_only':
        assert e.client.get(path(e.ids)+f'/cases/{row["id"]}').status_code==403
        route=path(e.ids)+f'/cases/{row["id"]}/contribution-workspace'
        response=e.client.get(route);assert response.status_code==200,response.text;workspace=response.json()
        assert [s['key'] for s in workspace['assigned_sections']]==['body'] and 'content' not in workspace and 'subject' not in workspace
        response=e.client.post(path(e.ids)+f'/cases/{row["id"]}/contributions',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='body',kind='checked',text='Synthetic assigned generated section checked'));assert response.status_code==201,response.text
        assert [s['key'] for s in response.json()['assigned_sections']]==['body']
    else:
        response=e.client.get(path(e.ids)+f'/cases/{row["id"]}');assert response.status_code==200,response.text
        assert response.json()['revision']['content'] is not None and response.json()['revision']['source_status']=='current'
    # Processing recall still invalidates the selected derivative for every
    # legitimate consumer without asking that consumer to become a generator.
    with e.factory.begin() as db:db.get(ModelRelease,e.release).state='revoked'
    if scope=='assigned_section_only':
        assert e.client.get(route).status_code==409
    else:
        response=e.client.get(path(e.ids)+f'/cases/{row["id"]}');assert response.status_code==200,response.text;assert response.json()['revision']['content'] is None

def test_reader_source_scope_still_controls_selected_generated_text(generated_documents):
    e=generated_documents;evidence(e.client,e.ids,e.h);e.row=revised(e.client,e.ids,e.h,e.row);row=selected(e)
    narrow(e);login(e.client,'teacher')
    assert e.client.get(path(e.ids)+f'/cases/{row["id"]}').json()['revision']['content'] is not None
    with e.factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==e.ids['teacher'])):assignment.actions=[v for v in assignment.actions if v!='evidence.read']
    response=e.client.get(path(e.ids)+f'/cases/{row["id"]}');assert response.status_code==200,response.text
    assert response.json()['revision']['content'] is None and response.json()['revision']['snapshot'] is None

def test_assigned_section_status_withholds_uncited_late_source_coordinates(generated_documents):
    import json
    e=generated_documents;row=selected(e)
    response=e.client.post(path(e.ids)+f'/cases/{row["id"]}/assignments',headers=e.h,json=expected(row,revision_id=row['revision_id'],section_key='body',contributor_id=e.ids['teacher']));assert response.status_code==201,response.text
    _,item=evidence(e.client,e.ids,e.h);narrow(e,read=False);login(e.client,'teacher')
    response=e.client.get(path(e.ids)+f'/cases/{row["id"]}/contribution-workspace');assert response.status_code==200,response.text
    workspace=response.json();assert workspace['source_status']['state']=='review_required' and workspace['source_status']['late_sources']==[]
    assert item['id'] not in json.dumps(workspace) and workspace['sources']==[]
