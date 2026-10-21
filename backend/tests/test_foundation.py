from datetime import date, timedelta
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm.exc import StaleDataError

from spesped.auth import Actor, hash_password, hash_token, require_authority, require_learner_access
from spesped.cli import migrate, provision_school
from spesped.config import Settings
from spesped.db import make_session_factory, utcnow
from spesped.errors import DomainError
from spesped.main import create_app
from spesped.contexts.identity.models import AuditRecord, AuthorityGrant, GuardianRelationship, IdentityEvent, Learner, LoginSession, SchoolMembership, StaffAssignment, UserAccount

PASSWORD = "synthetic-test-passphrase"
ORIGIN = "http://testserver"


@pytest.fixture(params=["sqlite", "postgres"])
def env(request, tmp_path):
    schema = None
    admin_engine = None
    if request.param == "postgres":
        url = os.environ.get("SPESPED_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("Set SPESPED_TEST_POSTGRES_URL for PostgreSQL verification")
        schema = "j01_" + uuid4().hex
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path}/test.db"
    migrate(url)
    factory = make_session_factory(url)
    settings = Settings(environment="test", database_url=url, allowed_origins=[ORIGIN])
    with factory.begin() as db:
        school, leader = provision_school(db, school_name="Synthetic School A", kind="public", timezone="Europe/Oslo", email="leader@example.invalid", display_name="Synthetic Leader", password=PASSWORD)
        other, other_leader = provision_school(db, school_name="Synthetic School B", kind="montessori", timezone="Europe/Oslo", email="other@example.invalid", display_name="Synthetic Other", password=PASSWORD)
        ids = {"school": school.id, "other_school": other.id, "leader": leader.id}
        encoded = hash_password(PASSWORD)
        for key, role in (("teacher", "teacher"), ("tech", "technical_administrator"), ("assistant", "assistant"), ("guardian", "guardian")):
            user = UserAccount(email=f"{key}@example.invalid", display_name=f"Synthetic {key}", password_hash=encoded)
            db.add(user)
            db.flush()
            ids[key] = user.id
            db.add(SchoolMembership(school_id=school.id, user_id=user.id, role=role, valid_from=date.today()))
        db.flush()
        for key, sid in (("learner", school.id), ("hidden", school.id), ("foreign", other.id)):
            learner = Learner(school_id=sid, display_name=f"Synthetic {key}", grade=4, group_name="Synthetic group")
            db.add(learner)
            db.flush()
            ids[key] = learner.id
        assignment = StaffAssignment(school_id=school.id, learner_id=ids["learner"], user_id=ids["teacher"], actions=["learner.read", "learner.update", "document.contribute"], purpose="synthetic_teaching", valid_from=date.today())
        db.add(assignment)
        db.flush()
        ids["assignment"] = assignment.id
        db.add(StaffAssignment(school_id=school.id, learner_id=ids["learner"], user_id=ids["assistant"], actions=["brief.read", "observation.create"], purpose="synthetic_brief", valid_from=date.today()))
        # Infrastructure management deliberately lacks content and delegation permission.
        for action in ("assignment.manage", "authority.manage", "membership.manage"):
            db.add(AuthorityGrant(school_id=school.id, user_id=ids["tech"], action=action, valid_from=date.today(), granted_by=leader.id))
    app = create_app(settings, factory)
    with TestClient(app) as client:
        yield client, factory, settings, ids
    factory.kw["bind"].dispose()
    if schema:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def login(client, name="teacher"):
    response = client.post("/api/v1/auth/login", json={"email": f"{name}@example.invalid", "password": PASSWORD}, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def path(ids, key="learner"):
    return f'/api/v1/schools/{ids["school"]}/learners/{ids[key]}'


def test_real_login_csrf_origin_cookie_logout_and_hashes(env):
    client, factory, settings, ids = env
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/auth/me", headers={"X-User-ID": ids["teacher"], "X-Role": "school_leader"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}).status_code == 403
    bad = client.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": "wrong"}, headers={"Origin": ORIGIN})
    assert bad.status_code == 401 and "wrong" not in bad.text
    headers = login(client)
    token = client.cookies[settings.cookie_name]
    me = client.get("/api/v1/auth/me")
    assert me.json()["csrf_token"] == headers["X-CSRF-Token"]
    assert set(me.json()) == {"user", "csrf_token", "schools"}
    with factory() as db:
        session = db.scalar(select(LoginSession))
        assert session.token_hash == hash_token(token) and session.token_hash != token
        assert db.get(UserAccount, ids["teacher"]).password_hash.startswith("$argon2id$")
    change = {"grade": 5, "expected_version": 1}
    assert client.patch(path(ids), json=change).status_code == 403
    assert client.patch(path(ids), json=change, headers={**headers, "Origin": "http://evil.invalid"}).status_code == 403
    assert client.patch(path(ids), json=change, headers={"Origin": ORIGIN, "X-CSRF-Token": "bad"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(settings.cookie_name, token, path="/api")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_scope_filtered_pagination_unknown_ids_and_technical_admin(env):
    client, factory, settings, ids = env
    login(client)
    base = f'/api/v1/schools/{ids["school"]}/learners'
    result = client.get(base).json()
    assert result["total"] == 1 and result["items"][0]["id"] == ids["learner"]
    assert client.get(base + "?offset=1&limit=1").json() == {"items": [], "total": 1}
    assert client.get(base + "?limit=101").status_code == 422
    denied = client.get(path(ids, "hidden"))
    assert denied.status_code == 403
    assert client.get(path(ids, "foreign")).json() == denied.json()
    assert client.get(base + "/" + str(uuid4())).json() == denied.json()
    assert client.get(f'/api/v1/schools/{ids["other_school"]}/learners').status_code == 403
    login(client, "tech")
    assert client.get(base).json() == {"items": [], "total": 0}
    assert client.get(path(ids)).status_code == 403
    login(client, "assistant")
    assert client.get(path(ids)).status_code == 403
    with factory() as db:
        assert require_learner_access(db, Actor(ids["assistant"]), ids["school"], ids["learner"], "brief.read").id == ids["learner"]
        with pytest.raises(DomainError):
            require_learner_access(db, Actor(ids["assistant"]), ids["school"], ids["learner"], "evidence.read")


def test_expired_session_assignment_and_membership_rechecked(env):
    client, factory, settings, ids = env
    login(client)
    with factory.begin() as db:
        db.get(StaffAssignment, ids["assignment"]).valid_until = date.today() - timedelta(days=1)
        db.get(StaffAssignment, ids["assignment"]).valid_from = date.today() - timedelta(days=2)
    assert client.get(path(ids)).status_code == 403
    with factory() as db:
        with pytest.raises(DomainError):
            require_learner_access(db, Actor(ids["teacher"]), ids["school"], ids["learner"])
    with factory.begin() as db:
        db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(client.cookies[settings.cookie_name]))).expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    with factory.begin() as db:
        membership = db.scalar(select(SchoolMembership).where(SchoolMembership.user_id == ids["teacher"]))
        membership.state = "revoked"
    assert client.get(path(ids)).status_code == 403
    assert client.get("/api/v1/auth/me").json()["schools"] == []


def test_real_updates_conflict_persistence_audit_and_atomic_rollback(env):
    client, factory, settings, ids = env
    headers = login(client)
    response = client.patch(path(ids), json={"expected_version": 1, "grade": 6}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert client.patch(path(ids), json={"expected_version": 1, "grade": 7}, headers=headers).status_code == 409
    assert client.patch(path(ids), json={"expected_version": 2, "grade": 11}, headers=headers).status_code == 422
    assert client.patch(path(ids), json={"expected_version": 2, "display_name": None}, headers=headers).status_code == 422
    # A separately constructed app/session sees durable state.
    with TestClient(create_app(settings, make_session_factory(settings.database_url))) as restarted:
        login(restarted)
        assert restarted.get(path(ids)).json()["grade"] == 6
    with factory() as db:
        events = db.scalars(select(IdentityEvent).where(IdentityEvent.aggregate_id == ids["learner"])).all()
        audit = db.scalars(select(AuditRecord).where(AuditRecord.action == "learner.updated")).all()
        assert len(events) == len(audit) == 1
        assert "Synthetic" not in repr(audit[0].__dict__)
    # Two actual concurrent SQLAlchemy snapshots cannot overwrite each other.
    with factory() as left, factory() as right:
        one, two = left.get(Learner, ids["learner"]), right.get(Learner, ids["learner"])
        one.grade = 7
        left.commit()
        two.grade = 8
        with pytest.raises(StaleDataError):
            right.commit()
    # Audit helper never commits independently and rolls back with the business change.
    from spesped.audit import record_audit
    with factory() as db:
        row = db.get(Learner, ids["learner"])
        row.grade = 9
        record_audit(db, Actor(ids["teacher"]), ids["school"], "test.rollback", "learner", row.id)
        db.flush()
        db.rollback()
    with factory() as db:
        assert db.get(Learner, ids["learner"]).grade == 7
        assert db.scalar(select(AuditRecord).where(AuditRecord.action == "test.rollback")) is None


def test_role_is_not_authority_and_management_cannot_escalate(env):
    client, factory, settings, ids = env
    headers = login(client)
    base = f'/api/v1/schools/{ids["school"]}'
    assert client.post(base + "/learners", json={"display_name": "Synthetic new", "grade": 4, "group_name": "A"}, headers=headers).status_code == 403
    with factory() as db:
        with pytest.raises(DomainError):
            require_authority(db, Actor(ids["teacher"]), ids["school"], "document.approve", ids["learner"])
    headers = login(client, "tech")
    assignment = {"learner_id": ids["learner"], "user_id": ids["tech"], "actions": ["learner.read"], "purpose": "synthetic", "valid_from": date.today().isoformat()}
    assert client.post(base + "/assignments", json=assignment, headers=headers).status_code == 403
    grant = {"user_id": ids["tech"], "action": "learner.read", "valid_from": date.today().isoformat()}
    assert client.post(base + "/authorities", json=grant, headers=headers).status_code == 403
    assert client.post(base + "/authorities", json={**grant, "action": "authority.delegate"}, headers=headers).status_code == 403
    leader_headers = login(client, "leader")
    result = client.post(base + "/assignments", json=assignment, headers=leader_headers)
    assert result.status_code == 201, result.text
    assignment_id = result.json()["id"]
    login(client, "tech")
    assert client.get(path(ids)).status_code == 200
    revoke = {"expected_version": 1, "state": "revoked", "valid_from": date.today().isoformat(), "valid_until": None}
    assert client.patch(base + f"/access/assignments/{assignment_id}", json=revoke, headers=login(client, "leader")).status_code == 200
    tech_headers = login(client, "tech")
    assert client.patch(base + f"/access/assignments/{assignment_id}", json={**revoke, "state": "active", "expected_version": 2}, headers=tech_headers).status_code == 403
    assert client.get(path(ids)).status_code == 403


def test_dated_scoped_authority_and_guardian_relationship_not_read_permission(env):
    client, factory, settings, ids = env
    headers = login(client, "leader")
    base = f'/api/v1/schools/{ids["school"]}'
    future = date.today() + timedelta(days=1)
    grant = {"user_id": ids["teacher"], "action": "document.approve", "learner_id": ids["learner"], "valid_from": future.isoformat(), "valid_until": (future + timedelta(days=1)).isoformat()}
    assert client.post(base + "/authorities", json=grant, headers=headers).status_code == 201
    assert client.post(base + "/authorities", json={**grant, "learner_id": ids["foreign"]}, headers=headers).status_code == 403
    with factory() as db:
        with pytest.raises(DomainError):
            require_authority(db, Actor(ids["teacher"]), ids["school"], "document.approve", ids["learner"])
    # Dated rights and source exist independently of pupil dossier access.
    relationship = {"learner_id": ids["learner"], "guardian_user_id": ids["guardian"], "relationship": "parent", "source_reference": "synthetic-document-1", "parental_responsibility": True, "information_rights": "confirmed", "valid_from": date.today().isoformat()}
    result = client.post(base + "/guardians", json=relationship, headers=headers)
    assert result.status_code == 201, result.text
    guardian_headers = login(client, "guardian")
    assert client.get(path(ids)).status_code == 403
    assert client.get(base + "/learners").json() == {"items": [], "total": 0}


def test_create_learner_and_validation_safe_errors(env):
    client, factory, settings, ids = env
    headers = login(client, "leader")
    base = f'/api/v1/schools/{ids["school"]}/learners'
    response = client.post(base, json={"display_name": "Synthetic created", "grade": 3, "group_name": "B"}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["version"] == 1
    invalid = client.post(base, json={"display_name": "Synthetic sensitive input", "grade": "bad", "group_name": "B"}, headers=headers)
    assert invalid.status_code == 422 and "Synthetic sensitive input" not in invalid.text and '"bad"' not in invalid.text
    assert client.get(base).json()["total"] == 3


def test_production_configuration_rejects_unsafe_defaults():
    with pytest.raises(ValueError):
        Settings(environment="production")
    with pytest.raises(ValueError):
        Settings(environment="production", database_url="postgresql+psycopg://u:password@host/db", secret_key="x" * 64, cookie_secure=True, allowed_origins=["https://school.invalid"])
    safe = Settings(environment="production", database_url="postgresql+psycopg://user:nondefault-secret@host/db", secret_key="x" * 64, cookie_secure=True, allowed_origins=["https://school.invalid"])
    assert safe.cookie_secure


def test_current_authority_is_learner_case_and_date_specific(env):
    client, factory, settings, ids = env
    today = date.today()
    with factory.begin() as db:
        db.add_all([
            AuthorityGrant(school_id=ids["school"], user_id=ids["teacher"], action="document.approve", learner_id=ids["learner"], valid_from=today, valid_until=today, granted_by=ids["leader"]),
            AuthorityGrant(school_id=ids["school"], user_id=ids["teacher"], action="case.read", learner_id=ids["learner"], case_id=ids["hidden"], valid_from=today, granted_by=ids["leader"]),
        ])
    with factory() as db:
        actor = Actor(ids["teacher"])
        assert require_authority(db, actor, ids["school"], "document.approve", ids["learner"])
        for learner in (ids["hidden"], ids["foreign"], None):
            with pytest.raises(DomainError):
                require_authority(db, actor, ids["school"], "document.approve", learner)
        assert require_authority(db, actor, ids["school"], "case.read", ids["learner"], ids["hidden"])
        with pytest.raises(DomainError):
            require_authority(db, actor, ids["school"], "case.read", ids["learner"])
        with pytest.raises(DomainError):
            require_authority(db, actor, ids["school"], "case.read", ids["learner"], ids["foreign"])
    with factory.begin() as db:
        db.get(UserAccount, ids["teacher"]).state = "suspended"
    with factory() as db:
        with pytest.raises(DomainError):
            require_authority(db, Actor(ids["teacher"]), ids["school"], "document.approve", ids["learner"])


def test_delegated_manager_cannot_expand_scope_or_validity(env):
    client, factory, settings, ids = env
    today = date.today()
    tomorrow = today + timedelta(days=1)
    with factory.begin() as db:
        db.add(AuthorityGrant(school_id=ids["school"], user_id=ids["tech"], action="learner.read", learner_id=ids["learner"], valid_from=today, valid_until=tomorrow, granted_by=ids["leader"]))
    headers = login(client, "tech")
    base = f'/api/v1/schools/{ids["school"]}'
    assignment = {"learner_id": ids["learner"], "user_id": ids["teacher"], "actions": ["learner.read"], "purpose": "synthetic", "valid_from": today.isoformat(), "valid_until": tomorrow.isoformat()}
    assert client.post(base + "/assignments", json=assignment, headers=headers).status_code == 201
    assert client.post(base + "/assignments", json={**assignment, "valid_until": None}, headers=headers).status_code == 403
    assert client.post(base + "/assignments", json={**assignment, "learner_id": ids["hidden"]}, headers=headers).status_code == 403
    assert client.post(base + "/assignments", json={**assignment, "valid_from": (today - timedelta(days=1)).isoformat()}, headers=headers).status_code == 403
    grant = {"user_id": ids["teacher"], "action": "learner.read", "valid_from": today.isoformat(), "valid_until": tomorrow.isoformat()}
    # The technical manager's pupil-specific authority cannot become school-wide.
    assert client.post(base + "/authorities", json=grant, headers=headers).status_code == 403
    assert client.post(base + "/authorities", json={**grant, "learner_id": ids["learner"]}, headers=headers).status_code == 201


def test_login_rotation_and_durable_throttle(env):
    client, factory, settings, ids = env
    login(client)
    old = client.cookies[settings.cookie_name]
    login(client)
    new = client.cookies[settings.cookie_name]
    assert old != new
    client.cookies.set(settings.cookie_name, old, domain="testserver.local", path="/api")
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    for _ in range(settings.login_attempt_limit):
        assert client.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": "invalid"}, headers={"Origin": ORIGIN}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}, headers={"Origin": ORIGIN})
    assert response.status_code == 429
    with TestClient(create_app(settings, make_session_factory(settings.database_url))) as restarted:
        assert restarted.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}, headers={"Origin": ORIGIN}).status_code == 429


def test_database_rejects_cross_school_references(env):
    client, factory, settings, ids = env
    from sqlalchemy.exc import IntegrityError
    with factory() as db:
        db.add(StaffAssignment(school_id=ids["school"], learner_id=ids["foreign"], user_id=ids["teacher"], actions=["learner.read"], purpose="synthetic", valid_from=date.today()))
        with pytest.raises(IntegrityError):
            db.commit()
    with factory() as db:
        assert db.scalar(select(StaffAssignment).where(StaffAssignment.learner_id == ids["foreign"])) is None


def test_cookie_production_attributes(env):
    client, factory, settings, ids = env
    secure_settings = settings.model_copy(update={"cookie_secure": True})
    with TestClient(create_app(secure_settings, factory), base_url="https://testserver") as secure:
        response = secure.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}, headers={"Origin": ORIGIN})
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "path=/api" in cookie
