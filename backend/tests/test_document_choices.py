"""Real HTTP choices use native scoped source owners on SQLite/PostgreSQL."""
from datetime import date, datetime, timedelta
import json
import pytest
from sqlalchemy import select, text
from fastapi.testclient import TestClient
from documents_fixtures import (documents_env, generated_documents, document_wire, assessment_env, curriculum_env,
    teaching_env, env, login, path, base, create, template, evidence, ordinary_goal, observation, expected, retry, key)
from spesped.auth import Actor
from spesped.contexts.identity.models import StaffAssignment, AuthorityGrant, GuardianRelationship, UserAccount
from spesped.contexts.documents import choices
from spesped.contexts.evidence.models import SourceSubjectLink, SourceItem
from spesped.errors import DomainError
from spesped.db import utcnow

def pick(client, ids, category, **changes):
    response = client.get(path(ids)+f'/learners/{ids["a"]}/choices/{category}',params={
        'kind':'guardian_email','starts_on':'2026-10-01','ends_on':'2026-10-21',**changes})
    assert response.status_code == 200, response.text
    return response.json()

def test_manual_choices_scope_eligibility_exact_templates_and_counts(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    t=template(client,ids,h)
    guardians=pick(client,ids,'guardians');assert guardians['total']==1
    relation=guardians['items'][0];assert relation['relationship_id']==ids['guardian_relation'] and relation['state']=='eligible_proposal'
    assert relation['display_name']=='Synthetic guardian' and relation['disclosure']=='not_authorized'
    assert all(word not in json.dumps(guardians) for word in ('@','restrictions','source_reference'))
    owners=pick(client,ids,'owners',limit=1);second=pick(client,ids,'owners',offset=1,limit=1)
    assert owners['total']==2 and second['total']==2
    assert owners['items'][0]['user_id']!=second['items'][0]['user_id']
    assert pick(client,ids,'owners',query='teacher')['total']==1
    assert pick(client,ids,'owners',query='%')['total']==0
    assert {v['user_id'] for v in pick(client,ids,'contributors')['items']}=={ids['reviewer'],ids['teacher']}
    assert pick(client,ids,'templates')['total']==0
    current=pick(client,ids,'templates',kind='local_semester_report')['items'][0]
    assert current['revision_id']==t['revision_id'] and current['sections'][0]['label']=='Summary'
    assert 'requirement_version_id' in current
    with factory.begin() as db:
        relation=db.get(GuardianRelationship,ids['guardian_relation']);relation.restrictions='Synthetic confidential restriction must never appear'
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'])):
            assignment.actions=[a for a in assignment.actions if a!='documents.write']
    assert pick(client,ids,'guardians')['items'][0]['state']=='unresolved'
    assert pick(client,ids,'owners')['total']==1
    # A school role and another pupil's assignment do not make an owner.
    login(client,'teacher')
    assert client.get(path(ids)+f'/learners/{ids["a"]}/choices/owners',params={'kind':'guardian_email','starts_on':'2026-10-01','ends_on':'2026-10-21'}).status_code==403
    login(client)
    with factory.begin() as db:db.get(SourceItem,t['content']['sources'][0]['source_id']).state='withdrawn'
    assert pick(client,ids,'templates',kind='local_semester_report')['total']==0
    assert client.get(path(ids)+f'/learners/{ids["a"]}/choices/guardians',params={'kind':'guardian_email','starts_on':'2026-10-22','ends_on':'2026-10-21'}).status_code==422

def test_source_choices_interval_background_native_revocation_and_pagination(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    binding,item=evidence(client,ids,h);evidence(client,ids,h,learner='b',text='Synthetic sibling must not leak')
    goal,_=ordinary_goal(client,ids,h)
    obs=observation(client,ids,h,goal,occurred_at='2026-10-15T23:59:59+02:00')
    observation(client,ids,h,goal,occurred_at='2026-10-16T00:00:00+02:00')
    result=pick(client,ids,'sources',starts_on='2026-10-10',ends_on='2026-10-15',limit=1)
    assert result['total']==1 and result['items'][0]['reference']['id']==obs['revision_id']
    assert result['items'][0]['classification']=='interval_fact' and result['period']['timezone']=='Europe/Oslo'
    assert pick(client,ids,'sources',starts_on='2026-10-10',ends_on='2026-10-15',offset=1)['items']==[]
    background=pick(client,ids,'sources',starts_on='2026-10-10',ends_on='2026-10-15',source_mode='background',source_starts_on='2026-09-01')
    assert background['total']==1 and background['items'][0]['reference']['id']==item['id']
    assert background['items'][0]['classification']=='background_reference'
    assert background['items'][0]['reference']['link_id']==binding['link_id']
    with factory.begin() as db:db.get(SourceSubjectLink,binding['link_id']).revoked_at=utcnow()
    assert pick(client,ids,'sources',source_mode='background',starts_on='2026-10-10')['total']==0
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a']))
        assignment.actions=[a for a in assignment.actions if a not in {'evidence.read','teaching.read','assessment.read'}]
    login(client,'teacher');assert pick(client,ids,'sources')['total']==0
    response=client.get(path(ids)+f'/learners/{ids["b"]}/choices/guardians',params={'kind':'guardian_email','starts_on':'2026-10-01','ends_on':'2026-10-21'})
    assert response.status_code==403

def test_actual_future_and_historical_goal_coordinates(documents_env,monkeypatch):
    from teaching_fixtures import basis,session,actual
    from plans_fixtures import activate
    from spesped.contexts.plans import service as plans
    from spesped.contexts.plans.generation import command_content
    from spesped.contexts.plans.models import PlanRevision
    client,factory,app,ids=documents_env;h=login(client);first_goal,first=ordinary_goal(client,ids,h)
    change=utcnow()+timedelta(minutes=1);monkeypatch.setattr(plans,'utcnow',lambda:change)
    with factory() as db:content=command_content(db,db.get(PlanRevision,first['content']['id']))
    content['effective_from']=change.isoformat();content['goals'][0]['effective_from']=change.isoformat()
    response=client.post(base(ids)+f'/education-plans/{first["id"]}/revisions',headers=h,json=expected(first,**content));assert response.status_code==201,response.text
    second=activate(client,ids,h,response.json());goal=second['content']['goals'][0]['id']
    found=pick(client,ids,'goals')['items'];assert {v['goal_revision_id'] for v in found}=={first_goal,goal}
    assert datetime.fromisoformat(found[0]['effective_period']['ends_at_exclusive'])==change
    def future_basis(goals):
        response=client.post(base(ids)+'/teaching/bases',headers=h,json=retry(planned_at=(change+timedelta(days=2)).isoformat(),
            duration_minutes=30,learners=[{'learner_id':ids[name],'goal_revision_ids':[value]} for name,value in goals.items()],theme='Synthetic future theme',arena='Synthetic room',materials=[]))
        assert response.status_code==201,response.text;return response.json()
    future=session(client,ids,h,future_basis({'a':goal}))
    other_goal,_=ordinary_goal(client,ids,h,learner='b')
    session(client,ids,h,future_basis({'a':goal,'b':other_goal}))
    result=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual(ids,{'a':first_goal})));assert result.status_code==201,result.text
    actuals=pick(client,ids,'actuals')['items'];assert len(actuals)==1 and actuals[0]['classification']=='actual_delivery_not_learning_progress'
    future_choices=pick(client,ids,'future_plans')['items'];assert len(future_choices)==1
    assert future_choices[0]['session_revision_id']==future['revision_id'] and future_choices[0]['classification']=='future_plan_not_actual'

