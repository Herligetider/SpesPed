"""Opt-in demo provisioning, exercised against fresh native application/database.

PostgreSQL runs always use a random isolated schema, never the existing demo DB.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from spesped import cli, demo_access
from spesped.auth import Actor, require_authority, require_learner_access
from spesped.cli import demo, migrate
from spesped.config import Settings
from spesped.contexts.identity.models import (
    AuditRecord, AuthorityGrant, Enrollment, GuardianRelationship, IdentityEvent,
    Learner, School, SchoolMembership, StaffAssignment, UserAccount,
)
from spesped.contexts.entitlements.models import EntitlementEvent, SupportCase
from spesped.db import make_session_factory, utcnow
from spesped.errors import DomainError
from spesped.main import create_app
from plans_fixtures import evidence, expected, retry, confirmed_decision
from teaching_fixtures import ordinary_goal, basis, session

PASSWORD = "synthetic-demo-test-only"
ORIGIN = "http://testserver"


@pytest.fixture(params=["sqlite", "postgres"])
def demo_env(request, tmp_path):
    admin = None
    schema = None
    if request.param == "postgres":
        raw = os.environ.get("SPESPED_TEST_POSTGRES_URL")
        if not raw:
            pytest.skip("Set SPESPED_TEST_POSTGRES_URL for isolated PostgreSQL verification")
        schema = "demo_access_" + uuid4().hex
        admin = create_engine(raw)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(raw).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path}/demo.db"
    factory = None
    try:
        migrate(url)
        factory = make_session_factory(url)
        settings = Settings(environment="development", database_url=url, allowed_origins=[ORIGIN], evidence_storage_root=tmp_path / "private")
        with factory.begin() as db:
            demo(db, PASSWORD)
        with factory() as db:
            ids = {u.email.split("@")[0].split(".")[1]: u.id for u in db.scalars(select(UserAccount))}
            pupils = {p.display_name[-1].lower(): p for p in db.scalars(select(Learner))}
            ids.update({key: value.id for key, value in pupils.items()})
            ids.update(school=pupils['a'].school_id, other_school=pupils['c'].school_id, reviewer=ids['leader'])
        # No test authorization grants, fake qualification ports or provider setup.
        app = create_app(settings, factory)
        with TestClient(app) as client:
            yield client, factory, app, ids
    finally:
        if factory:
            factory.kw['bind'].dispose()
        if admin:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def login(client, key="leader"):
    response = client.post("/api/v1/auth/login", headers={"Origin": ORIGIN},
                           json={"email": f"demo.{key}@example.invalid", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def base(ids):
    return f'/api/v1/schools/{ids["school"]}'


def upgrade(factory):
    with factory.begin() as db:
        return demo_access.upgrade_demo_access(db, environment="development", confirm_synthetic=True)


def counts(factory):
    with factory() as db:
        return tuple(db.scalar(select(func.count()).select_from(model)) for model in
                     (AuthorityGrant, AuditRecord, IdentityEvent, SupportCase, EntitlementEvent))


def unchanged_identity(factory):
    with factory() as db:
        return {model.__tablename__: sorted([tuple(str(getattr(row, c.name)) for c in model.__table__.columns)
                                           for row in db.scalars(select(model))])
                for model in (School, UserAccount, SchoolMembership, Enrollment, StaffAssignment, GuardianRelationship)}


def test_current_workspaces_before_after_and_exact_preserved_scope(demo_env):
    client, factory, app, ids = demo_env
    login(client)
    paths = ["/intake"]
    for pupil in (ids['a'], ids['b']):
        prefix = f"/learners/{pupil}"
        paths += [prefix + suffix for suffix in (
            "/timeline", "/support-profile", "/education-plans", "/support-cases",
            "/teaching-sessions", "/teaching-deliveries", "/teaching-observations", "/teaching-follow-ups")]
        paths.append(f"/documents/learners/{pupil}/workspace")
        paths.append(f"/ai/choices?learner_id={pupil}&purpose=session_planning")
    for path in paths:
        response = client.get(base(ids) + path)
        assert response.status_code == 403, (path, response.status_code, response.text)
    identity = unchanged_identity(factory)
    before = counts(factory)
    result = upgrade(factory)
    assert result['added_grants'] == 2 * len(demo_access.PUPIL_ACTIONS) + 1 + 2 * len(demo_access.CASE_ACTIONS)
    assert result['learner_ids'] == sorted([ids['a'], ids['b']]) and len(result['case_ids']) == 2
    assert unchanged_identity(factory) == identity
    assert counts(factory)[0] - before[0] == result['added_grants']
    for path in paths:
        response = client.get(base(ids) + path)
        assert response.status_code == 200, (path, response.status_code, response.text)
    with factory() as db:
        added = db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'],
                                                     AuthorityGrant.action.not_in(cli.BOOTSTRAP_ACTIONS))).all()
        assert len(added) == result['added_grants']
        assert all(g.learner_id in {ids['a'], ids['b']} if g.action != 'evidence.intake'
                   else g.learner_id is None and g.case_id is None for g in added)
        assert all(g.case_id in result['case_ids'] for g in added if g.action in demo_access.CASE_ACTIONS)
        for forbidden in ('platform.manage', 'platform.review', 'documents.schedule.run',
                          'documents.templates.manage', 'dispatch.send', 'disclosure.approve', 'safeguarding.read'):
            with pytest.raises(DomainError):
                require_authority(db, Actor(ids['leader']), ids['school'], forbidden, ids['a'])
        for key in ('assistant', 'guardian', 'technical', 'other', 'teacher'):
            for action in demo_access.PUPIL_ACTIONS:
                with pytest.raises(DomainError):
                    require_learner_access(db, Actor(ids[key]), ids['school'], ids['a'], action)
        for action in demo_access.PUPIL_ACTIONS:
            with pytest.raises(DomainError):
                require_learner_access(db, Actor(ids['leader']), ids['other_school'], ids['c'], action)
        # Existing assistant brief permission is preserved and remains pupil A only.
        require_learner_access(db, Actor(ids['assistant']), ids['school'], ids['a'], 'brief.read')
        with pytest.raises(DomainError):
            require_learner_access(db, Actor(ids['assistant']), ids['school'], ids['b'], 'brief.read')
    for account in ('assistant', 'guardian', 'technical', 'other'):
        login(client, account)
        assert client.get(base(ids) + f'/learners/{ids["a"]}/support-profile').status_code == 403
        assert client.get(base(ids) + f'/support-cases/{result["case_ids"][0]}').status_code == 403
        assert client.get(base(ids) + '/intake').status_code == 403


def test_native_manual_evidence_profile_plan_teaching_case_decision_and_document(demo_env):
    client, factory, app, ids = demo_env
    upgrade(factory)
    h = login(client)
    binding, item = evidence(client, ids, h)
    profile = base(ids) + f'/learners/{ids["a"]}/support-profile'
    response = client.post(profile + '/statements', headers=h, json=retry(
        category='support_strategy', content='Synthetic visual support', source=binding,
        observed_at=(utcnow() - timedelta(days=1)).isoformat()))
    assert response.status_code == 201, response.text
    statement = response.json()
    response = client.post(profile + f'/statements/{statement["id"]}/review', headers=h,
                           json=expected(statement, outcome='confirmed', reason='Synthetic source checked'))
    assert response.status_code == 200 and response.json()['state'] == 'confirmed', response.text
    goal, plan = ordinary_goal(client, ids, h, binding=binding)
    assert plan['revision_state'] == 'active'
    prepared = basis(client, ids, h, {'a': goal})
    teaching = session(client, ids, h, prepared)
    # Native qualifications remain unresolved, without test eligibility bypass.
    response = client.post(base(ids) + f'/teaching/sessions/{teaching["id"]}/review', headers=h,
                           json=expected(teaching, revision_id=teaching['revision_id'],
                                         content_digest=teaching['content_digest'], reason='Synthetic human review'))
    assert response.status_code == 200, response.text
    cases = client.get(base(ids) + f'/learners/{ids["a"]}/support-cases').json()['items']
    assert len(cases) == 1 and 'Syntetisk' in cases[0]['concern']
    case = cases[0]
    response = client.patch(base(ids) + f'/support-cases/{case["id"]}', headers=h,
                            json=expected(case, concern='Synthetic reviewed concern', owner_id=ids['leader'], state='preparation'))
    assert response.status_code == 200, response.text
    decision = confirmed_decision(client, ids, h, response.json(), binding)
    assert decision['state'] == 'confirmed'
    response = client.post(base(ids) + '/documents/cases', headers=h, json=retry(
        learner_id=ids['a'], owner_id=ids['leader'], kind='local_semester_report', purpose='learning_summary',
        starts_on=(utcnow().date() - timedelta(days=30)).isoformat(), ends_on=utcnow().date().isoformat()))
    assert response.status_code == 201, response.text
    document = response.json()
    assert document['state'] == 'draft'
    response = client.post(base(ids) + f'/documents/cases/{document["id"]}/review', headers=h,
                           json=expected(document, revision_id=document['revision_id'], content_digest=document['content_digest'],
                                         action='review', reason='Synthetic manual review'))
    assert response.status_code == 200, response.text
    # Missing reviewed templates remain a visible domain/configuration gate.
    response = client.post(base(ids) + f'/documents/cases/{document["id"]}/review', headers=h,
                           json=expected(response.json(), revision_id=document['revision_id'],
                                         content_digest=document['content_digest'], action='approve', reason='Synthetic approval attempt'))
    assert response.status_code == 409 and response.json()['error']['code'] != 'access_denied', response.text
    response = client.post(base(ids) + '/documents/cases', headers=h, json=retry(
        learner_id=ids['a'], owner_id=ids['leader'], kind='guardian_email', purpose='learning_summary',
        starts_on=utcnow().date().isoformat(), ends_on=utcnow().date().isoformat()))
    assert response.status_code == 422 and response.json()['error']['code'] == 'recipient_selection'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(GuardianRelationship)) == 0
    before = counts(factory)
    assert upgrade(factory)['added_grants'] == 0
    assert counts(factory) == before


def test_idempotence_and_rollback_include_audit_outbox_and_native_cases(demo_env, monkeypatch):
    _, factory, _, _ = demo_env
    before = counts(factory)
    real = demo_access.create_case
    def fail_after_native_case(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError('synthetic rollback probe')
    monkeypatch.setattr(demo_access, 'create_case', fail_after_native_case)
    with pytest.raises(RuntimeError, match='rollback probe'):
        upgrade(factory)
    assert counts(factory) == before
    monkeypatch.setattr(demo_access, 'create_case', real)
    first = upgrade(factory)
    count = counts(factory)
    second = upgrade(factory)
    assert second == {**first, 'added_grants': 0}
    assert counts(factory) == count


@pytest.mark.parametrize('damage', ['audit', 'membership', 'account', 'pupil', 'replacement', 'assignment', 'baseline_grant'])
def test_non_demo_incomplete_changed_or_revoked_fixture_fails_before_mutation(demo_env, damage):
    _, factory, _, ids = demo_env
    with factory.begin() as db:
        if damage == 'audit':
            db.delete(db.scalar(select(AuditRecord).where(AuditRecord.action == 'synthetic_fixture.created')))
        elif damage == 'membership':
            db.scalar(select(SchoolMembership).where(SchoolMembership.user_id == ids['leader'])).state = 'revoked'
        elif damage == 'account':
            db.get(UserAccount, ids['leader']).display_name = 'An unrelated live account'
        elif damage == 'pupil':
            db.get(Learner, ids['a']).display_name = 'An unrelated pupil'
        elif damage == 'replacement':
            # Exact email/name alone cannot attest to an original fixture row.
            db.get(Learner, ids['a']).created_at = utcnow() + timedelta(seconds=1)
        elif damage == 'assignment':
            db.scalar(select(StaffAssignment).where(StaffAssignment.user_id == ids['assistant'])).state = 'revoked'
        else:
            db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'], AuthorityGrant.action == 'learner.read')).state = 'revoked'
    before = counts(factory)
    with pytest.raises(ValueError, match='Demo access refused'):
        upgrade(factory)
    assert counts(factory) == before


@pytest.mark.parametrize('damage', ['revoked', 'expired', 'deleted', 'changed_scope'])
def test_never_restore_previously_removed_scope(demo_env, damage):
    _, factory, _, ids = demo_env
    upgrade(factory)
    with factory.begin() as db:
        grant = db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'],
                          AuthorityGrant.action == 'evidence.read', AuthorityGrant.learner_id == ids['a']))
        if damage == 'deleted':
            db.delete(grant)
        elif damage == 'changed_scope':
            grant.learner_id = ids['b']
        elif damage == 'expired':
            grant.valid_from = utcnow().date() - timedelta(days=2)
            grant.valid_until = utcnow().date() - timedelta(days=1)
        else:
            grant.state = 'revoked'
    before = counts(factory)
    with pytest.raises(ValueError, match='removed|revoked|ambiguous'):
        upgrade(factory)
    assert counts(factory) == before


def test_new_native_demo_leader_cases_need_explicit_rerun_and_other_cases_stay_isolated(demo_env):
    client, factory, _, ids = demo_env
    seeded = upgrade(factory)
    h = login(client)
    response = client.post(base(ids) + f'/learners/{ids["a"]}/support-cases', headers=h,
                           json=retry(owner_id=ids['leader'], concern='Synthetic additional educational case'))
    assert response.status_code == 201, response.text
    created = response.json()
    assert client.get(base(ids) + f'/support-cases/{created["id"]}').status_code == 403
    with factory.begin() as db:
        # Existing unrelated/protected cases never gain scope by pupil coincidence.
        outsiders = []
        for learner_id, owner, purpose in ((ids['a'], ids['teacher'], 'educational_support'),
                                          (ids['b'], ids['leader'], 'school_environment'),
                                          (ids['c'], ids['other'], 'educational_support')):
            row = SupportCase(school_id=ids['other_school'] if learner_id == ids['c'] else ids['school'],
                              learner_id=learner_id, owner_id=owner, purpose=purpose,
                              concern='Synthetic out of scope', state='preparation')
            db.add(row); db.flush(); outsiders.append(row.id)
    result = upgrade(factory)
    assert result['added_grants'] == len(demo_access.CASE_ACTIONS)
    assert set(result['case_ids']) == set(seeded['case_ids']) | {created['id']}
    assert client.get(base(ids) + f'/support-cases/{created["id"]}').status_code == 200
    for case_id in outsiders:
        assert client.get(base(ids) + f'/support-cases/{case_id}').status_code == 403
    assert upgrade(factory)['added_grants'] == 0


def test_non_fixture_with_matching_leader_email_is_rejected(demo_env):
    _, factory, _, _ = demo_env
    # Even intact names and emails do not substitute for creation provenance.
    with factory.begin() as db:
        record = db.scalar(select(AuditRecord).where(AuditRecord.action == 'synthetic_fixture.created'))
        record.actor_id = db.scalar(select(UserAccount.id).where(UserAccount.email == 'demo.other@example.invalid'))
    before = counts(factory)
    with pytest.raises(ValueError, match='provenance'):
        upgrade(factory)
    assert counts(factory) == before


@pytest.mark.parametrize('environment', ['production', 'test', 'staging', '', None])
def test_callable_development_guard_runs_before_database_access(environment):
    with pytest.raises(ValueError, match='only.*development'):
        demo_access.upgrade_demo_access(None, environment=environment, confirm_synthetic=True)


@pytest.mark.parametrize('confirmation', [False, None, 'yes', 1])
def test_callable_requires_literal_confirmation(confirmation):
    with pytest.raises(ValueError, match='confirm-synthetic'):
        demo_access.upgrade_demo_access(None, environment='development', confirm_synthetic=confirmation)


def test_cli_confirmation_environment_and_no_password_reset(demo_env, monkeypatch, capsys):
    _, factory, app, _ = demo_env
    monkeypatch.setattr(cli, 'get_settings', lambda: app.state.settings)
    monkeypatch.setattr(cli, 'make_session_factory', lambda url: factory)
    monkeypatch.setattr(cli.getpass, 'getpass', lambda *args: pytest.fail('demo-access must never request/reset passwords'))
    monkeypatch.setattr('sys.argv', ['spesped', 'demo-access'])
    before = counts(factory)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2 and counts(factory) == before
    monkeypatch.setattr('sys.argv', ['spesped', 'demo-access', '--confirm-synthetic'])
    identity = unchanged_identity(factory)
    cli.main()
    assert 'Synthetic practitioner access ready' in capsys.readouterr().out
    assert unchanged_identity(factory) == identity
    cli.main()
    assert '0 grants added' in capsys.readouterr().out
    for environment in ('test', 'production'):
        monkeypatch.setattr(cli, 'get_settings', lambda: app.state.settings.model_copy(update={'environment': environment}))
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 2


def test_concurrent_upgrade_is_idempotent(demo_env):
    _, factory, _, _ = demo_env
    barrier = Barrier(2)
    def worker():
        barrier.wait(timeout=10)
        return upgrade(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(r['added_grants'] for r in results) == [0, 2 * len(demo_access.PUPIL_ACTIONS) + 11]
    assert results[0]['case_ids'] == results[1]['case_ids']


@pytest.mark.parametrize('damage', ['revoked', 'expired'])
def test_inactive_covering_authority_is_not_restored_by_narrower_grants(demo_env, damage):
    _, factory, _, ids = demo_env
    with factory.begin() as db:
        today = utcnow().date()
        db.add(AuthorityGrant(school_id=ids['school'], user_id=ids['leader'], action='documents.read',
                              valid_from=today - timedelta(days=2), granted_by=ids['leader'],
                              state='revoked' if damage == 'revoked' else 'active',
                              valid_until=today - timedelta(days=1) if damage == 'expired' else None))
    before = counts(factory)
    with pytest.raises(ValueError, match='overlapping.*expired or revoked'):
        upgrade(factory)
    assert counts(factory) == before


def test_missing_case_scope_cannot_be_hidden_by_moving_grant_to_new_demo_case(demo_env):
    client, factory, _, ids = demo_env
    upgrade(factory)
    h = login(client)
    response = client.post(base(ids) + f'/learners/{ids["a"]}/support-cases', headers=h,
                           json=retry(owner_id=ids['leader'], concern='Synthetic new unprovisioned case'))
    assert response.status_code == 201, response.text
    new_case = response.json()['id']
    with factory.begin() as db:
        grant = db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'],
                          AuthorityGrant.action == 'support_case.read', AuthorityGrant.learner_id == ids['a']))
        grant.case_id = new_case
    before = counts(factory)
    with pytest.raises(ValueError, match='case scope was removed or changed'):
        upgrade(factory)
    assert counts(factory) == before


@pytest.mark.parametrize('target', ['baseline', 'provisioned', 'membership'])
def test_clean_retained_session_cannot_hide_persisted_revocation(demo_env, target):
    _, factory, _, ids = demo_env
    if target == 'provisioned':
        upgrade(factory)
    with factory() as retained:
        if target == 'membership':
            model = SchoolMembership
            cached = retained.scalar(select(model).where(model.user_id == ids['leader']))
        else:
            model = AuthorityGrant
            action = 'learner.read' if target == 'baseline' else 'documents.read'
            cached = retained.scalar(select(model).where(model.user_id == ids['leader'], model.action == action))
        with factory.begin() as writer:
            writer.get(model, cached.id).state = 'revoked'
        assert cached.state == 'active'  # Retained identity is deliberately stale.
        before = counts(factory)
        with pytest.raises(ValueError, match='revoked|inactive'):
            demo_access.upgrade_demo_access(retained, environment='development', confirm_synthetic=True)
        retained.rollback()
        assert counts(factory) == before
