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


def test_explicit_delegation_bootstraps_case_grants_without_case_read_access(env):
    client, factory, settings, ids = env
    headers = login(client, "leader")
    base = f'/api/v1/schools/{ids["school"]}'
    case_id, other_case = str(uuid4()), str(uuid4())
    grant = {"user_id": ids["teacher"], "action": "case.read", "learner_id": ids["learner"], "case_id": case_id, "valid_from": date.today().isoformat()}
    response = client.post(base + "/authorities", json=grant, headers=headers)
    assert response.status_code == 201, response.text
    with factory() as db:
        # School-wide delegation enables issuance, never implicit content access.
        with pytest.raises(DomainError):
            require_authority(db, Actor(ids["leader"]), ids["school"], "case.read", ids["learner"], case_id)
        assert require_authority(db, Actor(ids["teacher"]), ids["school"], "case.read", ids["learner"], case_id)
        for learner_id, requested_case in ((ids["learner"], other_case), (ids["hidden"], case_id), (ids["learner"], None)):
            with pytest.raises(DomainError):
                require_authority(db, Actor(ids["teacher"]), ids["school"], "case.read", learner_id, requested_case)
    # A case-specific delegate can issue the initial content grant for that case
    # but cannot turn it into another case or a school-wide delegation.
    scoped = client.post(base + "/authorities", json={**grant, "user_id": ids["tech"], "action": "authority.delegate"}, headers=headers)
    assert scoped.status_code == 201
    tech_headers = login(client, "tech")
    assert client.post(base + "/authorities", json={**grant, "action": "case.update"}, headers=tech_headers).status_code == 201
    assert client.post(base + "/authorities", json={**grant, "case_id": other_case}, headers=tech_headers).status_code == 403
    assert client.post(base + "/authorities", json={**grant, "case_id": None}, headers=tech_headers).status_code == 403
    with factory() as db:
        with pytest.raises(DomainError):
            require_authority(db, Actor(ids["tech"]), ids["school"], "case.read", ids["learner"], case_id)


@pytest.mark.parametrize("record_kind,authority", [("assignments", "assignment.manage"), ("guardians", "guardian.manage")])
def test_scoped_manager_lists_shortens_and_revokes_only_own_pupil_scope(env, record_kind, authority):
    client, factory, settings, ids = env
    today = date.today()
    with factory.begin() as db:
        db.add_all([
            AuthorityGrant(school_id=ids["school"], user_id=ids["teacher"], action=authority, learner_id=ids["learner"], valid_from=today, granted_by=ids["leader"]),
            AuthorityGrant(school_id=ids["school"], user_id=ids["teacher"], action="learner.read", learner_id=ids["learner"], valid_from=today, granted_by=ids["leader"]),
        ])
    base = f'/api/v1/schools/{ids["school"]}'
    headers = login(client, "teacher")
    if record_kind == "assignments":
        values = {"user_id": ids["tech"], "actions": ["learner.read"], "purpose": "synthetic"}
    else:
        values = {"guardian_user_id": ids["guardian"], "relationship": "parent", "source_reference": "synthetic-source", "parental_responsibility": True, "information_rights": "confirmed"}
    values.update({"learner_id": ids["learner"], "valid_from": today.isoformat()})
    created = client.post(base + f"/{record_kind}", json=values, headers=headers)
    assert created.status_code == 201, created.text
    own_id = created.json()["id"]
    leader_headers = login(client, "leader")
    hidden = client.post(base + f"/{record_kind}", json={**values, "learner_id": ids["hidden"]}, headers=leader_headers)
    assert hidden.status_code == 201
    hidden_id = hidden.json()["id"]
    teacher_headers = login(client, "teacher")
    managed_path = base + f"/access/{record_kind}"
    listing = client.get(managed_path).json()
    assert listing["total"] >= 1 and all(item["learner_id"] == ids["learner"] for item in listing["items"])
    assert hidden_id not in {item["id"] for item in listing["items"]}
    page = client.get(managed_path + "?limit=1&offset=0").json()
    assert page["total"] == listing["total"] and len(page["items"]) == 1
    # Removing the manager's content authority cannot prevent reducing access.
    with factory.begin() as db:
        content = db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids["teacher"], AuthorityGrant.action == "learner.read"))
        content.state = "revoked"
    change = {"expected_version": 1, "state": "active", "valid_from": today.isoformat(), "valid_until": today.isoformat()}
    shortened = client.patch(managed_path + f"/{own_id}", json=change, headers=teacher_headers)
    assert shortened.status_code == 200 and shortened.json()["version"] == 2
    hidden_denial = client.patch(managed_path + f"/{hidden_id}", json=change, headers=teacher_headers)
    missing_denial = client.patch(managed_path + f"/{uuid4()}", json=change, headers=teacher_headers)
    assert hidden_denial.status_code == missing_denial.status_code == 403
    assert hidden_denial.json() == missing_denial.json()
    assert client.patch(managed_path + f"/{own_id}", json=change, headers=teacher_headers).status_code == 409
    revoked = client.patch(managed_path + f"/{own_id}", json={**change, "expected_version": 2, "state": "revoked"}, headers=teacher_headers)
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    if record_kind == "assignments":
        # Reopening this assignment would increase access and still requires
        # content/delegation authority, which was revoked above.
        assert client.patch(managed_path + f"/{own_id}", json={**change, "expected_version": 3}, headers=teacher_headers).status_code == 403
    with factory() as db:
        model = StaffAssignment if record_kind == "assignments" else GuardianRelationship
        assert db.get(model, hidden_id).version == 1 and db.get(model, hidden_id).state == "active"


