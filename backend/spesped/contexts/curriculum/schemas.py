"""Closed command shapes: unknown dates, rights and quantities stay explicit."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]
Tag = Annotated[str, Field(min_length=1, max_length=100)]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class Value(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Command(Value):
    request_key: str = Field(min_length=1, max_length=120)


class Expected(Command):
    expected_version: int = Field(strict=True, ge=1)


class SourceReference(Value):
    kind: Literal['school_document', 'evidence', 'curriculum_document', 'resource_document']
    source_id: UUID
    revision: int = Field(strict=True, ge=1)
    digest: Digest
    learner_id: UUID | None = None
    case_id: UUID | None = None


class Period(Value):
    valid_from: date
    valid_until: date

    @model_validator(mode='after')
    def ordered(self):
        if self.valid_until < self.valid_from:
            raise ValueError('The inclusive date interval must be ordered')
        return self


class CurriculumGoal(Value):
    code: Tag
    subject: Tag
    description: Text
    age_min: int = Field(strict=True, ge=0, le=30)
    age_max: int = Field(strict=True, ge=0, le=30)
    @model_validator(mode='after')
    def ages(self):
        if self.age_max < self.age_min: raise ValueError('Ages must be ordered')
        return self


class SubjectAllocation(Value):
    subject: Tag
    minutes: int = Field(strict=True, ge=0)
    period_description: Text


class AssessmentRule(Value):
    subject: Tag
    assessment_form: Text
    scale_description: Text
    completion_rule: Text
    exception_basis: Text | None = None


class SchemeContent(Period):
    title: Text
    pedagogy: Literal['public', 'montessori']
    goals: list[CurriculumGoal] = Field(min_length=1, max_length=500)
    subject_allocations: list[SubjectAllocation] = Field(default_factory=list, max_length=100)
    assessment_rules: list[AssessmentRule] = Field(min_length=1, max_length=100)
    sources: list[SourceReference] = Field(min_length=1, max_length=30)
    @model_validator(mode='after')
    def unique_goals(self):
        if len({g.code for g in self.goals}) != len(self.goals): raise ValueError('Goal codes must be unique')
        if any(s.learner_id or s.case_id for s in self.sources): raise ValueError('School schemes cannot contain pupil/case sources')
        return self


class SchemeCreate(Command):
    content: SchemeContent


class SchemeRevision(Expected):
    content: SchemeContent


class ExactReview(Expected):
    revision_id: UUID
    content_digest: Digest
    reason: Text


class SchemeReview(ExactReview):
    approval_reference: Text
    approved_on: date


class CurriculumReference(Value):
    scheme_revision_id: UUID
    goal_code: Tag


class ThemePeriod(Period):
    id: UUID
    title: Text
    learning_objectives: list[Text] = Field(min_length=1, max_length=50)
    curriculum_references: list[CurriculumReference] = Field(min_length=1, max_length=100)
    activities: list[Text] = Field(min_length=1, max_length=50)
    material_ids: list[UUID] = Field(default_factory=list, max_length=50)


class ClassPlanContent(Period):
    title: Text
    group_name: Tag
    school_year: str = Field(pattern=r'^\d{4}-\d{4}$')
    age_min: int = Field(strict=True, ge=0, le=30)
    age_max: int = Field(strict=True, ge=0, le=30)
    themes: list[ThemePeriod] = Field(default_factory=list, max_length=100)
    imported_sources: list[SourceReference] = Field(default_factory=list, max_length=30)
    import_notes: Text | None = None
    @model_validator(mode='after')
    def coherent(self):
        if self.age_max < self.age_min: raise ValueError('Ages must be ordered')
        if len({t.id for t in self.themes}) != len(self.themes): raise ValueError('Theme IDs must be unique')
        if any(t.valid_from < self.valid_from or t.valid_until > self.valid_until for t in self.themes): raise ValueError('Themes must lie within the plan period')
        if any(s.learner_id or s.case_id for s in self.imported_sources): raise ValueError('Class plans cannot expose pupil/case sources')
        years=[int(y) for y in self.school_year.split('-')]
        if years[1] != years[0]+1: raise ValueError('School year must span adjacent years')
        return self


class ClassPlanCreate(Command):
    content: ClassPlanContent


class ClassPlanRevision(Expected):
    content: ClassPlanContent


class PublishPlan(ExactReview):
    periods_checked: Literal[True]
    references_checked: Literal[True]


class GoalBindingCreate(Command):
    plan_revision_id: UUID
    theme_id: UUID
    learner_id: UUID
    goal_revision_id: UUID
    participation: Literal['participate', 'adapt', 'not_relevant']
    rationale: Text
    adaptation: Text | None = None
    materials: list[Text] = Field(default_factory=list, max_length=30)
    sources: list[SourceReference] = Field(min_length=1, max_length=30)
    @model_validator(mode='after')
    def adapted(self):
        if self.participation == 'adapt' and not self.adaptation: raise ValueError('An adaptation must be described')
        return self


class ImpactDecision(Expected):
    decision: Literal['keep', 'change']
    reason: Text
    replacement_session_revision_id: UUID | None = None
    @model_validator(mode='after')
    def replacement(self):
        if (self.decision == 'change') != bool(self.replacement_session_revision_id): raise ValueError('Change requires the exact replacement revision')
        return self


class ResourceRights(Value):
    license_name: Text
    rights_basis: Text
    valid_from: date
    valid_until: date | None = None
    read: bool = Field(strict=True)
    use: bool = Field(strict=True)
    copy: bool = Field(strict=True)
    ai: bool = Field(strict=True)
    share_team: bool = Field(strict=True)
    share_school: bool = Field(strict=True)
    @model_validator(mode='after')
    def coherent(self):
        if self.valid_until and self.valid_until < self.valid_from: raise ValueError('License dates must be ordered')
        if not self.read and (self.use or self.copy or self.ai or self.share_team or self.share_school): raise ValueError('Further uses require read rights')
        return self


class ResourceContent(Value):
    title: Text
    author: Text
    original_provenance: Text
    method: Text
    preparation: Text
    instructions: list[Text] = Field(min_length=1, max_length=100)
    subjects: list[Tag] = Field(min_length=1, max_length=30)
    skills: list[Tag] = Field(min_length=1, max_length=30)
    level: Tag | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=50)
    age_min: int = Field(strict=True, ge=0, le=30)
    age_max: int = Field(strict=True, ge=0, le=30)
    duration_minutes: int = Field(strict=True, ge=1, le=1440)
    group_min: int = Field(strict=True, ge=1, le=1000)
    group_max: int = Field(strict=True, ge=1, le=1000)
    prerequisites: list[Text] = Field(default_factory=list, max_length=30)
    material_ids: list[UUID] = Field(default_factory=list, max_length=50)
    sources: list[SourceReference] = Field(default_factory=list, max_length=30)
    rights: ResourceRights
    @model_validator(mode='after')
    def coherent(self):
        if self.age_max < self.age_min or self.group_max < self.group_min: raise ValueError('Ranges must be ordered')
        if any(s.case_id for s in self.sources): raise ValueError('Case sources are not reusable library resources')
        return self


class ResourceCreate(Command):
    content: ResourceContent
    original_revision_id: UUID | None = None
    changes: list[Text] = Field(default_factory=list, max_length=50)
    @model_validator(mode='after')
    def trace(self):
        if self.original_revision_id and not self.changes: raise ValueError('A variant must show its changes')
        return self


class ResourceRevision(Expected):
    content: ResourceContent
    changes: list[Text] = Field(min_length=1, max_length=50)


class ShareResource(ExactReview):
    visibility: Literal['private', 'team', 'school']
    team_id: UUID | None = None
    @model_validator(mode='after')
    def team(self):
        if (self.visibility == 'team') != bool(self.team_id): raise ValueError('Team sharing requires one exact team')
        return self


class Reason(Expected):
    reason: Text


class ExperienceCreate(Command):
    resource_revision_id: UUID
    learner_id: UUID
    session_delivery_revision_id: UUID
    observed_on: date
    experience: Text


class MaterialContent(Value):
    title: Text
    material_type: Tag
    location: Text
    count: int | None = Field(default=None, strict=True, ge=0, le=1000000)
    inventory_checked_on: date | None = None
    presentation_revision_ids: list[UUID] = Field(default_factory=list, max_length=50)
    @model_validator(mode='after')
    def known_count(self):
        if (self.count is None) != (self.inventory_checked_on is None): raise ValueError('A known count requires a dated inventory check')
        return self


class MaterialCreate(Command):
    content: MaterialContent


class MaterialUpdate(Expected):
    content: MaterialContent


class TeamCreate(Command):
    name: str = Field(min_length=1,max_length=200)


class TeamMembership(Expected,Period):
    user_id: UUID
    state: Literal['active','revoked']
