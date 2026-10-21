"""Authorized historical goal coordinates for document source selection."""
from sqlalchemy import select
from spesped.auth import require_learner_access
from spesped.errors import DomainError
from spesped.contexts.identity.document_choices import reader, bounded
from . import models as m
from .projections import reporting_goal_basis

def goals(db, actor, school_id, learner_id, start, end):
    with reader(db) as fresh:
        require_learner_access(fresh, actor, school_id, learner_id, 'plans.read')
        candidates = bounded(fresh, select(m.GoalRevision, m.PlanRevision, m.IndividualEducationPlan).join(
            m.PlanRevision, m.PlanRevision.id == m.GoalRevision.plan_revision_id).join(
            m.IndividualEducationPlan, m.IndividualEducationPlan.id == m.PlanRevision.plan_id).where(
            m.GoalRevision.school_id == school_id, m.IndividualEducationPlan.school_id == school_id,
            m.IndividualEducationPlan.learner_id == learner_id, m.PlanRevision.activated_at.is_not(None),
            m.GoalRevision.status == 'active', m.GoalRevision.effective_from < end, m.GoalRevision.effective_until > start,
            m.PlanRevision.effective_from < end, m.PlanRevision.effective_until > start,
            (m.PlanRevision.activation_until.is_(None) | (m.PlanRevision.activation_until > start))).order_by(m.GoalRevision.effective_from, m.GoalRevision.id))
        items = []
        for goal, revision, plan in candidates:
            instant = max(start, goal.effective_from, revision.effective_from)
            try:
                value = reporting_goal_basis(fresh, actor, school_id, learner_id, goal.id, at=instant)
            except DomainError as exc:
                if exc.status_code not in {403, 409}: raise
                continue
            items.append(dict(goal_revision_id=goal.id, goal_id=goal.goal_id, plan_revision_id=revision.id,
                title=goal.title, kind=plan.kind, effective_period=value['effective_period'], applicable_at=instant))
        return items