@pytest.mark.parametrize("bound", ["membership", "content", "delegation"])
def test_delegation_uses_intersection_of_membership_and_authority_periods(env, bound):
    client, factory, settings, ids = env
    today = date.today()
    tomorrow = today + timedelta(days=1)
    with factory.begin() as db:
        membership = db.scalar(select(SchoolMembership).where(SchoolMembership.user_id == ids["tech"]))
        membership.valid_until = today if bound == "membership" else tomorrow
        db.add(AuthorityGrant(school_id=ids["school"], user_id=ids["tech"], action="authority.delegate" if bound == "delegation" else "learner.read", learner_id=ids["hidden"], valid_from=today, valid_until=today if bound != "membership" else None, granted_by=ids["leader"]))
    headers = login(client, "tech")
    base = f'/api/v1/schools/{ids["school"]}'
    values = {"user_id": ids["teacher"], "action": "learner.read", "learner_id": ids["hidden"], "valid_from": tomorrow.isoformat(), "valid_until": None}
    assert client.post(base + "/authorities", json=values, headers=headers).status_code == 403
    assert client.post(base + "/authorities", json={**values, "valid_from": today.isoformat(), "valid_until": tomorrow.isoformat()}, headers=headers).status_code == 403
    # Both lower and upper bounds apply, and an inclusive matching end is valid.
    assert client.post(base + "/authorities", json={**values, "valid_from": (today - timedelta(days=1)).isoformat(), "valid_until": today.isoformat()}, headers=headers).status_code == 403
    allowed = client.post(base + "/authorities", json={**values, "valid_from": today.isoformat(), "valid_until": today.isoformat()}, headers=headers)
    assert allowed.status_code == 201, allowed.text
    assignment = {"user_id": ids["teacher"], "learner_id": ids["hidden"], "actions": ["learner.read"], "purpose": "synthetic", "valid_from": tomorrow.isoformat()}
    assert client.post(base + "/assignments", json=assignment, headers=headers).status_code == 403


