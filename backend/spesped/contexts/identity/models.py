from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from spesped.db import Base, UTCDateTime, utcnow


def new_id():
    return str(uuid4())


class Aggregate:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="active", nullable=False)

    @classmethod
    def __declare_last__(cls):
        cls.__mapper__.version_id_col = cls.__table__.c.version


class School(Aggregate, Base):
    __tablename__ = "identity_schools"
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    timezone: Mapped[str] = mapped_column(String(100), default="Europe/Oslo")


class UserAccount(Aggregate, Base):
    __tablename__ = "identity_users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(500))


class Dated:
    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_until: Mapped[date | None] = mapped_column(nullable=True)


class SchoolMembership(Aggregate, Dated, Base):
    __tablename__ = "identity_memberships"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    role: Mapped[str] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint("school_id", "user_id"), CheckConstraint("valid_until IS NULL OR valid_until >= valid_from"))


class Learner(Aggregate, Base):
    __tablename__ = "identity_learners"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    grade: Mapped[int] = mapped_column(Integer)
    group_name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("school_id", "id"), CheckConstraint("grade >= 1 AND grade <= 10"))


class Enrollment(Aggregate, Dated, Base):
    __tablename__ = "identity_enrollments"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), CheckConstraint("valid_until IS NULL OR valid_until >= valid_from"))


class StaffAssignment(Aggregate, Dated, Base):
    __tablename__ = "identity_staff_assignments"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    actions: Mapped[list[str]] = mapped_column(JSON)
    purpose: Mapped[str] = mapped_column(String(100))
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "user_id"], ["identity_memberships.school_id", "identity_memberships.user_id"]), CheckConstraint("valid_until IS NULL OR valid_until >= valid_from"))


class AuthorityGrant(Aggregate, Dated, Base):
    __tablename__ = "identity_authority_grants"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    learner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    granted_by: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "user_id"], ["identity_memberships.school_id", "identity_memberships.user_id"]), CheckConstraint("valid_until IS NULL OR valid_until >= valid_from"))


class GuardianRelationship(Aggregate, Dated, Base):
    __tablename__ = "identity_guardian_relationships"
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    guardian_user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    relationship: Mapped[str] = mapped_column(String(60))
    source_reference: Mapped[str] = mapped_column(String(200))
    parental_responsibility: Mapped[bool] = mapped_column(Boolean)
    information_rights: Mapped[str] = mapped_column(String(30))
    restrictions: Mapped[str] = mapped_column(String(1000), default="")
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "guardian_user_id"], ["identity_memberships.school_id", "identity_memberships.user_id"]), CheckConstraint("valid_until IS NULL OR valid_until >= valid_from"))


class LoginSession(Base):
    __tablename__ = "identity_login_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LoginThrottle(Base):
    __tablename__ = "identity_login_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    blocked_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AuditRecord(Base):
    __tablename__ = "identity_audit_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str | None] = mapped_column(ForeignKey("identity_schools.id"), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    outcome: Mapped[str] = mapped_column(String(30), default="success")


class IdentityEvent(Base):
    __tablename__ = "identity_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
