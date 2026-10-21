from datetime import date,timedelta
from sqlalchemy import select
from communication_fixtures import *
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.contexts.identity.models import GuardianRelationship,AuthorityGrant
from spesped.contexts.communication import models as m,service as svc,schemas as s

def test_portal_explicit_review_release_session_attachment_and_read(communication_env):
    client,factory,app,ids=communication_env;h=login(client);doc,policy,clearance,package,selection=setup(client,ids,h,attachments=True)
    preview=client.get(path(ids)+f'/packages/{package["id"]}/preview');assert preview.status_code==200;payload=preview.json();assert set(payload)=={'subject','body','attachments'}
    assert not any(v in preview.text for v in ('source_keys','snapshot_digest','guardian_user_id','example.invalid','handled_gaps'))
    package=authorize(client,ids,h,package);package=post(client,ids,h,f'/packages/{package["id"]}/export',review(package,mode='copied'));assert package['exports'] and not package['dispatches']
    package,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch);assert dispatch['state']=='sending';dispatch=release(client,ids,h,dispatch)
    assert dispatch['state']=='accepted' and not dispatch['read_acknowledged'];grant=dispatch['portal_grants'][0]
    gh=login(client,'guardian');assert client.get(base(ids)+f'/learners/{ids["a"]}').status_code==403
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==403
    opened=post(client,ids,gh,f'/portal/grants/{grant["id"]}/open',expected(grant));received=client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload');assert received.status_code==200;assert received.json()==payload
    attachment=client.get(path(ids)+f'/portal/grants/{grant["id"]}/attachments/{payload["attachments"][0]["id"]}');assert attachment.status_code==200 and b'Synthetic human text' in attachment.content
    opened=post(client,ids,gh,f'/portal/grants/{grant["id"]}/read-receipt',expected(opened))
    h=login(client);state=client.get(path(ids)+f'/dispatches/{dispatch["id"]}').json();assert state['transport_accepted'] and state['read_acknowledged']
    gh=login(client,'guardian');assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==403
    post(client,ids,gh,f'/portal/grants/{grant["id"]}/open',expected(opened))
    with factory.begin() as db:db.get(GuardianRelationship,ids['guardian_relation']).information_rights='unknown'
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code in {403,409}
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/attachments/{payload["attachments"][0]["id"]}').status_code in {403,409}

def test_queued_and_prepared_rights_revocation_blocks_release(communication_env):
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h);package=authorize(client,ids,h,package);package,dispatch=queued(client,ids,h,package)
    with factory.begin() as db:db.get(GuardianRelationship,ids['guardian_relation']).restrictions='Synthetic current sharing restriction'
    response=client.post(path(ids)+f'/dispatches/{dispatch["id"]}/prepare',headers=h,json=expected(dispatch,reason='Synthetic explicit release'));assert response.status_code==409
    with factory() as db:assert db.scalar(select(m.DispatchAttempt.id)) is None

def test_package_revision_invalidates_review_and_stale_signature_scope(communication_env):
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,selection=setup(client,ids,h);package=authorize(client,ids,h,package)
    changed=post(client,ids,h,f'/packages/{package["id"]}/revisions',expected(package,selection=selection,reason='Synthetic selected package change'),201);assert changed['state']=='draft' and changed['revision_id']!=package['revision_id']
    response=client.post(path(ids)+f'/packages/{package["id"]}/dispatches',headers=h,json=review(changed));assert response.status_code==409
    changed=authorize(client,ids,h,changed)
    with factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id==ids['reviewer'],AuthorityGrant.action=='communication.authorize'));grant.learner_id=ids['a'];grant.version+=1
    assert client.post(path(ids)+f'/packages/{package["id"]}/dispatches',headers=h,json=review(changed)).status_code==409

def test_missing_https_configuration_never_claims_delivery(communication_env):
    client,_,_,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package)
    assert client.post(path(ids)+f'/packages/{package["id"]}/dispatches',headers=h,json=review(package)).status_code==503