def test_contributor_inbox_no_whole_document_or_editor_grants(documents_env):
    client,factory,app,ids=documents_env;h=login(client);row=create(client,ids,h)
    result=client.post(path(ids)+f'/cases/{row["id"]}/assignments',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='body',contributor_id=ids['teacher']));assert result.status_code==201,result.text
    create(client,ids,h)  # Same pupil, with no assignment to this contributor.
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'])):
            assignment.actions=['documents.contribute']
    login(client,'teacher')
    response=client.get(path(ids)+f'/learners/{ids["a"]}/contribution-inbox');assert response.status_code==200,response.text
    inbox=response.json();assert inbox['total']==1 and inbox['items'][0]['document_id']==row['id']
    assert inbox['items'][0]['sections']==[{'key':'body','label':'body','required':True}]
    assert client.get(path(ids)+f'/learners/{ids["a"]}/contribution-inbox',params={'offset':1,'limit':1}).json()['items']==[]
    assert all(word not in json.dumps(inbox) for word in ('content','subject','snapshot','source_keys'))
    assert client.get(path(ids)+f'/cases/{row["id"]}').status_code==403
    assert client.get(path(ids)+f'/cases/{row["id"]}/suggestions').status_code==403
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a']));assignment.state='revoked'
    assert client.get(path(ids)+f'/learners/{ids["a"]}/contribution-inbox').status_code==403

