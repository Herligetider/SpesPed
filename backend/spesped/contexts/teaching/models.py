"""BC07 context-owned relational aggregates and immutable content histories."""
from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from spesped.db import Base, UTCDateTime, utcnow
from spesped.contexts.identity.models import Aggregate, new_id
from spesped.errors import DomainError


class SchoolRow:
    school_id: Mapped[str] = mapped_column(ForeignKey('identity_schools.id'), index=True)


class Record(SchoolRow):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


def parent_fk(field, table):
    return ForeignKeyConstraint(['school_id',field],[table+'.school_id',table+'.id'])


class TeachingBasis(Record, Base):
    __tablename__ = 'teaching_bases'
    planned_at: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_minutes: Mapped[int] = mapped_column(Integer)
    learners: Mapped[list] = mapped_column(JSON)
    theme: Mapped[str] = mapped_column(Text)
    arena: Mapped[str] = mapped_column(String(300))
    materials: Mapped[list] = mapped_column(JSON)
    missing_information: Mapped[list] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id','id'),CheckConstraint('duration_minutes > 0'))


class TeachingSession(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_sessions'
    current_revision: Mapped[int] = mapped_column(Integer,default=1)
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id','id'),CheckConstraint("state IN ('draft','in_review','approved','review_required')"))


class SessionRevision(Record, Base):
    __tablename__ = 'teaching_session_revisions'
    session_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    basis_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[dict] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text,default='Initial teaching plan')
    created_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    generation_job_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    generation_job_ids: Mapped[list] = mapped_column(JSON,default=list)
    field_job_ids: Mapped[dict] = mapped_column(JSON,default=dict)
    __table_args__ = (UniqueConstraint('school_id','id'),UniqueConstraint('school_id','session_id','revision'),parent_fk('session_id','teaching_sessions'),parent_fk('basis_id','teaching_bases'))


class SessionReview(Record, Base):
    __tablename__ = 'teaching_session_reviews'
    revision_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    content_digest: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    authority_id: Mapped[str | None] = mapped_column(Text,nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (parent_fk('revision_id','teaching_session_revisions'),CheckConstraint("kind IN ('review','approve')"))


class AssistantBrief(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_briefs'
    session_revision_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36))
    template: Mapped[str] = mapped_column(String(40))
    content: Mapped[dict] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(64))
    replaces_brief_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    authority_id: Mapped[str | None] = mapped_column(Text,nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'),parent_fk('session_revision_id','teaching_session_revisions'),parent_fk('learner_id','identity_learners'),CheckConstraint("state IN ('draft','approved','review_required')"))


class BriefAssignment(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_brief_assignments'
    brief_id: Mapped[str] = mapped_column(String(36))
    assistant_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime] = mapped_column(UTCDateTime())
    role: Mapped[str] = mapped_column(String(500))
    assigned_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id','id'),parent_fk('brief_id','teaching_briefs'),CheckConstraint('valid_from < valid_until'),CheckConstraint("state IN ('active','revoked')"))


class BriefMessage(Record, Base):
    __tablename__ = 'teaching_brief_messages'
    assignment_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    responds_to_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'),parent_fk('assignment_id','teaching_brief_assignments'),CheckConstraint("kind IN ('question','answer','feedback','guidance')"))


class SessionDelivery(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_deliveries'
    session_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    current_revision: Mapped[int] = mapped_column(Integer,default=1)
    __table_args__ = (UniqueConstraint('school_id','id'),UniqueConstraint('school_id','session_id'),parent_fk('session_id','teaching_sessions'),CheckConstraint("state IN ('delivered','partial','cancelled')"))


class DeliveryRevision(Record, Base):
    __tablename__ = 'teaching_delivery_revisions'
    delivery_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    session_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    activity: Mapped[str] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(String(40),nullable=True)
    cause_detail: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id','id'),UniqueConstraint('school_id','delivery_id','revision'),parent_fk('delivery_id','teaching_deliveries'),parent_fk('session_revision_id','teaching_session_revisions'),CheckConstraint('duration_minutes >= 0'))


class LearnerParticipation(Record, Base):
    __tablename__ = 'teaching_learner_participation'
    delivery_revision_id: Mapped[str] = mapped_column(String(36))
    learner_id: Mapped[str] = mapped_column(String(36))
    goal_revision_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    minutes: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(60))
    support: Mapped[str] = mapped_column(Text)
    provision: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    counting_basis: Mapped[str | None] = mapped_column(String(30),nullable=True)
    attributed_staff_minutes: Mapped[int | None] = mapped_column(Integer,nullable=True)
    __table_args__ = (UniqueConstraint('school_id','delivery_revision_id','learner_id','category'),parent_fk('delivery_revision_id','teaching_delivery_revisions'),parent_fk('learner_id','identity_learners'),CheckConstraint('minutes >= 0'))


class StaffParticipation(Record, Base):
    __tablename__ = 'teaching_staff_participation'
    delivery_revision_id: Mapped[str] = mapped_column(String(36))
    staff_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    minutes: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(60))
    __table_args__ = (UniqueConstraint('school_id','delivery_revision_id','staff_id','category'),parent_fk('delivery_revision_id','teaching_delivery_revisions'),CheckConstraint('minutes > 0'))


