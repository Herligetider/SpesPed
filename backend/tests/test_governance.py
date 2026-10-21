"""Actual authorized HTTP workflows on SQLite and isolated PostgreSQL schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import os
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from spesped.auth import Actor, hash_password
from spesped.cli import provision_school
from spesped.config import Settings
from spesped.db import make_session_factory, utcnow
from spesped.main import create_app
from spesped.errors import DomainError
from spesped.contexts.identity.models import SchoolMembership, StaffAssignment, AuthorityGrant, UserAccount, Learner, AuditRecord
from spesped.contexts.governance import router
from spesped.contexts.governance import models as m, schemas as s, service as svc
from spesped.contexts.governance.policies import evaluate_applicability, resolve_deadline
from spesped.contexts.governance.ports import ValidatedEvidenceReference

ORIGIN='http://testserver'
PASSWORD='synthetic-governance-passphrase'
ACTIONS=('rules.manage','rules.approve','tasks.manage','tasks.review','overview','workload.manage')

@pytest.fixture(params=['sqlite','postgres'])
def env(request,tmp_path):
    admin=None; schema=None
    if request.param=='postgres':
        url=os.getenv('SPESPED_TEST_POSTGRES_URL')
        if not url: pytest.skip('Set SPESPED_TEST_POSTGRES_URL for PostgreSQL verification')
        admin=create_engine(url)
        schema='j13_'+uuid4().hex
        with admin.begin() as connection: connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else: url=f'sqlite:///{tmp_path}/governance.db'
    config=Config(str(Path(__file__).parents[1]/'alembic.ini')); config.attributes['database_url']=url
    command.upgrade(config,'j13_governance')
    factory=make_session_factory(url)
    with factory.begin() as db:
        school,leader=provision_school(db,school_name='Synthetic governance school',kind='public',timezone='Europe/Oslo',email='leader@example.invalid',display_name='Leader',password=PASSWORD)
        other,other_leader=provision_school(db,school_name='Synthetic foreign school',kind='public',timezone='Europe/Oslo',email='foreign@example.invalid',display_name='Foreign',password=PASSWORD)
        ids={'school':school.id,'leader':leader.id,'other_school':other.id}
        encoded=hash_password(PASSWORD)
        for key in ('teacher','board','volunteer','outsider'):
            user=UserAccount(email=f'{key}@example.invalid',display_name='Synthetic '+key,password_hash=encoded)
            db.add(user); db.flush(); ids[key]=user.id
            db.add(SchoolMembership(school_id=school.id,user_id=user.id,role='teacher' if key!='board' else 'school_owner',valid_from=date(2020,1,1)))
        for action in ACTIONS:
            db.add(AuthorityGrant(school_id=school.id,user_id=leader.id,action='governance.'+action,valid_from=date(2020,1,1),granted_by=leader.id))
        db.add(AuthorityGrant(school_id=school.id,user_id=ids['board'],action='governance.overview',valid_from=date(2020,1,1),granted_by=leader.id))
        learner=Learner(school_id=school.id,display_name='SECRET PUPIL',grade=4,group_name='SECRET GROUP'); db.add(learner); db.flush();ids['learner']=learner.id
        for user in (leader.id,ids['teacher']):
            db.add(StaffAssignment(school_id=school.id,learner_id=learner.id,user_id=user,actions=['learner.read'],purpose='synthetic',valid_from=date(2020,1,1)))
        db.flush()
    ids['document']=str(uuid4())
    app=create_app(Settings(environment='test',database_url=url,allowed_origins=[ORIGIN]),factory)
    if not any('/governance/' in path for path in app.openapi()['paths']):app.include_router(router)
    def validator(db,actor,school_id,learner_id,case_id,reference_id):
        # A narrow synthetic source-context adapter, never used as proof of an
        # actual file upload or integration with the evidence context.
        if reference_id!=ids['document']: raise DomainError('access_denied','Unknown synthetic reference',403)
        return ValidatedEvidenceReference(reference_id,ids['school'],None,None,1,'a'*64)
    app.state.governance_evidence_validator=validator
    with TestClient(app) as client:yield client,factory,ids,request.param,config
    factory.kw['bind'].dispose()
    if admin:
        with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def login(client,key='leader'):
    r=client.post('/api/v1/auth/login',json={'email':f'{key}@example.invalid','password':PASSWORD},headers={'Origin':ORIGIN})
    assert r.status_code==200,r.text
    return {'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']}


def base(ids):return f'/api/v1/schools/{ids["school"]}/governance'


def post(client,path,body,headers,status=200):
    r=client.post(path,json=body,headers=headers)
    assert r.status_code==status,r.text
    return r.json()


def rule_setup(env,conditions=None,deadline=None,code=None,review=True,documents=None):
    c,f,ids,_,_=env;h=login(c);b=base(ids)
    definition=post(c,b+'/requirements',{'code':code or 'R'+uuid4().hex,'title':'Synthetic procedure duty','source_type':'law','source_reference':'Synthetic reviewed test source; not legal advice'},h,201)
    version=post(c,b+f'/requirements/{definition["id"]}/versions',{'expected_version':1,'valid_from':'2020-01-01','conditions':conditions or [],'trigger_type':'synthetic_event','deadline':deadline or {'kind':'without_undue_delay','legal_basis':'Synthetic qualitative timing'},'required_action':'Perform and review the actual action','required_document_types':documents or [],'accountable_role':'educator','interpretation_notes':'Synthetic interpretation for runtime test only'},h,201)
    if review:version=post(c,b+f'/requirement-versions/{version["id"]}/review',{'expected_version':version['version'],'rationale':'Synthetic authorized review'},h)
    return definition,version,h


def profile_setup(env,version,h,activate=True,**changes):
    c,_,ids,_,_=env;b=base(ids)
    profile=post(c,b+'/profiles',{'label':'Synthetic profile','requirement_version_ids':[version['id']],'valid_from':'2020-01-01',**changes},h,201)
    if activate:
        impact=c.get(b+f'/profiles/{profile["id"]}/impact').json()
        profile=post(c,b+f'/profiles/{profile["id"]}/activate',{'expected_version':1,'rationale':'Reviewed for this school','impact_digest':impact['impact_digest']},h)
    return profile


def trigger_body(profile,**changes):
    return {'event_key':'event-'+uuid4().hex,'profile_id':profile['id'],'event_type':'synthetic_event','occurred_at':(utcnow()-timedelta(days=1)).isoformat(),'period_key':'2026-test',**changes}


def trigger_setup(env,**kwargs):
    d,v,h=rule_setup(env,**kwargs);p=profile_setup(env,v,h);c,_,ids,_,_=env
    body=trigger_body(p)
    task=post(c,base(ids)+'/triggers',body,h,201)['items'][0]
    return task,h,p,body


def test_no_file_presence_activation_import_review_and_current_authority(env):
    c,f,ids,_,_=env;b=base(ids);h=login(c)
    assert c.get(b+'/requirements').json()['total']==0
    imported=post(c,b+'/candidate-imports/bundled',{},h)
    assert imported['imported']==90 and imported['state']=='unreviewed'
    assert post(c,b+'/candidate-imports/bundled',{},h)['imported']==0
    assert c.get(b+'/requirements').json()['total']==0
    assert c.get(b+'/candidates').json()['items'][0]['state']=='unreviewed'
    _,v,h=rule_setup(env,review=False)
    p=profile_setup(env,v,h,activate=False)
    impact=c.get(b+f'/profiles/{p["id"]}/impact').json()
    body={'expected_version':1,'rationale':'Attempt','impact_digest':impact['impact_digest']}
    post(c,b+f'/profiles/{p["id"]}/activate',body,h,400)
    post(c,b+'/triggers',trigger_body(p),h,400)
    post(c,b+f'/requirement-versions/{v["id"]}/review',{'expected_version':1,'rationale':'Review'},h)
    with f.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['leader'],AuthorityGrant.action=='governance.rules.approve'));grant.state='revoked'
    post(c,b+f'/profiles/{p["id"]}/activate',body,h,403)
    h=login(c,'teacher')
    post(c,b+'/requirements',{'code':'cannot','title':'No','source_type':'local_routine','source_reference':'Synthetic'},h,403)
    assert c.get(b+'/candidates').status_code==403


def test_unresolved_applicability_inputs_are_not_green_and_timing_separate(env):
    task,h,p,body=trigger_setup(env,conditions=[{'fact':'support_entitlement','equals':'ITO'}],deadline={'kind':'calendar_period','legal_basis':'Synthetic different procedure','count':3,'unit':'weeks','calendar':'calendar_days','start':'provided_start'})
    c,f,ids,_,_=env;b=base(ids)
    assert task['applicability']=='unresolved' and task['unresolved_inputs']==['support_entitlement']
    assert task['deadline_at'] is None and 'Missing start_date' in task['deadline_reasons']
    assigned=post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':task['version'],'owner_id':ids['teacher'],'internal_planned_date':'2026-11-01','reason':'Local reminder only'},h)
    assert assigned['deadline_at'] is None and assigned['internal_planned_date']=='2026-11-01'
    resolved=post(c,b+f'/obligations/{task["id"]}/inputs',{'expected_version':assigned['version'],'inputs':{'support_entitlement':'ITO'},'timing':{'start_date':'2026-10-01'},'reason':'Confirmed inputs'},h)
    assert resolved['applicability']=='applicable' and resolved['deadline_date']=='2026-10-22'
    assert resolved['internal_planned_date']=='2026-11-01'
    assert datetime.fromisoformat(resolved['deadline_at'])==datetime(2026,10,22,22,tzinfo=timezone.utc)
    post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':assigned['version'],'owner_id':None,'reason':'Stale'},h,409)
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.ObligationAssignment))==1


def test_timing_types_local_calendar_and_dst_are_distinct():
    instant=datetime(2026,10,24,23,30,tzinfo=timezone.utc)
    fixed=s.DeadlineRule(kind='fixed_date',fixed_date=date(2026,10,25),legal_basis='Synthetic date')
    due,at,reasons=resolve_deadline(fixed,s.TimingInputs(),instant,'Europe/Oslo')
    assert due==date(2026,10,25) and at==datetime(2026,10,25,23,tzinfo=timezone.utc)
    immediate=s.DeadlineRule(kind='immediate',legal_basis='Synthetic immediate')
    assert resolve_deadline(immediate,s.TimingInputs(),instant,'Europe/Oslo')[1]==instant
    qualitative=s.DeadlineRule(kind='without_undue_delay',legal_basis='Synthetic qualitative')
    assert resolve_deadline(qualitative,s.TimingInputs(),instant,'Europe/Oslo')[1] is None
    for count in (3,14):
        rule=s.DeadlineRule(kind='calendar_period',legal_basis='Different synthetic procedure',count=count,unit='days',calendar='calendar_days',start='event_date')
        assert resolve_deadline(rule,s.TimingInputs(),instant,'Europe/Oslo')[0]==date(2026,10,25)+timedelta(days=count)
    school=s.DeadlineRule(kind='calendar_period',legal_basis='Synthetic school days',count=2,unit='days',calendar='school_days',start='provided_start')
    assert resolve_deadline(school,s.TimingInputs(start_date=date(2026,10,23)),instant,'Europe/Oslo')[1] is None
    timing=s.TimingInputs(start_date=date(2026,10,23),calendar_reference='reviewed local calendar',calendar_valid_from=date(2026,10,1),calendar_valid_until=date(2026,11,1),school_dates=[date(2026,10,27),date(2026,10,30)])
    assert resolve_deadline(school,timing,instant,'Europe/Oslo')[0]==date(2026,10,30)
    assert evaluate_applicability([{'fact':'learner_grade','equals':True}],{'learner_grade':1})[0]=='not_applicable'
    with pytest.raises(ValueError):s.Trigger.model_validate({'event_key':'x','profile_id':str(uuid4()),'event_type':'x','occurred_at':'2026-10-25T12:00:00','period_key':'x'})


def test_document_is_not_performed_action_or_deviation_resolution(env):
    task,h,_,_=trigger_setup(env,documents=['report']);c,f,ids,_,_=env;b=base(ids);path=b+f'/obligations/{task["id"]}'
    deviation=post(c,b+'/deviations',{'obligation_id':task['id'],'issue_type':'missing_delivery','description':'Synthetic missing actual delivery','owner_id':ids['leader']},h,201)
    upload=post(c,path+'/actions',{'expected_version':task['version'],'kind':'document_upload','action_type':'report','description':'Synthetic report upload','occurred_at':utcnow().isoformat(),'evidence_references':[ids['document']]},h,201)
    post(c,path+'/review',{'expected_version':upload['obligation']['version'],'decision':'satisfied','rationale':'Attempt'},h,400)
    post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':deviation['version'],'action':'resolve','explanation':'Attempt','performed_action_id':upload['action']['id']},h,400)
    action=post(c,path+'/actions',{'expected_version':upload['obligation']['version'],'kind':'performed_action','action_type':'delivered_support','description':'Synthetic observed actual action','occurred_at':utcnow().isoformat()},h,201)
    reviewed=post(c,path+'/review',{'expected_version':action['obligation']['version'],'decision':'satisfied','rationale':'Human checked actual fulfillment'},h)
    assert reviewed['state']=='reviewed_satisfied'
    assert c.get(b+f'/deviations/{deviation["id"]}').json()['state']=='open'
    resolved=post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':deviation['version'],'action':'resolve','explanation':'Remedial action reviewed','performed_action_id':action['action']['id']},h)
    assert resolved['state']=='resolved'
    post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':resolved['version'],'action':'reopen','explanation':'Further issue'},h)


def test_idempotency_conflicting_key_concurrency_and_transaction_rollback(env,monkeypatch):
    task,h,p,body=trigger_setup(env);c,f,ids,dialect,_=env;b=base(ids)
    duplicate=post(c,b+'/triggers',body,h,201)['items'][0]
    assert duplicate['id']==task['id']
    post(c,b+'/triggers',{**body,'period_key':'other'},h,409)
    actor=Actor(ids['leader']);new=trigger_body(p)
    if dialect=='postgres':
        def run():
            with f() as db:return svc.trigger_obligations(db,actor,ids['school'],s.Trigger.model_validate(new))[0].id
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        assert len(set(results))==1
    with f() as db:
        before=db.scalar(select(func.count()).select_from(m.ObligationInstance));audit=db.scalar(select(func.count()).select_from(AuditRecord));events=db.scalar(select(func.count()).select_from(m.GovernanceEvent))
    original=svc.publish
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('synthetic failure after flush')
    monkeypatch.setattr(svc,'publish',fail)
    with f() as db,pytest.raises(RuntimeError):svc.trigger_obligations(db,actor,ids['school'],s.Trigger.model_validate(trigger_body(p)))
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.ObligationInstance))==before
        assert db.scalar(select(func.count()).select_from(AuditRecord))==audit
        assert db.scalar(select(func.count()).select_from(m.GovernanceEvent))==events


def test_rule_revisions_impact_binding_preserves_historical_tasks_and_profile_dates(env):
    task,h,p,body=trigger_setup(env);c,f,ids,_,_=env;b=base(ids)
    with f() as db:v=db.get(m.RequirementVersion,task['requirement_version_id']);requirement=db.get(m.RequirementDefinition,v.requirement_id);rid=requirement.id;rv=requirement.version
    v2=post(c,b+f'/requirements/{rid}/versions',{'expected_version':rv,'valid_from':'2020-01-01','conditions':[],'trigger_type':'synthetic_event','deadline':{'kind':'fixed_date','fixed_date':'2026-11-01','legal_basis':'Different synthetic timing'},'required_action':'Revised action','accountable_role':'educator','interpretation_notes':'Reviewed change'},h,201)
    v2=post(c,b+f'/requirement-versions/{v2["id"]}/review',{'expected_version':1,'rationale':'Authorized revision'},h)
    p2=profile_setup(env,v2,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=p['id'])
    impact=c.get(b+f'/profiles/{p2["id"]}/impact').json()
    assert impact['total']==1 and impact['items'][0]['obligation_id']==task['id']
    changed=post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':task['version'],'owner_id':ids['leader'],'reason':'Changes reviewed impact'},h)
    post(c,b+f'/profiles/{p2["id"]}/activate',{'expected_version':1,'rationale':'Attempt','impact_digest':impact['impact_digest']},h,409)
    impact=c.get(b+f'/profiles/{p2["id"]}/impact').json()
    post(c,b+f'/profiles/{p2["id"]}/activate',{'expected_version':1,'rationale':'Review actual affected tasks','impact_digest':impact['impact_digest']},h)
    old=c.get(b+f'/obligations/{task["id"]}').json();assert old['deadline_kind']=='without_undue_delay'
    post(c,b+'/triggers',trigger_body(p,occurred_at=utcnow().isoformat()),h,400)
    newtask=post(c,b+'/triggers',trigger_body(p2,occurred_at=utcnow().isoformat()),h,201)['items'][0]
    assert newtask['deadline_date']=='2026-11-01'
    with f() as db,pytest.raises(ValueError):
        row=db.get(m.RequirementVersion,v2['id']);row.required_action='Silent rewrite';db.flush()
    if env[3]=='postgres':
        with f() as db,pytest.raises(DBAPIError):db.execute(text('UPDATE governance_requirement_versions SET required_action=:text WHERE id=:id'),{'text':'Silent SQL rewrite','id':v2['id']})


def test_owner_assignment_not_content_authority_and_leadership_suppression(env):
    _,v,h=rule_setup(env);p=profile_setup(env,v,h);c,f,ids,_,_=env;b=base(ids)
    task=post(c,b+'/triggers',trigger_body(p,learner_id=ids['learner']),h,201)['items'][0]
    assigned=post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':task['version'],'owner_id':ids['outsider'],'reason':'Follow-up owner'},h)
    h2=login(c,'outsider')
    work=c.get(b+'/obligations').json();assert work['total']==1
    assert 'learner_id' not in work['items'][0] and 'evaluated_inputs' not in work['items'][0]
    assert c.get(b+f'/obligations/{task["id"]}').status_code==403
    post(c,b+f'/obligations/{task["id"]}/actions',{'expected_version':assigned['version'],'kind':'performed_action','action_type':'attempt','description':'Attempt','occurred_at':utcnow().isoformat()},h2,403)
    login(c,'board')
    overview=c.get(b+'/overview').json()
    assert overview['pupil_cohort_status']=='suppressed' and overview['indicators']['no_owner']==0
    assert 'SECRET' not in str(overview) and task['id'] not in str(overview)
    assert c.get(b+'/deviations').json()=={'items':[],'total':0}
    login(c)
    assert c.get(f'/api/v1/schools/{ids["other_school"]}/governance/obligations/{task["id"]}').status_code==403


def test_overdue_no_owner_inactive_owner_and_unknown_remain_distinct(env):
    task,h,_,_=trigger_setup(env,deadline={'kind':'immediate','legal_basis':'Synthetic immediate duty'});c,f,ids,_,_=env;b=base(ids)
    status=task['status'];assert status['overdue'] and status['owner_status']=='no_owner' and not status['unknown_rule']
    post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':task['version'],'owner_id':ids['teacher'],'reason':'Owner'},h)
    with f.begin() as db:
        member=db.scalar(select(SchoolMembership).where(SchoolMembership.user_id==ids['teacher']));member.state='revoked'
    status=c.get(b+f'/obligations/{task["id"]}').json()['status']
    assert status['overdue'] and status['owner_status']=='inactive_owner'
    overview=c.get(b+'/overview').json();assert overview['indicators']['overdue']==1 and overview['indicators']['inactive_owner']==1


def test_workload_voluntary_comparable_all_time_cost_no_fake_savings(env):
    c,f,ids,_,_=env;b=base(ids);h=login(c)
    study=post(c,b+'/workload-studies',{'title':'Synthetic preparation study','task_type':'session_preparation','protocol':'Same task, scenario and complexity before and with assistance','quality_rubric':'Human review on agreed five point scale','minimum_quality':3},h,201)
    path=b+f'/workload-studies/{study["id"]}'
    measurement={'match_key':'same-preparation','mode':'manual','complexity':'medium','scenario':'Synthetic matched lesson','primary_minutes':10,'review_minutes':0,'correction_minutes':0,'duplicate_entry_minutes':0,'followup_minutes':0,'quality':4,'usefulness':3}
    post(c,path+'/measurements',measurement,h,403)
    assert c.get(path+'/results').json()['saving_percent'] is None
    for who in ('leader','teacher','volunteer'):
        h=login(c,who)
        post(c,path+'/participation',{'consent':True},h)
        post(c,path+'/measurements',measurement,h,201)
        post(c,path+'/measurements',{**measurement,'mode':'assisted','primary_minutes':5,'review_minutes':10},h,201)
        post(c,path+'/measurements',{**measurement,'match_key':'incomplete','review_minutes':None},h,201)
        post(c,path+'/measurements',{**measurement,'match_key':'incomplete','mode':'assisted'},h,201)
        post(c,path+'/measurements',{**measurement,'match_key':'mismatch'},h,201)
        post(c,path+'/measurements',{**measurement,'match_key':'mismatch','mode':'assisted','complexity':'high'},h,201)
        post(c,path+'/measurements',{**measurement,'match_key':'no-baseline','mode':'assisted'},h,201)
    h=login(c)
    result=c.get(path+'/results').json()
    assert result['status']=='comparable' and result['saved_minutes']==-15 and result['saving_percent']==-50
    assert result['manual_minutes']==30 and result['assisted_minutes']==45
    assert result['incomplete_or_noncomparable']=={'incomplete_time_or_quality':3,'noncomparable_task':3,'missing_matched_baseline_or_assisted':3}
    assert ids['teacher'] not in str(result)
    mine=c.get(path+'/my-measurements').json()['items']
    old=next(r for r in mine if r['match_key']=='same-preparation' and r['mode']=='assisted')
    post(c,path+'/measurements',{**measurement,'mode':'assisted','primary_minutes':5},h,409)
    revised=post(c,path+'/measurements',{**measurement,'mode':'assisted','primary_minutes':5,'quality':1,'previous_measurement_id':old['id']},h,201)
    assert revised['revision_number']==2
    result=c.get(path+'/results').json();assert result['status']=='quality_review_required' and result['saving_percent'] is None and result['saved_minutes'] is None
    participation=post(c,path+'/participation',{'consent':False,'expected_version':1},h)
    assert participation['version']==2
    assert c.get(path+'/results').json()['status']=='insufficient_comparable_sample'
    post(c,path+'/measurements',{**measurement,'match_key':'after-withdrawal'},h,403)
    h=login(c,'teacher');assert c.get(path+'/results').status_code==403


def test_protected_case_grant_is_exact_and_revoked_scope_denies_existing_owner(env):
    _,v,h=rule_setup(env);p=profile_setup(env,v,h);c,f,ids,_,_=env;b=base(ids);case=str(uuid4())
    body=trigger_body(p,learner_id=ids['learner'],case_id=case)
    # A learner team assignment and school governance authority are insufficient.
    post(c,b+'/triggers',body,h,403)
    with f.begin() as db:
        grant=AuthorityGrant(school_id=ids['school'],user_id=ids['leader'],action='governance.case.read',learner_id=ids['learner'],case_id=case,valid_from=date(2020,1,1),granted_by=ids['leader'])
        db.add(grant);db.flush();grant_id=grant.id
    post(c,b+'/triggers',body,h,503)
    c.app.state.governance_case_scope_resolver=lambda db,actor,school_id,case_id: ids['learner'] if case_id==case and school_id==ids['school'] else None
    task=post(c,b+'/triggers',body,h,201)['items'][0]
    post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':1,'owner_id':ids['leader'],'reason':'Exact protected case follow-up'},h)
    assert c.get(b+f'/obligations/{task["id"]}').status_code==200
    with f.begin() as db:db.get(AuthorityGrant,grant_id).state='revoked'
    assert c.get(b+f'/obligations/{task["id"]}').status_code==403
    listing=c.get(b+'/obligations').json()['items'][0]
    assert 'case_id' not in listing and 'learner_id' not in listing
    assert 'period_key' not in listing


def test_current_rule_withdrawal_is_unknown_and_profile_revocation_never_reactivates_old(env):
    task,h,p,body=trigger_setup(env);c,f,ids,_,_=env;b=base(ids)
    withdrawn=post(c,b+f'/requirement-versions/{task["requirement_version_id"]}/withdraw',{'expected_version':2,'rationale':'Interpretation requires another review'},h)
    assert withdrawn['state']=='withdrawn' and withdrawn['review_rationale']=='Synthetic authorized review'
    assert withdrawn['withdrawal_rationale']=='Interpretation requires another review'
    assert c.get(b+f'/obligations/{task["id"]}').json()['status']['unknown_rule']
    post(c,b+'/triggers',trigger_body(p),h,400)
    # An exact retry remains historical and has no duplicate effect.
    assert post(c,b+'/triggers',body,h,201)['items'][0]['id']==task['id']
    post(c,b+f'/profiles/{p["id"]}/revoke',{'expected_version':p['version'],'rationale':'School approval withdrawn'},h)
    post(c,b+'/triggers',trigger_body(p),h,400)


def test_cell_suppression_for_single_deviation_inside_larger_pupil_cohort(env):
    _,v,h=rule_setup(env);p=profile_setup(env,v,h);c,f,ids,_,_=env;b=base(ids)
    learners=[]
    with f.begin() as db:
        for n in range(5):
            row=Learner(school_id=ids['school'],display_name='SYNTHETIC SECRET '+str(n),grade=3,group_name='Synthetic')
            db.add(row);db.flush();learners.append(row.id)
            db.add(StaffAssignment(school_id=ids['school'],user_id=ids['leader'],learner_id=row.id,actions=['learner.read'],purpose='synthetic',valid_from=date(2020,1,1)))
    for learner in learners:
        task=post(c,b+'/triggers',trigger_body(p,learner_id=learner),h,201)['items'][0]
    post(c,b+'/deviations',{'obligation_id':task['id'],'issue_type':'other','description':'SYNTHETIC SECRET CASE'},h,201)
    login(c,'board')
    report=c.get(b+'/overview').json()
    assert report['pupil_cohort_status']=='aggregated_with_cell_suppression'
    assert report['pupil_indicators']['no_owner']==5
    assert report['pupil_indicators']['open_deviations'] is None
    assert 'SECRET' not in str(report) and not any(i in str(report) for i in learners)


def test_required_document_action_future_and_append_only_assessment_history(env):
    task,h,p,body=trigger_setup(env,conditions=[{'fact':'support_entitlement','equals':'ITO'}],documents=['specific_report'])
    c,f,ids,_,_=env;b=base(ids);path=b+f'/obligations/{task["id"]}'
    task=post(c,path+'/inputs',{'expected_version':task['version'],'inputs':{'support_entitlement':'ITO'},'timing':{},'reason':'Synthetic verified entitlement'},h)
    history=c.get(path).json()['applicability_history']
    assert len(history)==2 and history[0]['applicability']=='unresolved' and history[1]['applicability']=='applicable'
    post(c,path+'/actions',{'expected_version':task['version'],'kind':'performed_action','action_type':'done','description':'Future is not actual','occurred_at':(utcnow()+timedelta(days=1)).isoformat()},h,400)
    action=post(c,path+'/actions',{'expected_version':task['version'],'kind':'performed_action','action_type':'done','description':'Actual action','occurred_at':utcnow().isoformat()},h,201)
    r=c.post(path+'/review',json={'expected_version':action['obligation']['version'],'decision':'satisfied','rationale':'Missing required document'},headers=h)
    assert r.status_code==400 and r.json()['error']['code']=='required_document_missing'
    if env[3]=='postgres':
        with f() as db,pytest.raises(DBAPIError):
            db.execute(text('DELETE FROM governance_applicability_decisions WHERE obligation_id=:id'),{'id':task['id']})


def test_workload_incomplete_can_be_corrected_zero_baseline_no_percentage_and_closed_study(env):
    c,f,ids,_,_=env;b=base(ids);h=login(c)
    study=post(c,b+'/workload-studies',{'title':'Zero synthetic baseline','task_type':'observation_note','protocol':'Matched zero duration tasks','quality_rubric':'Human scale','minimum_quality':3},h,201);path=b+f'/workload-studies/{study["id"]}'
    measurement={'match_key':'zero','mode':'manual','complexity':'low','scenario':'Synthetic zero baseline','primary_minutes':0,'review_minutes':0,'correction_minutes':0,'duplicate_entry_minutes':0,'followup_minutes':0,'quality':4}
    for who in ('leader','teacher','volunteer'):
        h=login(c,who);post(c,path+'/participation',{'consent':True},h)
        baseline=post(c,path+'/measurements',{**measurement,'review_minutes':None},h,201)
        post(c,path+'/measurements',{**measurement,'previous_measurement_id':baseline['id']},h,201)
        post(c,path+'/measurements',{**measurement,'mode':'assisted','review_minutes':2},h,201)
    h=login(c);result=c.get(path+'/results').json()
    assert result['status']=='comparable' and result['manual_minutes']==0 and result['saved_minutes']==-6 and result['saving_percent'] is None
    post(c,path+'/close',{'expected_version':1,'rationale':'Pilot complete'},h)
    post(c,path+'/measurements',{**measurement,'match_key':'closed'},h,400)


def test_context_migration_roundtrip_isolated_database(env):
    c,f,ids,dialect,config=env
    # Only this context's revision; other agents' migration heads are independent.
    command.downgrade(config,'a9e1f00151e4')
    command.upgrade(config,'j13_governance')
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.RequirementDefinition))==0
        assert db.get(UserAccount,ids['leader']) is not None


def test_scoped_deviation_owner_can_follow_up_but_cannot_self_approve_resolution(env):
    _,v,h=rule_setup(env);p=profile_setup(env,v,h);c,f,ids,_,_=env;b=base(ids)
    task=post(c,b+'/triggers',trigger_body(p,learner_id=ids['learner']),h,201)['items'][0]
    deviation=post(c,b+'/deviations',{'obligation_id':task['id'],'issue_type':'missing_delivery','description':'Synthetic issue','owner_id':ids['teacher']},h,201)
    h=login(c,'teacher')
    assert c.get(b+'/deviations').json()['total']==1
    followed=post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':deviation['version'],'action':'followup','explanation':'Contacted the responsible educator; review pending'},h)
    post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':followed['version'],'action':'resolve','explanation':'Attempted self approval'},h,403)
    assert len(c.get(b+f'/deviations/{deviation["id"]}').json()['followups'])==1


def test_evidence_adapter_is_required_scope_checked_and_revision_rechecked(env):
    task,h,_,_=trigger_setup(env,documents=['report']);c,f,ids,_,_=env;b=base(ids);path=b+f'/obligations/{task["id"]}'
    evidence={'expected_version':task['version'],'kind':'document_upload','action_type':'report','description':'Synthetic attribution','occurred_at':utcnow().isoformat(),'evidence_references':[ids['document']]}
    del c.app.state.governance_evidence_validator
    post(c,path+'/actions',evidence,h,503)
    post(c,path+'/actions',{**evidence,'evidence_references':[]},h,422)
    def foreign(db,actor,school_id,learner_id,case_id,reference_id):
        return ValidatedEvidenceReference(reference_id,ids['other_school'],None,None,1,'a'*64)
    c.app.state.governance_evidence_validator=foreign
    post(c,path+'/actions',evidence,h,403)
    def valid(db,actor,school_id,learner_id,case_id,reference_id):
        return ValidatedEvidenceReference(reference_id,school_id,learner_id,case_id,1,'a'*64)
    c.app.state.governance_evidence_validator=valid
    upload=post(c,path+'/actions',evidence,h,201)
    assert upload['action']['evidence_references']==[{'reference_id':ids['document'],'revision':1,'digest':'a'*64}]
    performed=post(c,path+'/actions',{'expected_version':upload['obligation']['version'],'kind':'performed_action','action_type':'actual_action','description':'Human performed the real action','occurred_at':utcnow().isoformat()},h,201)
    def changed(db,actor,school_id,learner_id,case_id,reference_id):
        return ValidatedEvidenceReference(reference_id,school_id,learner_id,case_id,2,'b'*64)
    c.app.state.governance_evidence_validator=changed
    post(c,path+'/review',{'expected_version':performed['obligation']['version'],'decision':'satisfied','rationale':'Changed source must not reuse old evidence binding'},h,409)
    refreshed=post(c,path+'/actions',{**evidence,'expected_version':performed['obligation']['version']},h,201)
    assert post(c,path+'/review',{'expected_version':refreshed['obligation']['version'],'decision':'satisfied','rationale':'Reviewed refreshed documentation and performed action'},h)['state']=='reviewed_satisfied'


def test_idempotent_retry_in_reused_service_session_returns_current_owner(env):
    task,h,p,body=trigger_setup(env);c,f,ids,_,_=env;actor=Actor(ids['leader'])
    with f() as first:
        original=svc.trigger_obligations(first,actor,ids['school'],s.Trigger.model_validate(body))[0]
        assert original.owner_id is None
        with f() as second:
            changed=svc.assign_task(second,actor,ids['school'],task['id'],s.Assignment(expected_version=original.version,owner_id=ids['teacher'],reason='Synthetic concurrent reassignment'))
        retried=svc.trigger_obligations(first,actor,ids['school'],s.Trigger.model_validate(body))[0]
        assert retried.id==original.id and retried.owner_id==ids['teacher'] and retried.version==changed.version


def test_review_r1_impact_filters_identifiable_scope_and_binds_hidden_changes(env):
    c,f,ids,_,_=env;b=base(ids)
    _,version,h=rule_setup(env)
    profile=profile_setup(env,version,h)
    case=str(uuid4())
    with f.begin() as db:
        db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['leader'],action='governance.case.read',learner_id=ids['learner'],case_id=case,valid_from=date(2020,1,1),granted_by=ids['leader']))
        db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['outsider'],action='governance.rules.approve',valid_from=date(2020,1,1),granted_by=ids['leader']))
    c.app.state.governance_case_scope_resolver=lambda db,actor,school,case_id: ids['learner'] if case_id==case else None
    task=post(c,b+'/triggers',trigger_body(profile,learner_id=ids['learner'],case_id=case),h,201)['items'][0]
    _,replacement,h=rule_setup(env)
    proposed=profile_setup(env,replacement,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'])
    leader_impact=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert leader_impact['items'][0]['obligation_id']==task['id']
    h_outsider=login(c,'outsider')
    assert c.get(b+f'/obligations/{task["id"]}').status_code==403
    limited=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert limited['items']==[] and limited['total']==0
    assert limited['total_scope']=='authorized_obligations_only'
    assert limited['impact_digest']==leader_impact['impact_digest']
    assert task['id'] not in str(limited) and case not in str(limited) and ids['learner'] not in str(limited)
    assert version['id'] not in str(limited)
    # A change to hidden work still invalidates the approval fingerprint, without
    # disclosing the hidden task or its exact count to this rule approver.
    h=login(c)
    post(c,b+f'/obligations/{task["id"]}/assignment',{'expected_version':task['version'],'owner_id':ids['leader'],'reason':'Changed during review'},h)
    h_outsider=login(c,'outsider')
    post(c,b+f'/profiles/{proposed["id"]}/activate',{'expected_version':proposed['version'],'rationale':'Stale restricted preview','impact_digest':limited['impact_digest']},h_outsider,409)
    updated=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert updated['items']==[] and updated['total']==0 and updated['impact_digest']!=limited['impact_digest']
    post(c,b+f'/profiles/{proposed["id"]}/activate',{'expected_version':proposed['version'],'rationale':'Reviewed school rule change with subject details restricted','impact_digest':updated['impact_digest']},h_outsider)


def test_review_r1_revoked_case_authority_removes_impact_details(env):
    c,f,ids,_,_=env;b=base(ids)
    _,version,h=rule_setup(env);profile=profile_setup(env,version,h);case=str(uuid4())
    with f.begin() as db:
        grant=AuthorityGrant(school_id=ids['school'],user_id=ids['leader'],action='governance.case.read',learner_id=ids['learner'],case_id=case,valid_from=date(2020,1,1),granted_by=ids['leader'])
        db.add(grant);db.flush();grant_id=grant.id
    c.app.state.governance_case_scope_resolver=lambda *args:ids['learner']
    task=post(c,b+'/triggers',trigger_body(profile,learner_id=ids['learner'],case_id=case),h,201)['items'][0]
    _,replacement,h=rule_setup(env)
    proposed=profile_setup(env,replacement,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'])
    full=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert full['total']==1
    with f.begin() as db:db.get(AuthorityGrant,grant_id).state='revoked'
    limited=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert limited['items']==[] and limited['total']==0
    assert limited['impact_digest']==full['impact_digest']
    assert task['id'] not in str(limited)


def test_review_r2_same_rule_school_facts_show_changed_and_unknown_applicability(env):
    c,f,ids,_,_=env;b=base(ids)
    _,version,h=rule_setup(env,conditions=[{'fact':'curriculum_scheme','equals':'A'}])
    profile=profile_setup(env,version,h,school_inputs={'curriculum_scheme':'A'})
    task=post(c,b+'/triggers',trigger_body(profile),h,201)['items'][0]
    proposed=profile_setup(env,version,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'],school_inputs={'curriculum_scheme':'B'})
    impact=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert impact['total']==1
    effect=impact['items'][0]
    assert effect['previous_requirement_version_id']==effect['proposed_requirement_version_id']==version['id']
    assert effect['before']['applicability']=='applicable' and effect['after']['applicability']=='not_applicable'
    assert effect['before']['deadline_kind']==effect['after']['deadline_kind']=='without_undue_delay'
    assert effect['changed_school_inputs']==[{'fact':'curriculum_scheme','before_known':True,'before':'A','after_known':True,'after':'B'}]
    missing=profile_setup(env,version,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'],school_inputs={})
    missing_impact=c.get(b+f'/profiles/{missing["id"]}/impact').json()
    assert missing_impact['items'][0]['after']['applicability']=='unresolved'
    assert missing_impact['items'][0]['after']['unresolved_inputs']==['curriculum_scheme']
    assert missing_impact['school_input_changes'][0]['after_known'] is False
    post(c,b+f'/profiles/{proposed["id"]}/activate',{'expected_version':1,'rationale':'Reviewed applicability effect','impact_digest':impact['impact_digest']},h)
    assert c.get(b+f'/obligations/{task["id"]}').json()['applicability']=='applicable'
    assert post(c,b+'/triggers',trigger_body(proposed,occurred_at=utcnow().isoformat()),h,201)['items'][0]['applicability']=='not_applicable'


def test_review_r2_previously_not_applicable_and_changed_deadline_inputs_are_visible(env):
    c,f,ids,_,_=env;b=base(ids)
    _,version,h=rule_setup(env,conditions=[{'fact':'curriculum_scheme','equals':'A'}])
    profile=profile_setup(env,version,h,school_inputs={'curriculum_scheme':'B'})
    task=post(c,b+'/triggers',trigger_body(profile),h,201)['items'][0]
    assert task['applicability']=='not_applicable'
    proposed=profile_setup(env,version,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'],school_inputs={'curriculum_scheme':'A'})
    impact=c.get(b+f'/profiles/{proposed["id"]}/impact').json()
    assert impact['items'][0]['before']['applicability']=='not_applicable'
    assert impact['items'][0]['after']['applicability']=='applicable'
    with f() as db:
        old=db.get(m.RequirementVersion,version['id']);definition=db.get(m.RequirementDefinition,old.requirement_id)
        definition_id,expected=definition.id,definition.version
    revision=post(c,b+f'/requirements/{definition_id}/versions',{'expected_version':expected,'valid_from':'2020-01-01','conditions':[{'fact':'curriculum_scheme','equals':'A'}],'trigger_type':'synthetic_event','deadline':{'kind':'calendar_period','count':3,'unit':'days','calendar':'school_days','start':'provided_start','legal_basis':'Synthetic changed legal timing'},'required_action':'Same synthetic action','accountable_role':'educator','interpretation_notes':'Reviewed timing change'},h,201)
    revision=post(c,b+f'/requirement-versions/{revision["id"]}/review',{'expected_version':1,'rationale':'Reviewed timing'},h)
    timed=profile_setup(env,revision,h,activate=False,valid_from=date.today().isoformat(),supersedes_profile_id=profile['id'],school_inputs={'curriculum_scheme':'A'})
    timed_impact=c.get(b+f'/profiles/{timed["id"]}/impact').json()['items'][0]
    assert timed_impact['after']['deadline_kind']=='calendar_period'
    assert timed_impact['after']['deadline_at'] is None and timed_impact['after']['deadline_reasons']==['Missing start_date']
    assert c.get(b+f'/obligations/{task["id"]}').json()['deadline_kind']=='without_undue_delay'


def test_review_r3_closed_study_withdrawal_keeps_history_and_excludes_aggregate(env):
    c,f,ids,_,_=env;b=base(ids);h=login(c)
    study=post(c,b+'/workload-studies',{'title':'Synthetic consent study','task_type':'session_preparation','protocol':'Matched synthetic tasks','quality_rubric':'Synthetic quality scale','minimum_quality':3},h,201)
    path=b+f'/workload-studies/{study["id"]}'
    measurement={'match_key':'matched','mode':'manual','complexity':'low','scenario':'Synthetic','primary_minutes':10,'review_minutes':0,'correction_minutes':0,'duplicate_entry_minutes':0,'followup_minutes':0,'quality':4}
    for who in ('leader','teacher','volunteer'):
        h=login(c,who);post(c,path+'/participation',{'consent':True},h)
        post(c,path+'/measurements',measurement,h,201)
        post(c,path+'/measurements',{**measurement,'mode':'assisted','primary_minutes':5},h,201)
    h=login(c);assert c.get(path+'/results').json()['manual_minutes']==30
    post(c,path+'/close',{'expected_version':1,'rationale':'Collection complete'},h)
    post(c,path+'/participation',{'consent':False,'expected_version':0},h,409)
    assert post(c,path+'/participation',{'consent':False,'expected_version':1},h)=={'consent':False,'version':2}
    result=c.get(path+'/results').json()
    assert result['status']=='insufficient_comparable_sample' and result['manual_minutes'] is None
    assert c.get(path+'/my-measurements').json()['total']==2
    with f() as db:
        participant=db.scalar(select(m.WorkloadParticipant).where(m.WorkloadParticipant.study_id==study['id'],m.WorkloadParticipant.user_id==ids['leader']))
        withdrawal=participant.withdrawn_at
        assert participant.consented_at < withdrawal
        assert db.scalar(select(func.count()).select_from(m.WorkloadMeasurement).where(m.WorkloadMeasurement.participant_id==participant.id))==2
    assert post(c,path+'/participation',{'consent':False,'expected_version':2},h)=={'consent':False,'version':2}
    with f() as db:assert db.get(m.WorkloadParticipant,participant.id).withdrawn_at==withdrawal
    post(c,path+'/participation',{'consent':True,'expected_version':2},h,400)
    post(c,path+'/measurements',{**measurement,'match_key':'after-close'},h,400)
    h=login(c,'outsider');post(c,path+'/participation',{'consent':True},h,400)


def test_review_r4_action_occurrence_and_reopening_bound_remedial_period(env):
    task,h,_,_=trigger_setup(env);c,f,ids,_,_=env;b=base(ids);path=b+f'/obligations/{task["id"]}'
    deviation=post(c,b+'/deviations',{'obligation_id':task['id'],'issue_type':'missing_delivery','description':'Current synthetic missing delivery'},h,201)
    old=post(c,path+'/actions',{'expected_version':task['version'],'kind':'performed_action','action_type':'old_delivery','description':'A month-old action entered after the current issue','occurred_at':(utcnow()-timedelta(days=30)).isoformat()},h,201)
    resolution={'expected_version':deviation['version'],'action':'resolve','explanation':'Attempt to reuse earlier actual delivery','performed_action_id':old['action']['id']}
    rejected=c.post(b+f'/deviations/{deviation["id"]}/followups',json=resolution,headers=h)
    assert rejected.status_code==400 and rejected.json()['error']['code']=='remedial_action_predates_issue'
    current=c.get(b+f'/deviations/{deviation["id"]}').json()
    assert current['state']=='open' and current['version']==deviation['version'] and current['followups']==[]
    actual=post(c,path+'/actions',{'expected_version':old['obligation']['version'],'kind':'performed_action','action_type':'remedial_delivery','description':'Performed after the current reported issue','occurred_at':utcnow().isoformat()},h,201)
    resolved=post(c,b+f'/deviations/{deviation["id"]}/followups',{**resolution,'performed_action_id':actual['action']['id']},h)
    reopened=post(c,b+f'/deviations/{deviation["id"]}/followups',{'expected_version':resolved['version'],'action':'reopen','explanation':'A renewed issue requires current remediation'},h)
    post(c,b+f'/deviations/{deviation["id"]}/followups',{**resolution,'expected_version':reopened['version'],'performed_action_id':actual['action']['id']},h,400)
    final_action=post(c,path+'/actions',{'expected_version':actual['obligation']['version'],'kind':'performed_action','action_type':'renewed_remediation','description':'Performed after reopening','occurred_at':utcnow().isoformat()},h,201)
    assert post(c,b+f'/deviations/{deviation["id"]}/followups',{**resolution,'expected_version':reopened['version'],'performed_action_id':final_action['action']['id']},h)['state']=='resolved'
