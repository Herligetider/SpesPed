"""Narrow future J19 boundary; unconfigured competence/grade/exemption is unknown.

Only trusted server adapters can return exact reviewed records. Authority grants
still apply independently. Resolving never flushes, commits or mutates a session.
"""
from datetime import date
from typing import Literal,Protocol
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from sqlalchemy.orm import Session
from spesped.auth import Actor
from .schemas import Value,Tag,Digest
class AuthorityRequest(Value):
    school_id:UUID
    learner_id:UUID
    person_id:UUID
    purpose:Literal['instrument_administration','result_review','statement_finalize','grade_set']
    exact_revision_id:UUID
    exact_digest:Digest
    starts_on:date
    ends_on:date
    subject:Tag|None=None
    scheme_revision_id:UUID|None=None
class AuthoritySource(Value):
    record_id:UUID
    revision:int=Field(strict=True,ge=1)
    digest:Digest
class AuthorityResult(Value):
    request:AuthorityRequest
    state:Literal['reviewed_current','unavailable','unresolved','ineligible']
    review_id:UUID|None=None
    reviewed_by:UUID|None=None
    reviewed_at:AwareDatetime|None=None
    effective_from:date|None=None
    effective_until:date|None=None
    sources:list[AuthoritySource]=Field(default_factory=list,max_length=30)
    completion:Literal['unresolved','ongoing','completes_in_period','already_completed']='unresolved'
    exemption:Literal['unresolved','not_exempt','assessment_exempt','grade_exempt']='unresolved'
    grade_policy:Literal['unresolved','not_applicable','optional','required']='unresolved'
    grade_values:list[Tag]=Field(default_factory=list,max_length=100)
class AssessmentAuthorityPort(Protocol):
    def resolve(self,db:Session,actor:Actor,request:AuthorityRequest)->AuthorityResult:...

def authority_basis(db,actor,request,required=False):
    from spesped.db import utcnow
    from spesped.errors import DomainError
    port=db.info.get('assessment_authority_port')
    if port is None:value=AuthorityResult(request=request,state='unavailable')
    else:
        try:value=AuthorityResult.model_validate(port.resolve(db,actor,request))
        except (ValueError,TypeError):raise DomainError('assessment_authority_contract','The reviewed authority source returned an invalid binding.',503) from None
    if value.request!=request:raise DomainError('assessment_authority_scope','Authority must cover this exact person, pupil, purpose, revision and period.',409)
    if value.state=='reviewed_current':
        if not(value.review_id and value.reviewed_by and value.reviewed_at and value.reviewed_at<=utcnow() and value.effective_from and value.effective_until and value.effective_from<=request.starts_on<=request.ends_on<=value.effective_until and value.sources):raise DomainError('assessment_authority_contract','A current exact reviewed source and effective coverage are required.',409)
    elif required:raise DomainError('assessment_authority_unresolved','Qualification, competence or subject authority requires a current reviewed source; role labels cannot establish it.',409)
    return value.model_dump(mode='json')
