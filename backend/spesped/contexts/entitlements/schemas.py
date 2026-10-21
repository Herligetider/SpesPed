from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Retry(Command):
    request_key: str = Field(min_length=1, max_length=120)


class Expected(Retry):
    expected_version: int = Field(ge=1)


class SourceBinding(Command):
    evidence_id: UUID
    evidence_revision: int = Field(ge=1)
    link_id: UUID


class Period(Command):
    effective_from: AwareDatetime
    effective_until: AwareDatetime

    @model_validator(mode='after')
    def period_valid(self):
        if self.effective_from >= self.effective_until:
            raise ValueError('The end must follow the start')
        return self


Category = Literal['individually_adapted_education', 'personal_assistance', 'physical_adaptation']


class ProvisionInput(Period):
    clause: str = Field(min_length=1, max_length=160)
    category: Category
    subject: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)
    organization: str = Field(min_length=1, max_length=5000)
    competence: str = Field(min_length=1, max_length=5000)
    amount: Decimal | None = Field(default=None, ge=0, le=100000, max_digits=14, decimal_places=4)
    unit: Literal['minutes', 'hours'] | None = None
    counting_basis: Literal['learner_time', 'staff_time'] | None = None
    source: SourceBinding

    @model_validator(mode='after')
    def complete_quantity(self):
        if (self.amount is None) != (self.unit is None) or (self.amount is None) != (self.counting_basis is None):
            raise ValueError('Amount, unit and counting basis must all be supplied together')
        if self.category != 'physical_adaptation' and self.amount is None:
            raise ValueError('Education and personal assistance require an explicit quantity')
        return self


class CreateCase(Retry):
    concern: str = Field(min_length=1, max_length=10000)
    owner_id: UUID
    purpose: Literal['educational_support'] = 'educational_support'


class CaseUpdate(Expected):
    concern: str = Field(min_length=1, max_length=10000)
    owner_id: UUID
    state: Literal['preparation','awaiting_basis','follow_up','closed']


class ConsentInput(Retry):
    kind: Literal['education_action','disclosure_permission','processing_basis']
    purpose: str = Field(min_length=1, max_length=160)
    action_scope: Literal['referral_submission', 'decision_preparation', 'plan_participation']
    representative: str = Field(min_length=1, max_length=320)
    representative_capacity: str = Field(min_length=1, max_length=5000)
    valid_from: AwareDatetime
    valid_until: AwareDatetime | None = None
    source: SourceBinding

    @model_validator(mode='after')
    def consent_period(self):
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError('The end must follow the start')
        return self


class Reason(Expected):
    reason: str = Field(min_length=1, max_length=2000)


class ReferralContent(Command):
    concern: str = Field(min_length=1, max_length=10000)
    prior_measures: str = Field(min_length=1, max_length=10000)
    observed_outcomes: str = Field(min_length=1, max_length=10000)
    requested_assessment: str = Field(min_length=1, max_length=10000)
    learner_view: str = Field(min_length=1, max_length=5000)
    guardian_view: str = Field(min_length=1, max_length=5000)
    recipient: str = Field(min_length=1, max_length=320)
    sources: list[SourceBinding] = Field(min_length=1, max_length=100)
    consent_ids: list[UUID] = Field(max_length=20)
    permission_requirement: Literal['required','not_required_with_basis']
    permission_basis: str = Field(min_length=1, max_length=5000)
    disclosure_requirement: Literal['required','not_required_with_basis']
    disclosure_permission_ids: list[UUID] = Field(max_length=20)
    disclosure_basis: str = Field(min_length=1, max_length=5000)
    processing_basis_id: UUID


class CreateReferral(ReferralContent, Retry): pass
class ReviseReferral(ReferralContent, Expected): pass


class ExactReview(Expected):
    content_digest: str = Field(pattern='^[a-f0-9]{64}$')
    reason: str = Field(min_length=1, max_length=2000)


class ContactInput(Expected):
    kind: Literal['submission','receipt','follow_up']
    actual_contact: bool
    occurred_at: AwareDatetime
    recipient: str = Field(min_length=1, max_length=320)
    channel: Literal['secure_external_system','in_person','telephone','planned']
    external_reference: str | None = Field(default=None, min_length=1, max_length=320)
    note: str = Field(min_length=1, max_length=5000)
    source: SourceBinding | None = None

    @model_validator(mode='after')
    def actual_proof(self):
        if self.actual_contact and (self.channel == 'planned' or self.source is None or not self.external_reference):
            raise ValueError('Actual contact requires dated source and external reference')
        if self.kind in {'submission','receipt'} and not self.actual_contact:
            raise ValueError('A submission or receipt must be an actual contact')
        if not self.actual_contact and self.channel != 'planned':
            raise ValueError('Future tasks use the planned channel')
        return self


class RecommendationInput(Period):
    category: Category
    subject: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=10000)
    amount: Decimal | None = Field(default=None, ge=0, le=100000, max_digits=14, decimal_places=4)
    unit: Literal['minutes','hours'] | None = None
    counting_basis: Literal['learner_time','staff_time'] | None = None
    source: SourceBinding

    @model_validator(mode='after')
    def complete_quantity(self):
        if (self.amount is None) != (self.unit is None) or (self.amount is None) != (self.counting_basis is None):
            raise ValueError('Quantity requires amount, unit and counting basis')
        return self


class AssessmentInput(Retry):
    issuer: str = Field(min_length=1, max_length=320)
    assessment_at: AwareDatetime
    valid_until: AwareDatetime | None = None
    source: SourceBinding
    recommendations: list[RecommendationInput] = Field(min_length=1, max_length=100)


class DecisionContent(Period):
    issuing_authority: str = Field(min_length=1, max_length=320)
    authority_basis: str = Field(min_length=1, max_length=5000)
    issued_at: AwareDatetime
    source: SourceBinding
    provisions: list[ProvisionInput] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def within_decision(self):
        if len({p.clause for p in self.provisions}) != len(self.provisions):
            raise ValueError('Each provision requires a distinct clause')
        for p in self.provisions:
            if p.effective_from < self.effective_from or p.effective_until > self.effective_until:
                raise ValueError('A provision must fit inside its decision period')
        return self


class DecisionInput(DecisionContent, Retry): pass
class DecisionUpdate(DecisionContent, Expected): pass


class ClarificationInput(Retry):
    kind: Literal['missing_decision','unclear_unit','contradictory_period','recommendation_difference','source_review','other']
    description: str = Field(min_length=1,max_length=5000)
    due_at: AwareDatetime | None = None
    source: SourceBinding | None = None


class ResolveClarification(Expected):
    resolution: str = Field(min_length=1,max_length=5000)
