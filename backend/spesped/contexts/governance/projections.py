"""Read-only, authorized rule metadata for a protected case workspace.

Recorded obligations are not a complete inventory of legal duties. This port
does not activate rules, create tasks, interpret an action as a notification,
or mark either a document or an action as completed.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from spesped.errors import DomainError, access_denied
from . import models as m, service


@dataclass(frozen=True)
class RuleBinding:
    profile_id: str
    profile_version: int
    profile_digest: str
    requirement_version_id: str
    requirement_revision: int
    requirement_digest: str
    state: Literal["current", "unreviewed", "withdrawn", "profile_revoked", "ineffective"]


@dataclass(frozen=True)
class CaseObligationProjection:
    id: str
    version: int
    state: str
    applicability: str
    source: RuleBinding | None
    review_required: bool
    required_action: str | None
    required_document_types: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    deadline_kind: str
    recorded_deadline_date: date | None
    recorded_deadline_at: datetime | None


@dataclass(frozen=True)
class CaseRequirementProjection:
    state: Literal["available", "review_required", "unavailable"]
    obligations: tuple[CaseObligationProjection, ...]
    # Always present, even for an empty or wholly inaccessible set. An empty
    # view must never become a conclusion that this case has no legal duties.
    coverage: str = "authorized_recorded_obligations_only"
    legal_completeness: str = "not_assessed"


def _source_binding(db, task):
    receipt = db.scalar(select(m.TriggerReceipt).where(
        m.TriggerReceipt.school_id == task.school_id,
        m.TriggerReceipt.id == task.receipt_id,
    ).execution_options(populate_existing=True))
    rule = db.scalar(select(m.RequirementVersion).where(
        m.RequirementVersion.school_id == task.school_id,
        m.RequirementVersion.id == task.requirement_version_id,
    ).execution_options(populate_existing=True))
    if receipt is None or rule is None:
        return None, None
    profile = db.scalar(select(m.SchoolRuleProfile).where(
        m.SchoolRuleProfile.school_id == task.school_id,
        m.SchoolRuleProfile.id == receipt.profile_id,
    ).execution_options(populate_existing=True))
    if profile is None or rule.id not in profile.requirement_version_ids:
        return None, None
    event_date = receipt.occurred_at.astimezone(ZoneInfo(task.timezone)).date()
    if rule.state == "withdrawn":
        state = "withdrawn"
    elif rule.state != "reviewed":
        state = "unreviewed"
    elif profile.state == "revoked":
        state = "profile_revoked"
    elif (not service.profile_effective(db, profile, event_date)
          or rule.valid_from > event_date
          or (rule.valid_until is not None and rule.valid_until < event_date)):
        state = "ineffective"
    else:
        state = "current"
    return RuleBinding(profile.id, profile.version, profile.content_digest,
                       rule.id, rule.revision_number, rule.content_digest, state), rule


def case_requirements(db, actor, school_id, learner_id, case_id):
    """Return only currently authorized recorded obligations, without writes.

    Requires governance's exact case permission AND the owning context's live
    resolver. Each detailed task also retains its existing owner/management
    check. An inaccessible task is omitted without revealing its identity/count.
    This port never grants case access or expands it through assignment metadata.
    """
    try:
        school_id, learner_id, case_id = (str(UUID(str(value)))
                                         for value in (school_id, learner_id, case_id))
    except (TypeError, ValueError):
        raise access_denied() from None
    service.scope_access(db, actor, school_id, learner_id, case_id)
    query = select(m.ObligationInstance).where(
        m.ObligationInstance.school_id == school_id,
        m.ObligationInstance.learner_id == learner_id,
        m.ObligationInstance.case_id == case_id,
    ).order_by(m.ObligationInstance.id).execution_options(populate_existing=True)
    result = []
    for task in db.scalars(query):
        try:
            service.task_access(db, actor, task)
        except DomainError as error:
            if error.status_code != 403:
                raise
            continue
        binding, rule = _source_binding(db, task)
        review_required = (binding is None or binding.state != "current"
                           or task.applicability == "unresolved"
                           or task.state == "unresolved")
        actionable = not review_required and task.applicability == "applicable"
        result.append(CaseObligationProjection(
            task.id, task.version, task.state, task.applicability, binding,
            review_required, rule.required_action if actionable else None,
            tuple(rule.required_document_types) if actionable else (),
            tuple(task.unresolved_inputs), task.deadline_kind,
            task.deadline_date, task.deadline_at,
        ))
    state = ("unavailable" if not result else "review_required"
             if any(item.review_required for item in result) else "available")
    return CaseRequirementProjection(state, tuple(result))


def report_obligation_basis(db, actor, school_id, learner_id, obligation_id, document_kind, starts_on, ends_on):
    """Read the exact human-reviewed reporting interval without caller mutation."""
    from .report_periods import report_obligation_basis as resolve
    return resolve(db, actor, school_id, learner_id, obligation_id, document_kind, starts_on, ends_on)
