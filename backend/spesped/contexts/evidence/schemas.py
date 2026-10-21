from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IntakeMetadata(Command):
    request_key: str = Field(min_length=1, max_length=120)
    external_scope: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=320)
    sender: str = Field(min_length=1, max_length=320)
    document_type: str = Field(min_length=1, max_length=80)
    received_at: AwareDatetime
    original_at: AwareDatetime | None = None


class NoteIntake(IntakeMetadata):
    text: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=100_000)


class Expected(Command):
    expected_version: int = Field(ge=1)


FieldName = Literal["content", "learner", "document_date", "goal", "measure", "follow_up", "hours", "document_type"]


def validate_field(name, value):
    if name == "hours":
        try:
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0 or amount > 100000:
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise ValueError("Hours must be a nonnegative finite decimal") from None
    elif name == "document_date":
        from datetime import date
        date.fromisoformat(value)
    elif name == "learner":
        UUID(value)
    return value


class ProposeField(Expected):
    page: int = Field(ge=1, le=200)
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=1)
    field_name: FieldName
    proposed_value: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def typed_field(self):
        validate_field(self.field_name, self.proposed_value)
        return self


class ReviewField(Expected):
    outcome: Literal["accepted", "edited", "rejected"]
    value: str | None = Field(default=None, min_length=1, max_length=20000)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def edit_value(self):
        if (self.outcome == "edited") != (self.value is not None):
            raise ValueError("Only an edit requires a replacement value")
        return self


class Attributed(Command):
    learner_id: UUID
    claim_type: Literal["report", "observation", "professional_judgement"]
    reporter: str = Field(min_length=1, max_length=320)
    observer: str | None = Field(default=None, min_length=1, max_length=320)
    source_type: Literal["direct_observation", "reported_information", "imported_document"]
    certainty: Literal["confirmed", "uncertain", "disputed"]
    occurred_at: AwareDatetime
    topic: str = Field(min_length=1, max_length=100)
    goal_revision_id: UUID | None = None

    @model_validator(mode="after")
    def observer_required(self):
        if self.source_type == "direct_observation" and not self.observer:
            raise ValueError("Direct observation requires an observer")
        return self


class ConfirmEvidence(Attributed, Expected):
    """Each confirmation selects exactly the source span released to this pupil."""
    excerpt_page: int = Field(ge=1, le=200)
    excerpt_start: int = Field(ge=0)
    excerpt_end: int = Field(ge=1)


class CorrectEvidence(Attributed, Expected):
    content: str = Field(min_length=1, max_length=20000)
    reason: str = Field(min_length=1, max_length=1000)
    excerpt_page: int | None = Field(default=None, ge=1, le=200)
    excerpt_start: int | None = Field(default=None, ge=0)
    excerpt_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def replacement_span(self):
        supplied = (self.excerpt_page, self.excerpt_start, self.excerpt_end)
        if any(value is not None for value in supplied) and not all(value is not None for value in supplied):
            raise ValueError("A replacement excerpt requires page, start and end")
        if self.excerpt_start is not None and self.excerpt_start >= self.excerpt_end:
            raise ValueError("A replacement excerpt requires a nonempty span")
        return self


class RegisterDerivative(Command):
    evidence_revision: int = Field(ge=1)
    target_type: str = Field(min_length=1, max_length=80)
    target_id: UUID
    target_revision: int = Field(ge=1)
    state: Literal["draft", "shared"]
