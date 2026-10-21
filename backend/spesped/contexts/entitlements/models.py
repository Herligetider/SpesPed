"""BC04: protected support cases and source-confirmed education entitlements."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id


class SchoolRow:
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)


class SubjectRow(SchoolRow):
    learner_id: Mapped[str] = mapped_column(String(36), index=True)


class SupportCase(Aggregate, SubjectRow, Base):
    __tablename__ = 'entitlements_support_cases'
    concern: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(String(80), default='educational_support')
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id', 'id'), UniqueConstraint('school_id', 'learner_id', 'id'), ForeignKeyConstraint(['school_id','learner_id'], ['identity_learners.school_id','identity_learners.id']), CheckConstraint("state IN ('preparation','referral_submitted','awaiting_basis','decision_received','follow_up','closed')"))


class CaseRow(SubjectRow):
    case_id: Mapped[str] = mapped_column(String(36), index=True)


def case_constraints():
    return (ForeignKeyConstraint(['school_id','learner_id','case_id'], ['entitlements_support_cases.school_id','entitlements_support_cases.learner_id','entitlements_support_cases.id']), UniqueConstraint('school_id','id'))


class EducationConsent(Aggregate, CaseRow, Base):
    __tablename__ = 'entitlements_education_consents'
    kind: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(160))
    action_scope: Mapped[str] = mapped_column(String(160))
    representative: Mapped[str] = mapped_column(String(320))
    representative_capacity: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source: Mapped[dict] = mapped_column(JSON)
    confirmed_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (*case_constraints(), CheckConstraint("kind IN ('education_action','disclosure_permission','processing_basis')"), CheckConstraint('valid_until IS NULL OR valid_from < valid_until'), CheckConstraint("state IN ('confirmed','revoked')"))


class Referral(Aggregate, CaseRow, Base):
    __tablename__ = 'entitlements_referrals'
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    __table_args__ = (*case_constraints(), CheckConstraint("state IN ('draft','reviewed','submitted','receipt_received','follow_up','closed')"))


class ReferralRevision(SchoolRow, Base):
    __tablename__ = 'entitlements_referral_revisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    concern: Mapped[str] = mapped_column(Text)
    prior_measures: Mapped[str] = mapped_column(Text)
    observed_outcomes: Mapped[str] = mapped_column(Text)
    requested_assessment: Mapped[str] = mapped_column(Text)
    learner_view: Mapped[str] = mapped_column(Text)
    guardian_view: Mapped[str] = mapped_column(Text)
    recipient: Mapped[str] = mapped_column(String(320))
    sources: Mapped[list] = mapped_column(JSON)
    consent_ids: Mapped[list] = mapped_column(JSON)
    permission_requirement: Mapped[str] = mapped_column(String(40))
    permission_basis: Mapped[str] = mapped_column(Text)
    disclosure_requirement: Mapped[str] = mapped_column(String(40))
    disclosure_permission_ids: Mapped[list] = mapped_column(JSON)
    disclosure_basis: Mapped[str] = mapped_column(Text)
    processing_basis_id: Mapped[str] = mapped_column(String(36))
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','referral_id'],['entitlements_referrals.school_id','entitlements_referrals.id']), UniqueConstraint('school_id','referral_id','revision'))


class ReferralContact(SchoolRow, Base):
    __tablename__ = 'entitlements_referral_contacts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    referral_id: Mapped[str] = mapped_column(String(36))
    referral_revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    actual_contact: Mapped[bool] = mapped_column(default=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    recipient: Mapped[str] = mapped_column(String(320))
    channel: Mapped[str] = mapped_column(String(80))
    external_reference: Mapped[str | None] = mapped_column(String(320), nullable=True)
    note: Mapped[str] = mapped_column(Text)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','referral_id','referral_revision'],['entitlements_referral_revisions.school_id','entitlements_referral_revisions.referral_id','entitlements_referral_revisions.revision']), CheckConstraint("kind IN ('submission','receipt','follow_up')"))


class ExpertAssessment(Aggregate, CaseRow, Base):
    __tablename__ = 'entitlements_expert_assessments'
    issuer: Mapped[str] = mapped_column(String(320))
    assessment_at: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source: Mapped[dict] = mapped_column(JSON)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    __table_args__ = case_constraints()


class Recommendation(SchoolRow, Base):
    __tablename__ = 'entitlements_recommendations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14,4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    counting_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (ForeignKeyConstraint(['school_id','assessment_id'],['entitlements_expert_assessments.school_id','entitlements_expert_assessments.id']), CheckConstraint('effective_from < effective_until'), CheckConstraint('amount IS NULL OR amount >= 0'))


class EducationDecision(Aggregate, CaseRow, Base):
    __tablename__ = 'entitlements_education_decisions'
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = case_constraints()


class DecisionRevision(Aggregate, SchoolRow, Base):
    __tablename__ = 'entitlements_decision_revisions'
    decision_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    issuing_authority: Mapped[str] = mapped_column(String(320))
    authority_basis: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[dict] = mapped_column(JSON)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    confirmation_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','decision_id'],['entitlements_education_decisions.school_id','entitlements_education_decisions.id']), UniqueConstraint('school_id','id'), UniqueConstraint('school_id','decision_id','revision'), CheckConstraint('effective_from < effective_until'), CheckConstraint("state IN ('proposed','confirmed','disputed','superseded')"))


class DecisionProvision(SchoolRow, Base):
    __tablename__ = 'entitlements_decision_provisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    decision_revision_id: Mapped[str] = mapped_column(String(36))
    clause: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    organization: Mapped[str] = mapped_column(Text)
    competence: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14,4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    counting_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (ForeignKeyConstraint(['school_id','decision_revision_id'],['entitlements_decision_revisions.school_id','entitlements_decision_revisions.id']), UniqueConstraint('school_id','id'), CheckConstraint('effective_from < effective_until'), CheckConstraint('amount IS NULL OR amount >= 0'), CheckConstraint("category IN ('individually_adapted_education','personal_assistance','physical_adaptation')"), CheckConstraint("(amount IS NULL AND unit IS NULL AND counting_basis IS NULL) OR (amount IS NOT NULL AND unit IN ('minutes','hours') AND counting_basis IN ('learner_time','staff_time'))"))


class EntitlementCommand(SchoolRow, Base):
    __tablename__ = 'entitlements_commands'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    request_key: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint('school_id','actor_id','request_key'),)


class EntitlementEvent(SchoolRow, Base):
    __tablename__ = 'entitlements_outbox'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


# These rows are records of exact source content. Corrections create new records;
# aggregate lifecycle fields (confirmation/state/version) remain mutable.
from sqlalchemy import event as _event, inspect as _inspect
from spesped.errors import DomainError as _DomainError


def _immutable_record(mapper, connection, target):
    raise _DomainError('immutable_revision', 'Create a new revision instead of changing recorded source content.', 409)


def _immutable_decision_content(mapper, connection, target):
    fields=('decision_id','revision','issuing_authority','authority_basis','issued_at','effective_from','effective_until','source')
    if any(_inspect(target).attrs[name].history.has_changes() for name in fields):
        _immutable_record(mapper,connection,target)


for _record in (ReferralRevision,ReferralContact,Recommendation,DecisionProvision):
    _event.listen(_record,'before_update',_immutable_record)
_event.listen(DecisionRevision,'before_update',_immutable_decision_content)


class CaseClarification(Aggregate, CaseRow, Base):
    __tablename__='entitlements_case_clarifications'
    kind: Mapped[str]=mapped_column(String(60))
    description: Mapped[str]=mapped_column(Text)
    owner_id: Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    due_at: Mapped[datetime | None]=mapped_column(UTCDateTime(),nullable=True)
    source: Mapped[dict | None]=mapped_column(JSON,nullable=True)
    reference_id: Mapped[str | None]=mapped_column(String(36),nullable=True)
    resolution: Mapped[str | None]=mapped_column(Text,nullable=True)
    resolved_by: Mapped[str | None]=mapped_column(ForeignKey('identity_users.id'),nullable=True)
    resolved_at: Mapped[datetime | None]=mapped_column(UTCDateTime(),nullable=True)
    __table_args__=(*case_constraints(),CheckConstraint("kind IN ('missing_decision','unclear_unit','contradictory_period','recommendation_difference','source_review','other')"),CheckConstraint("state IN ('open','resolved')"))
