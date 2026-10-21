"""Context-owned aggregates; rule/profile content and evidence are append-only."""
from datetime import date, datetime
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, JSON, UniqueConstraint, CheckConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id

class Tenant:
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)

class LegalImportCandidate(Tenant, Base):
    __tablename__ = 'governance_legal_candidates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    registry_code: Mapped[str] = mapped_column(String(100))
    registry_checked: Mapped[date] = mapped_column()
    raw_source: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(30), default='unreviewed')
    __table_args__ = (UniqueConstraint('school_id', 'registry_code'), UniqueConstraint('school_id', 'id'))

class RequirementDefinition(Aggregate, Tenant, Base):
    __tablename__ = 'governance_requirements'
    code: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(30))
    source_reference: Mapped[str] = mapped_column(String(2000))
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (UniqueConstraint('school_id', 'code'), UniqueConstraint('school_id', 'id'), ForeignKeyConstraint(['school_id','candidate_id'], ['governance_legal_candidates.school_id','governance_legal_candidates.id']))

class RequirementVersion(Aggregate, Tenant, Base):
    __tablename__ = 'governance_requirement_versions'
    requirement_id: Mapped[str] = mapped_column(String(36))
    revision_number: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date | None] = mapped_column(nullable=True)
    conditions: Mapped[list] = mapped_column(JSON)
    trigger_type: Mapped[str] = mapped_column(String(100))
    deadline_rule: Mapped[dict] = mapped_column(JSON)
    required_action: Mapped[str] = mapped_column(String(2000))
    required_document_types: Mapped[list] = mapped_column(JSON)
    accountable_role: Mapped[str] = mapped_column(String(100))
    interpretation_notes: Mapped[str] = mapped_column(String(2000))
    content_digest: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    withdrawn_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    withdrawal_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), UniqueConstraint('requirement_id','revision_number'), ForeignKeyConstraint(['school_id','requirement_id'], ['governance_requirements.school_id','governance_requirements.id']), CheckConstraint('valid_until IS NULL OR valid_until >= valid_from'))

class SchoolRuleProfile(Aggregate, Tenant, Base):
    __tablename__ = 'governance_school_rule_profiles'
    label: Mapped[str] = mapped_column(String(200))
    requirement_version_ids: Mapped[list] = mapped_column(JSON)
    school_inputs: Mapped[dict] = mapped_column(JSON)
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date | None] = mapped_column(nullable=True)
    supersedes_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    approval_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    impact_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revocation_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','supersedes_profile_id'], ['governance_school_rule_profiles.school_id','governance_school_rule_profiles.id']), CheckConstraint('valid_until IS NULL OR valid_until >= valid_from'))

class TriggerReceipt(Tenant, Base):
    __tablename__ = 'governance_trigger_receipts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_key: Mapped[str] = mapped_column(String(200))
    request_digest: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint('school_id','id'), UniqueConstraint('school_id','event_key'), ForeignKeyConstraint(['school_id','profile_id'], ['governance_school_rule_profiles.school_id','governance_school_rule_profiles.id']))

class ObligationInstance(Aggregate, Tenant, Base):
    __tablename__ = 'governance_obligations'
    requirement_version_id: Mapped[str] = mapped_column(String(36))
    receipt_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    period_key: Mapped[str] = mapped_column(String(100))
    applicability: Mapped[str] = mapped_column(String(30))
    evaluated_inputs: Mapped[dict] = mapped_column(JSON)
    applicability_reasons: Mapped[list] = mapped_column(JSON)
    unresolved_inputs: Mapped[list] = mapped_column(JSON)
    timing_inputs: Mapped[dict] = mapped_column(JSON)
    deadline_kind: Mapped[str] = mapped_column(String(30))
    deadline_date: Mapped[date | None] = mapped_column(nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deadline_reasons: Mapped[list] = mapped_column(JSON)
    timezone: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    internal_planned_date: Mapped[date | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    review_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), UniqueConstraint('receipt_id','requirement_version_id'), ForeignKeyConstraint(['school_id','requirement_version_id'], ['governance_requirement_versions.school_id','governance_requirement_versions.id']), ForeignKeyConstraint(['school_id','receipt_id'], ['governance_trigger_receipts.school_id','governance_trigger_receipts.id']), ForeignKeyConstraint(['school_id','learner_id'], ['identity_learners.school_id','identity_learners.id']), ForeignKeyConstraint(['school_id','owner_id'], ['identity_memberships.school_id','identity_memberships.user_id']))

class ApplicabilityDecision(Tenant, Base):
    __tablename__ = 'governance_applicability_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    obligation_id: Mapped[str] = mapped_column(String(36))
    obligation_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reason: Mapped[str] = mapped_column(String(2000))
    applicability: Mapped[str] = mapped_column(String(30))
    evaluated_inputs: Mapped[dict] = mapped_column(JSON)
    reasons: Mapped[list] = mapped_column(JSON)
    unresolved_inputs: Mapped[list] = mapped_column(JSON)
    timing_inputs: Mapped[dict] = mapped_column(JSON)
    deadline_date: Mapped[date | None] = mapped_column(nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    deadline_reasons: Mapped[list] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','obligation_id'], ['governance_obligations.school_id','governance_obligations.id']),)

class ObligationReview(Tenant, Base):
    __tablename__ = 'governance_obligation_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    obligation_id: Mapped[str] = mapped_column(String(36))
    obligation_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    decision: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(String(2000))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','obligation_id'], ['governance_obligations.school_id','governance_obligations.id']),)

class ObligationAssignment(Tenant, Base):
    __tablename__ = 'governance_obligation_assignments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    obligation_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    previous_owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    internal_planned_date: Mapped[date | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(String(2000))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','obligation_id'], ['governance_obligations.school_id','governance_obligations.id']),)