def test_secure_lost_reply_reconciliation_does_not_resubmit(communication_env,secure_wire):
    client,factory,app,ids=communication_env;configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https',attachments=True);package=authorize(client,ids,h,package);package,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    secure_wire.mode='lost_reply';command=expected(dispatch,reason='Synthetic explicit wire release');dispatch=post(client,ids,h,f'/dispatches/{dispatch["id"]}/release',command);assert dispatch['state']=='unknown' and len(secure_wire.submissions)==1
    replay=post(client,ids,h,f'/dispatches/{dispatch["id"]}/release',command);assert replay['state']=='unknown' and len(secure_wire.submissions)==1
    assert client.post(path(ids)+f'/dispatches/{dispatch["id"]}/prepare',headers=h,json=expected(dispatch,reason='Synthetic invalid blind retry')).status_code==409
    dispatch=post(client,ids,h,f'/dispatches/{dispatch["id"]}/reconcile',expected(dispatch,reason='Synthetic exact provider reconciliation'));assert dispatch['state']=='accepted' and len(secure_wire.submissions)==1 and len(secure_wire.lookups)==1
    assert secure_wire.submissions[0]['attachments'] and set(secure_wire.submissions[0]['payload'])=={'subject','body'}
    assert dispatch['read_receipts']==[]

def test_current_source_recall_and_attachment_tamper_block(communication_env):
    client,factory,app,ids=communication_env;h=login(client);doc,_,_,package,_=setup(client,ids,h,attachments=True);package=authorize(client,ids,h,package);package,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    transition(client,ids,h,doc,'recall')
    assert client.post(path(ids)+f'/dispatches/{dispatch["id"]}/release',headers=h,json=expected(dispatch,reason='Synthetic explicit release')).status_code==403
    with factory() as db:assert db.get(m.Dispatch,dispatch['id']).state=='sending'

def test_attachment_tamper_blocks_preview_and_release(communication_env):
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h,attachments=True);package=authorize(client,ids,h,package);package,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    with factory.begin() as db:db.execute(m.Attachment.__table__.update().where(m.Attachment.revision_id==package['revision_id']).values(data=b'Synthetic unauthorized replacement bytes'))
    assert client.get(path(ids)+f'/packages/{package["id"]}/preview').status_code==409
    assert client.post(path(ids)+f'/dispatches/{dispatch["id"]}/release',headers=h,json=expected(dispatch,reason='Synthetic release')).status_code==409
    with factory() as db:assert not db.scalar(select(m.PortalAccessGrant.id))

def test_rights_change_after_durable_start_before_wire_is_blocked(communication_env,secure_wire,monkeypatch):
    client,factory,app,ids=communication_env;configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package);package,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    original=svc.mark_release
    def revoke_after_start(*args,**kwargs):
        value=original(*args,**kwargs)
        with factory.begin() as db:db.get(GuardianRelationship,ids['guardian_relation']).state='revoked'
        return value
    monkeypatch.setattr(svc,'mark_release',revoke_after_start)
    dispatch=release(client,ids,h,dispatch);assert dispatch['state']=='failed' and dispatch['receipts'][-1]['reason_code']=='release_authorization_changed' and secure_wire.submissions==[]

def test_portal_expiry_revocation_and_wrong_scope(communication_env):
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h);package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);dispatch=release(client,ids,h,prepare(client,ids,h,dispatch));grant=dispatch['portal_grants'][0]
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==403
    gh=login(client,'guardian');grant=post(client,ids,gh,f'/portal/grants/{grant["id"]}/open',expected(grant));assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==200
    assert client.get(path({**ids,'school':ids['other_school']})+f'/portal/grants/{grant["id"]}/payload').status_code==403
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/attachments/{key()}').status_code==403
    with factory.begin() as db:db.get(m.PortalAccessGrant,grant['id']).expires_at=utcnow()-timedelta(seconds=1)
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==403
    with factory.begin() as db:db.get(m.PortalAccessGrant,grant['id']).expires_at=utcnow()+timedelta(hours=1)
    h=login(client);grant=client.get(path(ids)+f'/portal/grants/{grant["id"]}').json();post(client,ids,h,f'/portal/grants/{grant["id"]}/revoke',expected(grant,reason='Synthetic explicit grant revocation'))
    login(client,'guardian');assert client.get(path(ids)+f'/portal/grants/{grant["id"]}/payload').status_code==403

