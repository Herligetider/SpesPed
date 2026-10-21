import pytest
from datetime import date,timedelta
from uuid import uuid4
from sqlalchemy import select,func
from documents_fixtures import documents_env,assessment_env,curriculum_env,teaching_env,env,login,ordinary_goal,source,observation,progress,path,base,payload,create,filled,revised,transition,template,expected,key,retry,evidence
from spesped.contexts.documents import models as m,service as svc,schemas as s
from spesped.contexts.identity.models import StaffAssignment,GuardianRelationship,AuthorityGrant,UserAccount
from spesped.auth import Actor
from spesped.db import utcnow

def test_empty_period_manual_recovery_exact_approval_and_revisions(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    row=create(client,ids,h)
    assert row['state']=='draft' and not row['revision']['content']['sections'][0]['text']
    assert 'no_confirmed_observations_in_selected_period' in row['revision']['snapshot']['manifest']['gaps']
    assert row['dispatch']['automatic_send'] is False
    row=transition(client,ids,h,row,'review');transition(client,ids,h,row,'approve',409)
    row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review');row=transition(client,ids,h,row,'approve')
    assert row['state']=='approved' and row['revision']['approval']['state']=='current'
    original=row['revision_id']
    with factory() as db:
        frozen=svc.frozen_revision(db,Actor(ids['reviewer']),ids['school'],ids['a'],original,'learning_summary')
        assert frozen['disclosure_authorized'] is False
    row=revised(client,ids,h,row,language='nn')
    assert row['state']=='draft' and row['revision_id']!=original and row['revision']['approval'] is None
    history=client.get(path(ids)+f'/cases/{row["id"]}/revisions').json()
    assert history['items'][-2]['approval']['state']=='superseded_or_recalled'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ContentApproval))==1
        event=db.scalar(select(m.DocumentEvent).limit(1));assert event.schema_version==1 and event.causation_id and event.correlation_id
        assert 'Synthetic' not in str(event.payload)

def test_templates_distinct_unknown_manual_and_required_contributor(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    row=create(client,ids,h,kind='annual_ito_evaluation');row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review');transition(client,ids,h,row,'approve',409)
    t=template(client,ids,h,sections=[{'key':'summary','label':'Summary','required':True,'contribution_required':True}])
    row=create(client,ids,h,kind='local_semester_report',template_revision_id=t['revision_id']);row=revised(client,ids,h,row)
    response=client.post(path(ids)+f'/cases/{row["id"]}/assignments',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='summary',contributor_id=ids['teacher']));assert response.status_code==201,response.text;row=response.json()
    row=transition(client,ids,h,row,'review');assert row['state']=='waiting_contributions'
    h=login(client,'teacher')
    result=client.post(path(ids)+f'/cases/{row["id"]}/contributions',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='summary',kind='checked',text='Synthetic assigned section sources checked'));assert result.status_code==201,result.text;row=client.get(path(ids)+f'/cases/{row["id"]}').json()
    h=login(client);row=transition(client,ids,h,row,'review');row=transition(client,ids,h,row,'approve');assert row['legal_finalization']=='reviewed_report'
    response=client.post(path(ids)+f'/templates/{t["id"]}/recall',headers=h,json=expected(t,revision_id=t['revision_id'],content_digest=t['content_digest'],reason='Synthetic school template recalled'));assert response.status_code==200,response.text
    row=client.get(path(ids)+f'/cases/{row["id"]}').json();assert row['revision']['review_required'] and row['legal_finalization']=='not_finalized'

