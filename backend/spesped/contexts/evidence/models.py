from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id


class SchoolRow:
    school_id: Mapped[str] = mapped_column(ForeignKey("identity_schools.id"), index=True)


class SourceItem(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_sources"
    external_scope: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(320))
    sender: Mapped[str] = mapped_column(String(320))
    document_type: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    original_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("school_id", "id"), UniqueConstraint("school_id", "external_scope", "external_id"), CheckConstraint("current_revision >= 1"))


class SourceRevision(SchoolRow, Base):
    __tablename__ = "evidence_source_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    sender: Mapped[str] = mapped_column(String(320))
    document_type: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    original_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(36))
    byte_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(["school_id", "source_id"], ["evidence_sources.school_id", "evidence_sources.id"]), UniqueConstraint("school_id", "source_id", "revision"), CheckConstraint("revision >= 1 AND byte_size > 0"))


class Inspection(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_inspections"
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    scan_state: Mapped[str] = mapped_column(String(40), default="pending")
    extraction_state: Mapped[str] = mapped_column(String(40), default="pending")
    issue: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pages: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]), UniqueConstraint("school_id", "source_id", "source_revision"))


class IntakeCommand(SchoolRow, Base):
    __tablename__ = "evidence_intake_commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_key: Mapped[str] = mapped_column(String(120))
    request_digest: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    __table_args__ = (ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]), UniqueConstraint("school_id", "request_key"))


class ExtractionProposal(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_proposals"
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    span_start: Mapped[int] = mapped_column(Integer)
    span_end: Mapped[int] = mapped_column(Integer)
    field_name: Mapped[str] = mapped_column(String(80))
    proposed_value: Mapped[str] = mapped_column(Text)
    reviewed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("identity_users.id"), nullable=True)
    generation_job_id: Mapped[str | None] = mapped_column(ForeignKey("platform_generation_jobs.id", name="fk_evidence_proposal_job"), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    __table_args__ = (ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]), UniqueConstraint("school_id", "id"), UniqueConstraint("school_id", "source_id", "source_revision", "page", "span_start", "span_end", "field_name"), CheckConstraint("page >= 1 AND span_start >= 0 AND span_end > span_start"), CheckConstraint("outcome IN ('pending','accepted','edited','rejected')"))


class EvidenceItem(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_items"
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    proposal_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "proposal_id"], ["evidence_proposals.school_id", "evidence_proposals.id"]), UniqueConstraint("school_id", "id"), UniqueConstraint("school_id", "proposal_id"))


class SourceSubjectLink(SchoolRow, Base):
    __tablename__ = "evidence_subject_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36))
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    source_digest: Mapped[str] = mapped_column(String(64))
    page: Mapped[int] = mapped_column(Integer)
    span_start: Mapped[int] = mapped_column(Integer)
    span_end: Mapped[int] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "evidence_id"], ["evidence_items.school_id", "evidence_items.id"]), ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]), UniqueConstraint("school_id", "id"), CheckConstraint("page >= 1 AND span_start >= 0 AND span_end > span_start"))


class EvidenceRevision(SchoolRow, Base):
    __tablename__ = "evidence_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    learner_id: Mapped[str] = mapped_column(String(36))
    link_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[str] = mapped_column(Text)
    field_name: Mapped[str] = mapped_column(String(80))
    topic: Mapped[str] = mapped_column(String(100))
    goal_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    claim_type: Mapped[str] = mapped_column(String(40))
    reporter: Mapped[str] = mapped_column(String(320))
    observer: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40))
    certainty: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    correction_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    __table_args__ = (ForeignKeyConstraint(["school_id", "evidence_id"], ["evidence_items.school_id", "evidence_items.id"]), ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "link_id"], ["evidence_subject_links.school_id", "evidence_subject_links.id"]), UniqueConstraint("school_id", "evidence_id", "revision"), CheckConstraint("revision >= 1 AND occurred_at <= recorded_at"), CheckConstraint("certainty IN ('confirmed','uncertain','disputed')"), CheckConstraint("claim_type IN ('report','observation','professional_judgement')"), CheckConstraint("source_type IN ('direct_observation','reported_information','imported_document')"), CheckConstraint("source_type != 'direct_observation' OR observer IS NOT NULL"))


class Derivative(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_derivatives"
    learner_id: Mapped[str] = mapped_column(String(36))
    evidence_id: Mapped[str] = mapped_column(String(36))
    evidence_revision: Mapped[int] = mapped_column(Integer)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    target_revision: Mapped[int] = mapped_column(Integer)
    __table_args__ = (ForeignKeyConstraint(["school_id", "learner_id"], ["identity_learners.school_id", "identity_learners.id"]), ForeignKeyConstraint(["school_id", "evidence_id", "evidence_revision"], ["evidence_revisions.school_id", "evidence_revisions.evidence_id", "evidence_revisions.revision"]), UniqueConstraint("school_id", "evidence_id", "evidence_revision", "target_type", "target_id", "target_revision"), CheckConstraint("state IN ('draft','shared','stale','shared_review_required')"))


class CorrectionImpact(SchoolRow, Base):
    __tablename__ = "evidence_correction_impacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(String(36))
    old_revision: Mapped[int] = mapped_column(Integer)
    new_revision: Mapped[int] = mapped_column(Integer)
    derivative_id: Mapped[str] = mapped_column(ForeignKey("evidence_derivatives.id"))
    disposition: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(["school_id", "evidence_id"], ["evidence_items.school_id", "evidence_items.id"]), UniqueConstraint("school_id", "derivative_id", "new_revision"))


class EvidenceEvent(SchoolRow, Base):
    __tablename__ = "evidence_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    # Metadata identifiers only. Consumer must reauthorize and retrieve controlled excerpts.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class StructuringApplication(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_structuring_applications"
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[str] = mapped_column(String(36))
    attempt_number: Mapped[int] = mapped_column(Integer)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]),
        ForeignKeyConstraint(["school_id", "job_id"], ["platform_generation_jobs.school_id", "platform_generation_jobs.id"]),
        UniqueConstraint("school_id", "job_id", "attempt_number"),
        CheckConstraint("attempt_number >= 1"),
    )


class ClarificationTask(Aggregate, SchoolRow, Base):
    __tablename__ = "evidence_clarification_tasks"
    source_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"))
    field_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(2000))
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("identity_users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(["school_id", "source_id", "source_revision"], ["evidence_source_revisions.school_id", "evidence_source_revisions.source_id", "evidence_source_revisions.revision"]),
        ForeignKeyConstraint(["school_id", "proposal_id"], ["evidence_proposals.school_id", "evidence_proposals.id"]),
        CheckConstraint("state IN ('open','resolved')"),
        CheckConstraint("(state = 'open' AND resolution IS NULL AND resolved_by IS NULL AND resolved_at IS NULL) OR (state = 'resolved' AND resolution IS NOT NULL AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)"),
        CheckConstraint("(page IS NULL AND span_start IS NULL AND span_end IS NULL) OR (page IS NOT NULL AND span_start IS NOT NULL AND span_end IS NOT NULL AND page >= 1 AND span_start >= 0 AND span_end > span_start)"),
    )


class ClarificationTransition(SchoolRow, Base):
    __tablename__ = 'evidence_clarification_transitions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('evidence_clarification_tasks.id'))
    task_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    assignee_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    action: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(String(2000))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint('task_id', 'task_version'),)