def test_durable_suggestion_recovery_restart_reviews_and_recall(generated_documents):
    from test_documents_generation import generate,diff,selection
    from spesped.main import create_app
    from spesped.contexts.platform.models import ModelRelease
    e=generated_documents;job=generate(e)
    restarted=create_app(e.app.state.settings,e.factory);restarted.state.evidence_storage=e.app.state.evidence_storage;restarted.state.ai_gateway=e.runtime
    with TestClient(restarted) as client:
        h=login(client);url=path(e.ids)+f'/cases/{e.row["id"]}/suggestions'
        response=client.get(url);assert response.status_code==200,response.text
        recovered=response.json();assert recovered['total']==1 and recovered['items'][0]['id']==job['id']
        assert recovered['items'][0]['availability']=='current' and recovered['items'][0]['reviews']==[]
        assert 'Synthetic source-backed' not in response.text and 'output' not in response.text
        p=diff(e,job)
        # e's fixture client and the restarted app share the durable database.
        response=client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=h,json=selection(e,p));assert response.status_code==200,response.text
        recovered=client.get(url).json();assert recovered['items'][0]['reviews'][0]['outcome']=='applied'
        evidence(e.client,e.ids,e.h)
        assert client.get(url).json()['items'][0]['availability']=='review_required'
        with e.factory.begin() as db:db.get(ModelRelease,e.release).state='revoked'
        recalled=client.get(url).json()['items'][0];assert recalled['state']=='succeeded' and recalled['availability']=='review_required'
        login(client,'teacher')
        with e.factory.begin() as db:
            for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==e.ids['teacher'],AuthorityGrant.action=='ai.guardian_email_drafting')):grant.state='revoked'
        assert client.get(url).status_code==403
        assert client.get(path(e.ids)+f'/cases/{e.row["id"]}').status_code==200

def test_owner_choice_read_preserves_pending_and_outer_transaction(documents_env):
    from spesped.contexts.identity.document_choices import guardians
    client,factory,app,ids=documents_env;login(client)
    with factory() as db:
        user=db.get(UserAccount,ids['reviewer']);user.display_name='Synthetic staged untouched'
        with pytest.raises(DomainError) as error:guardians(db,Actor(ids['reviewer']),ids['school'],ids['a'])
        assert error.value.code=='dependency_pending' and user in db.dirty and user.display_name=='Synthetic staged untouched'
        db.rollback()
        user=db.get(UserAccount,ids['reviewer']);user.display_name='Synthetic flushed outer transaction';db.flush()
        result=guardians(db,Actor(ids['reviewer']),ids['school'],ids['a']);assert len(result)==1 and db.in_transaction()
        assert user.display_name=='Synthetic flushed outer transaction'
        db.rollback()
    with factory() as db:assert db.get(UserAccount,ids['reviewer']).display_name=='Synthetic reviewer'
    with factory() as db:
        cached=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a']))
        with factory.begin() as other:other.get(StaffAssignment,cached.id).state='revoked'
        with pytest.raises(DomainError) as error:guardians(db,Actor(ids['reviewer']),ids['school'],ids['a'])
        assert error.value.status_code==403 and cached.state=='active' and db.in_transaction()

def test_reviewed_assessment_sources_remain_exact_and_late_review_is_visible(documents_env):
    from assessment_fixtures import instrument,planned,started,recorded,reviewed,progress,statement,statement_content,scheme
    from test_assessment import exact_progress,competence
    client,factory,app,ids=documents_env;h=login(client)
    instrument_row,_=instrument(client,ids,h)
    result=reviewed(client,ids,h,recorded(client,ids,h,started(client,ids,h,planned(client,ids,h,instrument_row))))
    goal,_=ordinary_goal(client,ids,h);observed=observation(client,ids,h,goal)
    report=progress(client,ids,h,goal)
    for action in ('submit','confirm'):
        response=client.post(base(ids)+f'/assessment/progress-reviews/{report["id"]}/review',headers=h,json=exact_progress(report,transition=action));assert response.status_code==200,response.text;report=response.json()
    binding,_=evidence(client,ids,h);sc,_=scheme(client,ids,h)
    subject=statement(client,ids,h,sc,content=statement_content(basis=[competence(binding)]))
    response=client.post(base(ids)+f'/assessment/statements/{subject["id"]}/finalize',headers=h,json=expected(subject,
        revision_id=subject['revision_id'],content_digest=subject['content_digest'],reason='Synthetic exact statement source review',contribution_ids=[],grade=None));assert response.status_code==200,response.text
    found=pick(client,ids,'sources')['items'];bykind={v['source_type']:v for v in found}
    assert bykind['assessment_result']['reference']['id']==result['result']['id']
    assert bykind['progress_review']['reference']['id']==report['id']
    assert bykind['assessment_statement']['reference']['id']==subject['id']
    assert bykind['assessment_statement']['reference']['revision']==1
    observation(client,ids,h,goal,occurred_at=observed['occurred_at'])
    found=pick(client,ids,'sources')['items'];review=next(v for v in found if v['source_type']=='progress_review')
    assert review['state']=='review_required'
    # Recalled assessment authority removes finalized subject sources without
    # suggesting that the recorded historic statement or result was deleted.
    app.state.assessment_authority_port.state='unresolved'
    assert 'assessment_statement' not in {v['source_type'] for v in pick(client,ids,'sources')['items']}

