"""Read-only recorded-rule metadata; this port never declares duties fulfilled."""
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ReviewedRuleSource(FrozenContext):
    profile_id: UUID
    profile_version: int = Field(ge=1, strict=True)
    profile_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    requirement_version_id: UUID
    requirement_revision: int = Field(ge=1, strict=True)
    requirement_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    state: Literal['current', 'unreviewed', 'withdrawn', 'profile_revoked', 'ineffective']


class RecordedCaseObligation(FrozenContext):
    id: UUID
    version: int = Field(ge=1, strict=True)
    state: str = Field(min_length=1, max_length=40)
    applicability: Literal['applicable', 'not_applicable', 'unresolved']
    source: ReviewedRuleSource | None
    review_required: bool = Field(strict=True)
    required_action: str | None
    required_document_types: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    deadline_kind: str
    recorded_deadline_date: date | None
    recorded_deadline_at: datetime | None

    @model_validator(mode='after')
    def actionability(self):
        needs_review = (self.source is None or self.source.state != 'current'
                        or self.applicability == 'unresolved' or self.state == 'unresolved')
        if self.review_required != needs_review:
            raise ValueError('Review status must preserve source and applicability uncertainty')
        if (self.required_action or self.required_document_types) and (
            self.review_required or self.applicability != 'applicable'
            or self.state == 'unresolved' or self.source is None or self.source.state != 'current'
        ):
            raise ValueError('Unresolved or recalled requirements cannot be presented as actionable')
        return self


class ReviewedRuleContext(FrozenContext):
    state: Literal['available', 'review_required', 'unavailable']
    obligations: tuple[RecordedCaseObligation, ...] = ()
    coverage: Literal['authorized_recorded_obligations_only'] = 'authorized_recorded_obligations_only'
    legal_completeness: Literal['not_assessed'] = 'not_assessed'

    @model_validator(mode='after')
    def consistent_state(self):
        expected = ('unavailable' if not self.obligations else 'review_required'
                    if any(item.review_required for item in self.obligations) else 'available')
        if self.state != expected:
            raise ValueError('Rule availability must match its recorded obligations')
        return self


class ReviewedRuleContextResolver(Protocol):
    def __call__(self, db, actor, school_id: str, learner_id: str, case_id: str) -> ReviewedRuleContext:
        """Reauthorize exact case/task access and return recorded rule metadata.

        Registered as app.state.safeguarding_rule_context or the corresponding
        db.info entry. Do not commit, create tasks, infer notification duties or
        flatten multiple historical profiles into a single current profile.
        Expected unavailable/denied context raises DomainError; the authorized
        protected dossier remains readable with an unavailable rule projection.
        """
        ...
