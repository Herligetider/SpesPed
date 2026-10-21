from dataclasses import dataclass
from datetime import date
import hashlib
import hmac
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from spesped.db import get_db, utcnow
from spesped.errors import DomainError, access_denied
from spesped.contexts.identity.models import AuthorityGrant, Learner, LoginSession, School, SchoolMembership, StaffAssignment, UserAccount

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
# Constant expensive check for unknown accounts to reduce account discovery by timing.
_dummy_password_hash = password_hasher.hash("not-a-login-credential")


@dataclass(frozen=True)
class Actor:
    user_id: str


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Passwords must contain 12–1024 characters")
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        return password_hasher.verify(encoded or _dummy_password_hash, password) and encoded is not None
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(raw_session: str, secret: str) -> str:
    return hmac.new(secret.encode(), ("csrf:" + raw_session).encode(), hashlib.sha256).hexdigest()


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    settings = request.app.state.settings
    raw = request.cookies.get(settings.cookie_name)
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(raw))) if raw else None
    now = utcnow()
    if not session or session.revoked_at is not None or session.expires_at <= now:
        raise DomainError("authentication_required", "Sign in to continue.", 401)
    user = db.get(UserAccount, session.user_id)
    if user is None or user.state != "active":
        raise DomainError("authentication_required", "Sign in to continue.", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied, csrf_token(raw, settings.secret_key)):
            raise DomainError("csrf_failed", "Refresh the page before retrying this change.", 403)
    request.state.login_session = session
    request.state.actor = Actor(user_id=user.id)
    return request.state.actor


def require_origin(request: Request):
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise DomainError("origin_denied", "This request origin is not allowed.", 403)


def school_today(school: School) -> date:
    return utcnow().astimezone(ZoneInfo(school.timezone)).date()


def active_at(model, today):
    return (model.state == "active", model.valid_from <= today, or_(model.valid_until.is_(None), model.valid_until >= today))


def require_school_access(db: Session, actor: Actor, school_id: str) -> SchoolMembership:
    user = db.get(UserAccount, actor.user_id)
    school = db.get(School, school_id)
    if user is None or user.state != "active" or school is None or school.state != "active":
        raise access_denied()
    membership = db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id, SchoolMembership.user_id == actor.user_id, *active_at(SchoolMembership, school_today(school))))
    if membership is None:
        raise access_denied()
    return membership


def require_authority(db: Session, actor: Actor, school_id: str, action: str, learner_id: str | None = None, case_id: str | None = None) -> AuthorityGrant:
    require_school_access(db, actor, school_id)
    today = school_today(db.get(School, school_id))
    # A case grant can never imply access to another case or the general learner dossier.
    conditions = [AuthorityGrant.school_id == school_id, AuthorityGrant.user_id == actor.user_id, AuthorityGrant.action == action, *active_at(AuthorityGrant, today)]
    conditions.append(or_(AuthorityGrant.learner_id.is_(None), AuthorityGrant.learner_id == learner_id) if learner_id else AuthorityGrant.learner_id.is_(None))
    conditions.append(AuthorityGrant.case_id == case_id if case_id else AuthorityGrant.case_id.is_(None))
    grant = db.scalar(select(AuthorityGrant).where(*conditions))
    if grant is None:
        raise access_denied()
    return grant


def require_learner_access(db: Session, actor: Actor, school_id: str, learner_id: str, action: str = "read") -> Learner:
    membership = require_school_access(db, actor, school_id)
    if membership.role == "guardian":
        raise access_denied()
    learner = db.scalar(select(Learner).where(Learner.id == learner_id, Learner.school_id == school_id, Learner.state == "active"))
    if learner is None:
        raise access_denied()
    today = school_today(db.get(School, school_id))
    # Multiple dated assignments are allowed; do not trust role names or guardian relationships.
    assignments = db.scalars(select(StaffAssignment).where(StaffAssignment.school_id == school_id, StaffAssignment.learner_id == learner_id, StaffAssignment.user_id == actor.user_id, *active_at(StaffAssignment, today))).all()
    requested = action if "." in action else f"learner.{action}"
    if any(requested in a.actions for a in assignments):
        return learner
    require_authority(db, actor, school_id, requested, learner_id=learner_id)
    return learner


def require_delegation(db, actor, school_id, action, valid_from, valid_until, learner_id=None, case_id=None):
    """Delegate only within the actor's effective membership and authority.

    Explicit delegation may cover a school, pupil or case, including the first
    case grant. This is a delegation-only rule: require_authority still demands
    an exact case grant before reading or acting on protected case content.
    """
    membership = require_school_access(db, actor, school_id)
    if not period_contains(membership, valid_from, valid_until):
        raise access_denied()
    today = school_today(db.get(School, school_id))
    query = select(AuthorityGrant).where(
        AuthorityGrant.school_id == school_id,
        AuthorityGrant.user_id == actor.user_id,
        AuthorityGrant.action == "authority.delegate",
        *active_at(AuthorityGrant, today),
        or_(AuthorityGrant.learner_id.is_(None), AuthorityGrant.learner_id == learner_id) if learner_id else AuthorityGrant.learner_id.is_(None),
        or_(AuthorityGrant.case_id.is_(None), AuthorityGrant.case_id == case_id) if case_id else AuthorityGrant.case_id.is_(None),
    )
    for grant in db.scalars(query):
        if period_contains(grant, valid_from, valid_until):
            return grant
    # Managers without delegation permission may only delegate an exact content
    # authority they currently hold; a case grant never becomes school-wide.
    grant = require_authority(db, actor, school_id, action, learner_id, case_id)
    if not period_contains(grant, valid_from, valid_until):
        raise access_denied()
    return grant


def period_contains(record, valid_from, valid_until):
    return valid_from >= record.valid_from and (
        record.valid_until is None or
        (valid_until is not None and valid_until <= record.valid_until)
    )
