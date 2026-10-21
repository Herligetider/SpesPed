from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from spesped.contexts.entitlements.schemas import Command, Expected, Retry, Period, SourceBinding


class ProfileInput(Retry):
    category: Literal['strength','interest','language','communication','support_strategy']
    content: str = Field(min_length=1, max_length=5000)
    source: SourceBinding
    observed_at: AwareDatetime
    replaces_id: UUID | None = None


class ProfileReviewInput(Expected):
    outcome: Literal['confirmed','disputed','rejected']
    reason: str = Field(min_length=1, max_length=2000)


class GoalInput(Period):
    goal_id: UUID | None = None
    parent_goal_id: UUID | None = None
    status: Literal['active','closed'] = 'active'
    title: str = Field(min_length=1, max_length=320)
    expected_action: str = Field(min_length=1, max_length=10000)
    arena: str = Field(min_length=1, max_length=5000)
    support: str = Field(min_length=1, max_length=5000)
    responsibility: str = Field(min_length=1, max_length=5000)
    evaluation_method: str = Field(min_length=1, max_length=5000)
    curriculum_reference: str = Field(min_length=1, max_length=320)


class AdaptationInput(Command):
    goal_id: UUID | None = None
    measure: str = Field(min_length=1, max_length=5000)
    arena: str = Field(min_length=1, max_length=5000)
    responsibility: str = Field(min_length=1, max_length=5000)
    evaluation_method: str = Field(min_length=1, max_length=5000)


class ContributionInput(Command):
    goal_id: UUID | None = None
    participant: str = Field(min_length=1, max_length=320)
    role: Literal['learner','guardian']
    content: str = Field(min_length=1, max_length=5000)
    disagreement: bool = False
    response: str = Field(min_length=1, max_length=5000)
    occurred_at: AwareDatetime
    source: SourceBinding


class AllocationInput(Period):
    provision_id: UUID
    decision_id: UUID
    decision_revision_id: UUID
    amount: Decimal | None = Field(default=None, ge=0, le=100000, max_digits=14, decimal_places=4)
    unit: Literal['minutes','hours'] | None = None
    counting_basis: Literal['learner_time','staff_time'] | None = None

    @model_validator(mode='after')
    def quantity(self):
        if (self.amount is None) != (self.unit is None) or (self.amount is None) != (self.counting_basis is None):
            raise ValueError('A quantity requires amount, unit and counting basis')
        return self


class OriginalApproval(Command):
    approver: str = Field(min_length=1, max_length=320)
    authority: str = Field(min_length=1, max_length=2000)
    approved_at: AwareDatetime
    source: SourceBinding


class PlanContent(Period):
    title: str = Field(min_length=1, max_length=320)
    rationale: str = Field(min_length=1, max_length=10000)
    organization: str = Field(min_length=1, max_length=5000)
    responsibility: str = Field(min_length=1, max_length=5000)
    evaluation_method: str = Field(min_length=1, max_length=5000)
    decision_id: UUID | None = None
    decision_revision_id: UUID | None = None
    origin: Literal['authored','imported'] = 'authored'
    sources: list[SourceBinding] = Field(default_factory=list, max_length=100)
    original_approval: OriginalApproval | None = None
    goals: list[GoalInput] = Field(min_length=1, max_length=200)
    adaptations: list[AdaptationInput] = Field(default_factory=list, max_length=200)
    contributions: list[ContributionInput] = Field(default_factory=list, max_length=100)
    participation_record: str = Field(min_length=1, max_length=5000)
    allocations: list[AllocationInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def structure(self):
        if (self.decision_id is None) != (self.decision_revision_id is None):
            raise ValueError('A decision reference requires its exact revision')
        if self.origin == 'imported' and (not self.sources or self.original_approval is None):
            raise ValueError('Imported plans require source and original approval evidence')
        if self.origin == 'authored' and self.original_approval is not None:
            raise ValueError('Original approval is reserved for imported plans')
        ids = [g.goal_id for g in self.goals if g.goal_id]
        if len(ids) != len(set(ids)): raise ValueError('Duplicate goal identity')
        if len({a.provision_id for a in self.allocations}) != len(self.allocations): raise ValueError('Duplicate provision allocation')
        for goal in self.goals:
            if goal.effective_from < self.effective_from or goal.effective_until > self.effective_until:
                raise ValueError('Goal dates must fit within the plan')
        return self


class CreatePlan(PlanContent, Retry):
    kind: Literal['individual_education','ordinary_teaching']


class RevisePlan(PlanContent, Expected): pass


class PlanLifecycle(Expected):
    revision_id: UUID
    content_digest: str = Field(pattern='^[a-f0-9]{64}$')
    reason: str = Field(min_length=1, max_length=2000)
