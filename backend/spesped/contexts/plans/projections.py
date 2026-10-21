"""Narrow BC05 ports for authorized teaching and curated derivative currency.

The metadata predicate authorizes no source text. Callers must first authorize
an explicit teaching assignment or their own aggregate projection.
"""
from sqlalchemy import select
from spesped.db import utcnow
from spesped.errors import DomainError
from spesped.domain.approval import canonical_content_digest
from spesped.contexts.evidence.projections import confirmed_binding_is_current
from spesped.contexts.entitlements.projections import provision_binding_is_current
from . import service
from .models import IndividualEducationPlan, PlanRevision, GoalRevision, ProvisionAllocation


def teaching_goal_basis(db, actor, school_id, learner_id, goal_revision_id, at=None, historical=False):
    goal = service.goal_reference(db, actor, school_id, learner_id, goal_revision_id, at=at, historical=historical)
    revision = db.get(PlanRevision, goal['plan_revision_id'])
    parent = db.get(IndividualEducationPlan, goal['plan_id'])
    bindings = service.projection_bindings(db, actor, parent, revision)
    # Source bearing metadata is only returned after the full public goal read
    # has checked its transitive sources, decision and actor permissions.
    return {'goal': goal, 'source_bindings': bindings,
            'provisions': [{'decision_id':a.decision_id,'decision_revision_id':a.decision_revision_id,'provision_id':a.provision_id}
                           for a in service.children(db,ProvisionAllocation,revision)]}


def goal_binding_is_current(db, school_id, learner_id, binding, at=None, *, historical=False):
    """Exact goal/plan/decision/source currency, no pupil prose or source access."""
    try:
        goal = binding['goal']
        row = db.execute(select(IndividualEducationPlan.id,IndividualEducationPlan.active_revision_id).where(IndividualEducationPlan.school_id == school_id, IndividualEducationPlan.learner_id == learner_id, IndividualEducationPlan.id == goal['plan_id']).execution_options(populate_existing=True)).first()
        revision = db.execute(select(PlanRevision.id,PlanRevision.content_digest,PlanRevision.state,PlanRevision.activated_at,PlanRevision.activation_until).where(PlanRevision.school_id == school_id, PlanRevision.plan_id == goal['plan_id'], PlanRevision.id == goal['plan_revision_id']).execution_options(populate_existing=True)).first()
        version = db.execute(select(GoalRevision.id,GoalRevision.status,GoalRevision.effective_from,GoalRevision.effective_until).where(GoalRevision.school_id == school_id, GoalRevision.plan_revision_id == goal['plan_revision_id'], GoalRevision.id == goal['id']).execution_options(populate_existing=True)).first()
        if row is None or revision is None or version is None or version.status != 'active' or revision.activated_at is None: return False
        if revision.content_digest != goal['plan_digest']: return False
        instant = at or utcnow()
        end = min(version.effective_until,revision.activation_until) if revision.activation_until else version.effective_until
        if not version.effective_from <= instant < end: return False
        if not historical and (row.active_revision_id != revision.id or revision.state != 'active'): return False
        if any(not confirmed_binding_is_current(db,school_id,learner_id,str(s['evidence_id']),s['evidence_revision'],str(s['link_id'])) for s in binding['source_bindings']): return False
        expected = [{'decision_id':a.decision_id,'decision_revision_id':a.decision_revision_id,'provision_id':a.provision_id} for a in db.execute(select(ProvisionAllocation.decision_id,ProvisionAllocation.decision_revision_id,ProvisionAllocation.provision_id).where(ProvisionAllocation.school_id == school_id,ProvisionAllocation.plan_revision_id == revision.id).order_by(ProvisionAllocation.id))]
        if expected != binding['provisions']: return False
        if any(not provision_binding_is_current(db,school_id,learner_id,p,instant,historical=historical) for p in expected): return False
        return True
    except (KeyError,TypeError,ValueError,DomainError):
        return False


def profile_bindings_are_current(db,school_id,learner_id,bindings):
    """Currency of exact previously curated confirmed profile statements."""
    from .models import LearnerSupportProfile,ProfileStatement
    from fastapi.encoders import jsonable_encoder
    for binding in bindings:
        row=db.execute(select(ProfileStatement.id,ProfileStatement.state,ProfileStatement.version,ProfileStatement.confirmed_by,ProfileStatement.source).join(LearnerSupportProfile,ProfileStatement.profile_id == LearnerSupportProfile.id).where(ProfileStatement.school_id == school_id,LearnerSupportProfile.learner_id == learner_id,ProfileStatement.id == binding['id']).execution_options(populate_existing=True)).first()
        if row is None or row.state != 'confirmed' or row.version != binding['version'] or row.confirmed_by != binding['confirmed_by']:return False
        if row.source != binding['source']:return False
        if not confirmed_binding_is_current(db,school_id,learner_id,str(row.source['evidence_id']),row.source['evidence_revision'],str(row.source['link_id'])):return False
    return True
