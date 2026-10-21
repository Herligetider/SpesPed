"""BC09 concrete aggregates with immutable, attributed historical revisions."""
from datetime import datetime,date
from sqlalchemy import String,Integer,JSON,Text,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from spesped.db import Base,UTCDateTime,utcnow
from spesped.contexts.identity.models import Aggregate,new_id

class Tenant:
    school_id:Mapped[str]=mapped_column(ForeignKey('identity_schools.id'),index=True)
class Row(Tenant):
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=utcnow)
class Instrument(Aggregate,Tenant,Base):
    __tablename__='assessment_instruments'
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    owner_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),)
class InstrumentRevision(Row,Base):
    __tablename__='assessment_instrument_revisions'
    instrument_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    authored_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('instrument_id','number'),ForeignKeyConstraint(['school_id','instrument_id'],['assessment_instruments.school_id','assessment_instruments.id']))
class InstrumentReview(Row,Base):
    __tablename__='assessment_instrument_reviews'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['assessment_instrument_revisions.school_id','assessment_instrument_revisions.id']))
class Administration(Aggregate,Tenant,Base):
    __tablename__='assessment_administrations'
    learner_id:Mapped[str]=mapped_column(String(36),index=True)
    instrument_revision_id:Mapped[str]=mapped_column(String(36))
    planned_on:Mapped[date]=mapped_column()
    purpose:Mapped[str]=mapped_column(Text)
    conditions:Mapped[dict]=mapped_column(JSON)
    eligibility:Mapped[dict]=mapped_column(JSON)
    started_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)
    current_result:Mapped[int]=mapped_column(Integer,default=0)
    abort_reason:Mapped[str|None]=mapped_column(Text,nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),ForeignKeyConstraint(['school_id','instrument_revision_id'],['assessment_instrument_revisions.school_id','assessment_instrument_revisions.id']),CheckConstraint("state IN ('planned','started','recorded','professionally_reviewed','aborted')"))
class ResultRevision(Row,Base):
    __tablename__='assessment_result_revisions'
    administration_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    raw:Mapped[dict]=mapped_column(JSON)
    conditions:Mapped[dict]=mapped_column(JSON)
    recorded_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    correction_reason:Mapped[str|None]=mapped_column(Text,nullable=True)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('administration_id','number'),ForeignKeyConstraint(['school_id','administration_id'],['assessment_administrations.school_id','assessment_administrations.id']))
class ResultReview(Row,Base):
    __tablename__='assessment_result_reviews'
    result_revision_id:Mapped[str]=mapped_column(String(36))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    interpretation:Mapped[str]=mapped_column(Text)
    comparison:Mapped[str]=mapped_column(String(30))
    comparison_reason:Mapped[str]=mapped_column(Text)
    competence:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('school_id','result_revision_id'),ForeignKeyConstraint(['school_id','result_revision_id'],['assessment_result_revisions.school_id','assessment_result_revisions.id']))
class FollowUp(Aggregate,Tenant,Base):
    __tablename__='assessment_follow_ups'
    administration_id:Mapped[str]=mapped_column(String(36))
    result_revision_id:Mapped[str]=mapped_column(String(36))
    proposed_on:Mapped[date|None]=mapped_column(nullable=True)
    selected_on:Mapped[date|None]=mapped_column(nullable=True)
    guidance:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    decided_by:Mapped[str|None]=mapped_column(ForeignKey('identity_users.id'),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','result_revision_id'),ForeignKeyConstraint(['school_id','administration_id'],['assessment_administrations.school_id','assessment_administrations.id']),ForeignKeyConstraint(['school_id','result_revision_id'],['assessment_result_revisions.school_id','assessment_result_revisions.id']))
class ProgressReview(Aggregate,Tenant,Base):
    __tablename__='assessment_progress_reviews'
    learner_id:Mapped[str]=mapped_column(String(36),index=True)
    goal_revision_id:Mapped[str]=mapped_column(String(36))
    starts_at:Mapped[datetime]=mapped_column(UTCDateTime())
    ends_at:Mapped[datetime]=mapped_column(UTCDateTime())
    snapshot:Mapped[dict]=mapped_column(JSON)
    snapshot_digest:Mapped[str]=mapped_column(String(64))
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint('ends_at > starts_at'))
class ProgressRevision(Row,Base):
    __tablename__='assessment_progress_revisions'
    review_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    finding:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    status:Mapped[str]=mapped_column(String(30))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('review_id','number'),ForeignKeyConstraint(['school_id','review_id'],['assessment_progress_reviews.school_id','assessment_progress_reviews.id']))
