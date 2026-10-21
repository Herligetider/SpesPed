from datetime import timedelta
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from spesped.audit import record_audit
from spesped.auth import Actor, active_at, csrf_token, get_actor, hash_token, password_hasher, period_contains, require_authority, require_delegation, require_learner_access, require_origin, require_school_access, school_today, verify_password
from spesped.db import get_db, utcnow
from spesped.errors import DomainError, access_denied
from .models import AuthorityGrant, Enrollment, GuardianRelationship, IdentityEvent, Learner, LoginSession, LoginThrottle, School, SchoolMembership, StaffAssignment, UserAccount
from .schemas import AssignmentInput, AuthorityInput, DatedUpdate, GuardianInput, LearnerCreate, LearnerPatch, Login, MembershipInput

router = APIRouter(prefix="/api/v1", tags=["identity"])


def school_views(db, actor):
    memberships = db.scalars(select(SchoolMembership).where(SchoolMembership.user_id == actor.user_id, SchoolMembership.state == "active")).all()
    result = []
    for membership in memberships:
        school = db.get(School, membership.school_id)
        today = school_today(school)
        if school.state == "active" and membership.valid_from <= today and (membership.valid_until is None or today <= membership.valid_until):
            result.append({"id": school.id, "name": school.name, "kind": school.kind, "timezone": school.timezone, "role": membership.role})
    return sorted(result, key=lambda item: item["id"])


def me_view(db, actor, request, raw):
    user = db.get(UserAccount, actor.user_id)
    return {"user": {"id": user.id, "email": user.email, "display_name": user.display_name}, "csrf_token": csrf_token(raw, request.app.state.settings.secret_key), "schools": school_views(db, actor)}


def claim_login_throttle(db, key, now):
    """Create the first key atomically, then serialize account checks on its row.

    PostgreSQL's conflicting upsert waits for the current owner before the row
    lock is acquired. SQLite serializes the corresponding writer transaction.
    No expensive password check occurs before this durable key is claimed.
    """
    insert = postgres_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(LoginThrottle).values(
        key=key, failures=0, window_started_at=now, blocked_until=None,
    ).on_conflict_do_nothing(index_elements=[LoginThrottle.key]))
    return db.scalar(select(LoginThrottle).where(LoginThrottle.key == key).with_for_update())