def test_inclusive_timezone_late_sources_frozen_text_and_revocation(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    goal,_=ordinary_goal(client,ids,h)
    observation(client,ids,h,goal,occurred_at='2026-10-01T00:00:00+02:00')
    observation(client,ids,h,goal,occurred_at='2026-10-15T23:59:59+02:00')
    observation(client,ids,h,goal,occurred_at='2026-10-16T00:00:00+02:00')
    row=create(client,ids,h,ends_on='2026-10-15');manifest=row['revision']['snapshot']['manifest'];assert len(manifest['entries'])==2
    assert manifest['period']['ends_at_exclusive'].replace(' ','T').startswith('2026-10-15T22:00:00')
    row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review');row=transition(client,ids,h,row,'approve');text=row['revision']['content']
    observation(client,ids,h,goal,occurred_at='2026-10-10T12:00:00+02:00')
    row=client.get(path(ids)+f'/cases/{row["id"]}').json()
    assert row['revision']['content']==text and row['revision']['source_status']=='review_required' and len(row['revision']['source_changes']['late_sources'])==1
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a']));assignment.actions=[v for v in assignment.actions if v!='teaching.read']
    row=client.get(path(ids)+f'/cases/{row["id"]}').json();assert row['revision']['content'] is None and row['revision']['source_status']=='unavailable'

def test_idempotency_scope_conflict_approval_authority_and_relationship(documents_env):
    client,factory,app,ids=documents_env;h=login(client);command=payload(ids)
    first=client.post(path(ids)+'/cases',headers=h,json=command);assert first.status_code==201,first.text
    row=first.json();assert client.post(path(ids)+'/cases',headers=h,json=command).json()['id']==row['id']
    assert client.post(path(ids)+'/cases',headers=h,json={**command,'purpose':'other'}).status_code==409
    row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review')
    with factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='documents.approve'));grant.state='revoked'
    transition(client,ids,h,row,'approve',403)
    with factory.begin() as db:
        relation=db.get(GuardianRelationship,ids['guardian_relation']);relation.information_rights='unresolved'
    row=client.get(path(ids)+f'/cases/{row["id"]}').json();assert row['revision']['review_required']
    resolve=client.post(path(ids)+'/period-resolution',headers=h,json={'learner_id':ids['a'],'purpose':'learning_summary','starts_on':'2026-10-01','ends_on':'2026-10-21','shortcut':'since_last_sent'}).json()
    assert resolve['state']=='unresolved' and resolve['choose_dates_required']
    assert client.post(path(ids)+'/cases',headers=h,json={**payload(ids),'starts_on':'2026-10-22'}).status_code==422
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'],StaffAssignment.learner_id==ids['a']));assignment.state='revoked'
    assert client.post(path(ids)+'/cases',headers=h,json=command).status_code==403

def settings(ids,**changes):
    return {'learner_id':ids['a'],'owner_id':ids['teacher'],'purpose':'learning_summary','recipient_relationship_ids':[ids['guardian_relation']],'first_run_at':(utcnow()-timedelta(minutes=1)).isoformat(),'ends_at':(utcnow()+timedelta(days=70)).isoformat(),'recurrence':'days','recurrence_count':14,'period_rule':'rolling_days','period_days':8,**changes}
def schedule(client,ids,h,**changes):
    response=client.post(path(ids)+'/schedules',headers=h,json=retry(settings=settings(ids,**changes)));assert response.status_code==201,response.text;row=response.json();assert row['state']=='inactive'
    response=client.post(path(ids)+f'/schedules/{row["id"]}/state',headers=h,json=expected(row,action='activate'));assert response.status_code==200,response.text;return response.json()
def test_schedule_opt_in_distinct_period_dedup_owner_pause_and_missed_reconcile(documents_env):
    client,factory,app,ids=documents_env;h=login(client);row=schedule(client,ids,h)
    command=expected(row);route=path(ids)+f'/schedules/{row["id"]}/run'
    response=client.post(route,headers=h,json=command);assert response.status_code==200,response.text;row=response.json()
    assert len(row['runs'])==1 and row['runs'][0]['status']=='draft_created' and row['automatic_send'] is False
    assert client.post(route,headers=h,json=command).json()['runs']==row['runs']
    response=client.post(route,headers=h,json=expected(row));assert response.status_code==200,response.text;assert len(response.json()['runs'])==1
    missed=schedule(client,ids,h,first_run_at=(utcnow()-timedelta(days=30)).isoformat())
    response=client.post(path(ids)+f'/schedules/{missed["id"]}/run',headers=h,json=expected(missed));assert response.status_code==200,response.text
    missed=response.json();assert missed['state']=='paused' and len(missed['runs'])==1 and missed['runs'][0]['status']=='reconciliation_required' and missed['runs'][0]['document_id'] is None
    owner=schedule(client,ids,h)
    with factory.begin() as db:db.get(UserAccount,ids['teacher']).state='inactive'
    response=client.post(path(ids)+f'/schedules/{owner["id"]}/run',headers=h,json=expected(owner));assert response.status_code==200,response.text
    assert response.json()['state']=='paused' and response.json()['pause_reason']=='owner_inactive_or_scope_revoked'

