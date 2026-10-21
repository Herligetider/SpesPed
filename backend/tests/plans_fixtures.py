"""Synthetic HTTP fixtures shared only by the BC04/BC05 tests."""
from datetime import date,timedelta
import os
from pathlib import Path
from uuid import uuid4
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from spesped.auth import hash_password
from spesped.cli import provision_school
from spesped.config import Settings
from spesped.db import make_session_factory,utcnow
from spesped.main import create_app
from spesped.contexts.identity.models import AuthorityGrant,Learner,SchoolMembership,StaffAssignment,UserAccount
from spesped.contexts.evidence.router import router as evidence_router
from spesped.contexts.evidence.processing import LocalStorage
from spesped.contexts.entitlements.router import router as entitlements_router
from spesped.contexts.plans.router import router as plans_router
from spesped.contexts.plans.service import validate_goal_reference

PASSWORD='synthetic-plans-passphrase'
ORIGIN='http://testserver'


@pytest.fixture(params=['sqlite','postgres'])
def env(request,tmp_path):
    schema=None;admin=None
    if request.param == 'postgres':
        url=os.environ.get('SPESPED_TEST_POSTGRES_URL')
        if not url: pytest.skip('Set an isolated SPESPED_TEST_POSTGRES_URL for PostgreSQL verification')
        if make_url(url).database == 'spesped_demo': pytest.fail('Demo database is forbidden for tests')
        schema='j05_'+uuid4().hex;admin=create_engine(url)
        with admin.begin() as db: db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(url).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else: url=f'sqlite:///{tmp_path}/plans.db'
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    command.upgrade(config,'j05_plans')
    # Shared checkout can contain the parallel evidence branch before the root
    # merge migration lands; exercise both explicit compatible heads.
    migration_versions=Path(__file__).resolve().parents[1]/'migrations/versions'
    if (migration_versions/'j04_manual_recovery.py').exists():
        command.upgrade(config,'j04_manual_recovery')
    elif (migration_versions/'j04_structuring.py').exists():
        command.upgrade(config,'j04_structuring')
    factory=make_session_factory(url)
    with factory.begin() as db:
        school,leader=provision_school(db,school_name='Synthetic plan school',kind='public',timezone='Europe/Oslo',email='leader@example.invalid',display_name='Synthetic leader',password=PASSWORD)
        other,_=provision_school(db,school_name='Synthetic other school',kind='public',timezone='Europe/Oslo',email='other@example.invalid',display_name='Synthetic other',password=PASSWORD)
        ids={'school':school.id,'leader':leader.id,'other_school':other.id}
        for name in ('a','b'):
            row=Learner(school_id=school.id,display_name='Synthetic '+name,grade=4,group_name='Synthetic');db.add(row);db.flush();ids[name]=row.id
        for name,role in [('reviewer','teacher'),('teacher','teacher'),('assistant','assistant'),('tech','technical_administrator'),('guardian','guardian')]:
            row=UserAccount(email=name+'@example.invalid',display_name='Synthetic '+name,password_hash=hash_password(PASSWORD));db.add(row);db.flush();ids[name]=row.id
            db.add(SchoolMembership(school_id=school.id,user_id=row.id,role=role,valid_from=date.today()-timedelta(days=1)))
        for name in ('reviewer','teacher'):
            for learner in ('a','b') if name == 'reviewer' else ('a',):
                db.add(StaffAssignment(school_id=school.id,learner_id=ids[learner],user_id=ids[name],actions=['evidence.read','evidence.write','profile.read','profile.write','profile.confirm','plans.read','plans.write','support_case.access','support_case.create'],purpose='educational_support',valid_from=date.today()-timedelta(days=1)))
        db.add(StaffAssignment(school_id=school.id,learner_id=ids['a'],user_id=ids['assistant'],actions=['profile.brief'],purpose='assigned_support_brief',valid_from=date.today()-timedelta(days=1)))
        for action in ('evidence.intake','support_case.create','profile.confirm','plans.approve'):
            db.add(AuthorityGrant(school_id=school.id,user_id=ids['reviewer'],action=action,valid_from=date.today()-timedelta(days=1),granted_by=leader.id))
    settings=Settings(environment='test',database_url=url,allowed_origins=[ORIGIN])
    app=create_app(settings,factory)
    for router,ending in ((evidence_router,'/intake/notes'),(entitlements_router,'/support-cases/{case_id}'),(plans_router,'/education-plans/{plan_id}')):
        if not any(getattr(r,'path','').endswith(ending) for r in app.routes): app.include_router(router)
    app.state.evidence_storage=LocalStorage(tmp_path/'private');app.state.evidence_goal_validator=validate_goal_reference
    with TestClient(app) as client: yield client,factory,app,ids
    factory.kw['bind'].dispose()
    if schema:
        with admin.begin() as db: db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def login(client,name='reviewer'):
    result=client.post('/api/v1/auth/login',json={'email':name+'@example.invalid','password':PASSWORD},headers={'Origin':ORIGIN})
    assert result.status_code == 200,result.text
    return {'Origin':ORIGIN,'X-CSRF-Token':result.json()['csrf_token']}


