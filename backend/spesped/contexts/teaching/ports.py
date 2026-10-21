"""Optional owning-context qualification read contract. Unconfigured is unknown.

Only a trusted server adapter may implement this port. It must perform its own
current actor/school access checks and resolve reviewed qualification/responsibility
records for the exact staff, provision and full actual event interval. Calls are read-only: no
commit, rollback, audit or business mutation of the consumer's transaction. Role labels and teaching
access grants are not qualification evidence. The result never decides fulfilment.
"""
from typing import Literal,Protocol
from uuid import UUID
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,model_validator
from sqlalchemy.orm import Session
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.errors import DomainError


class Value(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)


class QualificationRequest(Value):
    school_id: UUID
    learner_id: UUID
    staff_id: UUID
    decision_id: UUID
    decision_revision_id: UUID
    provision_id: UUID
    provision_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    occurred_at: AwareDatetime
    ended_at: AwareDatetime

    @model_validator(mode='after')
    def actual_interval(self):
        if self.ended_at <= self.occurred_at:raise ValueError('Qualification coverage requires a positive actual interval')
        return self


class QualificationSource(Value):
    kind: Literal['staff_qualification','staff_responsibility','competence_review']
    source_id: UUID
    revision: int = Field(strict=True,ge=1)
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class QualificationResult(Value):
    request: QualificationRequest
    state: Literal['reviewed_current','unavailable','unresolved','ineligible']
    responsibility: Literal['responsible_teaching','assistant_support','unknown'] = 'unknown'
    review_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: AwareDatetime | None = None
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None
    sources: list[QualificationSource] = Field(default_factory=list,max_length=20)


class QualificationReadPort(Protocol):
    def resolve(self,db:Session,actor:Actor,request:QualificationRequest)->QualificationResult: ...


def resolve_qualification(db,actor,request):
    port=db.info.get('teaching_qualification_port')
    if port is None:return QualificationResult(request=request,state='unavailable')
    try:
        value=port.resolve(db,actor,request)
        result=QualificationResult.model_validate(value.model_dump(mode='python') if isinstance(value,QualificationResult) else value)
    except (ValueError,TypeError):raise DomainError('qualification_contract','The qualification source returned an invalid result.',503) from None
    if result.request != request:raise DomainError('qualification_scope','The qualification result does not match this exact staff, pupil, provision and occurrence.',409)
    if result.state == 'reviewed_current':
        valid=(result.responsibility == 'responsible_teaching' and result.review_id and result.reviewed_by
               and result.reviewed_at and result.reviewed_at <= utcnow() and result.effective_from
               and result.effective_until and result.effective_from <= request.occurred_at < request.ended_at <= result.effective_until
               and result.sources and len({(s.kind,s.source_id,s.revision) for s in result.sources}) == len(result.sources))
        if not valid:raise DomainError('qualification_contract','A current reviewed qualification and responsibility basis covering the full actual interval with exact source versions is required.',409)
    return result