def test_read_contract_preserves_staged_orm_and_transaction(documents_env):
    import pytest
    from spesped.errors import DomainError
    client,factory,app,ids=documents_env;h=login(client);row=create(client,ids,h)
    with factory() as db:
        user=db.get(UserAccount,ids['reviewer']);user.display_name='Staged synthetic value'
        with pytest.raises(DomainError,match='staged'):svc.document_view(db,Actor(ids['reviewer']),ids['school'],row['id'])
        assert user.display_name=='Staged synthetic value' and user in db.dirty and db.in_transaction()
        db.rollback()
        result=svc.document_view(db,Actor(ids['reviewer']),ids['school'],row['id']);assert result['id']==row['id'] and db.in_transaction()

def test_atomic_audit_failure_rolls_back_business_receipt_and_events(documents_env,monkeypatch):
    import pytest
    from spesped.contexts.identity.models import AuditRecord
    client,factory,app,ids=documents_env;h=login(client);models=(m.DocumentCase,m.DocumentRevision,m.EvidenceSnapshot,m.DocumentCommand,m.DocumentEvent,AuditRecord)
    with factory() as db:before=tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    def fail(*args,**kwargs):raise RuntimeError('Synthetic late audit failure')
    monkeypatch.setattr(svc,'record_audit',fail)
    with pytest.raises(RuntimeError,match='late audit'):client.post(path(ids)+'/cases',headers=h,json=payload(ids))
    with factory() as db:after=tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    assert before==after

def test_postgres_concurrent_semantic_create_and_schedule_period_dedup(documents_env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import pytest
    client,factory,app,ids=documents_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('Actual PostgreSQL row-lock concurrency')
    h=login(client);command=s.DocumentCreate.model_validate(payload(ids));barrier=Barrier(2)
    def write():
        with factory() as db:barrier.wait();return svc.create_document(db,Actor(ids['reviewer']),ids['school'],command)['id']
    with ThreadPoolExecutor(max_workers=2) as pool:ids_result=list(pool.map(lambda _:write(),range(2)))
    assert len(set(ids_result))==1
    row=schedule(client,ids,h);barrier=Barrier(2);run_command=s.ScheduleRun.model_validate(expected(row))
    def run():
        with factory() as db:barrier.wait();return svc.run_schedule(db,Actor(ids['reviewer']),ids['school'],row['id'],run_command)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert results[0]['runs']==results[1]['runs'] and len(results[0]['runs'])==1

def test_native_actuals_goal_basis_and_correction_never_become_planned_delivery(documents_env):
    from teaching_fixtures import actual,basis,session,content
    client,factory,app,ids=documents_env;h=login(client);goal,plan=ordinary_goal(client,ids,h)
    record=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual(ids,{'a':goal})));assert record.status_code==201,record.text
    delivery=record.json();at=utcnow()-timedelta(minutes=30)
    row=create(client,ids,h,selection={'goals':[{'goal_revision_id':goal,'applicable_at':at.isoformat()}],'actual_revision_ids':[delivery['revision_id']]})
    snap=row['revision']['snapshot']['manifest'];assert len([v for v in snap['entries'] if v['reference']['kind']=='actual'])==1
    assert snap['planned_activity_is_delivery'] is False and snap['missing_evidence_is_progress'] is False
    assert 'no_confirmed_observations_in_selected_period' in snap['gaps']
    # A single-pupil projection excludes group narrative and other pupil counts.
    actual_value=next(v['value'] for v in snap['entries'] if v['reference']['kind']=='actual')
    assert ids['b'] not in str(actual_value)