@router.post("/auth/login")
def login(data: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    require_origin(request)
    settings = request.app.state.settings
    email = data.email.strip().lower()
    now = utcnow()
    throttle_key = hashlib.sha256(email.encode()).hexdigest()
    throttle = claim_login_throttle(db, throttle_key, now)
    now = utcnow()  # Lock contention must not extend an expired block by using an old clock.
    if throttle.blocked_until and throttle.blocked_until > now:
        raise DomainError("login_throttled", "Please wait before trying to sign in again.", 429)
    user = db.scalar(select(UserAccount).where(UserAccount.email == email))
    valid = verify_password(data.password, user.password_hash if user else None)
    if not valid or not user or user.state != "active":
        if now - throttle.window_started_at > timedelta(minutes=settings.login_lock_minutes):
            throttle.failures = 0
            throttle.window_started_at = now
        throttle.failures += 1
        if throttle.failures >= settings.login_attempt_limit:
            throttle.blocked_until = now + timedelta(minutes=settings.login_lock_minutes)
        db.commit()
        raise DomainError("invalid_credentials", "The email or password is incorrect.", 401)
    # Keep the key stable: a concurrent request may have completed its no-op
    # upsert and still be waiting to SELECT this row FOR UPDATE. Deleting it
    # here would make that request lose its claim; reset under our lock instead.
    throttle.failures = 0
    throttle.window_started_at = now
    throttle.blocked_until = None
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(data.password)
    # Re-authentication rotates and invalidates the current browser session.
    old_token = request.cookies.get(settings.cookie_name)
    if old_token:
        old = db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(old_token)))
        if old and old.revoked_at is None:
            old.revoked_at = now
    raw = secrets.token_urlsafe(48)
    session = LoginSession(user_id=user.id, token_hash=hash_token(raw), expires_at=now + timedelta(hours=settings.session_hours))
    db.add(session)
    actor = Actor(user.id)
    db.flush()
    record_audit(db, actor, None, "session.login", "session", session.id)
    result = me_view(db, actor, request, raw)
    db.commit()
    response.set_cookie(settings.cookie_name, raw, max_age=settings.session_hours * 3600, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/api")
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/auth/me")
def me(request: Request, response: Response, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return me_view(db, actor, request, request.cookies[request.app.state.settings.cookie_name])


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    session = request.state.login_session
    session.revoked_at = utcnow()
    record_audit(db, actor, None, "session.logout", "session", session.id)
    db.commit()
    response.delete_cookie(request.app.state.settings.cookie_name, path="/api", httponly=True, secure=request.app.state.settings.cookie_secure, samesite="lax")


@router.get("/schools")
def schools(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    items = school_views(db, actor)
    return {"items": items[offset:offset + limit], "total": len(items)}


def learner_view(learner):
    return {"id": learner.id, "display_name": learner.display_name, "grade": learner.grade, "group_name": learner.group_name, "version": learner.version}


@router.get("/schools/{school_id}/learners")
def learners(school_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    membership = require_school_access(db, actor, sid)
    if membership.role == "guardian":
        return {"items": [], "total": 0}
    # Filter before pagination and counting; inaccessible pupils do not affect total.
    today = school_today(db.get(School, sid))
    try:
        require_authority(db, actor, sid, "learner.read")
        global_read = True
    except DomainError:
        global_read = False
    allowed_ids = set()
    if not global_read:
        assignments = db.scalars(select(StaffAssignment).where(StaffAssignment.school_id == sid, StaffAssignment.user_id == actor.user_id, *active_at(StaffAssignment, today))).all()
        allowed_ids.update(a.learner_id for a in assignments if "learner.read" in a.actions)
        grants = db.scalars(select(AuthorityGrant).where(AuthorityGrant.school_id == sid, AuthorityGrant.user_id == actor.user_id, AuthorityGrant.action == "learner.read", AuthorityGrant.case_id.is_(None), *active_at(AuthorityGrant, today))).all()
        allowed_ids.update(g.learner_id for g in grants if g.learner_id)
    query = select(Learner).where(Learner.school_id == sid, Learner.state == "active")
    if not global_read:
        query = query.where(Learner.id.in_(allowed_ids))
    # COUNT uses the same access-filtered query as the page.
    from sqlalchemy import func
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Learner.id).offset(offset).limit(limit)).all()
    return {"items": [learner_view(row) for row in rows], "total": total}


def changed(db, actor, school_id, action, entity):
    db.flush()
    record_audit(db, actor, school_id, action, entity.__tablename__, entity.id)
    db.add(IdentityEvent(school_id=school_id, aggregate_id=entity.id, event_type=action, aggregate_version=entity.version))


@router.post("/schools/{school_id}/learners", status_code=201)
def create_learner(school_id: UUID, data: LearnerCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, "learner.create")
    learner = Learner(school_id=sid, **data.model_dump())
    db.add(learner)
    db.flush()
    db.add(Enrollment(school_id=sid, learner_id=learner.id, valid_from=school_today(db.get(School, sid))))
    changed(db, actor, sid, "learner.created", learner)
    result = learner_view(learner)
    db.commit()
    return result


@router.get("/schools/{school_id}/learners/{learner_id}")
def get_learner(school_id: UUID, learner_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    learner = require_learner_access(db, actor, str(school_id), str(learner_id))
    return learner_view(learner)


@router.patch("/schools/{school_id}/learners/{learner_id}")
def update_learner(school_id: UUID, learner_id: UUID, data: LearnerPatch, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    learner = require_learner_access(db, actor, sid, str(learner_id), "update")
    if learner.version != data.expected_version:
        raise DomainError("version_conflict", "This record changed. Reload and try again.", 409)
    for key, value in data.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(learner, key, value)
    changed(db, actor, sid, "learner.updated", learner)
    result = learner_view(learner)
    db.commit()
    return result


def check_subject(db, school_id, user_id, learner_id=None):
    # Subjects can have future-dated memberships, but must belong to this school.
    membership = db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id, SchoolMembership.user_id == user_id, SchoolMembership.state == "active"))
    if membership is None:
        raise access_denied()
    if learner_id and db.scalar(select(Learner).where(Learner.id == learner_id, Learner.school_id == school_id, Learner.state == "active")) is None:
        raise access_denied()
    return membership


def dated_view(entity):
    private = {"created_at", "updated_at"}
    return {c.name: getattr(entity, c.name) for c in entity.__table__.columns if c.name not in private}


@router.post("/schools/{school_id}/memberships", status_code=201)
def add_membership(school_id: UUID, data: MembershipInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, "membership.manage")
    user = db.get(UserAccount, str(data.user_id))
    if user is None or user.state != "active":
        raise access_denied()
    row = SchoolMembership(school_id=sid, **data.model_dump(mode="json"))
    row.valid_from, row.valid_until = data.valid_from, data.valid_until
    db.add(row)
    changed(db, actor, sid, "membership.created", row)
    result = dated_view(row)
    db.commit()
    return result


@router.post("/schools/{school_id}/assignments", status_code=201)
def add_assignment(school_id: UUID, data: AssignmentInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, "assignment.manage", learner_id=str(data.learner_id))
    membership = check_subject(db, sid, str(data.user_id), str(data.learner_id))
    if membership.role == "guardian":
        raise access_denied()
    if membership.role == "assistant" and any(action not in {"brief.read", "observation.create"} for action in data.actions):
        raise access_denied()
    for action in data.actions:
        require_delegation(db, actor, sid, action, data.valid_from, data.valid_until, str(data.learner_id))
    row = StaffAssignment(school_id=sid, **{**data.model_dump(), "user_id": str(data.user_id), "learner_id": str(data.learner_id)})
    db.add(row)
    changed(db, actor, sid, "assignment.created", row)
    result = dated_view(row)
    db.commit()
    return result


@router.post("/schools/{school_id}/authorities", status_code=201)
def add_authority(school_id: UUID, data: AuthorityInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    # Only a school-wide delegation administrator may create authority grants.
    require_authority(db, actor, sid, "authority.manage")
    membership = check_subject(db, sid, str(data.user_id), str(data.learner_id) if data.learner_id else None)
    if membership.role == "guardian" and not data.action.startswith("package."):
        raise access_denied()
    if membership.role == "assistant" and data.action not in {"brief.read", "observation.create"}:
        raise access_denied()
    require_delegation(db, actor, sid, data.action, data.valid_from, data.valid_until, str(data.learner_id) if data.learner_id else None, str(data.case_id) if data.case_id else None)
    values = data.model_dump()
    for key in ("user_id", "learner_id", "case_id"):
        values[key] = str(values[key]) if values[key] else None
    row = AuthorityGrant(school_id=sid, granted_by=actor.user_id, **values)
    db.add(row)
    changed(db, actor, sid, "authority.created", row)
    result = dated_view(row)
    db.commit()
    return result


@router.post("/schools/{school_id}/guardians", status_code=201)
def add_guardian(school_id: UUID, data: GuardianInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    require_authority(db, actor, sid, "guardian.manage", learner_id=str(data.learner_id))
    check_subject(db, sid, str(data.guardian_user_id), str(data.learner_id))
    row = GuardianRelationship(school_id=sid, **{**data.model_dump(), "learner_id": str(data.learner_id), "guardian_user_id": str(data.guardian_user_id)})
    db.add(row)
    changed(db, actor, sid, "guardian.created", row)
    result = dated_view(row)
    db.commit()
    return result


# Explicit dated commands share a shape: versions and validity are checked together.
MANAGED = {"memberships": (SchoolMembership, "membership.manage"), "assignments": (StaffAssignment, "assignment.manage"), "authorities": (AuthorityGrant, "authority.manage"), "guardians": (GuardianRelationship, "guardian.manage")}


def managed_query(db, actor, school_id, model, authority):
    """Filter records by current management scope before lookup/count/pagination."""
    require_school_access(db, actor, school_id)
    query = select(model).where(model.school_id == school_id)
    try:
        require_authority(db, actor, school_id, authority)
        return query
    except DomainError:
        # Membership and authority administration deliberately require school-wide
        # powers. Assignment and guardian management support individual pupils.
        if model not in {StaffAssignment, GuardianRelationship}:
            raise access_denied()
    today = school_today(db.get(School, school_id))
    learner_ids = select(AuthorityGrant.learner_id).where(
        AuthorityGrant.school_id == school_id,
        AuthorityGrant.user_id == actor.user_id,
        AuthorityGrant.action == authority,
        AuthorityGrant.learner_id.is_not(None),
        AuthorityGrant.case_id.is_(None),
        *active_at(AuthorityGrant, today),
    )
    if db.scalar(learner_ids.limit(1)) is None:
        raise access_denied()
    return query.where(model.learner_id.in_(learner_ids))


@router.get("/schools/{school_id}/access/{record_kind}")
def list_access(school_id: UUID, record_kind: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    if record_kind not in MANAGED:
        raise access_denied()
    model, authority = MANAGED[record_kind]
    query = managed_query(db, actor, sid, model, authority)
    from sqlalchemy import func
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(model.id).offset(offset).limit(limit)).all()
    return {"items": [dated_view(row) for row in rows], "total": total}


@router.patch("/schools/{school_id}/access/{record_kind}/{record_id}")
def change_access(school_id: UUID, record_kind: str, record_id: UUID, data: DatedUpdate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    sid = str(school_id)
    if record_kind not in MANAGED:
        raise access_denied()
    model, authority = MANAGED[record_kind]
    # The access-filtered lookup gives identical denials for hidden/missing rows.
    row = db.scalar(managed_query(db, actor, sid, model, authority).where(model.id == str(record_id)))
    if row is None:
        raise access_denied()
    require_authority(db, actor, sid, authority, learner_id=row.learner_id if model in {StaffAssignment, GuardianRelationship} else None)
    if row.version != data.expected_version:
        raise DomainError("version_conflict", "This record changed. Reload and try again.", 409)
    expands_access = data.state == "active" and (row.state != "active" or not period_contains(row, data.valid_from, data.valid_until))
    if expands_access:
        if isinstance(row, StaffAssignment):
            for action in row.actions:
                require_delegation(db, actor, sid, action, data.valid_from, data.valid_until, row.learner_id)
        elif isinstance(row, AuthorityGrant):
            require_delegation(db, actor, sid, row.action, data.valid_from, data.valid_until, row.learner_id, row.case_id)
    row.valid_from, row.valid_until, row.state = data.valid_from, data.valid_until, data.state
    changed(db, actor, sid, f"{record_kind}.changed", row)
    result = dated_view(row)
    db.commit()
    return result