def test_obligation_choices_bind_requirement_and_reviewed_calendar_period(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    with factory.begin() as db:
        for action in ('governance.rules.manage','governance.rules.approve','governance.tasks.manage','governance.tasks.review'):
            db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['reviewer'],action=action,valid_from=date(2020,1,1),granted_by=ids['leader']))
    governance=base(ids)+'/governance'
    def post(url,data,code=201):
        response=client.post(governance+url,headers=h,json=data);assert response.status_code==code,response.text;return response.json()
    definition=post('/requirements',{'code':'synthetic-picker-annual','title':'Synthetic annual report obligation','source_type':'law','source_reference':'Synthetic September 2026 reviewed registry'})
    rule=post(f'/requirements/{definition["id"]}/versions',{'expected_version':1,'valid_from':'2020-01-01','conditions':[],
        'trigger_type':'annual_report','deadline':{'kind':'fixed_date','fixed_date':'2026-12-31','legal_basis':'Synthetic reviewed timing'},
        'required_action':'Human annual report','required_document_types':['annual_ito_evaluation'],'accountable_role':'responsible teacher','interpretation_notes':'Synthetic no new legal research'})
    rule=post(f'/requirement-versions/{rule["id"]}/review',{'expected_version':rule['version'],'rationale':'Synthetic reviewed requirement'},200)
    profile=post('/profiles',{'label':'Synthetic reviewed profile','requirement_version_ids':[rule['id']],'valid_from':'2020-01-01'})
    impact=client.get(governance+f'/profiles/{profile["id"]}/impact').json()
    profile=post(f'/profiles/{profile["id"]}/activate',{'expected_version':profile['version'],'impact_digest':impact['impact_digest'],'rationale':'Synthetic exact profile review'},200)
    obligation=post('/triggers',{'event_key':key(),'profile_id':profile['id'],'event_type':'annual_report','occurred_at':utcnow().isoformat(),
        'period_key':'untyped-not-calendar-coverage','learner_id':ids['a'],'inputs':{}})['items'][0]
    args={'kind':'annual_ito_evaluation','requirement_version_id':rule['id']}
    before=pick(client,ids,'obligations',**args)['items'];assert len(before)==1 and before[0]['state']=='unresolved' and before[0]['report_period'] is None
    history=client.get(governance+f'/obligations/{obligation["id"]}/report-period-reviews',params={'document_kind':'annual_ito_evaluation'}).json()
    post(f'/obligations/{obligation["id"]}/report-period-reviews',{'request_key':key(),'expected_version':0,
        'obligation_basis_digest':history['obligation_basis_digest'],'document_kind':'annual_ito_evaluation','starts_on':'2026-10-01','ends_on':'2026-10-21','rationale':'Synthetic human explicitly confirms report coverage'},200)
    item=pick(client,ids,'obligations',**args)['items'][0]
    assert item['state']=='applicable' and item['report_period']=={'starts_on':'2026-10-01','ends_on':'2026-10-21'}
    mismatch=pick(client,ids,'obligations',ends_on='2026-10-20',**args)['items'][0]
    assert mismatch['state']=='unresolved' and 'report_period_mismatch' in mismatch['unresolved_inputs']
    from uuid import uuid4
    assert pick(client,ids,'obligations',kind='annual_ito_evaluation',requirement_version_id=str(uuid4()))['total']==0

def test_inventory_cap_is_explicit_and_date_narrowing_remains_usable(documents_env,monkeypatch):
    from spesped.contexts.identity import document_choices as identity
    client,factory,app,ids=documents_env;h=login(client);goal,_=ordinary_goal(client,ids,h)
    observation(client,ids,h,goal,occurred_at='2026-10-12T12:00:00+02:00')
    observation(client,ids,h,goal,occurred_at='2026-10-14T12:00:00+02:00')
    # Exercise the same cap branch with two native records, avoiding a costly
    # thousand-record fixture that merely repeats identical authorization.
    monkeypatch.setattr(identity,'MAX_CANDIDATES',1)
    response=client.get(path(ids)+f'/learners/{ids["a"]}/choices/sources',params={'kind':'guardian_email','starts_on':'2026-10-01','ends_on':'2026-10-21'})
    assert response.status_code==422 and response.json()['error']['code']=='choice_limit'
    result=pick(client,ids,'sources',source_starts_on='2026-10-14',source_ends_on='2026-10-14')
    assert result['total']==1