def test_concurrent_first_postgres_login_failures_are_claimed_before_password_checks(env, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from sqlalchemy import event
    import hashlib
    import spesped.contexts.identity.router as router_module
    from spesped.contexts.identity.models import LoginThrottle

    client, factory, settings, ids = env
    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency is verified on PostgreSQL")
    attempts = 6
    barrier = Barrier(attempts)
    lock = Lock()
    verified = 0
    real_verify = router_module.verify_password

    def before_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO identity_login_throttles"):
            barrier.wait(timeout=15)

    def counted_verify(password, encoded):
        nonlocal verified
        with lock:
            verified += 1
        return real_verify(password, encoded)

    event.listen(engine, "before_cursor_execute", before_insert)
    monkeypatch.setattr(router_module, "verify_password", counted_verify)
    app = create_app(settings.model_copy(update={"login_attempt_limit": 3}), factory)

    def attempt(_):
        with TestClient(app, raise_server_exceptions=False) as separate:
            return separate.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": "synthetic-wrong-password"}, headers={"Origin": ORIGIN}).status_code

    try:
        with ThreadPoolExecutor(max_workers=attempts) as executor:
            statuses = list(executor.map(attempt, range(attempts)))
    finally:
        event.remove(engine, "before_cursor_execute", before_insert)
    assert sorted(statuses) == [401, 401, 401, 429, 429, 429]
    assert verified == 3
    with factory() as db:
        row = db.get(LoginThrottle, hashlib.sha256(b"teacher@example.invalid").hexdigest())
        assert row.failures == 3 and row.blocked_until > utcnow()
    with TestClient(app) as separate:
        followup = separate.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}, headers={"Origin": ORIGIN})
        assert followup.status_code == 429
    assert verified == 3


@pytest.mark.parametrize("competing_password", ["synthetic-wrong-password", PASSWORD])
def test_postgres_success_resets_stable_throttle_during_competing_login(env, competing_password):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock
    from sqlalchemy import event, func
    import hashlib
    from spesped.contexts.identity.models import LoginThrottle

    client, factory, settings, ids = env
    engine = factory.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Successful-login claim interleaving is verified on PostgreSQL")
    initial = client.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": "synthetic-wrong-password"}, headers={"Origin": ORIGIN})
    assert initial.status_code == 401
    key = hashlib.sha256(b"teacher@example.invalid").hexdigest()
    with factory() as db:
        original = db.get(LoginThrottle, key)
        assert original.failures == 1
        original_window = original.window_started_at

    claimed, resume = Event(), Event()
    lock = Lock()
    intercepted = False

    def after_insert(connection, cursor, statement, parameters, context, executemany):
        nonlocal intercepted
        if statement.startswith("INSERT INTO identity_login_throttles"):
            with lock:
                pause = not intercepted
                intercepted = True
            if pause:
                claimed.set()
                assert resume.wait(timeout=10), "The successful login did not complete"

    app = create_app(settings, factory)

    def attempt(password):
        with TestClient(app, raise_server_exceptions=False) as separate:
            return separate.post("/api/v1/auth/login", json={"email": "teacher@example.invalid", "password": password}, headers={"Origin": ORIGIN})

    event.listen(engine, "after_cursor_execute", after_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Pause A exactly after its existing-key upsert and before its lock.
            # B must commit a successful login while A is in that precise gap.
            competing = executor.submit(attempt, competing_password)
            assert claimed.wait(timeout=5), "The competing login did not claim its key"
            successful = executor.submit(attempt, PASSWORD)
            try:
                success_response = successful.result(timeout=5)
                assert success_response.status_code == 200
                with factory() as db:
                    reset = db.get(LoginThrottle, key)
                    assert reset is not None
                    assert reset.failures == 0 and reset.blocked_until is None
                    assert reset.window_started_at >= original_window
            finally:
                resume.set()
            competing_response = competing.result(timeout=5)
    finally:
        resume.set()
        event.remove(engine, "after_cursor_execute", after_insert)

    correct_competitor = competing_password == PASSWORD
    assert competing_response.status_code == (200 if correct_competitor else 401)
    with factory() as db:
        row = db.get(LoginThrottle, key)
        assert row is not None and row.failures == (0 if correct_competitor else 1)
        assert row.blocked_until is None
        assert db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id == ids["teacher"])) == (2 if correct_competitor else 1)
    # Each successful response carries a distinct real session that remains usable.
    tokens = [success_response.cookies[settings.cookie_name]]
    if correct_competitor:
        tokens.append(competing_response.cookies[settings.cookie_name])
        assert len(set(tokens)) == 2
    with TestClient(app) as separate:
        for token in tokens:
            separate.cookies.clear()
            separate.cookies.set(settings.cookie_name, token, path="/api")
            assert separate.get("/api/v1/auth/me").status_code == 200
