"""BC06 owned, tenant-scoped aggregates and append-only authored revisions."""
from datetime import date, datetime
from sqlalchemy import String, Integer, JSON, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Text, Index, text, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id


class Tenant:
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)


class Row(Tenant):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CurriculumScheme(Aggregate, Tenant, Base):
    __tablename__='curriculum_schemes'
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),)


class SchemeRevision(Aggregate, Tenant, Base):
    __tablename__='curriculum_scheme_revisions'
    scheme_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(2000))
    pedagogy: Mapped[str] = mapped_column(String(30))
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date] = mapped_column()
    goals: Mapped[list] = mapped_column(JSON)
    subject_allocations: Mapped[list] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    authored_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    approval_reference: Mapped[str | None] = mapped_column(Text,nullable=True)
    approved_on: Mapped[date | None] = mapped_column(nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('scheme_id','number'),ForeignKeyConstraint(['school_id','scheme_id'],['curriculum_schemes.school_id','curriculum_schemes.id']),CheckConstraint('valid_until >= valid_from'))


class AssessmentScheme(Row, Base):
    __tablename__='curriculum_assessment_schemes'
    scheme_revision_id: Mapped[str] = mapped_column(String(36))
    rules: Mapped[list] = mapped_column(JSON)
    __table_args__=(UniqueConstraint('school_id','scheme_revision_id'),ForeignKeyConstraint(['school_id','scheme_revision_id'],['curriculum_scheme_revisions.school_id','curriculum_scheme_revisions.id']))


class ClassLearningPlan(Aggregate, Tenant, Base):
    __tablename__='curriculum_class_plans'
    current_revision: Mapped[int] = mapped_column(Integer,default=1)
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),)


class ClassPlanRevision(Aggregate, Tenant, Base):
    __tablename__='curriculum_class_plan_revisions'
    plan_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(2000))
    group_name: Mapped[str] = mapped_column(String(100))
    school_year: Mapped[str] = mapped_column(String(9))
    age_min: Mapped[int] = mapped_column(Integer)
    age_max: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date] = mapped_column()
    themes: Mapped[list] = mapped_column(JSON)
    imported_sources: Mapped[list] = mapped_column(JSON)
    import_notes: Mapped[str | None] = mapped_column(Text,nullable=True)
    content_digest: Mapped[str] = mapped_column(String(64))
    authored_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    published_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('plan_id','number'),ForeignKeyConstraint(['school_id','plan_id'],['curriculum_class_plans.school_id','curriculum_class_plans.id']),CheckConstraint('valid_until >= valid_from'),CheckConstraint('age_max >= age_min'))


class ThemeGoalBinding(Aggregate, Tenant, Base):
    __tablename__='curriculum_theme_goal_bindings'
    plan_revision_id: Mapped[str] = mapped_column(String(36))
    theme_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36),index=True)
    goal_revision_id: Mapped[str] = mapped_column(String(36))
    participation: Mapped[str] = mapped_column(String(30))
    rationale: Mapped[str] = mapped_column(Text)
    adaptation: Mapped[str | None] = mapped_column(Text,nullable=True)
    materials: Mapped[list] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    bound_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    goal_digest: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    correction_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','plan_revision_id'],['curriculum_class_plan_revisions.school_id','curriculum_class_plan_revisions.id']),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),ForeignKeyConstraint(['school_id','supersedes_id'],['curriculum_theme_goal_bindings.school_id','curriculum_theme_goal_bindings.id']),CheckConstraint("state IN ('active','superseded')"),Index('uq_curriculum_current_theme_goal_choice','school_id','plan_revision_id','theme_id','learner_id','goal_revision_id',unique=True,sqlite_where=text("state = 'active'"),postgresql_where=text("state = 'active'")))


class SessionImpact(Aggregate, Tenant, Base):
    __tablename__='curriculum_session_impacts'
    dependency_kind: Mapped[str] = mapped_column(String(30))
    dependency_changed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    old_revision_id: Mapped[str] = mapped_column(String(36))
    new_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    session_id: Mapped[str] = mapped_column(String(36))
    session_revision_id: Mapped[str] = mapped_column(String(36))
    planned_at: Mapped[datetime] = mapped_column(UTCDateTime())
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    learner_ids: Mapped[list] = mapped_column(JSON)
    decision_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    replacement_session_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','old_revision_id','new_revision_id','session_revision_id'))


class ResourceTeam(Aggregate, Tenant, Base):
    __tablename__='curriculum_resource_teams'
    name: Mapped[str] = mapped_column(String(200))
    __table_args__=(UniqueConstraint('school_id','id'),)


