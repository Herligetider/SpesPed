"""Human-authored facts, judgements and performed actions are distinct commands."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from spesped.domain.primitives import instant

Text = Annotated[str, Field(min_length=1, max_length=12000)]
Short = Annotated[str, Field(min_length=1, max_length=2000)]
About = Literal['pupil','staff','headteacher']
Kind = Literal['environment','concern','physical']
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_key: Annotated[str, Field(min_length=1,max_length=100)]


class Change(Command):
    expected_version: int = Field(ge=1)


class Occurrence(BaseModel):
    occurred_at: datetime
    @field_validator('occurred_at')
    @classmethod
    def aware(cls,v): return instant(v)


class Account(Occurrence):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['own_observation','reported_information','uncertainty','investigation','problem_assessment','contradicting_account']
    statement: Text
    source: Short
    uncertainty: Annotated[str, Field(max_length=12000)] = ''
    corrects_id: UUID | None = None
    correction_reason: Short | None = None
    @model_validator(mode='after')
    def correction(self):
        if bool(self.corrects_id) != bool(self.correction_reason): raise ValueError('Correction needs original account and reason')
        return self


class PupilView(Occurrence):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    statement: Text | None = None
    source: Short
    missing_reason: Text | None = None
    followup_owner_id: UUID | None = None
    followup_due: date | None = None
    @model_validator(mode='after')
    def completeness(self):
        if self.statement is None:
            if not self.missing_reason or not self.followup_owner_id or not self.followup_due:
                raise ValueError('Missing pupil view needs reason, owner and followup date')
        elif any(v is not None for v in (self.missing_reason,self.followup_owner_id,self.followup_due)):
            raise ValueError('A supplied view must not be marked missing')
        return self


class NewCase(Command, Occurrence):
    learner_id: UUID
    about: About = 'pupil'
    excluded_user_ids: list[UUID] = Field(default_factory=list,max_length=30)
    @model_validator(mode='after')
    def exclusion(self):
        if self.about != 'pupil' and not self.excluded_user_ids: raise ValueError('Staff concerns must identify excluded subjects')
        if len(self.excluded_user_ids)!=len(set(self.excluded_user_ids)): raise ValueError('Duplicate excluded person')
        return self


class EnvironmentCreate(NewCase):
    received_concern: Text
    received_from: Short


class ConcernCreate(NewCase):
    author_assessment: Text
    urgency: Literal['concern','urgent','emergency']
    accounts: list[Account] = Field(default_factory=list,max_length=100)


class InvolvedRole(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    person_reference: Short
    role: Short


class PhysicalDuration(BaseModel):
    @model_validator(mode='after')
    def duration_shape(self):
        if self.duration_seconds is None and not self.duration_unknown_reason:raise ValueError('Unknown duration needs an explicit reason')
        if self.duration_seconds is not None and self.duration_unknown_reason is not None:raise ValueError('A measured duration must not be marked unknown')
        return self


class PhysicalCreate(NewCase, PhysicalDuration):
    place: Short
    before_facts: Text
    during_facts: Text
    actual_action: Text
    duration_seconds: int | None = Field(default=None,ge=0,le=86400)
    duration_unknown_reason: Text | None = None
    involved_roles: list[InvolvedRole] = Field(min_length=1,max_length=100)
    observed_consequences: Text
    pupil_view: PupilView


class AddAccount(Change, Account): pass
class AddPupilView(Change, PupilView): pass


class Measure(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    measure: Text
    owner_id: UUID
    planned_date: date
    evaluation_method: Text


class PlanCreate(Change):
    problem_assessment: Text
    evaluation_date: date
    measures: list[Measure] = Field(min_length=1,max_length=100)


class ActualAction(Change, Occurrence):
    description: Text
    outcome: Text
    outcome_state: Literal['observed','unknown','incomplete']
    measure_id: UUID | None = None


class DraftCreate(Change):
    recipient: Short
    purpose: Short
    body: Text


class DraftReview(Change):
    draft_digest: Digest
    rationale: Text


class Contact(Change, Occurrence):
    contact_kind: Literal['notification','personal_contact','emergency_action','submission','information']
    recipient: Short
    channel: Short
    information_shared: Text
    outcome: Literal['performed','attempted','unknown','failed']
    receipt_state: Literal['not_requested','pending','received','unknown']
    receipt_detail: Text
    route_id: UUID | None = None
    route_deviation_reason: Text | None = None
    draft_id: UUID | None = None
    draft_digest: Digest | None = None
    @model_validator(mode='after')
    def draft(self):
        if bool(self.draft_id)!=bool(self.draft_digest): raise ValueError('Draft reference needs exact reviewed digest')
        if self.outcome!='performed' and self.receipt_state=='received': raise ValueError('Receipt cannot imply performed contact when outcome is unknown')
        return self


class FollowupCreate(Change):
    kind: Literal['prevention','contact','pupil_view','investigation','evaluation','other']
    description: Text
    owner_id: UUID
    due_date: date


class FollowupComplete(Change, Occurrence):
    outcome: Text
    state: Literal['performed','unknown','incomplete']


class Review(Change, Occurrence):
    decision: Literal['investigating','evaluating','continue','close','reopen','checked','corrected']
    assessment: Text
    pupil_situation: Text


class Assign(Change):
    owner_id: UUID
    reason: Text


class RouteCreate(Command):
    purpose: Kind
    about: About
    owner_id: UUID
    recipient: Short
    recipient_user_id: UUID | None = None
    channel: Short
    contact_details: Text
    guidance: Text
    valid_from: date
    valid_until: date
    supersedes_id: UUID | None = None
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until<self.valid_from: raise ValueError('Invalid route period')
        return self


class RouteReview(Change):
    digest: Digest
    rationale: Text
    decision: Literal['approve','revoke']

class ReconcileContact(Change, Occurrence):
    outcome: Literal['performed','attempted','unknown','failed']
    receipt_state: Literal['not_requested','pending','received','unknown']
    receipt_detail: Text
    @model_validator(mode='after')
    def shape(self):
        if self.outcome!='performed' and self.receipt_state=='received': raise ValueError('Receipt requires confirmed performed contact')
        return self

class EnvironmentCorrection(Change):
    received_concern: Text
    received_from: Short
    correction_reason: Text

class ConcernCorrection(Change):
    author_assessment: Text
    urgency: Literal['concern','urgent','emergency']
    correction_reason: Text

class PhysicalCorrection(Change, PhysicalDuration):
    place: Short
    before_facts: Text
    during_facts: Text
    actual_action: Text
    duration_seconds: int | None = Field(default=None,ge=0,le=86400)
    duration_unknown_reason: Text | None = None
    involved_roles: list[InvolvedRole] = Field(min_length=1,max_length=100)
    observed_consequences: Text
    correction_reason: Text

class ProtectionChange(Change):
    about: About
    excluded_user_ids: list[UUID] = Field(min_length=1,max_length=30)
    reason: Text
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.excluded_user_ids))!=len(self.excluded_user_ids):raise ValueError('Duplicate excluded person')
        return self