class Statement(Aggregate,Tenant,Base):
    __tablename__='assessment_statements'
    learner_id:Mapped[str]=mapped_column(String(36),index=True)
    scheme_revision_id:Mapped[str]=mapped_column(String(36),nullable=True)
    subject:Mapped[str]=mapped_column(String(100))
    assessment_type:Mapped[str]=mapped_column(String(30))
    starts_on:Mapped[date]=mapped_column()
    ends_on:Mapped[date]=mapped_column()
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint('ends_on >= starts_on'))
class StatementRevision(Row,Base):
    __tablename__='assessment_statement_revisions'
    statement_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('statement_id','number'),ForeignKeyConstraint(['school_id','statement_id'],['assessment_statements.school_id','assessment_statements.id']))
class Contribution(Row,Base):
    __tablename__='assessment_contributions'
    statement_id:Mapped[str]=mapped_column(String(36))
    statement_revision_id:Mapped[str]=mapped_column(String(36))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    kind:Mapped[str]=mapped_column(String(30))
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    content:Mapped[str]=mapped_column(Text)
    sources:Mapped[list]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','statement_id'],['assessment_statements.school_id','assessment_statements.id']),ForeignKeyConstraint(['school_id','statement_revision_id'],['assessment_statement_revisions.school_id','assessment_statement_revisions.id']))
class StatementFinalization(Row,Base):
    __tablename__='assessment_statement_finalizations'
    statement_revision_id:Mapped[str]=mapped_column(String(36))
    revision_digest:Mapped[str]=mapped_column(String(64))
    authorized_person_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority_binding:Mapped[dict]=mapped_column(JSON)
    grade:Mapped[str|None]=mapped_column(String(100),nullable=True)
    grade_authority:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    contribution_ids:Mapped[list]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','statement_revision_id'),ForeignKeyConstraint(['school_id','statement_revision_id'],['assessment_statement_revisions.school_id','assessment_statement_revisions.id']))
class Communication(Row,Base):
    __tablename__='assessment_communications'
    statement_revision_id:Mapped[str]=mapped_column(String(36))
    recorded_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    destination:Mapped[str]=mapped_column(String(30))
    method:Mapped[str]=mapped_column(String(100))
    factual_reference:Mapped[str]=mapped_column(Text)
    __table_args__=(ForeignKeyConstraint(['school_id','statement_revision_id'],['assessment_statement_revisions.school_id','assessment_statement_revisions.id']),)
class AssessmentCommand(Row,Base):
    __tablename__='assessment_commands'
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    request_key:Mapped[str]=mapped_column(String(120))
    operation:Mapped[str]=mapped_column(String(100))
    digest:Mapped[str]=mapped_column(String(64))
    target_kind:Mapped[str]=mapped_column(String(30))
    target_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','actor_id','request_key'),)
class AssessmentEvent(Row,Base):
    __tablename__='assessment_outbox'
    aggregate_id:Mapped[str]=mapped_column(String(36))
    aggregate_version:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    event_type:Mapped[str]=mapped_column(String(100))
    payload:Mapped[dict]=mapped_column(JSON,default=dict)
    causation_id:Mapped[str]=mapped_column(String(120))
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    recorded_at:Mapped[datetime]=mapped_column(UTCDateTime())
    correlation_id:Mapped[str]=mapped_column(String(36))
    schema_version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('schema_version >= 0',name='ck_assessment_event_schema_version'),)
    processed_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)

_IMMUTABLE=(InstrumentRevision,InstrumentReview,ResultRevision,ResultReview,ProgressRevision,StatementRevision,Contribution,StatementFinalization,Communication)
for _model in _IMMUTABLE:
    @event.listens_for(_model,'before_update')
    def _immutable(mapper,connection,target):
        if any(inspect(target).attrs[c.key].history.has_changes() for c in mapper.columns):
            raise ValueError('Assessment history is immutable; append an attributed revision.')
    @event.listens_for(_model,'before_delete')
    def _undeletable(mapper,connection,target):
        raise ValueError('Assessment history cannot be deleted through a business session.')


@event.listens_for(ProgressReview,'before_update')
def _frozen_snapshot(mapper,connection,target):
    for name in ('learner_id','goal_revision_id','starts_at','ends_at','snapshot','snapshot_digest'):
        if inspect(target).attrs[name].history.has_changes():raise ValueError('Progress snapshots are immutable; create a new review for new evidence.')