def test_semantic_replay_conflict_and_atomic_rollback_after_outbox(communication_env,monkeypatch):
    from sqlalchemy import func
    from spesped.errors import DomainError
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,selection=setup(client,ids,h);command=retry(selection=selection)
    replay=post(client,ids,h,'/packages',command,201);again=post(client,ids,h,'/packages',command,201);assert replay['id']==again['id']
    changed={**command,'selection':{**selection,'purpose':'changed-purpose'}};assert client.post(path(ids)+'/packages',headers=h,json=changed).status_code==409
    with factory() as db:before={model:db.scalar(select(func.count()).select_from(model)) for model in (m.DisclosurePackage,m.PackageRevision,m.CommunicationCommand,m.CommunicationEvent)}
    original=svc.event
    def fail_after_outbox(*args,**kwargs):
        original(*args,**kwargs)
        if args[3]=='communication.package.created':raise DomainError('synthetic_rollback','Synthetic failure after outbox insertion',503)
    monkeypatch.setattr(svc,'event',fail_after_outbox);assert client.post(path(ids)+'/packages',headers=h,json=retry(selection=selection)).status_code==503
    with factory() as db:
        for model,total in before.items():assert db.scalar(select(func.count()).select_from(model))==total

def test_dispatch_history_is_accepted_fact_and_read_preserves_pending(communication_env):
    from spesped.contexts.communication.adapters import NativeDispatchHistoryPort
    from spesped.errors import DomainError
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h);package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);port=NativeDispatchHistoryPort()
    with factory() as db:
        actor=Actor(ids['reviewer']);assert port.confirmed_periods(db,actor,ids['school'],ids['a'],ids['guardian_relation'],'learning_summary')==[]
    dispatch=release(client,ids,h,prepare(client,ids,h,dispatch))
    with factory() as db:
        values=port.confirmed_periods(db,Actor(ids['reviewer']),ids['school'],ids['a'],ids['guardian_relation'],'learning_summary');assert len(values)==1 and str(values[0].dispatch_id)==dispatch['id']
        relationship=db.get(GuardianRelationship,ids['guardian_relation']);relationship.restrictions='Synthetic unflushed edit'
        with pytest.raises(DomainError,match='staged'):port.confirmed_periods(db,Actor(ids['reviewer']),ids['school'],ids['a'],ids['guardian_relation'],'learning_summary')
        assert relationship.restrictions=='Synthetic unflushed edit' and relationship in db.dirty and db.in_transaction()
        db.rollback()
    assert client.get(path(ids)+f'/packages/{package["id"]}/preview').status_code==200

def test_receipt_rollback_and_lost_completion_reconcile_exact_key(communication_env,secure_wire,monkeypatch):
    from sqlalchemy import func
    from spesped.errors import DomainError
    from spesped.contexts.identity.models import AuditRecord
    client,factory,app,ids=communication_env;configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    with factory() as db:before={model:db.scalar(select(func.count()).select_from(model)) for model in (m.DeliveryReceipt,m.CommunicationCommand,m.CommunicationEvent,AuditRecord)}
    original=svc.event
    def fail_receipt(*args,**kwargs):
        original(*args,**kwargs)
        if args[3]=='communication.dispatch.unknown':raise DomainError('synthetic_receipt_rollback','Synthetic failure after receipt and outbox',503)
    monkeypatch.setattr(svc,'event',fail_receipt);response=client.post(path(ids)+f'/dispatches/{dispatch["id"]}/release',headers=h,json=expected(dispatch,reason='Synthetic release rollback'));assert response.status_code==503 and secure_wire.submissions==[]
    with factory() as db:
        for model,total in before.items():assert db.scalar(select(func.count()).select_from(model))==total
        assert db.get(m.Dispatch,dispatch['id']).state=='sending'
    def fail_completion(*args,**kwargs):
        original(*args,**kwargs)
        if args[3]=='communication.dispatch.accepted':raise DomainError('synthetic_completion_lost','Synthetic accepted completion transaction fails',503)
    monkeypatch.setattr(svc,'event',fail_completion);response=client.post(path(ids)+f'/dispatches/{dispatch["id"]}/release',headers=h,json=expected(dispatch,reason='Synthetic delivery completion rollback'));assert response.status_code==503 and len(secure_wire.submissions)==1
    monkeypatch.setattr(svc,'event',original);current=client.get(path(ids)+f'/dispatches/{dispatch["id"]}').json();assert current['state']=='unknown' and [v['outcome'] for v in current['receipts']]==['unknown']
    current=post(client,ids,h,f'/dispatches/{dispatch["id"]}/reconcile',expected(current,reason='Synthetic exact status after completion loss'));assert current['state']=='accepted' and len(secure_wire.submissions)==1 and len(secure_wire.lookups)==1

