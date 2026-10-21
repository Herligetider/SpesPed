"""Exact bounded commands; clients cannot choose transport destinations or recipients by email."""
from datetime import datetime
from typing import Literal,Annotated
from uuid import UUID
from pydantic import Field,StringConstraints,model_validator,AwareDatetime
from spesped.contexts.documents.schemas import Value,Command,Expected,Tag,Text,Digest,Kind
from spesped.contexts.curriculum.schemas import SourceReference
Filename=Annotated[str,StringConstraints(pattern=r'^[A-Za-z0-9][A-Za-z0-9 _.-]{0,160}\.txt$')]
class ChannelSettings(Value):
    channel:Literal['portal','secure_https','export']
    connection_key:Tag|None=None
    purposes:list[Tag]=Field(min_length=1,max_length=30)
    document_kinds:list[Kind]=Field(min_length=1,max_length=4)
    allow_attachments:bool=False
    portal_lifetime_hours:int=Field(default=168,strict=True,ge=1,le=720)
    expires_at:AwareDatetime
    sources:list[SourceReference]=Field(min_length=1,max_length=20)
    @model_validator(mode='after')
    def connection(self):
        if (self.channel=='secure_https')!=(self.connection_key is not None):raise ValueError('Secure HTTPS requires exactly one trusted operator connection key')
        if any(v.learner_id or v.case_id for v in self.sources):raise ValueError('Channel policy requires school sources')
        return self
class ChannelCreate(Command):settings:ChannelSettings
class ChannelChange(Expected):settings:ChannelSettings
class Review(Expected):
    revision_id:UUID
    content_digest:Digest
    reason:Text
class Revoke(Expected):reason:Text
class RecipientSettings(Value):
    purposes:list[Tag]=Field(min_length=1,max_length=30)
    expires_at:AwareDatetime
    sources:list[SourceReference]=Field(min_length=1,max_length=20)
class RecipientCreate(Command):
    learner_id:UUID
    relationship_id:UUID
    settings:RecipientSettings
class RecipientChange(Expected):settings:RecipientSettings
class AttachmentSelection(Value):
    document_revision_id:UUID
    filename:Filename
class PackageSelection(Value):
    learner_id:UUID
    document_revision_id:UUID
    recipient_revision_id:UUID
    channel_revision_id:UUID
    purpose:Tag
    section_keys:list[Tag]=Field(min_length=1,max_length=40)
    attachments:list[AttachmentSelection]=Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def distinct(self):
        if len(set(self.section_keys))!=len(self.section_keys):raise ValueError('Section selections must be distinct')
        if len({v.filename for v in self.attachments})!=len(self.attachments):raise ValueError('Attachment names must be distinct')
        return self
class PackageCreate(Command):
    selection:PackageSelection
    corrects_dispatch_id:UUID|None=None
class PackageChange(Expected):
    selection:PackageSelection
    reason:Text
class Export(Review):mode:Literal['copied','exported']
class DispatchQueue(Review):pass
class DispatchCommand(Expected):reason:Text
class PortalCommand(Expected):pass
