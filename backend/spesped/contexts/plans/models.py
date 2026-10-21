"""BC05 immutable pedagogical content versions and exact human approvals."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id
from spesped.contexts.entitlements.models import SchoolRow, SubjectRow


class LearnerSupportProfile(Aggregate, SubjectRow, Base):
    __tablename__ = 'plans_support_profiles'
    __table_args__ = (UniqueConstraint('school_id','learner_id'), UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']))


class ProfileStatement(Aggregate, SchoolRow, Base):
    __tablename__ = 'plans_profile_statements'
    profile_id: Mapped[str] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    proposed_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaces_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','profile_id'],['plans_support_profiles.school_id','plans_support_profiles.id']), UniqueConstraint('school_id','id'), CheckConstraint("category IN ('strength','interest','language','communication','support_strategy')"), CheckConstraint("state IN ('proposed','confirmed','disputed','replaced','rejected')"))


class ProfileReview(SchoolRow, Base):
    __tablename__ = 'plans_profile_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    statement_id: Mapped[str] = mapped_column(String(36))
    outcome: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','statement_id'],['plans_profile_statements.school_id','plans_profile_statements.id']),)


class IndividualEducationPlan(Aggregate, SubjectRow, Base):
    __tablename__ = 'plans_individual_education_plans'
    kind: Mapped[str] = mapped_column(String(30))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    active_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'), ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']), CheckConstraint("kind IN ('individual_education','ordinary_teaching')"))


class PlanRevision(Aggregate, SchoolRow, Base):
    __tablename__ = 'plans_revisions'
    plan_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(320))
    rationale: Mapped[str] = mapped_column(Text)
    organization: Mapped[str] = mapped_column(Text)
    responsibility: Mapped[str] = mapped_column(Text)
    evaluation_method: Mapped[str] = mapped_column(Text)
    participation_record: Mapped[str] = mapped_column(Text)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    origin: Mapped[str] = mapped_column(String(30))
    sources: Mapped[list] = mapped_column(JSON)
    original_approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    content_digest: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    activation_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    approval_binding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_id'],['plans_individual_education_plans.school_id','plans_individual_education_plans.id']), UniqueConstraint('school_id','id'), UniqueConstraint('school_id','plan_id','revision'), CheckConstraint('effective_from < effective_until'), CheckConstraint("state IN ('draft','in_review','approved','active','historical')"), CheckConstraint("origin IN ('authored','imported')"))


class LearningGoal(SchoolRow, Base):
    __tablename__ = 'plans_learning_goals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_id'],['plans_individual_education_plans.school_id','plans_individual_education_plans.id']), UniqueConstraint('school_id','id'))


class GoalRevision(SchoolRow, Base):
    __tablename__ = 'plans_goal_revisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    goal_id: Mapped[str] = mapped_column(String(36))
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    parent_goal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(320))
    expected_action: Mapped[str] = mapped_column(Text)
    arena: Mapped[str] = mapped_column(Text)
    support: Mapped[str] = mapped_column(Text)
    responsibility: Mapped[str] = mapped_column(Text)
    evaluation_method: Mapped[str] = mapped_column(Text)
    curriculum_reference: Mapped[str] = mapped_column(String(320))
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    __table_args__ = (ForeignKeyConstraint(['school_id','goal_id'],['plans_learning_goals.school_id','plans_learning_goals.id']), ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']), UniqueConstraint('school_id','id'), UniqueConstraint('school_id','plan_revision_id','goal_id'), CheckConstraint('effective_from < effective_until'), CheckConstraint("status IN ('active','closed')"))


class Adaptation(SchoolRow, Base):
    __tablename__ = 'plans_adaptations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    goal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    measure: Mapped[str] = mapped_column(Text)
    arena: Mapped[str] = mapped_column(Text)
    responsibility: Mapped[str] = mapped_column(Text)
    evaluation_method: Mapped[str] = mapped_column(Text)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']),)


class PlanContribution(SchoolRow, Base):
    __tablename__ = 'plans_contributions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    goal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    participant: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    disagreement: Mapped[bool] = mapped_column(default=False)
    response: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    source: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']), CheckConstraint("role IN ('learner','guardian')"))


class ProvisionAllocation(SchoolRow, Base):
    __tablename__ = 'plans_provision_allocations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    provision_id: Mapped[str] = mapped_column(String(36))
    decision_id: Mapped[str] = mapped_column(String(36))
    decision_revision_id: Mapped[str] = mapped_column(String(36))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14,4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    counting_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_until: Mapped[datetime] = mapped_column(UTCDateTime())
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']), ForeignKeyConstraint(['school_id','provision_id'],['entitlements_decision_provisions.school_id','entitlements_decision_provisions.id']), UniqueConstraint('school_id','plan_revision_id','provision_id'), CheckConstraint('effective_from < effective_until'), CheckConstraint('amount IS NULL OR amount >= 0'))


class PlanApproval(SchoolRow, Base):
    __tablename__ = 'plans_approvals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(30))
    digest: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    authority_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_revision_id'],['plans_revisions.school_id','plans_revisions.id']),)


class PlanImpact(Aggregate, SubjectRow, Base):
    __tablename__ = 'plans_change_impacts'
    plan_id: Mapped[str] = mapped_column(String(36))
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    old_reference: Mapped[str] = mapped_column(String(36))
    new_reference: Mapped[str] = mapped_column(String(36))
    resolved_by_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    __table_args__ = (ForeignKeyConstraint(['school_id','plan_id'],['plans_individual_education_plans.school_id','plans_individual_education_plans.id']), UniqueConstraint('school_id','plan_revision_id','kind','new_reference'))


class PlanCommand(SchoolRow, Base):
    __tablename__ = 'plans_commands'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    request_key: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint('school_id','actor_id','request_key'),)


class PlanEvent(SchoolRow, Base):
    __tablename__ = 'plans_outbox'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


# Protect immutable pedagogical content at the ORM boundary as well as through
# append-only HTTP commands. Lifecycle metadata is outside the approved content.
from sqlalchemy import event as _event, inspect as _inspect
from spesped.errors import DomainError as _DomainError


def _immutable_record(mapper,connection,target):
    raise _DomainError('immutable_revision','Create a new revision instead of changing historical pedagogical content.',409)


def _immutable_plan_content(mapper,connection,target):
    fields=('plan_id','revision','title','rationale','organization','responsibility','evaluation_method','participation_record','decision_id','decision_revision_id','effective_from','effective_until','origin','sources','original_approval','created_by')
    if any(_inspect(target).attrs[name].history.has_changes() for name in fields):
        _immutable_record(mapper,connection,target)


def _immutable_profile_content(mapper,connection,target):
    fields=('profile_id','category','content','source','observed_at','proposed_by','replaces_id')
    if any(_inspect(target).attrs[name].history.has_changes() for name in fields):
        _immutable_record(mapper,connection,target)


for _record in (LearningGoal,GoalRevision,Adaptation,PlanContribution,ProvisionAllocation,PlanApproval,ProfileReview):
    _event.listen(_record,'before_update',_immutable_record)
_event.listen(PlanRevision,'before_update',_immutable_plan_content)
_event.listen(ProfileStatement,'before_update',_immutable_profile_content)
