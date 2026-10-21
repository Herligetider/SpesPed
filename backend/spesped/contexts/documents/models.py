"""Tenant-scoped aggregates and immutable authored, source and review histories."""
from datetime import datetime
from sqlalchemy import String,Integer,JSON,Text,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from spesped.db import Base,UTCDateTime,utcnow
from spesped.contexts.identity.models import Aggregate,new_id
class Tenant:
    school_id:Mapped[str]=mapped_column(ForeignKey('identity_schools.id'),index=True)
class Row(Tenant):
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=utcnow)
class Template(Aggregate,Tenant,Base):
    __tablename__='documents_templates'
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),)
class TemplateRevision(Row,Base):
    __tablename__='documents_template_revisions'
    template_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('template_id','number'),ForeignKeyConstraint(['school_id','template_id'],['documents_templates.school_id','documents_templates.id']))
class TemplateReview(Row,Base):
    __tablename__='documents_template_reviews'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['documents_template_revisions.school_id','documents_template_revisions.id']))
class DocumentCase(Aggregate,Tenant,Base):
    __tablename__='documents_cases'
    learner_id:Mapped[str]=mapped_column(String(36),index=True)
    owner_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    kind:Mapped[str]=mapped_column(String(40))
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint("state IN ('draft','waiting_contributions','in_review','approved','discarded')"))
class EvidenceSnapshot(Row,Base):
    __tablename__='documents_snapshots'
    document_id:Mapped[str]=mapped_column(String(36))
    learner_id:Mapped[str]=mapped_column(String(36))
    cutoff:Mapped[datetime]=mapped_column(UTCDateTime())
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','document_id'],['documents_cases.school_id','documents_cases.id']),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']))
class DocumentRevision(Row,Base):
    __tablename__='documents_revisions'
    document_id:Mapped[str]=mapped_column(String(36))
    snapshot_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    configuration:Mapped[dict]=mapped_column(JSON)
    content:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    lineage:Mapped[dict]=mapped_column(JSON,default=dict)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('document_id','number'),ForeignKeyConstraint(['school_id','document_id'],['documents_cases.school_id','documents_cases.id']),ForeignKeyConstraint(['school_id','snapshot_id'],['documents_snapshots.school_id','documents_snapshots.id']))
class ContributionAssignment(Row,Base):
    __tablename__='documents_contribution_assignments'
    revision_id:Mapped[str]=mapped_column(String(36))
    section_key:Mapped[str]=mapped_column(String(100))
    contributor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    required:Mapped[bool]=mapped_column()
    assigned_by:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','revision_id','section_key','contributor_id'),ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']))
class Contribution(Row,Base):
    __tablename__='documents_contributions'
    revision_id:Mapped[str]=mapped_column(String(36))
    section_key:Mapped[str]=mapped_column(String(100))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    kind:Mapped[str]=mapped_column(String(30))
    text:Mapped[str]=mapped_column(Text)
    source_keys:Mapped[list]=mapped_column(JSON)
    __table_args__=(ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']),)
class ContentApproval(Row,Base):
    __tablename__='documents_approvals'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    approver_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    action:Mapped[str]=mapped_column(String(100))
    authority:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']))
class ReviewRecord(Row,Base):
    __tablename__='documents_review_records'
    revision_id:Mapped[str]=mapped_column(String(36))
    action:Mapped[str]=mapped_column(String(30))
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']),)
class ProposalReview(Row,Base):
    __tablename__='documents_proposal_reviews'
    document_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    job_id:Mapped[str]=mapped_column(ForeignKey('platform_generation_jobs.id'))
    proposal_digest:Mapped[str]=mapped_column(String(64))
    outcome:Mapped[str]=mapped_column(String(20))
    selection:Mapped[dict]=mapped_column(JSON)
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','job_id'),ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']),ForeignKeyConstraint(['school_id','document_id'],['documents_cases.school_id','documents_cases.id']))
class EmailDraftSchedule(Aggregate,Tenant,Base):
    __tablename__='documents_email_schedules'
    learner_id:Mapped[str]=mapped_column(String(36))
    owner_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    next_run_at:Mapped[datetime]=mapped_column(UTCDateTime())
    pause_reason:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint("state IN ('inactive','active','paused','ended')"))
class ScheduleRevision(Row,Base):
    __tablename__='documents_schedule_revisions'
    schedule_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    settings:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('schedule_id','number'),ForeignKeyConstraint(['school_id','schedule_id'],['documents_email_schedules.school_id','documents_email_schedules.id']))