def test_selected_other_pupil_evidence_is_denied_and_section_contributor_cannot_read_whole(documents_env):
    client,factory,app,ids=documents_env;h=login(client)
    binding,item=evidence(client,ids,h,learner='b')
    response=client.post(path(ids)+'/cases',headers=h,json=payload(ids,selection={'references':[{'kind':'evidence','id':item['id'],'revision':item['revision'],'link_id':binding['link_id']}]}));assert response.status_code==403,response.text
    row=create(client,ids,h);row=revised(client,ids,h,row)
    response=client.post(path(ids)+f'/cases/{row["id"]}/assignments',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='body',contributor_id=ids['teacher']));assert response.status_code==201,response.text;row=response.json()
    with factory.begin() as db:
        assignment=db.scalar(select(StaffAssignment).where(StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a']));assignment.actions=[v for v in assignment.actions if v!='documents.read']
    h=login(client,'teacher')
    assert client.get(path(ids)+f'/cases/{row["id"]}').status_code==403
    response=client.get(path(ids)+f'/cases/{row["id"]}/contribution-workspace');assert response.status_code==200,response.text
    workspace=response.json();assert [v['key'] for v in workspace['assigned_sections']]==['body'] and 'content' not in workspace
    response=client.post(path(ids)+f'/cases/{row["id"]}/contributions',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='next_steps',kind='comment',text='Unauthorized section comment'));assert response.status_code==403
    response=client.post(path(ids)+f'/cases/{row["id"]}/contributions',headers=h,json=expected(row,revision_id=row['revision_id'],section_key='body',kind='checked',text='Synthetic assigned section checked'));assert response.status_code==201,response.text

@pytest.mark.parametrize('coverage_year',[2026,2025])
def test_native_annual_ito_reviewed_rule_two_historical_goals_actual_missing_outcome(documents_env,monkeypatch,coverage_year):
    from datetime import datetime
    from plans_fixtures import support_case,confirmed_decision,plan_payload,activate
    from teaching_fixtures import actual
    from spesped.contexts.plans import service as plans
    from spesped.contexts.teaching import service as teaching
    client,factory,app,ids=documents_env;h=login(client)
    with factory.begin() as db:
        for action in ('governance.rules.manage','governance.rules.approve','governance.tasks.manage','governance.tasks.review'):
            db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['reviewer'],action=action,valid_from=date(2020,1,1),granted_by=ids['leader']))
    def post(url,data,code=201):
        r=client.post(url,headers=h,json=data);assert r.status_code==code,r.text;return r.json()
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h);decision=confirmed_decision(client,ids,h,case,binding)
    first=post(base(ids)+f'/learners/{ids["a"]}/education-plans',plan_payload(binding,decision));first=activate(client,ids,h,first)
    first_goal=first['content']['goals'][0]['id'];clock=utcnow();old_at=clock+timedelta(seconds=15);change_at=clock+timedelta(minutes=1)
    # A synthetic clock advances a minute so two actual approved IOP revisions
    # can coexist historically within the same chosen report calendar interval.
    monkeypatch.setattr(plans,'utcnow',lambda:change_at)
    from spesped.contexts.plans.generation import command_content
    from spesped.contexts.plans.models import PlanRevision
    with factory() as db:data=command_content(db,db.get(PlanRevision,first['content']['id']))
    data['effective_from']=change_at.isoformat();data['goals'][0]['effective_from']=change_at.isoformat();data['goals'][0]['expected_action']='Synthetic revised observable reading action'
    second=post(base(ids)+f'/education-plans/{first["id"]}/revisions',expected(first,**data));second=activate(client,ids,h,second);second_goal=second['content']['goals'][0]['id']
    new_at=change_at+timedelta(seconds=15);later=change_at+timedelta(hours=1)
    monkeypatch.setattr(teaching,'utcnow',lambda:later);monkeypatch.setattr(svc,'utcnow',lambda:later)
    record=post(base(ids)+'/teaching/deliveries',retry(content=actual(ids,{'a':first_goal},occurred_at=old_at.isoformat())))
    governance=base(ids)+'/governance'
    definition=post(governance+'/requirements',{'code':'synthetic-annual-ito','title':'Synthetic reviewed annual ITO requirement','source_type':'law','source_reference':'Synthetic September 2026 registry interpretation; human reviewed'})
    rule=post(governance+f'/requirements/{definition["id"]}/versions',{'expected_version':1,'valid_from':'2020-01-01','conditions':[{'fact':'support_entitlement','equals':'individually_adapted_education'}],'trigger_type':'annual_ito_review','deadline':{'kind':'fixed_date','fixed_date':'2026-12-31','legal_basis':'Synthetic school reviewed timing'},'required_action':'Human evaluates actual delivery and documented outcome','required_document_types':['annual_ito_evaluation'],'accountable_role':'responsible educator','interpretation_notes':'Synthetic reviewed applicability, no current law research claim'})
    rule=post(governance+f'/requirement-versions/{rule["id"]}/review',{'expected_version':rule['version'],'rationale':'Synthetic rule and applicability independently reviewed'},200)
    profile=post(governance+'/profiles',{'label':'Synthetic annual ITO profile','requirement_version_ids':[rule['id']],'valid_from':'2020-01-01'})
    impact=client.get(governance+f'/profiles/{profile["id"]}/impact').json()
    profile=post(governance+f'/profiles/{profile["id"]}/activate',{'expected_version':profile['version'],'rationale':'Synthetic school approval of exact rule profile','impact_digest':impact['impact_digest']},200)
    task=post(governance+'/triggers',{'event_key':key(),'profile_id':profile['id'],'event_type':'annual_ito_review','occurred_at':clock.isoformat(),'period_key':'2026','learner_id':ids['a'],'inputs':{'support_entitlement':'individually_adapted_education'}})['items'][0]
    period_review=client.get(governance+f'/obligations/{task["id"]}/report-period-reviews',params={'document_kind':'annual_ito_evaluation'});assert period_review.status_code==200,period_review.text
    post(governance+f'/obligations/{task["id"]}/report-period-reviews',{'request_key':key(),'expected_version':0,'document_kind':'annual_ito_evaluation','starts_on':f'{coverage_year}-10-01','ends_on':f'{coverage_year}-10-21','obligation_basis_digest':period_review.json()['obligation_basis_digest'],'rationale':'Synthetic responsible review binds this exact report interval to the current annual obligation'},200)
    t=template(client,ids,h,'annual_ito_evaluation',requirement_version_id=rule['id'],approval_action='documents.annual_ito.approve',sections=[{'key':'actual_delivery','label':'Actual delivery','required':True},{'key':'outcome','label':'Human evaluated outcome','required':True}])
    row=create(client,ids,h,kind='annual_ito_evaluation',template_revision_id=t['revision_id'],obligation_id=task['id'],selection={'goals':[{'goal_revision_id':first_goal,'applicable_at':old_at.isoformat()},{'goal_revision_id':second_goal,'applicable_at':new_at.isoformat()}],'actual_revision_ids':[record['revision_id']]})
    snapshot=row['revision']['snapshot']['manifest'];goals=[v for v in snapshot['entries'] if v['reference']['kind']=='goal']
    assert {v['value']['goal']['id'] for v in goals}=={first_goal,second_goal}
    bygoal={v['value']['goal']['id']:v['value'] for v in goals}
    assert datetime.fromisoformat(bygoal[first_goal]['effective_period']['ends_at_exclusive'])==change_at
    assert datetime.fromisoformat(bygoal[second_goal]['effective_period']['starts_at'])==change_at
    if coverage_year!=2026:
        assert snapshot['rule']['state']=='unresolved' and 'report_period_mismatch' in snapshot['rule']['unresolved_inputs'] and snapshot['rule']['report_period'] is None
        row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review');transition(client,ids,h,row,'approve',409)
        return
    assert snapshot['rule']['state']=='applicable' and snapshot['template']['state']=='reviewed_current'
    assert 'professional_progress_review_not_selected' in snapshot['gaps'] and 'no_confirmed_observations_in_selected_period' in snapshot['gaps']
    assert snapshot['planned_activity_is_delivery'] is False
    row=transition(client,ids,h,row,'review');transition(client,ids,h,row,'approve',409)
    row=revised(client,ids,h,row);row=transition(client,ids,h,row,'review');row=transition(client,ids,h,row,'approve')
    assert row['legal_finalization']=='reviewed_report'
    source_ref=t['content']['sources'][0]
    from spesped.contexts.evidence.models import SourceItem
    with factory.begin() as db:db.get(SourceItem,source_ref['source_id']).state='withdrawn'
    result=client.get(path(ids)+f'/cases/{row["id"]}').json();assert result['revision']['content'] is None and result['legal_finalization']=='not_finalized'

