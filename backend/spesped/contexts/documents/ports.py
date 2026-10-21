"""Future native dispatch records. An unconfigured connection is unresolved."""
from datetime import date
from typing import Literal,Protocol
from uuid import UUID
from pydantic import Field
from sqlalchemy.orm import Session
from spesped.auth import Actor
from .schemas import Value,Digest,Tag
class SentPeriod(Value):
    school_id:UUID
    learner_id:UUID
    dispatch_id:UUID
    document_revision_id:UUID
    package_digest:Digest
    recipient_relationship_id:UUID
    purpose:Tag
    starts_on:date
    ends_on:date
    status:Literal['confirmed_sent']='confirmed_sent'
class DispatchHistoryPort(Protocol):
    def confirmed_periods(self,db:Session,actor:Actor,school_id:str,learner_id:str,recipient_relationship_id:str,purpose:str)->list[SentPeriod]:...