def base(ids): return f'/api/v1/schools/{ids["school"]}'
def key(): return str(uuid4())
def retry(**values): return {'request_key':key(),**values}
def expected(row,**values): return retry(expected_version=row['version'],**values)


def evidence(client,ids,headers,learner='a',text='Synthetic reviewed educational source'):
    result=client.post(base(ids)+'/intake/notes',headers=headers,json=retry(external_scope='manual',external_id=key(),sender='Synthetic school professional',document_type='education_document',received_at=utcnow().isoformat(),text=text))
    assert result.status_code == 201,result.text
    proposal=client.get(base(ids)+'/intake/'+result.json()['id']+'/proposals').json()['items'][0]
    review=client.post(base(ids)+'/extraction-proposals/'+proposal['id']+'/review',headers=headers,json={'expected_version':proposal['version'],'outcome':'accepted','reason':'Synthetic source checked'})
    result=client.post(base(ids)+'/extraction-proposals/'+proposal['id']+'/confirm',headers=headers,json={'expected_version':review.json()['version'],'learner_id':ids[learner],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':(utcnow()-timedelta(days=20)).isoformat(),'topic':'education','excerpt_page':proposal['page'],'excerpt_start':proposal['span_start'],'excerpt_end':proposal['span_end']})
    assert result.status_code == 201,result.text
    item=result.json()
    return {'evidence_id':item['id'],'evidence_revision':item['revision'],'link_id':item['source']['link_id']},item


def support_case(client,factory,ids,headers):
    result=client.post(base(ids)+f'/learners/{ids["a"]}/support-cases',headers=headers,json=retry(concern='Synthetic support need',owner_id=ids['reviewer']))
    assert result.status_code == 201,result.text
    case=result.json()
    # Case creation never implicitly grants dossier access. A separate authorized
    # authority administration operation supplies exact permissions in this fixture.
    with factory.begin() as db:
        for action in ('support_case.read','support_case.write','support_case.confirm','support_case.submit','education_decision.confirm'):
            db.add(AuthorityGrant(school_id=ids['school'],learner_id=ids['a'],case_id=case['id'],user_id=ids['reviewer'],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    return case


def period():
    return {'effective_from':(utcnow()-timedelta(days=60)).replace(microsecond=0).isoformat(),'effective_until':(utcnow()+timedelta(days=180)).replace(microsecond=0).isoformat()}


def decision_payload(binding,**changes):
    dates=period()
    provision={'clause':'1','category':'individually_adapted_education','subject':'reading','content':'Synthetic individual reading support','organization':'Small group with professional teacher','competence':'Qualified teacher','amount':'100','unit':'hours','counting_basis':'learner_time','source':binding,**dates}
    return retry(issuing_authority='Synthetic municipal authority',authority_basis='Synthetic dated delegation record',issued_at=(utcnow()-timedelta(days=65)).isoformat(),source=binding,provisions=[provision],**dates,**changes)


def confirmed_decision(client,ids,headers,case,binding):
    path=base(ids)+f'/support-cases/{case["id"]}/decisions'
    result=client.post(path,headers=headers,json=decision_payload(binding));assert result.status_code == 201,result.text
    row=result.json();result=client.post(path+'/'+row['id']+'/confirm',headers=headers,json=expected(row,reason='Checked original decision and provisions'))
    assert result.status_code == 200,result.text
    return result.json()


def plan_payload(binding=None,decision=None,**changes):
    dates=period()
    if decision: dates={k:decision['content'][k] for k in ('effective_from','effective_until')}
    goal={'title':'Synthetic reading goal','expected_action':'Read a short sentence independently','arena':'Classroom','support':'Visual word cards','responsibility':'Qualified teacher','evaluation_method':'Record observed independent attempts','curriculum_reference':'Synthetic reading curriculum',**dates}
    values={'kind':'ordinary_teaching','title':'Synthetic teaching plan','rationale':'Confirmed learning needs','organization':'Classroom activities','responsibility':'Synthetic teacher','evaluation_method':'Review dated observations','participation_record':'Learner and guardian invited; views recorded below','sources':[binding] if binding else [],'goals':[goal],'adaptations':[{'measure':'Visual supports','arena':'Classroom','responsibility':'Teacher','evaluation_method':'Review observed use'}],**dates}
    if binding:
        values['contributions']=[{'participant':'Synthetic learner','role':'learner','content':'Prefers visual cards','disagreement':True,'response':'Teacher records disagreement and offers alternatives','occurred_at':(utcnow()-timedelta(days=3)).isoformat(),'source':binding}]
    if decision:
        p=decision['provisions'][0]
        values.update(kind='individual_education',decision_id=decision['id'],decision_revision_id=decision['content']['id'],allocations=[{'provision_id':p['id'],'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'amount':str(p['amount']),'unit':p['unit'],'counting_basis':p['counting_basis'],**dates}])
    values.update(changes)
    return retry(**values)


def activate(client,ids,headers,row):
    for action in ('review','approve','activate'):
        result=client.post(base(ids)+f'/education-plans/{row["id"]}/{action}',headers=headers,json=expected(row,revision_id=row['content']['id'],content_digest=row['content_digest'],reason='Synthetic exact content '+action))
        assert result.status_code == 200,result.text
        row=result.json()
    return row


def reviewed_referral(client,ids,headers,case,binding):
    """Prepare a fully sourced reviewed referral without recording any contact."""
    path=base(ids)+f'/support-cases/{case["id"]}'
    consents={}
    for kind in ('education_action','processing_basis','disclosure_permission'):
        response=client.post(path+'/consents',headers=headers,json=retry(kind=kind,purpose='Synthetic referral purpose',action_scope='referral_submission',representative='Synthetic authorized representative',representative_capacity='Sourced representation for this action',valid_from=(utcnow()-timedelta(days=30)).isoformat(),source=binding))
        assert response.status_code == 201,response.text
        consents[kind]=response.json()
    payload=retry(concern='Synthetic support concern',prior_measures='Visual support tried',observed_outcomes='Observed learning difficulty',requested_assessment='Educational assessment',learner_view='Wants visual materials',guardian_view='Agrees to referral',recipient='Synthetic expert service',sources=[binding],consent_ids=[consents['education_action']['id']],permission_requirement='required',permission_basis='Separate educational permission checked',disclosure_requirement='required',disclosure_permission_ids=[consents['disclosure_permission']['id']],disclosure_basis='Separate disclosure permission checked',processing_basis_id=consents['processing_basis']['id'])
    response=client.post(path+'/referrals',headers=headers,json=payload);assert response.status_code == 201,response.text
    row=response.json()
    response=client.post(path+f'/referrals/{row["id"]}/review',headers=headers,json=expected(row,content_digest=row['content']['digest'],reason='Synthetic source, permission and recipient review'))
    assert response.status_code == 200,response.text
    return response.json(),consents
