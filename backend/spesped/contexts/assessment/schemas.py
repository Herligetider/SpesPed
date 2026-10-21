"""Closed assessment commands; no norm, diagnosis or machine grade fields."""
from datetime import date
from decimal import Decimal
from typing import Annotated,Literal
from uuid import UUID
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,StringConstraints,model_validator
from spesped.contexts.curriculum.schemas import SourceReference
Text=Annotated[str,StringConstraints(min_length=1,max_length=4000,strip_whitespace=True)]
Tag=Annotated[str,StringConstraints(min_length=1,max_length=100,strip_whitespace=True)]
Digest=Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
class Value(BaseModel):model_config=ConfigDict(extra='forbid',frozen=True)
class Command(Value):request_key:Tag
class Expected(Command):expected_version:int=Field(strict=True,ge=1)
class Scale(Value):
    code:Tag
    label:Tag
    kind:Literal['numeric','categorical']
    minimum:Decimal|None=None
    maximum:Decimal|None=None
    categories:list[Tag]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def bounds(self):
        if self.kind=='numeric':
            if self.minimum is None or self.maximum is None or not self.minimum.is_finite() or not self.maximum.is_finite() or self.maximum<self.minimum or self.categories:raise ValueError('A numeric scale needs finite ordered bounds only')
        elif not self.categories or len(set(self.categories))!=len(self.categories) or self.minimum is not None or self.maximum is not None:raise ValueError('A categorical scale needs distinct named values only')
        return self
class Guidance(Value):
    minimum_days:int=Field(strict=True,ge=1,le=3650)
    rationale:Text
    source:SourceReference
class InstrumentContent(Value):
    title:Tag
    publisher_version:Tag
    instructions:Text
    scales:list[Scale]=Field(min_length=1,max_length=30)
    eligible_conditions:list[Tag]=Field(min_length=1,max_length=50)
    qualification_requirement:Text
    license_basis:Text
    license_from:date
    license_until:date
    permitted_use:bool
    sources:list[SourceReference]=Field(min_length=1,max_length=30)
    reassessment:Guidance|None=None
    @model_validator(mode='after')
    def valid(self):
        if self.license_until<self.license_from:raise ValueError('License interval must be ordered')
        if len({s.code for s in self.scales})!=len(self.scales):raise ValueError('Scale codes must be distinct')
        if len(set(self.eligible_conditions))!=len(self.eligible_conditions):raise ValueError('Conditions must be distinct')
        if any(r.learner_id or r.case_id for r in self.sources):raise ValueError('Instrument sources must be school sources')
        if self.reassessment and self.reassessment.source not in self.sources:raise ValueError('Guidance must cite one of the reviewed sources')
        return self
class InstrumentCreate(Command):content:InstrumentContent
class InstrumentRevise(Expected):content:InstrumentContent
class ExactReview(Expected):
    revision_id:UUID
    content_digest:Digest
    reason:Text
class InstrumentReview(ExactReview):pass
class Conditions(Value):
    method:Tag
    language:Tag
    support:Text
    adaptations:list[Text]=Field(default_factory=list,max_length=30)
    context:Text
    condition_codes:list[Tag]=Field(min_length=1,max_length=50)
class AdministrationPlan(Command):
    learner_id:UUID
    instrument_revision_id:UUID
    planned_on:date
    purpose:Text
    conditions:Conditions
class AdministrationStart(Expected):occurred_at:AwareDatetime
class AdministrationAbort(Expected):reason:Text
class RecordResult(Expected):
    occurred_at:AwareDatetime
    raw:dict[Tag,Tag]=Field(min_length=1,max_length=30)
    conditions:Conditions
    correction_reason:Text|None=None
class ReviewResult(ExactReview):
    interpretation:Text
    comparison:Literal['separate','comparable','incomparable']
    comparison_reason:Text
