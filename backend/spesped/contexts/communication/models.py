"""Tenant scoped communication state and retained immutable histories."""
from datetime import datetime
from sqlalchemy import String,Integer,JSON,Text,LargeBinary,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from spesped.db import Base,UTCDateTime,utcnow
from spesped.contexts.identity.models import Aggregate,new_id
class Tenant:
    school_id:Mapped[str]=mapped_column(ForeignKey('identity_schools.id'),index=True)
class Row(Tenant):
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime(),default=utcnow)
class ChannelPolicy(Aggregate,Tenant,Base):
    __tablename__='communication_channel_policies'
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),)
class ChannelRevision(Row,Base):
    __tablename__='communication_channel_revisions'
    policy_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    settings:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('policy_id','number'),ForeignKeyConstraint(['school_id','policy_id'],['communication_channel_policies.school_id','communication_channel_policies.id']))
class ChannelReview(Row,Base):
    __tablename__='communication_channel_reviews'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['communication_channel_revisions.school_id','communication_channel_revisions.id']))
class RecipientClearance(Aggregate,Tenant,Base):
    __tablename__='communication_recipient_clearances'
    learner_id:Mapped[str]=mapped_column(String(36))
    relationship_id:Mapped[str]=mapped_column(String(36))
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']))
class RecipientRevision(Row,Base):
    __tablename__='communication_recipient_revisions'
    clearance_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    settings:Mapped[dict]=mapped_column(JSON)
    relationship_binding:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('clearance_id','number'),ForeignKeyConstraint(['school_id','clearance_id'],['communication_recipient_clearances.school_id','communication_recipient_clearances.id']))
class RecipientReview(Row,Base):
    __tablename__='communication_recipient_reviews'
    revision_id:Mapped[str]=mapped_column(String(36))
    digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['communication_recipient_revisions.school_id','communication_recipient_revisions.id']))
class DisclosurePackage(Aggregate,Tenant,Base):
    __tablename__='communication_packages'
    learner_id:Mapped[str]=mapped_column(String(36))
    owner_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    current_revision:Mapped[int]=mapped_column(Integer,default=1)
    corrects_dispatch_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','learner_id'],['identity_learners.school_id','identity_learners.id']),CheckConstraint("state IN ('draft','content_reviewed','authorized','revoked')"))
class PackageRevision(Row,Base):
    __tablename__='communication_package_revisions'
    package_id:Mapped[str]=mapped_column(String(36))
    number:Mapped[int]=mapped_column(Integer)
    manifest:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    content_digest:Mapped[str]=mapped_column(String(64))
    author_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('package_id','number'),ForeignKeyConstraint(['school_id','package_id'],['communication_packages.school_id','communication_packages.id']))
class Attachment(Row,Base):
    __tablename__='communication_attachments'
    revision_id:Mapped[str]=mapped_column(String(36))
    filename:Mapped[str]=mapped_column(String(200))
    content_type:Mapped[str]=mapped_column(String(100))
    data:Mapped[bytes]=mapped_column(LargeBinary)
    digest:Mapped[str]=mapped_column(String(64))
    source_revision_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']),ForeignKeyConstraint(['school_id','source_revision_id'],['documents_revisions.school_id','documents_revisions.id']))
class ContentReview(Row,Base):
    __tablename__='communication_content_reviews'
    revision_id:Mapped[str]=mapped_column(String(36))
    content_digest:Mapped[str]=mapped_column(String(64))
    reviewer_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']))
class RecipientAuthorization(Row,Base):
    __tablename__='communication_authorizations'
    revision_id:Mapped[str]=mapped_column(String(36))
    package_digest:Mapped[str]=mapped_column(String(64))
    approver_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    authority:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']))
