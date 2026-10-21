"""Exact, actor-aware read contracts. Ports never commit the caller's transaction."""
from datetime import date
from typing import Literal, Protocol
from uuid import UUID
from pydantic import AwareDatetime, Field
from sqlalchemy.orm import Session
from spesped.auth import Actor
from .schemas import Value, SourceReference, Digest


class SourceRequest(Value):
    school_id: UUID
    reference: SourceReference
    purpose: Literal['read','use','copy','ai']


class AuthorizedSource(Value):
    request: SourceRequest
    original_digest: Digest
    text: str = Field(max_length=1000000)
    media_type: str


class SourceReadPort(Protocol):
    def resolve(self, db: Session, actor: Actor, request: SourceRequest) -> AuthorizedSource: ...


class DependencyRequest(Value):
    school_id: UUID
    kind: Literal['class_plan','resource','scheme']
    old_revision_id: UUID
    new_revision_id: UUID | None = None
    changed_at: AwareDatetime


class FutureSession(Value):
    request: DependencyRequest
    session_id: UUID
    session_revision_id: UUID
    owner_id: UUID
    learner_ids: list[UUID] = Field(min_length=1,max_length=100)
    planned_at: AwareDatetime


class FutureSessionReadPort(Protocol):
    def upcoming(self,db: Session,actor: Actor,request: DependencyRequest) -> list[FutureSession]: ...
    def validate_decision(self,db: Session,actor: Actor,session: FutureSession,decision: Literal['keep','change'],replacement_session_revision_id: UUID | None) -> bool: ...


class AvailabilityRequest(Value):
    school_id: UUID
    material_id: UUID
    material_version: int = Field(strict=True,ge=1)
    count: int = Field(strict=True,ge=1)
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class MaterialAvailability(Value):
    request: AvailabilityRequest
    state: Literal['available','insufficient','unknown','unavailable']
    available_count: int | None = Field(default=None,strict=True,ge=0)
    checked_at: AwareDatetime | None = None
    reservation_revision: str | None = None


class MaterialReservationPort(Protocol):
    def availability(self,db: Session,actor: Actor,request: AvailabilityRequest) -> MaterialAvailability: ...