class DecideFollowUp(Expected):
    decision:Literal['accepted','moved','rejected']
    selected_on:date|None=None
    reason:Text
class EvidenceRef(Value):
    kind:Literal['evidence','observation','assessment_result','progress_review']
    id:UUID
    revision:int=Field(strict=True,ge=1)
    link_id:UUID|None=None
    digest:Digest|None=None
    @model_validator(mode='after')
    def coordinate(self):
        if self.kind=='evidence' and self.link_id is None:raise ValueError('Evidence requires its exact controlled link')
        return self
class NextTask(Value):
    owner_id:UUID
    due_on:date
    action:Text
class Finding(Value):
    judgement:Text
    outcome:Literal['continue','adapt','more_information']
    missing_evidence:list[Text]=Field(default_factory=list,max_length=50)
    contradictory_evidence:list[Text]=Field(default_factory=list,max_length=50)
    comparison_limitations:list[Text]=Field(default_factory=list,max_length=50)
    tasks:list[NextTask]=Field(default_factory=list,max_length=30)
class ProgressCreate(Command):
    learner_id:UUID
    goal_revision_id:UUID
    starts_at:AwareDatetime
    ends_at:AwareDatetime
    references:list[EvidenceRef]=Field(default_factory=list,max_length=100)
    delivery_revision_ids:list[UUID]=Field(default_factory=list,max_length=100)
    finding:Finding
    @model_validator(mode='after')
    def period(self):
        if self.ends_at<=self.starts_at:raise ValueError('Use a positive half-open interval')
        if len(set(self.delivery_revision_ids))!=len(self.delivery_revision_ids):raise ValueError('Duplicate actual deliveries')
        if len({(r.kind,r.id,r.revision) for r in self.references})!=len(self.references):raise ValueError('Duplicate exact references')
        return self
class ProgressRevise(Expected):finding:Finding
class ProgressTransition(ExactReview):transition:Literal['submit','confirm']
class CompetenceBasis(Value):
    reference:EvidenceRef
    curriculum_goal_code:Tag
    relevance:Text
    role:Literal['subject_competence','iop_context']
class StatementContent(Value):
    judgement:Text
    next_work:Text
    basis:list[CompetenceBasis]=Field(default_factory=list,max_length=100)
    missing_evidence:list[Text]=Field(default_factory=list,max_length=50)
    completion:Literal['unresolved','ongoing','completes_in_period','already_completed']='unresolved'
    exemption:Literal['unresolved','not_exempt','assessment_exempt','grade_exempt']='unresolved'
    expected_contributors:list[UUID]=Field(default_factory=list,max_length=50)
class StatementCreate(Command):
    learner_id:UUID
    scheme_revision_id:UUID|None=None
    subject:Tag
    assessment_type:Literal['ordinary','formative','half_year','final']
    starts_on:date
    ends_on:date
    content:StatementContent
    @model_validator(mode='after')
    def ordered(self):
        if self.ends_on<self.starts_on:raise ValueError('Use an ordered inclusive period')
        return self
class StatementRevise(Expected):
    content:StatementContent
    scheme_revision_id:UUID|None=None
class Contribute(Expected):
    kind:Literal['staff','learner_self_assessment']
    occurred_at:AwareDatetime
    content:Text
    sources:list[EvidenceRef]=Field(min_length=1,max_length=30)
    learner_account_confirmed:bool=False
    @model_validator(mode='after')
    def own_account(self):
        if self.kind=='learner_self_assessment' and not self.learner_account_confirmed:raise ValueError('A staff recorder must confirm this is the learner’s own account')
        return self
class FinalizeStatement(ExactReview):
    contribution_ids:list[UUID]=Field(default_factory=list,max_length=100)
    grade:Tag|None=None
class RecordCommunication(Expected):
    revision_id:UUID
    occurred_at:AwareDatetime
    destination:Literal['pupil','guardian','authoritative_system']
    method:Tag
    factual_reference:Text