class DraftRun(Row,Base):
    __tablename__='documents_draft_runs'
    schedule_revision_id:Mapped[str]=mapped_column(String(36))
    learner_id:Mapped[str]=mapped_column(String(36))
    period_key:Mapped[str]=mapped_column(String(100))
    status:Mapped[str]=mapped_column(String(30))
    summary:Mapped[dict]=mapped_column(JSON)
    document_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','schedule_revision_id','learner_id','period_key'),ForeignKeyConstraint(['school_id','schedule_revision_id'],['documents_schedule_revisions.school_id','documents_schedule_revisions.id']),ForeignKeyConstraint(['school_id','document_id'],['documents_cases.school_id','documents_cases.id']),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']))
class ScheduledGenerationRequest(Aggregate,Tenant,Base):
    __tablename__='documents_scheduled_generation_requests'
    run_id:Mapped[str]=mapped_column(String(36))
    document_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    snapshot_id:Mapped[str]=mapped_column(String(36))
    owner_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    policy_id:Mapped[str]=mapped_column(String(36))
    release_id:Mapped[str]=mapped_column(String(36))
    configuration_binding:Mapped[dict]=mapped_column(JSON)
    logical_key:Mapped[str]=mapped_column(String(120))
    job_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    reason_code:Mapped[str|None]=mapped_column(String(100),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','run_id'),UniqueConstraint('school_id','logical_key'),ForeignKeyConstraint(['school_id','run_id'],['documents_draft_runs.school_id','documents_draft_runs.id']),ForeignKeyConstraint(['school_id','document_id'],['documents_cases.school_id','documents_cases.id']),ForeignKeyConstraint(['school_id','revision_id'],['documents_revisions.school_id','documents_revisions.id']),ForeignKeyConstraint(['school_id','snapshot_id'],['documents_snapshots.school_id','documents_snapshots.id']),ForeignKeyConstraint(['school_id','policy_id'],['platform_processing_policies.school_id','platform_processing_policies.id']),ForeignKeyConstraint(['school_id','release_id'],['platform_model_releases.school_id','platform_model_releases.id']),ForeignKeyConstraint(['school_id','job_id'],['platform_generation_jobs.school_id','platform_generation_jobs.id']),CheckConstraint("state IN ('pending','queued','running','succeeded','failed','blocked')"))
class DocumentCommand(Row,Base):
    __tablename__='documents_commands'
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    request_key:Mapped[str]=mapped_column(String(100))
    operation:Mapped[str]=mapped_column(String(100))
    digest:Mapped[str]=mapped_column(String(64))
    target_kind:Mapped[str]=mapped_column(String(30))
    target_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','actor_id','request_key'),)
class DocumentEvent(Row,Base):
    __tablename__='documents_outbox'
    aggregate_id:Mapped[str]=mapped_column(String(36))
    aggregate_version:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    event_type:Mapped[str]=mapped_column(String(100))
    payload:Mapped[dict]=mapped_column(JSON)
    causation_id:Mapped[str]=mapped_column(String(100))
    occurred_at:Mapped[datetime]=mapped_column(UTCDateTime())
    recorded_at:Mapped[datetime]=mapped_column(UTCDateTime())
    correlation_id:Mapped[str]=mapped_column(String(36))
    schema_version:Mapped[int]=mapped_column(Integer,default=1)
    processed_at:Mapped[datetime|None]=mapped_column(UTCDateTime(),nullable=True)
    __table_args__=(CheckConstraint('schema_version >= 1',name='ck_documents_event_schema_version'),)
for _model in (TemplateRevision,TemplateReview,EvidenceSnapshot,DocumentRevision,ContributionAssignment,Contribution,ContentApproval,ReviewRecord,ProposalReview,ScheduleRevision,DraftRun):
    @event.listens_for(_model,'before_update')
    def immutable(mapper,connection,target):
        if any(inspect(target).attrs[c.key].history.has_changes() for c in mapper.columns):raise ValueError('Document history is immutable; append a revision')
    @event.listens_for(_model,'before_delete')
    def retained(mapper,connection,target):raise ValueError('Document history must be retained')

@event.listens_for(ScheduledGenerationRequest,'before_update')
def frozen_generation_request(mapper,connection,target):
    for name in ('school_id','run_id','document_id','revision_id','snapshot_id','owner_id','policy_id','release_id','configuration_binding','logical_key'):
        if inspect(target).attrs[name].history.has_changes():raise ValueError('Scheduled generation identity, scope and configuration are immutable')
