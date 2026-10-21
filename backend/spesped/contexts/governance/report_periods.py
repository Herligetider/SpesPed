"""BC03 human-reviewed reporting coverage, independent of task fulfillment."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from spesped.auth import Actor, require_learner_access
from spesped.contexts.identity import models as identity
from spesped.errors import DomainError, access_denied
from . import models as m, service as svc
from .policies import evaluate_applicability


class ReportPeriodCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=0)
    obligation_basis_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    document_kind: str = Field(min_length=1, max_length=100)
    starts_on: date
    ends_on: date
    rationale: str = Field(min_length=1, max_length=2000)
    action: Literal['review', 'revoke'] = 'review'

    @model_validator(mode='after')
    def interval(self):
        if self.ends_on < self.starts_on:
            raise ValueError('The inclusive reporting interval must be ordered')
        if not self.rationale.strip() or not self.request_key.strip():
            raise ValueError('A review rationale and request key are required')
        return self


@contextmanager
def owner_reader(db):
    dependencies = ('spesped.contexts.governance', 'spesped.contexts.identity')
    for row in db.new | db.dirty | db.deleted:
        if type(row).__module__.startswith(dependencies) and not isinstance(row, (m.GovernanceEvent, identity.AuditRecord)):
            raise DomainError('dependency_pending', 'Resolve staged governance or identity changes before reading reporting coverage.', 409)
    with db.no_autoflush:
        reader = Session(bind=db.connection(), join_transaction_mode='rollback_only', autoflush=False, expire_on_commit=False)
        reader.info.update(db.info)
        try:
            yield reader
        finally:
            reader.close()


def _task(db, actor, school_id, obligation_id, learner_id=None, manage=False):
    row = db.scalar(select(m.ObligationInstance).where(m.ObligationInstance.school_id == school_id, m.ObligationInstance.id == obligation_id))
    if row is None or row.case_id is not None or row.learner_id is None or (learner_id is not None and row.learner_id != learner_id):
        raise access_denied()
    require_learner_access(db, actor, school_id, row.learner_id)
    # An ordinary authorized pupil reader can consume curated reporting metadata.
    if manage:
        svc.authority(db, actor, school_id, 'tasks.manage')
        svc.authority(db, actor, school_id, 'tasks.review')
    return row


def _latest(db, task, kind):
    return db.scalar(select(m.ReportPeriodReview).where(m.ReportPeriodReview.school_id == task.school_id,
        m.ReportPeriodReview.obligation_id == task.id, m.ReportPeriodReview.document_kind == kind)
        .order_by(m.ReportPeriodReview.revision.desc()).limit(1))


def _reviewer_current(db, task, user_id, actions, pupil=True):
    if not user_id:
        return False
    try:
        actor = Actor(user_id)
        if pupil:
            require_learner_access(db, actor, task.school_id, task.learner_id)
        for action in actions:
            svc.authority(db, actor, task.school_id, action)
        return True
    except DomainError:
        return False


def _basis(db, task, kind):
    from .projections import _source_binding
    binding, rule = _source_binding(db, task)
    receipt = db.get(m.TriggerReceipt, task.receipt_id)
    profile = db.get(m.SchoolRuleProfile, receipt.profile_id) if receipt else None
    school = db.get(identity.School, task.school_id)
    learner = db.get(identity.Learner, task.learner_id)
    decision = db.scalar(select(m.ApplicabilityDecision).where(m.ApplicabilityDecision.school_id == task.school_id,
        m.ApplicabilityDecision.obligation_id == task.id).order_by(m.ApplicabilityDecision.recorded_at.desc(), m.ApplicabilityDecision.id.desc()).limit(1))
    value = {'obligation_id': task.id, 'school_id': task.school_id, 'learner_id': task.learner_id,
        'case_id': task.case_id, 'requirement_version_id': task.requirement_version_id,
        'document_kind': kind, 'binding': asdict(binding) if binding else None,
        'applicability': task.applicability, 'evaluated_inputs': task.evaluated_inputs,
        'unresolved_inputs': task.unresolved_inputs, 'timing_inputs': task.timing_inputs,
        'period_key': task.period_key, 'deadline_kind': task.deadline_kind,
        'deadline_date': task.deadline_date, 'deadline_at': task.deadline_at,
        'timezone': task.timezone, 'applicability_decision_id': decision.id if decision else None,
        'school_kind': school.kind, 'learner_grade': learner.grade}
    reasons = []
    if binding is None or binding.state != 'current': reasons.append('report_rule_binding_unresolved')
    if rule is None or kind not in rule.required_document_types: reasons.append('report_document_kind_unresolved')
    inputs = dict(task.evaluated_inputs)
    if profile:
        inputs.update(profile.school_inputs)
    inputs.update(school_kind=school.kind, learner_grade=learner.grade)
    if inputs != task.evaluated_inputs or rule is None or evaluate_applicability(rule.conditions, inputs)[0] != 'applicable' or task.applicability != 'applicable' or task.unresolved_inputs:
        reasons.append('report_applicability_unresolved')
    # Original source approvals must remain currently authorized; no source prose
    # or legal interpretation is exported by this curated contract.
    if rule and not _reviewer_current(db, task, rule.reviewed_by, ('rules.approve',), pupil=False):
        reasons.append('report_rule_reviewer_unavailable')
    if profile and not _reviewer_current(db, task, profile.approved_by, ('rules.approve',), pupil=False):
        reasons.append('report_profile_reviewer_unavailable')
    return value, svc.digest(value), reasons, rule, profile


def _period_reasons(db, rule, profile, starts_on, ends_on):
    if rule is None or profile is None:
        return ['report_period_rule_coverage_unresolved']
    if (rule.valid_from > starts_on or (rule.valid_until is not None and ends_on > rule.valid_until)
            or not svc.profile_effective(db, profile, starts_on) or not svc.profile_effective(db, profile, ends_on)):
        return ['report_period_rule_coverage_unresolved']
    return []


def _view(review):
    if review is None: return None
    return {key: getattr(review, key) for key in ('id', 'obligation_id', 'learner_id', 'document_kind', 'revision', 'action', 'starts_on', 'ends_on', 'obligation_basis_digest', 'actor_id', 'rationale', 'recorded_at')}


def report_period_history(db, actor, school_id, obligation_id, document_kind):
    with owner_reader(db) as reader:
        task = _task(reader, actor, school_id, obligation_id, manage=True)
        _, token, reasons, rule, profile = _basis(reader, task, document_kind)
        history = list(reader.scalars(select(m.ReportPeriodReview).where(m.ReportPeriodReview.school_id == school_id,
            m.ReportPeriodReview.obligation_id == obligation_id, m.ReportPeriodReview.document_kind == document_kind).order_by(m.ReportPeriodReview.revision)))
        latest = history[-1] if history else None
        if latest is None:
            reasons.append('report_period_review_missing')
        else:
            reasons += _period_reasons(reader, rule, profile, latest.starts_on, latest.ends_on)
            if latest.action != 'review': reasons.append('report_period_review_revoked')
            if latest.obligation_basis_digest != token: reasons.append('report_period_basis_changed')
            if not _reviewer_current(reader, task, latest.actor_id, ('tasks.manage', 'tasks.review')):
                reasons.append('report_period_reviewer_unavailable')
        return {'obligation_id': task.id, 'document_kind': document_kind, 'obligation_basis_digest': token,
            'state': 'applicable' if not reasons else 'unresolved',
            'version': latest.revision if latest else 0, 'current': _view(latest),
            'history': [_view(row) for row in history], 'unresolved_inputs': sorted(set(reasons)),
            'period_key': task.period_key, 'deadline_date': task.deadline_date, 'deadline_at': task.deadline_at}


@svc.transaction
def review_report_period(db, actor, school_id, obligation_id, command):
    svc.school_lock(db, actor, school_id)
    task = _task(db, actor, school_id, obligation_id, manage=True)
    fingerprint = svc.digest({'actor_id': actor.user_id, 'obligation_id': obligation_id, **command.model_dump(mode='json')})
    previous = db.scalar(select(m.ReportPeriodReview).where(m.ReportPeriodReview.school_id == school_id, m.ReportPeriodReview.request_key == command.request_key))
    if previous:
        if previous.request_digest != fingerprint:
            raise DomainError('idempotency_conflict', 'This request key already identifies another review.', 409)
        return {'review': _view(previous), 'version': previous.revision}
    latest = _latest(db, task, command.document_kind)
    revision = latest.revision if latest else 0
    if command.expected_version != revision:
        raise DomainError('version_conflict', 'Reporting coverage changed. Reload before reviewing.', 409)
    value, token, reasons, rule, profile = _basis(db, task, command.document_kind)
    if token != command.obligation_basis_digest:
        raise DomainError('report_basis_changed', 'The obligation basis changed. Review its current inputs before submitting.', 409)
    if command.action == 'review':
        reasons += _period_reasons(db, rule, profile, command.starts_on, command.ends_on)
        if reasons:
            raise DomainError('report_basis_unresolved', 'Resolve the current reviewed rule and applicability before reviewing reporting coverage.', 409)
    elif latest is None or latest.action != 'review' or latest.starts_on != command.starts_on or latest.ends_on != command.ends_on:
        raise DomainError('report_review_missing', 'Revoke the exact current reviewed interval.', 409)
    row = m.ReportPeriodReview(school_id=school_id, obligation_id=task.id, learner_id=task.learner_id,
        document_kind=command.document_kind, revision=revision+1, action=command.action,
        starts_on=command.starts_on, ends_on=command.ends_on, obligation_basis_digest=token,
        reviewed_binding=json.loads(json.dumps(value, default=str)), actor_id=actor.user_id, rationale=command.rationale,
        request_key=command.request_key, request_digest=fingerprint)
    db.add(row)
    svc.publish(db, actor, school_id, 'governance.report_period.' + ('reviewed' if row.action == 'review' else 'revoked'), row)
    # publish's complete event envelope uses the review's ledger revision.
    event = db.scalar(select(m.GovernanceEvent).where(m.GovernanceEvent.aggregate_id == row.id))
    event.aggregate_version = row.revision
    db.flush()
    return {'review': _view(row), 'version': row.revision}


def report_obligation_basis(db, actor, school_id, learner_id, obligation_id, document_kind, starts_on, ends_on):
    if type(starts_on) is not date or type(ends_on) is not date or ends_on < starts_on:
        raise DomainError('report_period_invalid', 'Supply an ordered inclusive interval of actual dates.', 422)
    try:
        school_id, learner_id, obligation_id = (str(UUID(str(value))) for value in (school_id, learner_id, obligation_id))
    except (ValueError, TypeError):
        raise access_denied() from None
    with owner_reader(db) as reader:
        task = _task(reader, actor, school_id, obligation_id, learner_id)
        value, token, reasons, rule, profile = _basis(reader, task, document_kind)
        reasons += _period_reasons(reader, rule, profile, starts_on, ends_on)
        review = _latest(reader, task, document_kind)
        if review is None: reasons.append('report_period_review_missing')
        else:
            if review.action != 'review': reasons.append('report_period_review_revoked')
            if review.obligation_basis_digest != token: reasons.append('report_period_basis_changed')
            if (review.starts_on, review.ends_on) != (starts_on, ends_on): reasons.append('report_period_mismatch')
            if not _reviewer_current(reader, task, review.actor_id, ('tasks.manage', 'tasks.review')):
                reasons.append('report_period_reviewer_unavailable')
        valid = not reasons
        return {'obligation_id': task.id, 'requirement_version_id': task.requirement_version_id,
            'binding': value['binding'], 'state': 'applicable' if valid else 'unresolved',
            'unresolved_inputs': sorted(set(reasons + task.unresolved_inputs)),
            'report_period': {'starts_on': review.starts_on, 'ends_on': review.ends_on} if valid else None,
            'report_period_review': {'id': review.id, 'revision': review.revision, 'digest': svc.digest({'id': review.id, 'basis': review.obligation_basis_digest, 'starts_on': review.starts_on, 'ends_on': review.ends_on, 'action': review.action})} if review else None,
            'obligation_basis_digest': token, 'period_key': task.period_key,
            'deadline_kind': task.deadline_kind, 'deadline_date': task.deadline_date, 'deadline_at': task.deadline_at}
