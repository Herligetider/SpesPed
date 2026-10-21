"""Bounded teaching commands. Planned values never imply actual delivery."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


Material = Annotated[str, StringConstraints(min_length=1, max_length=1000, strip_whitespace=True)]
BoundedNote = Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]


class Value(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Command(Value):
    request_key: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:-]+$')


class Expected(Command):
    expected_version: int = Field(strict=True, ge=1)


class Binding(Value):
    evidence_id: UUID
    evidence_revision: int = Field(strict=True, ge=1)
    link_id: UUID


class LearnerBasis(Value):
    learner_id: UUID
    goal_revision_ids: list[UUID] = Field(min_length=1, max_length=10)
    profile_statement_ids: list[UUID] = Field(default_factory=list, max_length=20)
    observation_revision_ids: list[UUID] = Field(default_factory=list, max_length=10)
    sources: list[Binding] = Field(default_factory=list, max_length=20)


class CreateBasis(Command):
    planned_at: AwareDatetime
    duration_minutes: int = Field(strict=True, ge=1, le=480)
    learners: list[LearnerBasis] = Field(min_length=1, max_length=20)
    theme: str = Field(default='', max_length=1000)
    arena: str = Field(min_length=1, max_length=300)
    materials: list[Material] = Field(default_factory=list, max_length=30)
    missing_information: list[BoundedNote] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def unique_learners(self):
        if len({x.learner_id for x in self.learners}) != len(self.learners):
            raise ValueError('Select each learner once')
        for x in self.learners:
            if len(set(x.goal_revision_ids)) != len(x.goal_revision_ids): raise ValueError('Select each goal once')
        return self


class Step(Value):
    instruction: str = Field(min_length=1, max_length=2000)
    minutes: int = Field(strict=True, ge=0, le=480)


class SessionContent(Value):
    title: str = Field(min_length=1, max_length=320)
    goal: str = Field(min_length=1, max_length=2000)
    preparation: str = Field(min_length=1, max_length=3000)
    materials: list[Material] = Field(max_length=30)
    steps: list[Step] = Field(min_length=1, max_length=12)
    support: str = Field(min_length=1, max_length=3000)
    simplification: str = Field(min_length=1, max_length=3000)
    observation_focus: str = Field(min_length=1, max_length=2000)


class SaveSession(Command):
    basis_id: UUID
    owner_id: UUID
    content: SessionContent


class ReviseSession(SaveSession):
    manual_replacements: list[Literal['title','goal','preparation','materials','steps','support','simplification','observation_focus']] = Field(default_factory=list,max_length=8)
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def distinct_fields(self):
        if len(set(self.manual_replacements)) != len(self.manual_replacements):raise ValueError('Select each independently replaced field once')
        return self


class ReviewSession(Expected):
    revision_id: UUID
    content_digest: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)


class BriefContent(Value):
    simple_goal: str = Field(min_length=1, max_length=1000)
    material_location: str = Field(min_length=1, max_length=1500)
    steps: list[BoundedNote] = Field(min_length=3, max_length=5)
    support: str = Field(min_length=1, max_length=2000)
    simplification: str = Field(min_length=1, max_length=1500)
    help_when: str = Field(min_length=1, max_length=1500)
    contact: str = Field(min_length=1, max_length=500)
    training_guidance: str = Field(min_length=1, max_length=1500)


class CreateBrief(Command):
    session_revision_id: UUID
    learner_id: UUID
    template: Literal['practical','visual_support','guided_practice'] = 'practical'
    content: BriefContent
    replaces_brief_id: UUID | None = None


class ReviewBrief(Expected):
    content_digest: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)


class AssignBrief(Expected):
    assistant_id: UUID
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    role: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def interval(self):
        if self.valid_from >= self.valid_until: raise ValueError('Assignment needs a nonempty interval')
        return self


class BriefInteraction(Command):
    kind: Literal['question','answer','feedback','guidance']
    text: str = Field(min_length=1, max_length=3000)
    responds_to_id: UUID | None = None
    needs_follow_up: bool = False


Category = Literal['ordinary_teaching','individually_adapted_education','personal_assistance','physical_adaptation']


class ProvisionReference(Value):
    decision_id: UUID
    decision_revision_id: UUID
    provision_id: UUID


class Participation(Value):
    learner_id: UUID
    goal_revision_ids: list[UUID] = Field(default_factory=list, max_length=10)
    status: Literal['participated','partial','absent']
    minutes: int = Field(strict=True, ge=0, le=480)
    category: Category
    support: str = Field(min_length=1, max_length=1500)
    support_status: Literal['assessed','unassessed'] = 'assessed'
    provision: ProvisionReference | None = None
    # This describes what was actually observed, never a fabricated allocation.
    counting_basis: Literal['learner_time','staff_time'] | None = None
    attributed_staff_minutes: int | None = Field(default=None, strict=True, ge=0, le=480)

    @model_validator(mode='after')
    def actual(self):
        if (self.status == 'absent') != (self.minutes == 0): raise ValueError('Absence has zero participation; participation needs actual minutes')
        if self.status == 'absent' and self.attributed_staff_minutes not in {None,0}:raise ValueError('Absence cannot receive delivered staff-time support; record actual staff expenditure separately')
        if self.category == 'ordinary_teaching' and self.provision is not None: raise ValueError('Ordinary teaching cannot claim an entitlement')
        if self.provision is None and (self.counting_basis is not None or self.attributed_staff_minutes is not None): raise ValueError('A counting basis requires an exact provision')
        if self.counting_basis == 'staff_time' and self.attributed_staff_minutes is None: raise ValueError('Record an explicit staff allocation')
        if self.counting_basis != 'staff_time' and self.attributed_staff_minutes is not None: raise ValueError('Only a staff-time provision uses allocated staff minutes')
        return self


class StaffTime(Value):
    staff_id: UUID
    minutes: int = Field(strict=True, ge=1, le=480)
    role: str = Field(min_length=1, max_length=500)
    category: Category


class DeliveryContent(Value):
    session_revision_id: UUID | None = None
    occurred_at: AwareDatetime
    duration_minutes: int = Field(strict=True, ge=0, le=480)
    status: Literal['delivered','partial','cancelled']
    activity: str = Field(min_length=1, max_length=3000)
    participants: list[Participation] = Field(min_length=1, max_length=20)
    staff: list[StaffTime] = Field(max_length=30)
    cause: Literal['learner_absence','staff_unavailable','changed_activity','other'] | None = None
    cause_detail: str = Field(default='', max_length=2000)
    follow_up_owner_id: UUID | None = None
    follow_up: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode='after')
    def actual_shape(self):
        if len({(x.learner_id,x.category) for x in self.participants}) != len(self.participants): raise ValueError('Record each learner support category once')
        if len({(x.staff_id,x.category) for x in self.staff}) != len(self.staff): raise ValueError('Record each employee support category once')
        for staff_id in {x.staff_id for x in self.staff}:
            if sum(x.minutes for x in self.staff if x.staff_id == staff_id) > self.duration_minutes:raise ValueError('Do not double-count an employee across support categories')
        if any(x.minutes > self.duration_minutes for x in self.participants+self.staff): raise ValueError('Actual minutes cannot exceed the session duration')
        if self.status == 'cancelled' and (self.duration_minutes or self.staff or any(x.minutes for x in self.participants)): raise ValueError('Cancellation carries no delivered minutes')
        if self.status != 'cancelled' and (self.duration_minutes == 0 or not self.staff): raise ValueError('Delivery needs an actual duration and staffing')
        if self.status == 'delivered' and any(p.status != 'participated' or p.support_status == 'unassessed' for p in self.participants):raise ValueError('Absence, partial participation or unassessed support requires a partial record with a cause and owned follow-up')
        if self.status in {'partial','cancelled'} and (self.cause is None or self.follow_up_owner_id is None or not self.follow_up): raise ValueError('A deviation requires a cause and owned follow-up')
        if (self.follow_up_owner_id is None) != (self.follow_up is None): raise ValueError('Follow-up needs an owner and action')
        if self.cause == 'other' and not self.cause_detail: raise ValueError('Describe the cause')
        return self


class SaveDelivery(Command):
    content: DeliveryContent


class CorrectDelivery(SaveDelivery):
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class ObservationContent(Value):
    learner_id: UUID
    occurred_at: AwareDatetime
    session_revision_id: UUID | None = None
    assignment_id: UUID | None = None
    goal_revision_id: UUID | None = None
    observation: str = Field(min_length=1, max_length=3000)
    support: str = Field(min_length=1, max_length=1500)
    interpretation: str | None = Field(default=None, max_length=2000)
    next_step: str | None = Field(default=None, max_length=2000)
    input_method: Literal['manual','unconfirmed_transcript','confirmed_transcript'] = 'manual'
    transcript_reviewed: bool = False


class SaveObservation(Command):
    content: ObservationContent
    save: bool = True

    @model_validator(mode='after')
    def confirmed_text(self):
        if self.save and (self.content.input_method == 'unconfirmed_transcript' or (self.content.input_method == 'confirmed_transcript' and not self.content.transcript_reviewed)):
            raise ValueError('Review a transcript before saving confirmed observation content')
        return self


class CorrectObservation(SaveObservation):
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class ResolveFollowUp(Expected):
    resolution: str = Field(min_length=1, max_length=2000)


class RequestSuggestion(Command):
    policy_id: UUID
    release_id: UUID


class ReviewSuggestion(Expected):
    job_id: UUID
    outcome: Literal['accepted','edited','rejected']
    selected_fields: list[Literal['title','goal','preparation','materials','steps','support','simplification','observation_focus']] = Field(max_length=8)
    content: SessionContent | None = None
    reason: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def selection(self):
        if len(set(self.selected_fields)) != len(self.selected_fields): raise ValueError('Select each field once')
        if self.outcome == 'rejected' and (self.selected_fields or self.content): raise ValueError('A rejection selects no replacement fields')
        if self.outcome != 'rejected' and not self.selected_fields: raise ValueError('Choose the fields to replace')
        if (self.outcome == 'edited') != (self.content is not None): raise ValueError('Only an edited suggestion carries a replacement')
        return self


class ActualInputContent(Value):
    occurred_at: AwareDatetime
    duration_minutes: int = Field(strict=True, ge=0,le=480)
    status: Literal['participated','partial','absent']
    category: Literal['personal_assistance','physical_adaptation','ordinary_teaching']
    activity: str = Field(min_length=1,max_length=2000)
    support: str = Field(min_length=1,max_length=1500)
    difficulty: str = Field(default='',max_length=2000)

    @model_validator(mode='after')
    def actual(self):
        if (self.status == 'absent') != (self.duration_minutes == 0):raise ValueError('Absence carries no delivered minutes')
        return self


class SubmitActualInput(Command):
    content: ActualInputContent


class ReviewActualInput(Expected):
    outcome: Literal['recorded','needs_clarification','rejected']
    delivery_revision_id: UUID | None = None
    reason: str = Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def delivery(self):
        if (self.outcome == 'recorded') != (self.delivery_revision_id is not None):raise ValueError('Link the exact actual delivery revision only when recorded')
        return self
