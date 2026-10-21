"""BC01 professional records with immutable human decisions and event receipts."""
from datetime import datetime,date
from sqlalchemy import String,Integer,JSON,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,Text,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from spesped.db import Base,UTCDateTime,utcnow
from spesped.contexts.identity.models import Aggregate,new_id
class Tenant:
    school_id:Mapped[str]=mapped_column(ForeignKey('identity_schools.id'),index=True)
class Row(Tenant):
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=utcnow)
class ProfessionalRecord(Aggregate,Tenant,Base):
    __tablename__='administration_professional_records'
    kind:Mapped[str]=mapped_column(String(30))
    learner_id:Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    person_id:Mapped[str|None]=mapped_column(ForeignKey('identity_users.id'),nullable=True,index=True)
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint("state IN ('draft','reviewed','revoked')"),CheckConstraint("kind IN ('qualification','responsibility','assessment_policy','teaching_review','assessment_review')"))
class ProfessionalRevision(Row,Base):
    __tablename__='administration_professional_revisions'
    record_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    authored_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('record_id','number'),ForeignKeyConstraint(['school_id','record_id'],['administration_professional_records.school_id','administration_professional_records.id']))
class ProfessionalCheck(Row,Base):
    __tablename__='administration_professional_checks'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority_action:Mapped[str]=mapped_column(String(100))
    reason:Mapped[str]=mapped_column(Text)
    source_checked_on:Mapped[date]=mapped_column()
    outcome:Mapped[str]=mapped_column(String(20))
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['administration_professional_revisions.school_id','administration_professional_revisions.id']),CheckConstraint("outcome IN ('eligible','ineligible','unresolved')"))
class ProfessionalRevocation(Row,Base):
    __tablename__='administration_professional_revocations'
    record_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    revoked_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','record_id'),ForeignKeyConstraint(['school_id','record_id'],['administration_professional_records.school_id','administration_professional_records.id']),ForeignKeyConstraint(['school_id','revision_id'],['administration_professional_revisions.school_id','administration_professional_revisions.id']))
class ProfessionalCommand(Row,Base):
    __tablename__='administration_professional_commands'
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    request_key:Mapped[str]=mapped_column(String(120))
    digest:Mapped[str]=mapped_column(String(64))
    target_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','actor_id','request_key'),)
class ProfessionalEvent(Row,Base):
    __tablename__='administration_professional_outbox'
    aggregate_id:Mapped[str]=mapped_column(String(36))
    aggregate_version:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    event_type:Mapped[str]=mapped_column(String(100))
    payload:Mapped[dict]=mapped_column(JSON)
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    recorded_at:Mapped[datetime]=mapped_column(UTCDateTime())
    correlation_id:Mapped[str]=mapped_column(String(36))
    causation_id:Mapped[str]=mapped_column(String(120))
    schema_version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('schema_version >= 1'),)
for cls in (ProfessionalRevision,ProfessionalCheck,ProfessionalRevocation,ProfessionalCommand):
    @event.listens_for(cls,'before_update')
    def immutable(mapper,connection,target):
        if any(inspect(target).attrs[c.key].history.has_changes() for c in mapper.columns):raise ValueError('Professional history is immutable; append a revision')
    @event.listens_for(cls,'before_delete')
    def retained(mapper,connection,target):raise ValueError('Professional history must be retained')
