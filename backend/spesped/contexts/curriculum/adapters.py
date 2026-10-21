"""Concrete BC02/BC05 adapters; bytes and scopes come from owning services."""
import hashlib
import json
from sqlalchemy import select
from spesped.auth import require_authority, require_learner_access
from spesped.errors import DomainError, access_denied
from spesped.contexts.evidence import service as evidence
from spesped.contexts.evidence.models import SourceSubjectLink
from .ports import AuthorizedSource


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class EvidenceSourceReadPort:
    """School imports require separate explicit original-document authority.

    Evidence imports retain only an authorized controlled excerpt and attribution.
    They remain pupil-scoped even when used by a library variant. AI/copy/use
    rights are separately enforced by the resource context before this adapter.
    """
    def __init__(self,storage): self.storage=storage

    def resolve(self,db,actor,request):
        ref=request.reference; school_id=str(request.school_id)
        if ref.case_id: raise access_denied()
        if ref.kind == 'evidence':
            if ref.learner_id is None: raise access_denied()
            row=evidence.evidence(db,actor,school_id,str(ref.source_id))
            db.refresh(row)
            if row.learner_id != str(ref.learner_id) or row.current_revision != ref.revision or row.state != 'active':
                raise DomainError('source_changed','Select a current authorized original.',409)
            value=evidence.evidence_view(db,row)
            from spesped.contexts.evidence.projections import confirmed_binding_is_current
            if not confirmed_binding_is_current(db,school_id,row.learner_id,row.id,ref.revision,value['source']['link_id']):
                raise DomainError('source_changed','The exact confirmed excerpt or its original has changed.',409)
            value['controlled_excerpt']=evidence.excerpt_view(db,actor,school_id,value['source']['link_id'])['excerpt']
            text=canonical(value); actual=hashlib.sha256(text.encode()).hexdigest()
        else:
            require_authority(db,actor,school_id,'curriculum.source.read')
            row=evidence.source(db,actor,school_id,str(ref.source_id))
            db.refresh(row)
            if row.current_revision != ref.revision or row.state in {'withdrawn','rejected','quarantined'}:
                raise DomainError('source_changed','Select a current authorized original.',409)
            links=list(db.scalars(select(SourceSubjectLink).where(SourceSubjectLink.school_id==school_id,SourceSubjectLink.source_id==row.id,SourceSubjectLink.revoked_at.is_(None))))
            # A caller cannot relabel a pupil original as a school document.
            if links or ref.learner_id: raise access_denied()
            revision=evidence.source_revision(db,school_id,row.id,ref.revision)
            inspected=evidence.inspection(db,row)
            if inspected is None or inspected.extraction_state != 'ready' or inspected.scan_state not in {'clean','not_required_note'}:
                raise DomainError('source_unavailable','The original requires clean inspection and reviewed extraction.',409)
            if self.storage is None: raise DomainError('source_storage_unavailable','Original storage is unavailable.',503)
            evidence.read_original(self.storage,revision)
            actual=revision.digest
            text=canonical({'source_digest':actual,'pages':inspected.pages})
        if actual != ref.digest: raise DomainError('source_digest_changed','The exact original content no longer matches.',409)
        return AuthorizedSource(request=request,original_digest=actual,text=text,media_type='text/plain')


def current_goal(db,actor,school_id,learner_id,goal_revision_id):
    from spesped.contexts.plans.service import goal_reference
    from spesped.contexts.plans.models import GoalRevision,PlanRevision,IndividualEducationPlan
    require_learner_access(db,actor,school_id,learner_id,'plans.read')
    goal=db.scalar(select(GoalRevision).where(GoalRevision.school_id==school_id,GoalRevision.id==str(goal_revision_id)).execution_options(populate_existing=True))
    if goal is None:raise access_denied()
    revision=db.scalar(select(PlanRevision).where(PlanRevision.school_id==school_id,PlanRevision.id==goal.plan_revision_id).execution_options(populate_existing=True))
    if revision is None:raise access_denied()
    plan=db.scalar(select(IndividualEducationPlan).where(IndividualEducationPlan.school_id==school_id,IndividualEducationPlan.id==revision.plan_id).execution_options(populate_existing=True))
    if plan is None or plan.learner_id!=learner_id:raise access_denied()
    return goal_reference(db,actor,school_id,learner_id,goal_revision_id)


def actual_experience(db,actor,school_id,learner_id,delivery_revision_id,observed_on):
    from spesped.contexts.teaching import service as teaching, models as m
    require_learner_access(db,actor,school_id,learner_id,'teaching.read')
    revision=db.scalar(select(m.DeliveryRevision).where(m.DeliveryRevision.school_id==school_id,m.DeliveryRevision.id==str(delivery_revision_id)))
    if revision is None: raise access_denied()
    delivery=db.scalar(select(m.SessionDelivery).where(m.SessionDelivery.school_id==school_id,m.SessionDelivery.id==revision.delivery_id).execution_options(populate_existing=True))
    if delivery is None:raise access_denied()
    if delivery.current_revision != revision.revision: raise DomainError('actual_changed','Select the current actual delivery revision.',409)
    # Owning projection rechecks participants/sources; no approval is inferred.
    participant=db.scalar(select(m.LearnerParticipation).where(m.LearnerParticipation.school_id==school_id,m.LearnerParticipation.delivery_revision_id==revision.id,m.LearnerParticipation.learner_id==learner_id,m.LearnerParticipation.status.in_(['participated','partial']),m.LearnerParticipation.minutes>0))
    if participant is None or revision.status not in {'delivered','partial'}: raise access_denied()
    from spesped.contexts.identity.models import School
    from zoneinfo import ZoneInfo
    if revision.occurred_at.astimezone(ZoneInfo(db.get(School,school_id).timezone)).date() != observed_on:
        raise DomainError('actual_date','The experience date must match the actual delivery.',409)
    return True