class TeamMember(Aggregate, Tenant, Base):
    __tablename__='curriculum_team_members'
    team_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    valid_from: Mapped[date] = mapped_column()
    valid_until: Mapped[date] = mapped_column()
    __table_args__=(ForeignKeyConstraint(['school_id','team_id'],['curriculum_resource_teams.school_id','curriculum_resource_teams.id']),UniqueConstraint('school_id','team_id','user_id'),CheckConstraint('valid_until >= valid_from'))


class TeachingResource(Aggregate, Tenant, Base):
    __tablename__='curriculum_resources'
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    current_revision: Mapped[int] = mapped_column(Integer,default=1)
    visibility: Mapped[str] = mapped_column(String(20),default='private')
    team_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    shared_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    shared_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    shared_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','team_id'],['curriculum_resource_teams.school_id','curriculum_resource_teams.id']))


class ResourceRevision(Row, Base):
    __tablename__='curriculum_resource_revisions'
    resource_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    original_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    previous_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    original_provenance: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    preparation: Mapped[str] = mapped_column(Text)
    instructions: Mapped[list] = mapped_column(JSON)
    subjects: Mapped[list] = mapped_column(JSON)
    skills: Mapped[list] = mapped_column(JSON)
    level: Mapped[str | None] = mapped_column(String(100),nullable=True)
    tags: Mapped[list] = mapped_column(JSON)
    age_min: Mapped[int] = mapped_column(Integer)
    age_max: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    group_min: Mapped[int] = mapped_column(Integer)
    group_max: Mapped[int] = mapped_column(Integer)
    prerequisites: Mapped[list] = mapped_column(JSON)
    material_ids: Mapped[list] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    rights: Mapped[dict] = mapped_column(JSON)
    changes: Mapped[list] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    authored_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('resource_id','number'),ForeignKeyConstraint(['school_id','resource_id'],['curriculum_resources.school_id','curriculum_resources.id']),ForeignKeyConstraint(['school_id','original_revision_id'],['curriculum_resource_revisions.school_id','curriculum_resource_revisions.id']),ForeignKeyConstraint(['school_id','previous_revision_id'],['curriculum_resource_revisions.school_id','curriculum_resource_revisions.id']),CheckConstraint('age_max >= age_min'),CheckConstraint('group_max >= group_min'),CheckConstraint('duration_minutes > 0'))


class ResourceExperience(Row, Base):
    __tablename__='curriculum_resource_experiences'
    resource_revision_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36))
    session_delivery_revision_id: Mapped[str] = mapped_column(String(36))
    observed_on: Mapped[date] = mapped_column()
    experience: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(ForeignKeyConstraint(['school_id','resource_revision_id'],['curriculum_resource_revisions.school_id','curriculum_resource_revisions.id']),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']))


class MaterialCatalogItem(Aggregate, Tenant, Base):
    __tablename__='curriculum_materials'
    title: Mapped[str] = mapped_column(Text)
    material_type: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(Text)
    count: Mapped[int | None] = mapped_column(Integer,nullable=True)
    inventory_checked_on: Mapped[date | None] = mapped_column(nullable=True)
    presentation_revision_ids: Mapped[list] = mapped_column(JSON)
    __table_args__=(UniqueConstraint('school_id','id'),CheckConstraint('count IS NULL OR count >= 0'))


class CommandReceipt(Row, Base):
    __tablename__='curriculum_commands'
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    request_key: Mapped[str] = mapped_column(String(120))
    operation: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__=(UniqueConstraint('school_id','actor_id','request_key'),)


class CurriculumEvent(Row, Base):
    __tablename__='curriculum_outbox'
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    payload: Mapped[dict] = mapped_column(JSON,default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=utcnow)
    schema_version: Mapped[int] = mapped_column(Integer,default=1)
    correlation_id: Mapped[str] = mapped_column(String(36),default=new_id)
    causation_id: Mapped[str | None] = mapped_column(String(120),nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)


def immutable(mapper,connection,target):
    state=inspect(target)
    allowed={'state','version','updated_at','reviewed_by','reviewed_at','review_reason','approval_reference','approved_on','published_by','published_at'}
    if any(state.attrs[c.name].history.has_changes() for c in target.__table__.columns if c.name not in allowed):
        raise ValueError('Authored revisions and provenance are immutable; append a revision')


def no_delete(mapper,connection,target):
    raise ValueError('Curriculum history is retained; withdraw instead')


for _model in (SchemeRevision,ClassPlanRevision,AssessmentScheme,ResourceRevision,ResourceExperience,ThemeGoalBinding):
    event.listen(_model,'before_update',immutable)
    event.listen(_model,'before_delete',no_delete)
