"""Case-owned safeguarding records. No table is an ordinary evidence/timeline source."""
from datetime import date, datetime
from uuid import uuid4
from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow


def uid(): return str(uuid4())


class Row:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)


class CaseRecord(Row, Base):
    __tablename__ = 'safeguarding_cases'
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    about: Mapped[str] = mapped_column(String(30))
    excluded_user_ids: Mapped[list] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(30), default='received')
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']), CheckConstraint("kind IN ('environment','concern','physical')"))
    __mapper_args__ = {'version_id_col': version}


class CaseChild(Row):
    case_id: Mapped[str] = mapped_column(String(36), index=True)


class EnvironmentCase(CaseChild, Base):
    __tablename__ = 'safeguarding_environment_cases'
    received_concern: Mapped[str] = mapped_column(Text)
    received_from: Mapped[str] = mapped_column(String(1000))
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id'))


class ConcernReport(CaseChild, Base):
    __tablename__ = 'safeguarding_concern_reports'
    author_assessment: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(30))
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id'))


class PhysicalInterventionRecord(CaseChild, Base):
    __tablename__ = 'safeguarding_physical_records'
    place: Mapped[str] = mapped_column(String(1000))
    before_facts: Mapped[str] = mapped_column(Text)
    during_facts: Mapped[str] = mapped_column(Text)
    actual_action: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_unknown_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    involved_roles: Mapped[list] = mapped_column(JSON)
    observed_consequences: Mapped[str] = mapped_column(Text)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id'), CheckConstraint('duration_seconds >= 0'))


class AttributedAccount(CaseChild, Base):
    __tablename__ = 'safeguarding_accounts'
    kind: Mapped[str] = mapped_column(String(30))
    statement: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(2000))
    uncertainty: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    corrects_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class PupilPerspective(CaseChild, Base):
    __tablename__ = 'safeguarding_pupil_views'
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(2000))
    missing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    followup_due: Mapped[date | None] = mapped_column(nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class ActionPlan(CaseChild, Base):
    __tablename__ = 'safeguarding_action_plans'
    revision: Mapped[int] = mapped_column(Integer)
    problem_assessment: Mapped[str] = mapped_column(Text)
    evaluation_date: Mapped[date] = mapped_column()
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id','revision'), UniqueConstraint('school_id','case_id','id'))


class PlanMeasure(CaseChild, Base):
    __tablename__ = 'safeguarding_plan_measures'
    plan_id: Mapped[str] = mapped_column(String(36))
    measure: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    planned_date: Mapped[date] = mapped_column()
    evaluation_method: Mapped[str] = mapped_column(Text)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id','plan_id'],['safeguarding_action_plans.school_id','safeguarding_action_plans.case_id','safeguarding_action_plans.id']),)


class PerformedAction(CaseChild, Base):
    __tablename__ = 'safeguarding_performed_actions'
    description: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    outcome_state: Mapped[str] = mapped_column(String(30))
    measure_id: Mapped[str | None] = mapped_column(ForeignKey('safeguarding_plan_measures.id'), nullable=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class ConcernDraft(CaseChild, Base):
    __tablename__ = 'safeguarding_concern_drafts'
    revision: Mapped[int] = mapped_column(Integer)
    recipient: Mapped[str] = mapped_column(String(2000))
    purpose: Mapped[str] = mapped_column(String(2000))
    body: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id','revision'))


class ActualContact(CaseChild, Base):
    __tablename__ = 'safeguarding_actual_contacts'
    contact_kind: Mapped[str] = mapped_column(String(30))
    recipient: Mapped[str] = mapped_column(String(2000))
    channel: Mapped[str] = mapped_column(String(100))
    information_shared: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(30))
    receipt_state: Mapped[str] = mapped_column(String(30))
    receipt_detail: Mapped[str] = mapped_column(Text)
    route_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    route_deviation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey('safeguarding_concern_drafts.id'), nullable=True)
    draft_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class Followup(CaseChild, Base):
    __tablename__ = 'safeguarding_followups'
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    due_date: Mapped[date] = mapped_column()
    state: Mapped[str] = mapped_column(String(30), default='planned')
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class CaseReview(CaseChild, Base):
    __tablename__ = 'safeguarding_case_reviews'
    decision: Mapped[str] = mapped_column(String(30))
    assessment: Mapped[str] = mapped_column(Text)
    pupil_situation: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class ContactRoute(Row, Base):
    __tablename__ = 'safeguarding_contact_routes'
    purpose: Mapped[str] = mapped_column(String(30))
    about: Mapped[str] = mapped_column(String(30))
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recipient: Mapped[str] = mapped_column(String(2000))
    recipient_user_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    channel: Mapped[str] = mapped_column(String(100))
    contact_details: Mapped[str] = mapped_column(Text)
    guidance: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date] = mapped_column()
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('safeguarding_contact_routes.id'), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(30), default='unreviewed')
    digest: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (CheckConstraint('valid_until >= valid_from'),)
    __mapper_args__ = {'version_id_col': version}


class CaseSnapshot(CaseChild, Base):
    __tablename__ = 'safeguarding_case_snapshots'
    revision: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']), UniqueConstraint('school_id','case_id','revision'))


class CommandReceipt(Row, Base):
    __tablename__ = 'safeguarding_command_receipts'
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('school_id','actor_id','request_key'),)


class SafeguardingEvent(Row, Base):
    __tablename__ = 'safeguarding_outbox'
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    correlation_id: Mapped[str] = mapped_column(String(36), default=uid)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class RecordCorrection(CaseChild, Base):
    __tablename__ = 'safeguarding_record_corrections'
    prior_revision: Mapped[int] = mapped_column(Integer)
    correction_reason: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)


class ContactReconciliation(CaseChild, Base):
    __tablename__ = 'safeguarding_contact_reconciliations'
    contact_id: Mapped[str] = mapped_column(ForeignKey('safeguarding_actual_contacts.id'))
    outcome: Mapped[str] = mapped_column(String(30))
    receipt_state: Mapped[str] = mapped_column(String(30))
    receipt_detail: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','case_id'],['safeguarding_cases.school_id','safeguarding_cases.id']),)
