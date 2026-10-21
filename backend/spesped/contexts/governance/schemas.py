"""Typed governance commands. No expression evaluation or inferred legal timings."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from spesped.domain.primitives import instant

class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Fact = Literal['school_kind', 'curriculum_scheme', 'support_entitlement', 'procedure_type', 'school_approval_id', 'learner_grade', 'case_type', 'academic_year']
SchoolFact = Literal['school_kind', 'curriculum_scheme', 'school_approval_id', 'academic_year']
Scalar = str | int | bool

class Condition(Command):
    fact: Fact
    equals: Scalar

class DeadlineRule(Command):
    kind: Literal['fixed_date', 'calendar_period', 'immediate', 'without_undue_delay', 'unresolved']
    legal_basis: Text
    fixed_date: date | None = None
    count: Annotated[int, Field(ge=1, le=3660)] | None = None
    unit: Literal['days', 'weeks', 'months'] | None = None
    calendar: Literal['calendar_days', 'school_days'] | None = None
    start: Literal['event_date', 'provided_start'] | None = None
    @model_validator(mode='after')
    def shape(self):
        if self.kind == 'calendar_period':
            if self.count is None or self.unit is None or self.calendar is None or self.start is None:
                raise ValueError('A period needs count, unit, calendar and start basis')
            if self.calendar == 'school_days' and self.unit != 'days':
                raise ValueError('School calendars count explicit days only')
        elif any(x is not None for x in (self.count, self.unit, self.calendar, self.start)):
            raise ValueError('Period fields require a calendar period')
        if self.fixed_date is not None and self.kind != 'fixed_date':
            raise ValueError('Fixed date belongs only to fixed date rules')
        return self

class RequirementCreate(Command):
    code: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.-]+$')]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    source_type: Literal['law', 'guidance', 'local_routine', 'optional_product']
    source_reference: Text
    candidate_id: UUID | None = None

class RequirementRevision(Command):
    expected_version: int = Field(ge=1)
    valid_from: date
    valid_until: date | None = None
    conditions: list[Condition] = Field(max_length=30)
    trigger_type: Annotated[str, Field(min_length=1, max_length=100)]
    deadline: DeadlineRule
    required_action: Text
    required_document_types: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=30)
    accountable_role: Annotated[str, Field(min_length=1, max_length=100)]
    interpretation_notes: Text
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until is not None and self.valid_until < self.valid_from: raise ValueError('Invalid effective period')
        if len({c.fact for c in self.conditions}) != len(self.conditions): raise ValueError('Repeated applicability fact')
        return self

class Review(Command):
    expected_version: int = Field(ge=1)
    rationale: Text

class ProfileCreate(Command):
    label: Annotated[str, Field(min_length=1, max_length=200)]
    requirement_version_ids: list[UUID] = Field(min_length=1, max_length=200)
    school_inputs: dict[SchoolFact, Scalar] = Field(default_factory=dict)
    valid_from: date
    valid_until: date | None = None
    supersedes_profile_id: UUID | None = None
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until is not None and self.valid_until < self.valid_from: raise ValueError('Invalid effective period')
        if len(set(self.requirement_version_ids)) != len(self.requirement_version_ids): raise ValueError('Duplicate rules')
        return self

class ProfileActivation(Review):
    impact_digest: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]

class TimingInputs(Command):
    start_date: date | None = None
    deadline_date: date | None = None
    calendar_reference: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    # An explicit reviewed calendar interval, never an assumed Monday–Friday week.
    calendar_valid_from: date | None = None
    calendar_valid_until: date | None = None
    school_dates: list[date] = Field(default_factory=list, max_length=4000)
    @model_validator(mode='after')
    def calendar_shape(self):
        if self.school_dates or self.calendar_reference:
            if not self.calendar_reference or not self.calendar_valid_from or not self.calendar_valid_until:
                raise ValueError('Calendar needs source and covered interval')
            if self.calendar_valid_from > self.calendar_valid_until: raise ValueError('Invalid calendar interval')
            if len(self.school_dates) != len(set(self.school_dates)): raise ValueError('Duplicate school date')
            if any(not self.calendar_valid_from <= d <= self.calendar_valid_until for d in self.school_dates): raise ValueError('School day outside calendar interval')
        return self

class Trigger(Command):
    event_key: Annotated[str, Field(min_length=1, max_length=200)]
    profile_id: UUID
    event_type: Annotated[str, Field(min_length=1, max_length=100)]
    occurred_at: datetime
    learner_id: UUID | None = None
    case_id: UUID | None = None
    period_key: Annotated[str, Field(min_length=1, max_length=100)]
    inputs: dict[Fact, Scalar | None] = Field(default_factory=dict)
    timing: TimingInputs = Field(default_factory=TimingInputs)
    @field_validator('occurred_at')
    @classmethod
    def aware(cls, value): return instant(value)
    @model_validator(mode='after')
    def scope(self):
        if self.case_id and not self.learner_id: raise ValueError('Case tasks require learner scope')
        return self

class Assignment(Command):
    expected_version: int = Field(ge=1)
    owner_id: UUID | None
    internal_planned_date: date | None = None
    reason: Text

class ResolveInputs(Command):
    expected_version: int = Field(ge=1)
    inputs: dict[Fact, Scalar | None]
    timing: TimingInputs
    reason: Text

class ActionSubmission(Command):
    expected_version: int = Field(ge=1)
    kind: Literal['performed_action', 'document_upload']
    action_type: Annotated[str, Field(min_length=1, max_length=100)]
    description: Text
    occurred_at: datetime
    evidence_references: list[UUID] = Field(default_factory=list, max_length=50)
    @field_validator('occurred_at')
    @classmethod
    def aware(cls, value): return instant(value)

    @model_validator(mode='after')
    def actual_document_reference(self):
        if self.kind == 'document_upload' and not self.evidence_references:
            raise ValueError('A document attribution requires a validated source reference')
        return self

class TaskReview(Review):
    decision: Literal['satisfied', 'reopen']

class DeviationCreate(Command):
    obligation_id: UUID
    issue_type: Literal['missing_delivery', 'missing_owner', 'missed_deadline', 'insufficient_evidence', 'other']
    description: Text
    owner_id: UUID | None = None

class DeviationAction(Command):
    expected_version: int = Field(ge=1)
    action: Literal['followup', 'resolve', 'reopen', 'reassign']
    explanation: Text
    performed_action_id: UUID | None = None
    owner_id: UUID | None = None

class StudyCreate(Command):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    task_type: Literal['session_preparation', 'assistant_brief', 'observation_note', 'report', 'communication']
    protocol: Text
    quality_rubric: Text
    minimum_quality: int = Field(ge=1, le=5)

class StudyParticipation(Command):
    consent: bool
    expected_version: int = Field(default=0, ge=0)

class Measurement(Command):
    previous_measurement_id: UUID | None = None
    match_key: Annotated[str, Field(min_length=1, max_length=100)]
    mode: Literal['manual', 'assisted']
    complexity: Literal['low', 'medium', 'high']
    scenario: Annotated[str, Field(min_length=1, max_length=200)]
    # Nullable values explicitly describe incomplete measurements.
    primary_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    review_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    correction_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    duplicate_entry_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    followup_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    quality: int | None = Field(default=None, ge=1, le=5)
    comprehension: int | None = Field(default=None, ge=1, le=5)
    usefulness: int | None = Field(default=None, ge=1, le=5)
