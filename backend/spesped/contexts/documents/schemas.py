"""Closed, typed human commands. No command authorizes external delivery."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from spesped.contexts.assessment.schemas import EvidenceRef as AssessmentEvidenceRef
from spesped.contexts.curriculum.schemas import SourceReference
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Gap = Annotated[str, StringConstraints(strip_whitespace=True,min_length=1,max_length=2000)]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Kind = Literal['annual_ito_evaluation','local_semester_report','ordinary_subject_assessment','guardian_email']
class Value(BaseModel): model_config=ConfigDict(extra='forbid',frozen=True)
class Command(Value): request_key:Tag
class Expected(Command): expected_version:int=Field(strict=True,ge=1)
class Period(Value):
    starts_on:date
    ends_on:date
    @model_validator(mode='after')
    def ordered(self):
        if self.ends_on<self.starts_on or self.ends_on==date.max: raise ValueError('Use an ordered, bounded calendar interval')
        return self
class SectionSpec(Value):
    key:Tag
    label:Tag
    required:bool=True
    contribution_required:bool=False
class TemplateContent(Value):
    kind:Kind
    title:Tag
    effective_from:date
    effective_until:date
    approval_action:Literal['documents.approve','documents.annual_ito.approve','documents.local_report.approve','documents.subject_report.approve']
    requirement_version_id:UUID|None=None
    sections:list[SectionSpec]=Field(min_length=1,max_length=40)
    sources:list[SourceReference]=Field(min_length=1,max_length=30)
    @model_validator(mode='after')
    def valid(self):
        if self.effective_until<self.effective_from: raise ValueError('Template effective period must be ordered')
        if len({v.key for v in self.sections})!=len(self.sections):raise ValueError('Section keys must be unique')
        if any(v.learner_id or v.case_id for v in self.sources):raise ValueError('Templates use school sources only')
        if self.kind=='annual_ito_evaluation' and self.requirement_version_id is None:raise ValueError('Statutory template requires a reviewed requirement version')
        return self
class TemplateCreate(Command): content:TemplateContent
class TemplateRevise(Expected): content:TemplateContent
class Exact(Expected):
    revision_id:UUID
    content_digest:Digest
    reason:Text
class GoalSelection(Value):
    goal_revision_id:UUID
    applicable_at:AwareDatetime
class EvidenceRef(AssessmentEvidenceRef):
    kind:Literal['evidence','observation','assessment_result','progress_review','assessment_statement']
class SnapshotSelection(Value):
    goals:list[GoalSelection]=Field(default_factory=list,max_length=80)
    references:list[EvidenceRef]=Field(default_factory=list,max_length=100)
    background_references:list[EvidenceRef]=Field(default_factory=list,max_length=100)
    actual_revision_ids:list[UUID]=Field(default_factory=list,max_length=100)
    future_plan_revision_ids:list[UUID]=Field(default_factory=list,max_length=30)
    discover_evidence:bool=True
    discover_observations:bool=True
    @model_validator(mode='after')
    def unique(self):
        if len({v.goal_revision_id for v in self.goals})!=len(self.goals):raise ValueError('Goal revisions must be distinct')
        if len({(v.kind,v.id) for v in self.references})!=len(self.references):raise ValueError('Source coordinates must be distinct')
        return self
class Section(Value):
    key:Tag
    text:Text|None=None
    source_keys:list[Tag]=Field(default_factory=list,max_length=100)
    missing_inputs:list[Gap]=Field(default_factory=list,max_length=30)
class Content(Value):
    subject:Tag|None=None
    sections:list[Section]=Field(min_length=1,max_length=40)
    handled_gaps:dict[Gap,Text]=Field(default_factory=dict,max_length=80)
    @model_validator(mode='after')
    def unique(self):
        if len({v.key for v in self.sections})!=len(self.sections):raise ValueError('Sections must be distinct')
        return self
class DocumentCreate(Command,Period):
    learner_id:UUID
    kind:Kind
    purpose:Tag
    language:Literal['nb','nn','en']='nb'
    length:Literal['short','standard','detailed']='standard'
    owner_id:UUID
    recipient_relationship_ids:list[UUID]=Field(default_factory=list,max_length=10)
    topics:list[Tag]=Field(default_factory=list,max_length=30)
    template_revision_id:UUID|None=None
    obligation_id:UUID|None=None
    selection:SnapshotSelection=Field(default_factory=SnapshotSelection)
    content:Content|None=None
class DocumentRevise(Expected):
    # A full replacement deliberately makes changed period/translation/recipients visible.
    document:DocumentCreate
    reason:Text
    sever_generation_fields:list[Tag]=Field(default_factory=list,max_length=40)
class Transition(Exact): action:Literal['review','approve','discard','recall']
class AssignContribution(Expected):
    revision_id:UUID
    section_key:Tag
    contributor_id:UUID
    required:bool=True
class Contribute(Expected):
    revision_id:UUID
    section_key:Tag
    kind:Literal['comment','submitted','checked']
    text:Text
    source_keys:list[Tag]=Field(default_factory=list,max_length=100)
class Suggest(Expected):
    revision_id:UUID
    policy_id:UUID
    release_id:UUID
class ApplySuggestion(Expected):
    revision_id:UUID
    job_id:UUID
    proposal_digest:Digest
    selected_sections:list[Tag]=Field(default_factory=list,max_length=40)
    select_subject:bool=False
    outcome:Literal['applied','rejected']
    reason:Text
class PeriodResolve(Period):
    learner_id:UUID
    purpose:Tag
    recipient_relationship_id:UUID|None=None
    shortcut:Literal['explicit','last_14_days','previous_month','since_last_sent']='explicit'
class ScheduleSettings(Value):
    learner_id:UUID
    owner_id:UUID
    purpose:Tag
    recipient_relationship_ids:list[UUID]=Field(min_length=1,max_length=10)
    first_run_at:AwareDatetime
    ends_at:AwareDatetime
    timezone:Tag|None=None
    recurrence:Literal['days','months']
    recurrence_count:int=Field(strict=True,ge=1,le=365)
    period_rule:Literal['rolling_days','previous_month']
    period_days:int=Field(default=14,strict=True,ge=1,le=366)
    language:Literal['nb','nn','en']='nb'
    length:Literal['short','standard','detailed']='standard'
    topics:list[Tag]=Field(default_factory=list,max_length=30)
    generation_mode:Literal['manual','local_ai']='manual'
    policy_id:UUID|None=None
    release_id:UUID|None=None
    selection:SnapshotSelection=Field(default_factory=SnapshotSelection)
    @model_validator(mode='after')
    def bounds(self):
        if (self.generation_mode=='local_ai')!=(self.policy_id is not None and self.release_id is not None):raise ValueError('Local AI recurrence requires both reviewed policy and release; manual recurrence has neither')
        if self.generation_mode=='manual' and (self.policy_id is not None or self.release_id is not None):raise ValueError('Manual recurrence cannot retain AI configuration')
        if self.ends_at<self.first_run_at:raise ValueError('Schedule end cannot precede its first execution')
        if (self.ends_at-self.first_run_at).days>3660:raise ValueError('Schedule exceeds ten years')
        return self
class ScheduleCreate(Command): settings:ScheduleSettings
class ScheduleChange(Expected):
    settings:ScheduleSettings
    reason:Text
class ScheduleTransition(Expected): action:Literal['activate','pause','end']
class ScheduleRun(Expected): pass
