from datetime import datetime
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id


class ProcessingPolicy(Aggregate, Base):
    __tablename__ = 'platform_processing_policies'
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    provider_key: Mapped[str] = mapped_column(String(80))
    configuration: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('school_id', 'id'),)


class ModelRelease(Aggregate, Base):
    __tablename__ = 'platform_model_releases'
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    provider_key: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(160))
    capability: Mapped[str] = mapped_column(String(30))
    template_version: Mapped[str] = mapped_column(String(80))
    output_schema_version: Mapped[str] = mapped_column(String(80))
    provider_digest: Mapped[str] = mapped_column(String(64))
    configuration_digest: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_evaluation_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id', 'id'),)


class ModelEvaluation(Base):
    __tablename__ = 'platform_model_evaluations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    release_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    release_digest: Mapped[str] = mapped_column(String(64))
    suite_name: Mapped[str] = mapped_column(String(100))
    suite_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30))
    metrics: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    artifact_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id', 'release_id'], ['platform_model_releases.school_id', 'platform_model_releases.id']),)


class GenerationJob(Aggregate, Base):
    __tablename__ = 'platform_generation_jobs'
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    learner_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    purpose: Mapped[str] = mapped_column(String(50))
    policy_id: Mapped[str] = mapped_column(String(36))
    policy_version: Mapped[int] = mapped_column(Integer)
    release_id: Mapped[str] = mapped_column(String(36))
    release_digest: Mapped[str] = mapped_column(String(64))
    logical_request_key: Mapped[str] = mapped_column(String(120))
    request_digest: Mapped[str] = mapped_column(String(64))
    source_manifest: Mapped[list] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (
        UniqueConstraint('school_id', 'id'),
        UniqueConstraint('school_id', 'actor_id', 'logical_request_key'),
        ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        ForeignKeyConstraint(['school_id', 'policy_id'], ['platform_processing_policies.school_id', 'platform_processing_policies.id']),
        ForeignKeyConstraint(['school_id', 'release_id'], ['platform_model_releases.school_id', 'platform_model_releases.id']),
        CheckConstraint("state IN ('queued','running','succeeded','failed','unavailable','cancelled')"),
    )


class GenerationAttempt(Base):
    __tablename__ = 'platform_generation_attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    job_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unsupported_source_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('job_id', 'number'), ForeignKeyConstraint(['school_id', 'job_id'], ['platform_generation_jobs.school_id', 'platform_generation_jobs.id']),)


class PlatformEvent(Base):
    __tablename__ = 'platform_outbox'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