def test_prior_background_is_explicit_and_since_last_requires_exact_confirmed_recipient_purpose(documents_env):
    from spesped.contexts.documents.ports import SentPeriod
    client,factory,app,ids=documents_env;h=login(client);binding,item=evidence(client,ids,h)
    ref={'kind':'evidence','id':item['id'],'revision':item['revision'],'link_id':binding['link_id']}
    response=client.post(path(ids)+'/cases',headers=h,json=payload(ids,starts_on='2026-10-20',selection={'references':[ref]}));assert response.status_code==422,response.text
    row=create(client,ids,h,starts_on='2026-10-20',selection={'background_references':[ref]})
    entries=row['revision']['snapshot']['manifest']['entries'];assert len(entries)==1 and entries[0]['classification']=='background_reference_not_interval_fact'
    assert 'no_confirmed_observations_in_selected_period' in row['revision']['snapshot']['manifest']['gaps']
    class History:
        def __init__(self):self.calls=[]
        def confirmed_periods(self,db,actor,school,learner,relationship,purpose):
            self.calls.append((school,learner,relationship,purpose))
            return [SentPeriod(school_id=school,learner_id=learner,dispatch_id=uuid4(),document_revision_id=uuid4(),package_digest='a'*64,recipient_relationship_id=relationship,purpose=purpose,starts_on=date(2026,10,1),ends_on=date(2026,10,15))]
    history=History();app.state.document_dispatch_history_port=history
    command={'learner_id':ids['a'],'purpose':'learning_summary','recipient_relationship_id':ids['guardian_relation'],'starts_on':'2026-10-01','ends_on':'2026-10-21','shortcut':'since_last_sent'}
    response=client.post(path(ids)+'/period-resolution',headers=h,json=command);assert response.status_code==200,response.text
    assert response.json()['period']['starts_on']=='2026-10-16' and history.calls[-1]==(ids['school'],ids['a'],ids['guardian_relation'],'learning_summary')
    command['shortcut']='explicit'
    response=client.post(path(ids)+'/period-resolution',headers=h,json=command);assert response.status_code==200,response.text;assert len(response.json()['overlaps'])==1