def test_late_native_source_requires_new_document_review(communication_env):
    from plans_fixtures import evidence
    client,factory,app,ids=communication_env;h=login(client);_,_,_,package,_=setup(client,ids,h);package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package)
    evidence(client,ids,h,text='Synthetic relevant late confirmed note about the selected educational period')
    assert client.get(path(ids)+f'/packages/{package["id"]}/preview').status_code==409
    assert client.post(path(ids)+f'/dispatches/{dispatch["id"]}/prepare',headers=h,json=expected(dispatch,reason='Synthetic no stale late-source release')).status_code==409

def test_other_guardian_and_other_learner_cannot_receive_package(communication_env):
    from spesped.auth import hash_password
    from spesped.contexts.identity.models import UserAccount,SchoolMembership
    from plans_fixtures import PASSWORD,ORIGIN
    client,factory,app,ids=communication_env;h=login(client);_,policy,clearance,package,selection=setup(client,ids,h);package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);dispatch=release(client,ids,h,prepare(client,ids,h,dispatch));grant=dispatch['portal_grants'][0]
    with factory.begin() as db:
        other=UserAccount(email='other-guardian@example.invalid',display_name='Synthetic independent guardian',password_hash=hash_password(PASSWORD));db.add(other);db.flush();db.add(SchoolMembership(school_id=ids['school'],user_id=other.id,role='guardian',valid_from=date(2020,1,1)));db.flush();relationship=GuardianRelationship(school_id=ids['school'],learner_id=ids['a'],guardian_user_id=other.id,relationship='parent',source_reference='synthetic-separate-guardian-source',parental_responsibility=True,information_rights='full',restrictions='',valid_from=date(2020,1,1));db.add(relationship);db.flush();other_id=other.id;relation_id=relationship.id
    response=client.post('/api/v1/auth/login',headers={'Origin':ORIGIN},json={'email':'other-guardian@example.invalid','password':PASSWORD});assert response.status_code==200;other_h={'Origin':ORIGIN,'X-CSRF-Token':response.json()['csrf_token']}
    assert client.get(path(ids)+'/portal/grants').json()['items']==[]
    assert client.get(path(ids)+f'/portal/grants/{grant["id"]}').status_code==403
    assert client.post(path(ids)+f'/portal/grants/{grant["id"]}/open',headers=other_h,json=expected(grant)).status_code==403
    assert client.get(path(ids)+f'/packages/{package["id"]}/preview').status_code==403
    h=login(client);other_clearance=post(client,ids,h,'/recipients',retry(learner_id=ids['a'],relationship_id=relation_id,settings=clearance['settings']),201);other_clearance=post(client,ids,h,f'/recipients/{other_clearance["id"]}/review',review(other_clearance))
    # A separate current rights review still cannot expand the BC10 source approval.
    response=client.post(path(ids)+'/packages',headers=h,json=retry(selection={**selection,'recipient_revision_id':other_clearance['revision_id']}));assert response.status_code==409
    response=client.post(path(ids)+'/packages',headers=h,json=retry(selection={**selection,'learner_id':ids['b']}));assert response.status_code==403
    preview=client.get(path(ids)+f'/packages/{package["id"]}/preview');assert preview.status_code==200 and other_id not in preview.text and relation_id not in preview.text and 'example.invalid' not in preview.text