class TeachingObservation(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_observations'
    learner_id: Mapped[str] = mapped_column(String(36))
    current_revision: Mapped[int] = mapped_column(Integer,default=1)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    __table_args__ = (UniqueConstraint('school_id','id'),parent_fk('learner_id','identity_learners'),CheckConstraint("state IN ('draft','saved','corrected')"))


class ObservationRevision(Record, Base):
    __tablename__ = 'teaching_observation_revisions'
    observation_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    learner_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    session_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    assignment_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    goal_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    observation: Mapped[str] = mapped_column(Text)
    support: Mapped[str] = mapped_column(Text)
    interpretation: Mapped[str | None] = mapped_column(Text,nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text,nullable=True)
    input_method: Mapped[str] = mapped_column(String(30))
    saved: Mapped[bool] = mapped_column(default=False)
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint('school_id','id'),UniqueConstraint('school_id','observation_id','revision'),parent_fk('observation_id','teaching_observations'),parent_fk('learner_id','identity_learners'),parent_fk('session_revision_id','teaching_session_revisions'),parent_fk('assignment_id','teaching_brief_assignments'))


class TeachingFollowUp(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_follow_ups'
    learner_id: Mapped[str] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    reason_code: Mapped[str] = mapped_column(String(60))
    owner_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    action: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text,nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'),UniqueConstraint('school_id','learner_id','target_type','target_id','reason_code'),parent_fk('learner_id','identity_learners'),CheckConstraint("state IN ('open','resolved')"))


class ProposalReview(Record, Base):
    __tablename__ = 'teaching_proposal_reviews'
    session_id: Mapped[str] = mapped_column(String(36))
    session_revision_id: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[str] = mapped_column(String(36))
    job_digest: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(20))
    selected_fields: Mapped[list] = mapped_column(JSON)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (parent_fk('session_id','teaching_sessions'),parent_fk('session_revision_id','teaching_session_revisions'))


class TeachingCommand(Record, Base):
    __tablename__ = 'teaching_commands'
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    request_key: Mapped[str] = mapped_column(String(120))
    operation: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint('school_id','actor_id','request_key'),)


class TeachingEvent(Record, Base):
    __tablename__ = 'teaching_outbox'
    aggregate_id: Mapped[str] = mapped_column(String(36))
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    payload: Mapped[dict] = mapped_column(JSON,default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(),default=utcnow)
    schema_version: Mapped[int] = mapped_column(Integer,default=1)
    correlation_id: Mapped[str] = mapped_column(String(36))
    causation_id: Mapped[str | None] = mapped_column(String(120),nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(),nullable=True)


def immutable(mapper,connection,row):
    raise DomainError('immutable_revision','Create a new version to correct historical teaching content.',409)


for record in (TeachingBasis,SessionRevision,SessionReview,BriefMessage,DeliveryRevision,LearnerParticipation,StaffParticipation,ObservationRevision,ProposalReview,TeachingCommand):
    event.listen(record,'before_update',immutable)


@event.listens_for(AssistantBrief,'before_update')
def immutable_brief_content(mapper,connection,row):
    if any(inspect(row).attrs[n].history.has_changes() for n in ('session_revision_id','learner_id','template','content','content_digest','replaces_brief_id','created_by')): immutable(mapper,connection,row)


class AssistantActualInput(Aggregate, SchoolRow, Base):
    __tablename__ = 'teaching_assistant_actual_inputs'
    assignment_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(ForeignKey('identity_users.id'))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    content: Mapped[dict] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('identity_users.id'),nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text,nullable=True)
    delivery_revision_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    __table_args__ = (UniqueConstraint('school_id','id'),parent_fk('assignment_id','teaching_brief_assignments'),parent_fk('delivery_revision_id','teaching_delivery_revisions'),CheckConstraint("state IN ('submitted','recorded','needs_clarification','rejected')"))


@event.listens_for(AssistantActualInput,'before_update')
def immutable_actual_input(mapper,connection,row):
    if any(inspect(row).attrs[n].history.has_changes() for n in ('assignment_id','author_id','occurred_at','content')):immutable(mapper,connection,row)

__all__ = ['TeachingBasis','TeachingSession','SessionRevision','SessionReview','AssistantBrief','BriefAssignment','BriefMessage','SessionDelivery','DeliveryRevision','LearnerParticipation','StaffParticipation','TeachingObservation','ObservationRevision','TeachingFollowUp','ProposalReview','TeachingCommand','TeachingEvent','AssistantActualInput']