class Dispatch(Aggregate,Tenant,Base):
    __tablename__='communication_dispatches'
    package_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    sender_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    latest_attempt_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    provider_reference:Mapped[str|None]=mapped_column(String(200),nullable=True)
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','revision_id'),ForeignKeyConstraint(['school_id','package_id'],['communication_packages.school_id','communication_packages.id']),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']),CheckConstraint("state IN ('queued','sending','accepted','failed','unknown')"))
class DispatchAttempt(Row,Base):
    __tablename__='communication_attempts'
    dispatch_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    submission_key:Mapped[str]=mapped_column(String(36),unique=True)
    provider_key:Mapped[str]=mapped_column(String(100))
    configuration_digest:Mapped[str]=mapped_column(String(64))
    package_digest:Mapped[str]=mapped_column(String(64))
    sender_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    __table_args__=(UniqueConstraint('school_id','id'),ForeignKeyConstraint(['school_id','dispatch_id'],['communication_dispatches.school_id','communication_dispatches.id']),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']))
class DeliveryReceipt(Row,Base):
    __tablename__='communication_receipts'
    dispatch_id:Mapped[str]=mapped_column(String(36))
    attempt_id:Mapped[str]=mapped_column(String(36))
    outcome:Mapped[str]=mapped_column(String(30))
    provider_reference:Mapped[str|None]=mapped_column(String(200),nullable=True)
    reason_code:Mapped[str]=mapped_column(String(100))
    __table_args__=(ForeignKeyConstraint(['school_id','dispatch_id'],['communication_dispatches.school_id','communication_dispatches.id']),ForeignKeyConstraint(['school_id','attempt_id'],['communication_attempts.school_id','communication_attempts.id']),CheckConstraint("outcome IN ('sending','accepted','failed','unknown','not_found')"))
class ExportRecord(Row,Base):
    __tablename__='communication_exports'
    revision_id:Mapped[str]=mapped_column(String(36))
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    mode:Mapped[str]=mapped_column(String(30))
    package_digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']),CheckConstraint("mode IN ('copied','exported')"))
class PortalAccessGrant(Aggregate,Tenant,Base):
    __tablename__='communication_portal_grants'
    dispatch_id:Mapped[str]=mapped_column(String(36))
    revision_id:Mapped[str]=mapped_column(String(36))
    guardian_user_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    expires_at:Mapped[datetime]=mapped_column(UTCDateTime())
    __table_args__=(UniqueConstraint('school_id','id'),UniqueConstraint('school_id','dispatch_id'),ForeignKeyConstraint(['school_id','dispatch_id'],['communication_dispatches.school_id','communication_dispatches.id']),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']),CheckConstraint("state IN ('active','revoked')"))
class PortalSessionGrant(Row,Base):
    __tablename__='communication_portal_session_grants'
    grant_id:Mapped[str]=mapped_column(String(36))
    session_id:Mapped[str]=mapped_column(ForeignKey('identity_login_sessions.id'))
    __table_args__=(UniqueConstraint('school_id','grant_id','session_id'),ForeignKeyConstraint(['school_id','grant_id'],['communication_portal_grants.school_id','communication_portal_grants.id']))
class PortalReadReceipt(Row,Base):
    __tablename__='communication_portal_reads'
    grant_id:Mapped[str]=mapped_column(String(36))
    session_id:Mapped[str]=mapped_column(ForeignKey('identity_login_sessions.id'))
    guardian_user_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    revision_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','grant_id','session_id'),ForeignKeyConstraint(['school_id','grant_id'],['communication_portal_grants.school_id','communication_portal_grants.id']),ForeignKeyConstraint(['school_id','revision_id'],['communication_package_revisions.school_id','communication_package_revisions.id']))
class CommunicationCommand(Row,Base):
    __tablename__='communication_commands'
    actor_id:Mapped[str]=mapped_column(ForeignKey('identity_users.id'))
    request_key:Mapped[str]=mapped_column(String(100))
    operation:Mapped[str]=mapped_column(String(100))
    digest:Mapped[str]=mapped_column(String(64))
    target_kind:Mapped[str]=mapped_column(String(30))
    target_id:Mapped[str]=mapped_column(String(36))
    __table_args__=(UniqueConstraint('school_id','actor_id','request_key'),)
class CommunicationEvent(Row,Base):
    __tablename__='communication_outbox'
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
    __table_args__=(CheckConstraint('schema_version >= 1'),)
for _model in (ChannelRevision,ChannelReview,RecipientRevision,RecipientReview,PackageRevision,Attachment,ContentReview,RecipientAuthorization,DispatchAttempt,DeliveryReceipt,ExportRecord,PortalSessionGrant,PortalReadReceipt,CommunicationCommand):
    @event.listens_for(_model,'before_update')
    def immutable(mapper,connection,target):
        if any(inspect(target).attrs[c.key].history.has_changes() for c in mapper.columns):raise ValueError('Communication history is immutable; append a new revision')
    @event.listens_for(_model,'before_delete')
    def retained(mapper,connection,target):raise ValueError('Communication histories must be retained')
