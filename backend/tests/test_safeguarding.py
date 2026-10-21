"""Real HTTP protected-workflow tests on SQLite and isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4
import os
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func, event
from sqlalchemy.engine import make_url
from spesped.auth import Actor, hash_password
from spesped.cli import provision_school
from spesped.config import Settings
from spesped.db import make_session_factory, utcnow
from spesped.main import create_app
from spesped.errors import DomainError
from spesped.contexts.identity.models import SchoolMembership, StaffAssignment, AuthorityGrant, UserAccount, Learner, AuditRecord
from spesped.contexts.safeguarding import router
from spesped.contexts.safeguarding import models as m, schemas as s, service as svc
from spesped.contexts.safeguarding.ports import ReviewedRuleContext

ORIGIN='http://testserver'
PASSWORD='synthetic-safeguarding-passphrase'

@pytest.fixture(params=['sqlite','postgres'])
def env(request,tmp_path):
    admin=None;schema=None;factory=None
    if request.param=='postgres':
        url=os.getenv('SPESPED_TEST_POSTGRES_URL')
        if not url:pytest.skip('Set SPESPED_TEST_POSTGRES_URL for PostgreSQL verification')
        admin=create_engine(url);schema='j16_'+uuid4().hex
        with admin.begin() as conn:conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/safeguarding.db'
    config=Config(str(Path(__file__).parents[1]/'alembic.ini'));config.attributes['database_url']=url
    try:
        command.upgrade(config,'j16_safeguarding')
        factory=make_session_factory(url)
        with factory.begin() as db:
            school,leader=provision_school(db,school_name='Synthetic protected school',kind='public',timezone='Europe/Oslo',email='leader@example.invalid',display_name='Leader',password=PASSWORD)
            foreign,_=provision_school(db,school_name='Synthetic other school',kind='public',timezone='Europe/Oslo',email='foreign@example.invalid',display_name='Foreign',password=PASSWORD)
            ids={'school':school.id,'leader':leader.id,'foreign_school':foreign.id}
            encoded=hash_password(PASSWORD)
            for key,role in [('teacher','teacher'),('owner','school_owner'),('participant','teacher'),('outsider','teacher'),('guardian','guardian')]:
                user=UserAccount(email=f'{key}@example.invalid',display_name='Synthetic '+key,password_hash=encoded)
                db.add(user);db.flush();ids[key]=user.id
                db.add(SchoolMembership(school_id=school.id,user_id=user.id,role=role,valid_from=date(2020,1,1)))
            learner=Learner(school_id=school.id,display_name='SYNTHETIC HIDDEN PUPIL',grade=5,group_name='SYNTHETIC');db.add(learner);db.flush();ids['learner']=learner.id
            learner2=Learner(school_id=school.id,display_name='SYNTHETIC SECOND PUPIL',grade=5,group_name='SYNTHETIC');db.add(learner2);db.flush();ids['learner2']=learner2.id
            for who in ('leader','teacher','owner','participant'):
                db.add(AuthorityGrant(school_id=school.id,user_id=ids[who],action='safeguarding.report',valid_from=date(2020,1,1),granted_by=leader.id))
                db.add(StaffAssignment(school_id=school.id,learner_id=learner.id,user_id=ids[who],actions=['learner.read'],purpose='synthetic teaching',valid_from=date(2020,1,1)))
            for action in ('routes.manage','routes.review'):
                db.add(AuthorityGrant(school_id=school.id,user_id=ids['owner'],action='safeguarding.'+action,valid_from=date(2020,1,1),granted_by=leader.id))
        app=create_app(Settings(environment='test',database_url=url,allowed_origins=[ORIGIN]),factory)
        if not any('/safeguarding/' in p for p in app.openapi()['paths']):app.include_router(router)
        with TestClient(app) as client:yield client,factory,ids,request.param,config,app
    finally:
        if factory:factory.kw['bind'].dispose()
        if admin:
            with admin.begin() as conn:conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def login(c,key='teacher'):
    r=c.post('/api/v1/auth/login',json={'email':f'{key}@example.invalid','password':PASSWORD},headers={'Origin':ORIGIN})
    assert r.status_code==200,r.text
    return {'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf_token']}


def base(ids):return f'/api/v1/schools/{ids["school"]}/safeguarding'
def key():return uuid4().hex
def when():return (utcnow()-timedelta(hours=2)).isoformat()
def change(version=1,**fields):return {'request_key':key(),'expected_version':version,**fields}


def post(c,path,body,h,status=200):
    r=c.post(path,json=body,headers=h)
    assert r.status_code==status,r.text
    return r.json()


def create(env,kind='environment',**changes):
    c,f,ids,_,_,_=env;h=login(c);b=base(ids)
    body={'request_key':key(),'learner_id':ids['learner'],'occurred_at':when()}
    if kind=='environment':body.update(received_concern='SYNTHETIC initial pupil experience',received_from='Synthetic pupil')
    elif kind=='concern':body.update(author_assessment='SYNTHETIC author assessment, no diagnosis',urgency='emergency',accounts=[{'kind':'own_observation','statement':'SYNTHETIC observed fact','source':'Own direct observation','uncertainty':'Not established why','occurred_at':when()}])
    else:body.update(place='SYNTHETIC classroom',before_facts='Observed before',during_facts='Observed during',actual_action='SYNTHETIC actual intervention description',duration_seconds=20,involved_roles=[{'person_reference':'Synthetic employee A','role':'Involved staff'}],observed_consequences='No conclusion; observations pending',pupil_view={'source':'Own collection attempt','missing_reason':'Pupil not ready to speak','followup_owner_id':ids['teacher'],'followup_due':'2026-11-01','occurred_at':when()})
    body.update(changes)
    endpoint={'environment':'environment-cases','concern':'concern-reports','physical':'physical-interventions'}[kind]
    result=post(c,b+'/'+endpoint,body,h,201)
    return result,h,body


def grants(env,case,who='teacher',actions=('read','write','review','export')):
    _,f,ids,_,_,_=env
    with f.begin() as db:
        for action in actions:db.add(AuthorityGrant(school_id=ids['school'],user_id=ids[who],action='safeguarding.case.'+action,learner_id=ids['learner'],case_id=case['id'],valid_from=date(2020,1,1),granted_by=ids['owner']))


def setup(env,kind='environment',**changes):
    result,h,body=create(env,kind,**changes);grants(env,result)
    c,_,ids,_,_,_=env
    return c.get(base(ids)+'/cases/'+result['id']).json(),h,body


def contact(version=1,**fields):
    return change(version,occurred_at=when(),contact_kind='notification',recipient='Synthetic external service',channel='telephone',information_shared='SYNTHETIC minimum actual information',outcome='performed',receipt_state='unknown',receipt_detail='No independent receipt is available',route_deviation_reason='Manual contact using existing school procedure; no configured route',**fields)


def test_author_projection_and_exact_case_grants_not_admin_or_pupil_access(env):
    original,h,body=create(env);c,f,ids,_,_,_=env;b=base(ids);cid=original['id']
    assert c.get(b+'/cases/'+cid).status_code==403
    assert c.get(b+'/cases').json()=={'items':[],'total':0}
    assert 'original_submission' in c.get(b+'/submissions/'+cid).json()
    for person in ('leader','owner','outsider','guardian'):
        login(c,person)
        assert c.get(b+'/cases/'+cid).status_code==403
        assert c.get(b+'/cases/'+cid+'/export').status_code==403
        assert c.get(b+'/cases/'+cid+'/history').status_code==403
        assert c.get(b+'/cases/'+cid+'/contact-routes').status_code==403
        assert c.get(b+'/submissions/'+cid).status_code==403
        assert c.get(b+'/cases').json()=={'items':[],'total':0}
    grants(env,original);h=login(c)
    assert c.get(b+'/cases/'+cid).status_code==200
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id==cid)):grant.state='revoked'
    assert c.get(b+'/cases/'+cid).status_code==403
    assert c.get(b+'/cases').json()['total']==0
    post(c,b+'/cases/'+cid+'/accounts',change(kind='investigation',statement='Denied',source='Own',occurred_at=when()),h,403)


def test_environment_plan_is_not_actual_action_and_reviewed_closure_reopening(env):
    case,h,_=setup(env);c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id']
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['teacher'],reason='Explicit responsible owner'),h)
    case=post(c,p+'/actual-contacts',contact(case['version']),h,201)
    assert case['state']=='notified' and case['actual_contacts'][0]['receipt_state']=='unknown'
    case=post(c,p+'/accounts',change(case['version'],kind='investigation',statement='Investigated concrete circumstances',source='Named synthetic witness',uncertainty='Other accounts differ',occurred_at=when()),h,201)
    case=post(c,p+'/pupil-views',change(case['version'],statement='Synthetic pupil experience',source='Pupil statement in own words',occurred_at=when()),h,201)
    plan=change(case['version'],problem_assessment='Responsible problem assessment',evaluation_date='2026-11-03',measures=[{'measure':'Agreed concrete support','owner_id':ids['teacher'],'planned_date':'2026-11-01','evaluation_method':'Ask pupil and observe actual situation'}])
    case=post(c,p+'/action-plans',plan,h,201)
    assert case['state']=='measures_active' and case['performed_actions']==[]
    oldplan=case['plans'][0]
    case=post(c,p+'/action-plans',{**plan,'request_key':key(),'expected_version':case['version'],'problem_assessment':'Revised assessment'},h,201)
    assert len(case['plans'])==2 and oldplan in case['plans']
    case=post(c,p+'/performed-actions',change(case['version'],description='Actual agreed support performed',outcome='Pupil situation uncertain',outcome_state='unknown',measure_id=case['measures'][0]['id'],occurred_at=when()),h,201)
    assert case['state']=='measures_active'
    case=post(c,p+'/review',change(case['version'],decision='evaluating',assessment='Responsible review',pupil_situation='Situation described explicitly',occurred_at=when()),h)
    assert case['state']=='evaluating'
    case=post(c,p+'/review',change(case['version'],decision='close',assessment='Responsible closure rationale despite explicitly unknown action outcome',pupil_situation='Pupil situation reviewed',occurred_at=when()),h)
    assert case['state']=='closed'
    post(c,p+'/accounts',change(case['version'],kind='investigation',statement='No silent reopening',source='Own',occurred_at=when()),h,400)
    case=post(c,p+'/review',change(case['version'],decision='reopen',assessment='New concern requires renewed investigation',pupil_situation='Renewed pupil experience',occurred_at=when()),h)
    assert case['state']=='investigating' and len(case['reviews'])==4
    history=c.get(p+'/history').json()
    assert history['total']==case['version'] and history['items'][0]['content']['state']=='received'
    exported=c.get(p+'/export').json();assert exported['rule_context']['state']=='unavailable'
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.SafeguardingEvent).where(m.SafeguardingEvent.aggregate_id==case['id']))==case['version']


def test_alternative_headteacher_route_and_accused_excluded_despite_grants(env):
    c,f,ids,_,_,_=env;b=base(ids);h=login(c,'owner')
    route=post(c,b+'/route-configurations',{'request_key':key(),'purpose':'environment','about':'headteacher','owner_id':ids['owner'],'recipient':'Synthetic school owner contact','recipient_user_id':ids['owner'],'channel':'telephone','contact_details':'SYNTHETIC configured telephone, not a real contact','guidance':'Use alternative reviewed owner route','valid_from':'2020-01-01','valid_until':'2030-01-01'},h,201)
    login(c);assert c.get(b+'/contact-routes?purpose=environment&about=headteacher').json()['state']=='unavailable'
    h=login(c,'owner');route=post(c,b+'/route-configurations/'+route['id']+'/review',change(route['version'],digest=route['digest'],decision='approve',rationale='Actual synthetic configuration review'),h)
    case,h,_=setup(env,about='headteacher',excluded_user_ids=[ids['leader']]);p=b+'/cases/'+case['id']
    routes=c.get(p+'/contact-routes').json();assert routes['items'][0]['recipient']==route['recipient']
    body=contact(case['version']);body.update(route_id=route['id'],route_deviation_reason=None,recipient=route['recipient'],channel=route['channel'])
    case=post(c,p+'/actual-contacts',body,h,201);assert case['state']=='notified'
    grants(env,case,'leader');login(c,'leader')
    assert c.get(p).status_code==403 and c.get(p+'/export').status_code==403
    assert c.get(p+'/contact-routes').status_code==403
    assert c.get(b+'/cases').json()['total']==0
    with f() as db:
        with pytest.raises(DomainError):svc.resolve_case_learner(db,Actor(ids['leader']),ids['school'],case['id'])
    h=login(c,'owner');post(c,b+'/route-configurations/'+route['id']+'/review',change(route['version'],digest=route['digest'],decision='revoke',rationale='Contact path retired'),h)
    login(c);assert c.get(p+'/contact-routes').json()['state']=='unavailable'


def test_personal_emergency_action_has_no_draft_or_supervisor_gate_and_narrow_projection(env):
    original,h,_=create(env,'concern');c,f,ids,_,_,_=env;b=base(ids);cid=original['id']
    assert c.get(b+'/cases/'+cid).status_code==403
    body=contact(1);body['contact_kind']='emergency_action'
    own=post(c,b+'/submissions/'+cid+'/personal-contacts',body,h,201)
    assert len(own['own_contacts'])==1 and own['own_contacts'][0]['draft_id'] is None
    assert own['own_contacts'][0]['occurred_at']<own['own_contacts'][0]['recorded_at']
    grants(env,original,'owner');adminh=login(c,'owner');p=b+'/cases/'+cid
    full=c.get(p).json()
    full=post(c,p+'/accounts',change(full['version'],kind='investigation',statement='SECRET OTHER CONTRIBUTOR TEXT',source='Synthetic witness',occurred_at=when()),adminh,201)
    h=login(c)
    projection=c.get(b+'/submissions/'+cid).json()
    assert 'SECRET OTHER CONTRIBUTOR TEXT' not in str(projection)
    assert 'reviews' not in projection and 'owner_id' not in projection
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['teacher'],AuthorityGrant.action=='safeguarding.report')):grant.state='revoked'
    assert c.get(b+'/submissions/'+cid).status_code==403
    post(c,b+'/submissions/'+cid+'/personal-contacts',contact(projection['version']),h,403)


def test_concern_draft_exact_review_and_actual_contact_separate(env):
    case,h,_=setup(env,'concern');c,_,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id']
    case=post(c,p+'/drafts',change(case['version'],recipient='Synthetic service',purpose='Responsible personal report',body='Human-authored minimum fact and uncertainty text'),h,201)
    assert case['state']=='message_prepared' and case['actual_contacts']==[]
    draft=case['drafts'][0]
    body=contact(case['version']);body.update(draft_id=draft['id'],draft_digest=draft['digest'],recipient=draft['recipient'])
    post(c,p+'/actual-contacts',body,h,409)
    case=post(c,p+'/drafts/'+draft['id']+'/review',change(case['version'],draft_digest=draft['digest'],rationale='Responsible sender reviewed exact text and recipient'),h)
    assert case['state']=='message_prepared' and case['actual_contacts']==[]
    case=post(c,p+'/drafts',change(case['version'],recipient=draft['recipient'],purpose='Responsible personal report',body='Revised human text'),h,201)
    body['request_key']=key();body['expected_version']=case['version'];post(c,p+'/actual-contacts',body,h,409)
    latest=max(case['drafts'],key=lambda d:d['revision'])
    case=post(c,p+'/drafts/'+latest['id']+'/review',change(case['version'],draft_digest=latest['digest'],rationale='Reviewed exact revised text'),h)
    body.update(request_key=key(),expected_version=case['version'],draft_id=latest['id'],draft_digest=latest['digest'],outcome='unknown')
    post(c,p+'/actual-contacts',body,h,409)
    body.update(request_key=key(),information_shared=latest['body'])
    case=post(c,p+'/actual-contacts',body,h,201)
    assert case['state']=='message_prepared' and case['actual_contacts'][0]['outcome']=='unknown'
    action=case['actual_contacts'][0]
    case=post(c,p+'/actual-contacts/'+action['id']+'/reconcile',change(case['version'],occurred_at=when(),outcome='performed',receipt_state='received',receipt_detail='Synthetic service confirmed receipt'),h)
    assert case['contact_reconciliations'][0]['receipt_state']=='received'
    assert case['actual_contacts'][0]['receipt_state']=='unknown'


def test_physical_missing_pupil_view_correction_prevention_and_repeated_scope(env):
    case,h,body=setup(env,'physical');c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    assert case['pupil_views'][0]['missing_reason'] and case['pupil_views'][0]['followup_owner_id']==ids['teacher']
    assert case['actual_contacts']==[]
    correction={k:body[k] for k in ('place','before_facts','during_facts','actual_action','duration_seconds','involved_roles','observed_consequences')}
    case=post(c,p+'/corrections/physical',change(case['version'],**{**correction,'duration_seconds':25},correction_reason='Corrected measured duration with origin retained'),h)
    assert case['record']['duration_seconds']==25 and case['state']=='corrected'
    assert c.get(p+'/history').json()['items'][0]['content']['record']['duration_seconds']==20
    case=post(c,p+'/pupil-views',change(case['version'],statement='Pupil later supplied own account',source='Synthetic pupil',occurred_at=when()),h,201)
    case=post(c,p+'/followups',change(case['version'],kind='prevention',description='Responsible preventive review',owner_id=ids['teacher'],due_date='2026-11-01'),h,201)
    task=case['followups'][0]
    case=post(c,p+'/followups/'+task['id']+'/completion',change(case['version'],state='incomplete',outcome='Needs further preventive assessment',occurred_at=when()),h)
    assert case['followups'][0]['state']=='incomplete'
    hidden,_,_=create(env,'physical');h=login(c)
    assert c.get(b+'/learners/'+ids['learner']+'/repeated-physical-events').status_code==403
    with f.begin() as db:db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['teacher'],action='safeguarding.repeated_events',learner_id=ids['learner'],valid_from=date(2020,1,1),granted_by=ids['owner']))
    result=c.get(b+'/learners/'+ids['learner']+'/repeated-physical-events').json()
    assert result['total']==1 and result['items'][0]['id']==case['id'] and hidden['id'] not in str(result)
    login(c,'leader');assert c.get(b+'/learners/'+ids['learner']+'/repeated-physical-events').status_code==403


def test_evidence_reference_current_revision_matching_scope_and_revoked_rights(env):
    case,h,_=setup(env);c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id'];reference=case['evidence_reference']
    with f() as db:
        assert svc.resolve_case_learner(db,Actor(ids['teacher']),ids['school'],case['id'])==ids['learner']
        ref=svc.validate_evidence_reference(db,Actor(ids['teacher']),ids['school'],ids['learner'],case['id'],reference['reference_id'])
        assert ref.revision==1 and ref.digest==reference['digest']
        for school,learner,cid in [(ids['foreign_school'],ids['learner'],case['id']),(ids['school'],ids['learner2'],case['id']),(ids['school'],ids['learner'],str(uuid4()))]:
            with pytest.raises(DomainError):svc.validate_evidence_reference(db,Actor(ids['teacher']),school,learner,cid,reference['reference_id'])
    case=post(c,p+'/accounts',change(case['version'],kind='investigation',statement='Source changed',source='Own',occurred_at=when()),h,201)
    with f() as db:
        with pytest.raises(DomainError):svc.validate_evidence_reference(db,Actor(ids['teacher']),ids['school'],ids['learner'],case['id'],reference['reference_id'])
        assert svc.validate_evidence_reference(db,Actor(ids['teacher']),ids['school'],ids['learner'],case['id'],case['evidence_reference']['reference_id']).revision==2
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id==case['id'])):grant.state='revoked'
    with f() as db:
        with pytest.raises(DomainError):svc.validate_evidence_reference(db,Actor(ids['teacher']),ids['school'],ids['learner'],case['id'],case['evidence_reference']['reference_id'])
    assert c.get(p+'/history').status_code==403


def test_idempotency_stale_version_and_changed_key_do_not_duplicate(env):
    case,h,body=setup(env);c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    original=post(c,b+'/environment-cases',body,h,201);assert original['id']==case['id']
    post(c,b+'/environment-cases',{**body,'received_concern':'Changed content'},h,409)
    cmd=change(case['version'],kind='investigation',statement='One investigation',source='Own',occurred_at=when())
    updated=post(c,p+'/accounts',cmd,h,201)
    assert post(c,p+'/accounts',cmd,h,201)==updated
    post(c,p+'/accounts',{**cmd,'request_key':key()},h,409)
    post(c,p+'/accounts',{**cmd,'statement':'Changed reused key'},h,409)
    with f() as db:
        assert len(svc.all_children(db,m.AttributedAccount,db.get(m.CaseRecord,case['id'])))==1
        assert db.scalar(select(func.count()).select_from(m.CaseSnapshot).where(m.CaseSnapshot.case_id==case['id']))==2


def test_revoked_assigned_owner_cannot_work_and_rolls_back_plan_assignment(env):
    case,h,_=setup(env);c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id']
    grants(env,case,'participant')
    case=post(c,p+'/followups',change(case['version'],kind='prevention',description='Assigned restricted followup',owner_id=ids['participant'],due_date='2026-11-01'),h,201)
    followup=case['followups'][0]
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id==case['id'],AuthorityGrant.user_id==ids['participant'])):grant.state='revoked'
    ph=login(c,'participant')
    post(c,p+'/followups/'+followup['id']+'/completion',change(case['version'],state='performed',outcome='Denied revoked owner',occurred_at=when()),ph,403)
    assert c.get(p).status_code==403
    h=login(c)
    post(c,p+'/action-plans',change(case['version'],problem_assessment='Will roll back',evaluation_date='2026-11-01',measures=[{'measure':'Invalid revoked owner','owner_id':ids['participant'],'planned_date':'2026-11-01','evaluation_method':'Review'}]),h,403)
    current=c.get(p).json();assert current['version']==case['version'] and current['plans']==[]


def test_cross_case_links_and_future_actual_times_rejected(env):
    case,_,_=setup(env);other,h,_=setup(env);c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id'];q=base(ids)+'/cases/'+other['id']
    other=post(c,q+'/accounts',change(other['version'],kind='own_observation',statement='Sibling protected prose',source='Own',occurred_at=when()),h,201)
    post(c,p+'/accounts',change(case['version'],kind='contradicting_account',statement='Cannot import sibling',source='Sibling',corrects_id=other['accounts'][0]['id'],correction_reason='Bad scope',occurred_at=when()),h,403)
    post(c,p+'/performed-actions',change(case['version'],description='Future is not actual',outcome='Unknown',outcome_state='unknown',occurred_at=(utcnow()+timedelta(days=1)).isoformat()),h,400)
    invalid=change(case['version'],source='Missing view',missing_reason='No owner',occurred_at=when())
    post(c,p+'/pupil-views',invalid,h,422)
    assert c.get(p).json()['version']==1


def test_transaction_audit_outbox_failure_rolls_back_business_and_receipt(env,monkeypatch):
    case,h,_=setup(env);c,f,ids,_,_,_=env
    with f() as db:
        before_audit=db.scalar(select(func.count()).select_from(AuditRecord))
        before_outbox=db.scalar(select(func.count()).select_from(m.SafeguardingEvent))
    def fail(*args,**kwargs):raise RuntimeError('Synthetic audit writer failure')
    monkeypatch.setattr(svc,'record_audit',fail)
    with f() as db:
        with pytest.raises(RuntimeError):svc.add_account(db,Actor(ids['teacher']),ids['school'],case['id'],s.AddAccount(**change(kind='investigation',statement='Rollback source',source='Own',occurred_at=when())))
    with f() as db:
        row=db.get(m.CaseRecord,case['id']);assert row.version==1
        assert svc.all_children(db,m.AttributedAccount,row)==[]
        assert db.scalar(select(func.count()).select_from(AuditRecord))==before_audit
        assert db.scalar(select(func.count()).select_from(m.SafeguardingEvent))==before_outbox
        assert db.scalar(select(func.count()).select_from(m.CommandReceipt))==1


def test_no_rule_adapter_is_unavailable_and_readonly_rule_context_contract(env):
    case,h,_=setup(env,'physical');c,_,ids,_,_,app=env;p=base(ids)+'/cases/'+case['id']
    assert c.get(p).json()['rule_context']['state']=='unavailable'
    app.state.safeguarding_rule_context=lambda db,actor,school,learner,cid:ReviewedRuleContext(str(uuid4()),2,('synthetic-obligation',),('Document actual facts',),('Reviewed notification requirement, not performed',))
    result=c.get(p).json();assert result['rule_context']['state']=='reviewed'
    assert result['actual_contacts']==[]
    app.state.safeguarding_rule_context=lambda *args:{'approved':True}
    assert c.get(p).status_code==503


def test_concurrent_duplicate_create_and_cas_mutation(env):
    c,f,ids,dialect,_,_=env
    if dialect!='postgres':pytest.skip('Production locking is verified on PostgreSQL')
    body=s.EnvironmentCreate(request_key=key(),learner_id=ids['learner'],occurred_at=when(),received_concern='Concurrent synthetic concern',received_from='Synthetic pupil')
    def run_create():
        with f() as db:return svc.create_environment(db,Actor(ids['teacher']),ids['school'],body)
    with ThreadPoolExecutor(max_workers=2) as pool:created=list(pool.map(lambda _:run_create(),range(2)))
    assert created[0]['id']==created[1]['id']
    grants(env,created[0])
    commands=[s.AddAccount(**change(kind='investigation',statement='Concurrent independent update',source='Own',occurred_at=when())) for _ in range(2)]
    def run_update(cmd):
        with f() as db:
            try:return svc.add_account(db,Actor(ids['teacher']),ids['school'],created[0]['id'],cmd)['version']
            except DomainError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run_update,commands))
    assert sorted(str(v) for v in results)==['2','version_conflict']
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.AttributedAccount))==1
        assert db.scalar(select(func.count()).select_from(m.SafeguardingEvent))==2


def test_context_migration_roundtrip(env):
    c,f,ids,_,config,_=env
    command.downgrade(config,'b1_integrate_contexts')
    with f() as db:
        from sqlalchemy import inspect
        assert not any(t.startswith('safeguarding_') for t in inspect(db.connection()).get_table_names())
        assert db.get(Learner,ids['learner']) is not None
    command.upgrade(config,'j16_safeguarding')
    with f() as db:
        from sqlalchemy import inspect
        assert len([t for t in inspect(db.connection()).get_table_names() if t.startswith('safeguarding_')])==19


def test_limited_participant_projection_followup_and_revoked_assignment(env):
    case,h,_=setup(env);c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    with f.begin() as db:
        db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['participant'],action='safeguarding.case.contribute',learner_id=ids['learner'],case_id=case['id'],valid_from=date(2020,1,1),granted_by=ids['owner']))
    case=post(c,p+'/accounts',change(case['version'],kind='investigation',statement='SECRET FULL DOSSIER INVESTIGATION',source='Restricted witness',occurred_at=when()),h,201)
    secret_account=case['accounts'][0]
    case=post(c,p+'/followups',change(case['version'],kind='prevention',description='Explicitly assigned limited prevention followup',owner_id=ids['participant'],due_date='2026-11-01'),h,201)
    task=case['followups'][0]
    ph=login(c,'participant');q=b+'/contributions/'+case['id']
    assert c.get(p).status_code==403 and c.get(p+'/export').status_code==403
    projection=c.get(q).json();assert 'SECRET FULL DOSSIER' not in str(projection)
    assert projection['assigned_followups'][0]['id']==task['id']
    assert c.get(b+'/contributions').json()['total']==1
    post(c,q+'/accounts',change(projection['version'],kind='contradicting_account',statement='Cannot inspect another account',source='Own',corrects_id=secret_account['id'],correction_reason='Invalid attempt',occurred_at=when()),ph,403)
    projection=post(c,q+'/accounts',change(projection['version'],kind='own_observation',statement='Limited participant own observation',source='Own',occurred_at=when()),ph,201)
    assert projection['own_accounts'][0]['statement']=='Limited participant own observation'
    projection=post(c,q+'/followups/'+task['id']+'/completion',change(projection['version'],state='performed',outcome='Performed actual preventive followup',occurred_at=when()),ph)
    assert projection['assigned_followups'][0]['state']=='performed'
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['participant'],AuthorityGrant.case_id==case['id'])):grant.state='revoked'
    assert c.get(q).status_code==403 and c.get(b+'/contributions').json()['total']==0
    post(c,q+'/performed-actions',change(projection['version'],description='Denied revoked contribution',outcome='Unknown',outcome_state='unknown',occurred_at=when()),ph,403)


def test_author_can_supply_later_pupil_view_and_urgent_action_after_closure(env):
    case,h,_=setup(env,'physical');c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['teacher'],reason='Responsible review owner'),h)
    case=post(c,p+'/review',change(case['version'],decision='close',assessment='Responsible review with pending pupil perspective explicit',pupil_situation='Pupil not ready; owned later followup retained',occurred_at=when()),h)
    assert case['state']=='closed'
    # Remove full dossier permissions while keeping narrow personal reporting.
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id==case['id'])):grant.state='revoked'
    own=post(c,b+'/submissions/'+case['id']+'/pupil-views',change(case['version'],statement='Later supplied pupil account',source='Synthetic pupil own words',occurred_at=when()),h,201)
    assert own['own_pupil_views'][-1]['statement']=='Later supplied pupil account'
    own=post(c,b+'/submissions/'+case['id']+'/personal-contacts',{**contact(own['version']),'contact_kind':'emergency_action'},h,201)
    assert own['own_contacts'][-1]['contact_kind']=='emergency_action'
    with f() as db:assert db.get(m.CaseRecord,case['id']).state=='closed'
    assert c.get(p).status_code==403


def test_new_staff_subject_exclusion_takes_effect_on_all_paths_and_reassigns_revoked_owner(env):
    case,h,_=setup(env);c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    grants(env,case,'leader');grants(env,case,'participant')
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['leader'],reason='Initial authorized case owner'),h)
    case=post(c,p+'/followups',change(case['version'],kind='investigation',description='Initially assigned restricted task',owner_id=ids['leader'],due_date='2026-11-01'),h,201)
    task=case['followups'][0]
    case=post(c,p+'/protection',change(case['version'],about='headteacher',excluded_user_ids=[ids['leader']],reason='New account concerns leader; exclude immediately'),h)
    assert case['owner_id'] is None
    lh=login(c,'leader')
    assert c.get(p).status_code==403 and c.get(p+'/history').status_code==403
    assert c.get(p+'/export').status_code==403 and c.get(p+'/contact-routes').status_code==403
    assert c.get(b+'/cases').json()['total']==0
    post(c,p+'/accounts',change(case['version'],kind='investigation',statement='Excluded actor denied',source='Own',occurred_at=when()),lh,403)
    h=login(c)
    case=post(c,p+'/followups/'+task['id']+'/assignment',change(case['version'],owner_id=ids['participant'],reason='Reassign away from excluded subject'),h)
    assert case['followups'][0]['owner_id']==ids['participant']
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['teacher'],reason='New authorized owner'),h)
    post(c,p+'/protection',change(case['version'],about='staff',excluded_user_ids=[ids['teacher']],reason='Cannot view after self exclusion'),h,403)


def test_physical_unknown_duration_is_explicit_and_not_zero(env):
    case,h,_=setup(env,'physical',duration_seconds=None,duration_unknown_reason='Witness cannot establish duration yet')
    c,f,ids,_,_,_=env
    assert case['record']['duration_seconds'] is None and case['record']['duration_unknown_reason']
    assert 'duration_unknown' in case['workflow_checks']['missing_documentation']
    assert 'pupil_perspective_pending' in case['workflow_checks']['missing_documentation']
    assert case['workflow_checks']['notification_execution']=='not_recorded'
    original,h,body=create(env,'physical');body.update(request_key=key(),duration_seconds=None)
    post(c,base(ids)+'/physical-interventions',body,h,422)


def test_guardian_never_gets_dossier_or_contributor_projection_even_with_grants(env):
    case,h,_=setup(env,'concern');c,f,ids,_,_,_=env;b=base(ids);p=b+'/cases/'+case['id']
    grants(env,case,'guardian',('read','write','review','export','contribute'))
    login(c,'guardian')
    for path in (p,p+'/export',p+'/history',p+'/contact-routes',b+'/contributions/'+case['id']):assert c.get(path).status_code==403
    assert c.get(b+'/cases').json()['total']==0
    assert c.get(b+'/contributions').json()['total']==0


def test_closed_case_owner_revocation_allows_authorized_reassignment_before_reopen(env):
    case,h,_=setup(env,'physical');c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id']
    grants(env,case,'owner')
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['teacher'],reason='Original reviewer'),h)
    case=post(c,p+'/review',change(case['version'],decision='close',assessment='Reviewed physical record',pupil_situation='Missing view explicitly assigned',occurred_at=when()),h)
    with f.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.case_id==case['id'],AuthorityGrant.user_id==ids['teacher'])):grant.state='revoked'
    oh=login(c,'owner')
    post(c,p+'/review',change(case['version'],decision='reopen',assessment='Cannot reuse revoked owner',pupil_situation='Renewed concern',occurred_at=when()),oh,403)
    case=post(c,p+'/assignment',change(case['version'],owner_id=ids['owner'],reason='Recover revoked responsible owner'),oh)
    assert case['state']=='closed' and case['review_required']
    case=post(c,p+'/review',change(case['version'],decision='reopen',assessment='Authorized reopened review',pupil_situation='Renewed pupil concern',occurred_at=when()),oh)
    assert case['state']=='under_review' and not case['review_required']


def test_support_person_cannot_rewrite_responsible_authors_assessment(env):
    case,h,_=setup(env,'concern');grants(env,case,'owner');c,f,ids,_,_,_=env;p=base(ids)+'/cases/'+case['id']
    oh=login(c,'owner')
    post(c,p+'/corrections/concern',change(case['version'],author_assessment='Must not be attributed to original author',urgency='concern',correction_reason='Support person attempting rewrite'),oh,403)
    assert c.get(p).json()['record']['author_assessment']==case['record']['author_assessment']
    h=login(c)
    case=post(c,p+'/corrections/concern',change(case['version'],author_assessment='Author own corrected assessment',urgency='urgent',correction_reason='Responsible author reviewed correction'),h)
    assert case['record']['author_assessment']=='Author own corrected assessment' and case['corrections']