class ObligationAction(Tenant, Base):
    __tablename__ = 'governance_obligation_actions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    obligation_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    kind: Mapped[str] = mapped_column(String(30))
    action_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(2000))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    evidence_references: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','obligation_id'], ['governance_obligations.school_id','governance_obligations.id']))

class ComplianceDeviation(Aggregate, Tenant, Base):
    __tablename__ = 'governance_deviations'
    obligation_id: Mapped[str] = mapped_column(String(36))
    issue_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(2000))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    resolution_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','obligation_id'], ['governance_obligations.school_id','governance_obligations.id']), ForeignKeyConstraint(['school_id','owner_id'], ['identity_memberships.school_id','identity_memberships.user_id']))

class DeviationFollowup(Tenant, Base):
    __tablename__ = 'governance_deviation_followups'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deviation_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    action: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(String(2000))
    performed_action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','deviation_id'], ['governance_deviations.school_id','governance_deviations.id']), ForeignKeyConstraint(['school_id','performed_action_id'], ['governance_obligation_actions.school_id','governance_obligation_actions.id']))

class WorkloadStudy(Aggregate, Tenant, Base):
    __tablename__ = 'governance_workload_studies'
    title: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(40))
    protocol: Mapped[str] = mapped_column(String(2000))
    quality_rubric: Mapped[str] = mapped_column(String(2000))
    minimum_quality: Mapped[int] = mapped_column(Integer)
    closed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closure_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), CheckConstraint('minimum_quality >= 1 AND minimum_quality <= 5'))

class WorkloadParticipant(Aggregate, Tenant, Base):
    __tablename__ = 'governance_workload_participants'
    study_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), UniqueConstraint('study_id','user_id'), ForeignKeyConstraint(['school_id','study_id'], ['governance_workload_studies.school_id','governance_workload_studies.id']))

class WorkloadMeasurement(Tenant, Base):
    __tablename__ = 'governance_workload_measurements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(String(36))
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    previous_measurement_id: Mapped[str | None] = mapped_column(ForeignKey('governance_workload_measurements.id'), nullable=True)
    match_key: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    complexity: Mapped[str] = mapped_column(String(20))
    scenario: Mapped[str] = mapped_column(String(200))
    primary_minutes: Mapped[float | None] = mapped_column(nullable=True)
    review_minutes: Mapped[float | None] = mapped_column(nullable=True)
    correction_minutes: Mapped[float | None] = mapped_column(nullable=True)
    duplicate_entry_minutes: Mapped[float | None] = mapped_column(nullable=True)
    followup_minutes: Mapped[float | None] = mapped_column(nullable=True)
    quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comprehension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usefulness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (UniqueConstraint('participant_id','match_key','mode','revision_number'), ForeignKeyConstraint(['school_id','participant_id'], ['governance_workload_participants.school_id','governance_workload_participants.id']))

class GovernanceEvent(Tenant, Base):
    __tablename__ = 'governance_outbox'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    correlation_id: Mapped[str] = mapped_column(String(36), default=new_id)
    causation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

# Defense in depth for application writes; migrations also install PostgreSQL
# immutability triggers so direct SQL cannot rewrite published historical content.
def immutable_content(mapper, connection, target):
    allowed = {'state','version','updated_at','reviewed_by','reviewed_at','review_rationale','approved_by','approved_at','approval_rationale','impact_digest','withdrawn_by','withdrawn_at','withdrawal_rationale','revoked_by','revoked_at','revocation_rationale','closed_by','closed_at','closure_rationale'}
    if any(a.history.has_changes() and a.key not in allowed for a in inspect(target).attrs):
        raise ValueError('Historical governance content is immutable; create a revision')

for cls in (RequirementDefinition, RequirementVersion, SchoolRuleProfile, WorkloadStudy):
    event.listen(cls, 'before_update', immutable_content)

def append_only(mapper, connection, target):
    raise ValueError('Governance evidence is append-only')

for cls in (RequirementDefinition, RequirementVersion, SchoolRuleProfile, WorkloadStudy):
    event.listen(cls, 'before_delete', append_only)

for cls in (ApplicabilityDecision, ObligationReview, ObligationAssignment, ObligationAction, DeviationFollowup, WorkloadMeasurement, LegalImportCandidate, TriggerReceipt):
    event.listen(cls, 'before_update', append_only)
    event.listen(cls, 'before_delete', append_only)

class ReportPeriodReview(Tenant, Base):
    """Append-only human review and command receipt; no inferred legacy coverage."""
    __tablename__ = 'governance_report_period_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    obligation_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36))
    document_kind: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    starts_on: Mapped[date] = mapped_column()
    ends_on: Mapped[date] = mapped_column()
    obligation_basis_digest: Mapped[str] = mapped_column(String(64))
    reviewed_binding: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    rationale: Mapped[str] = mapped_column(String(2000))
    request_key: Mapped[str] = mapped_column(String(200))
    request_digest: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (
        UniqueConstraint('school_id', 'id'),
        UniqueConstraint('school_id', 'request_key'),
        UniqueConstraint('obligation_id', 'document_kind', 'revision'),
        ForeignKeyConstraint(['school_id', 'obligation_id'], ['governance_obligations.school_id', 'governance_obligations.id']),
        ForeignKeyConstraint(['school_id', 'learner_id'], ['identity_learners.school_id', 'identity_learners.id']),
        CheckConstraint('ends_on >= starts_on'), CheckConstraint('revision >= 1'),
        CheckConstraint("action IN ('review', 'revoke')"),
    )

for operation in ('before_update', 'before_delete'):
    event.listen(ReportPeriodReview, operation, append_only)
