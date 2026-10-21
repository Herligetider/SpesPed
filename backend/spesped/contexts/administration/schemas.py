"""Human checked references; never an executable national qualification rule."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from spesped.contexts.teaching.ports import QualificationRequest
from spesped.contexts.assessment.ports import AuthorityRequest

class Value(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,str_strip_whitespace=True)
Digest=Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
Text=Annotated[str,Field(min_length=1,max_length=2000)]
class Source(Value):
    system:Annotated[str,Field(min_length=1,max_length=100)]
    identity:Annotated[str,Field(min_length=1,max_length=200)]
    version:Annotated[str,Field(min_length=1,max_length=100)]
    digest:Digest
    issued_on:date
    authority:Text
    scope:Text
    limitations:Text
class Period(Value):
    effective_from:AwareDatetime
    effective_until:AwareDatetime
    @model_validator(mode='after')
    def period(self):
        if self.effective_from>=self.effective_until:raise ValueError('A positive half-open effective interval is required')
        return self
class Qualification(Period):
    kind:Literal['qualification']='qualification'
    person_id:UUID
    qualification:Text
    purposes:list[Literal['teaching','instrument_administration','result_review','statement_finalize','grade_set']]=Field(min_length=1,max_length=5)
    source:Source
class Responsibility(Period):
    kind:Literal['responsibility']='responsibility'
    person_id:UUID
    learner_id:UUID
    subject:Annotated[str,Field(min_length=1,max_length=100)]
    responsibility:Literal['responsible_teaching','assistant_support']
    source:Source
class Policy(Period):
    kind:Literal['assessment_policy']='assessment_policy'
    learner_id:UUID
    subject:Annotated[str,Field(min_length=1,max_length=100)]
    scheme_revision_id:UUID
    completion:Literal['unresolved','ongoing','completes_in_period','already_completed']='unresolved'
    exemption:Literal['unresolved','not_exempt','assessment_exempt','grade_exempt']='unresolved'
    grade_policy:Literal['unresolved','not_applicable','optional','required']='unresolved'
    grade_values:list[Annotated[str,Field(min_length=1,max_length=100)]]=Field(default_factory=list,max_length=100)
    source:Source
    @model_validator(mode='after')
    def scale(self):
        if len(set(self.grade_values))!=len(self.grade_values):raise ValueError('Grade scale values must be unique')
        if self.grade_policy in {'optional','required'} and not self.grade_values:raise ValueError('A reviewed grading policy requires its exact scale')
        if self.grade_policy=='not_applicable' and self.grade_values:raise ValueError('No scale applies')
        return self
class Reference(Value):
    record_id:UUID
    revision:int=Field(strict=True,ge=1)
    digest:Digest
class TeachingReview(Period):
    kind:Literal['teaching_review']='teaching_review'
    request:QualificationRequest
    qualification:Reference
    responsibility:Reference
    source:Source
class AssessmentReview(Period):
    kind:Literal['assessment_review']='assessment_review'
    request:AuthorityRequest
    qualification:Reference
    responsibility:Reference
    policy:Reference|None=None
    source:Source
    @model_validator(mode='after')
    def requested_period(self):
        if self.request.starts_on>self.request.ends_on:raise ValueError('Choose an ordered assessment period')
        if self.request.purpose in {'statement_finalize','grade_set'} and self.policy is None:raise ValueError('A subject policy is required')
        return self
Content=Annotated[Qualification|Responsibility|Policy|TeachingReview|AssessmentReview,Field(discriminator='kind')]
class Create(Value):
    request_key:Annotated[str,Field(min_length=1,max_length=120)]
    content:Content
class Revise(Create):
    expected_version:int=Field(strict=True,ge=1)
class Review(Value):
    request_key:Annotated[str,Field(min_length=1,max_length=120)]
    expected_version:int=Field(strict=True,ge=1)
    revision_id:UUID
    content_digest:Digest
    reason:Text
    source_checked_on:date
    outcome:Literal['eligible','ineligible','unresolved']
class Revoke(Value):
    request_key:Annotated[str,Field(min_length=1,max_length=120)]
    expected_version:int=Field(strict=True,ge=1)
    reason:Text