def test_ordinary_subject_report_preserves_native_human_statement_and_recall(documents_env):
    from assessment_fixtures import scheme,statement,statement_content
    from test_assessment import competence
    client,factory,app,ids=documents_env;h=login(client);sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    assessment=statement(client,ids,h,sc,content=statement_content(basis=[competence(binding)]))
    response=client.post(base(ids)+f'/assessment/statements/{assessment["id"]}/finalize',headers=h,json=expected(assessment,revision_id=assessment['revision_id'],content_digest=assessment['content_digest'],reason='Synthetic professional exact statement approved',contribution_ids=[]));assert response.status_code==200,response.text;assessment=response.json()
    t=template(client,ids,h,kind='ordinary_subject_assessment',approval_action='documents.subject_report.approve')
    row=create(client,ids,h,kind='ordinary_subject_assessment',template_revision_id=t['revision_id'],selection={'references':[{'kind':'assessment_statement','id':assessment['id'],'revision':1}]})
    entry=next(v for v in row['revision']['snapshot']['manifest']['entries'] if v['reference']['kind']=='assessment_statement')
    assert entry['value']['classification']=='human_finalized_subject_statement' and entry['value']['revision_id']==assessment['revision_id']
    app.state.assessment_authority_port.state='unavailable'
    row=client.get(path(ids)+f'/cases/{row["id"]}').json();assert row['revision']['content'] is None
