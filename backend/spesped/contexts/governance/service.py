"""Authorized, transaction-owning governance use cases.

An assigned owner receives minimal task metadata; learner/case permissions are
rechecked for every detailed read or evidentiary mutation. No cross-context
prose is joined into leadership projections.
"""
from datetime import date
from functools import wraps
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select
from spesped.auth import Actor, active_at, require_authority, require_school_access, require_learner_access, school_today
from spesped.audit import record_audit
from spesped.db import utcnow
from spesped.errors import DomainError, access_denied
from spesped.contexts.identity.models import School, SchoolMembership
from .models import (LegalImportCandidate, RequirementDefinition, RequirementVersion, SchoolRuleProfile, TriggerReceipt,
    ObligationInstance, ApplicabilityDecision, ObligationReview, ObligationAssignment, ObligationAction, ComplianceDeviation, DeviationFollowup, WorkloadStudy,
    WorkloadParticipant, WorkloadMeasurement, GovernanceEvent)
from .schemas import DeadlineRule, TimingInputs
from .policies import evaluate_applicability, resolve_deadline, compare_measurements
from .ports import ValidatedEvidenceReference


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), default=str).encode()).hexdigest()


def transaction(fn):
    @wraps(fn)
    def command(db, *args, **kwargs):
        try:
            result = fn(db, *args, **kwargs)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    return command


def school_lock(db, actor, school_id):
    require_school_access(db, actor, school_id)
    return db.scalar(select(School).where(School.id == school_id).with_for_update().execution_options(populate_existing=True))


def get_scoped(db, model, school_id, identifier, expected=None):
    row = db.scalar(select(model).where(model.school_id == school_id, model.id == str(identifier)).with_for_update().execution_options(populate_existing=True))
    if row is None: raise access_denied()
    if expected is not None and row.version != expected:
        raise DomainError('version_conflict', 'This record changed. Reload before retrying.', 409)
    return row


def publish(db, actor, school_id, action, row, causation_id=None):
    db.flush()
    record_audit(db, actor, school_id, action, type(row).__name__, row.id)
    db.add(GovernanceEvent(school_id=school_id, aggregate_id=row.id,
        aggregate_version=getattr(row, 'version', 1), event_type=action, actor_id=actor.user_id,
        causation_id=causation_id))
    db.flush()


def authority(db, actor, school_id, action):
    return require_authority(db, actor, school_id, 'governance.' + action)


def scope_access(db, actor, school_id, learner_id=None, case_id=None):
    require_school_access(db, actor, school_id)
    if case_id:
        require_authority(db, actor, school_id, 'governance.case.read', learner_id=learner_id, case_id=case_id)
        resolver = db.info.get('governance_case_scope_resolver')
        if resolver is None: raise DomainError('case_scope_unavailable', 'The owning case context must validate the case and learner linkage.', 503)
        if resolver(db, actor, school_id, case_id) != learner_id: raise access_denied()
    elif learner_id:
        require_learner_access(db, actor, school_id, learner_id)


def task_access(db, actor, task, management=False):
    scope_access(db, actor, task.school_id, task.learner_id, task.case_id)
    if management or task.owner_id != actor.user_id:
        # Case authority is separate from school-wide administrative management.
        authority(db, actor, task.school_id, 'tasks.manage')


def can_scope(db, actor, task):
    try:
        scope_access(db, actor, task.school_id, task.learner_id, task.case_id)
        return True
    except DomainError:
        return False


def owner_valid(db, school_id, user_id):
    if user_id is None: return
    user_id = str(user_id)
    from spesped.contexts.identity.models import UserAccount
    user = db.get(UserAccount, user_id)
    school = db.get(School, school_id)
    membership = db.scalar(select(SchoolMembership).where(SchoolMembership.school_id == school_id,
        SchoolMembership.user_id == user_id, *active_at(SchoolMembership, school_today(school))))
    if user is None or user.state != 'active' or membership is None or membership.role == 'guardian':
        raise DomainError('invalid_owner', 'Select an active staff member in this school.')


@transaction
def import_candidates(db, actor, school_id):
    school_lock(db, actor, school_id)
    authority(db, actor, school_id, 'rules.manage')
    # This is an explicitly requested import of the repository's September 2026
    # research, never file-presence activation or a new legal certification.
    path = Path(__file__).resolve().parents[4] / 'docs' / 'legal-requirements.json'
    # Installed deployments may omit repository docs: unavailable stays explicit.
    if not path.exists():
        path = Path(__file__).resolve().parents[5] / 'docs' / 'legal-requirements.json'
    if not path.exists(): raise DomainError('registry_unavailable', 'The bundled candidate registry is unavailable.', 503)
    source = json.loads(path.read_text())
    existing = {c.registry_code for c in db.scalars(select(LegalImportCandidate).where(LegalImportCandidate.school_id == school_id))}
    imported = 0
    for entry in source:
        if entry['id'] in existing: continue
        row = LegalImportCandidate(school_id=school_id, registry_code=entry['id'], registry_checked=date.fromisoformat(entry['checked']), raw_source=entry, state='unreviewed')
        db.add(row)
        publish(db, actor, school_id, 'governance.candidate.imported', row)
        imported += 1
    return {'imported': imported, 'state': 'unreviewed', 'source_freshness': 'September 2026; school applicability and current law require review'}


@transaction
def create_requirement(db, actor, school_id, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.manage')
    if command.candidate_id: get_scoped(db, LegalImportCandidate, school_id, command.candidate_id)
    row = RequirementDefinition(school_id=school_id, **command.model_dump(mode='json'))
    db.add(row); publish(db, actor, school_id, 'governance.requirement.created', row)
    return row


@transaction
def revise_requirement(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.manage')
    requirement = get_scoped(db, RequirementDefinition, school_id, identifier, command.expected_version)
    values = command.model_dump(mode='json', exclude={'expected_version'})
    values['deadline_rule'] = values.pop('deadline')
    values['valid_from'] = command.valid_from; values['valid_until'] = command.valid_until
    previous = db.scalars(select(RequirementVersion).where(RequirementVersion.school_id == school_id, RequirementVersion.requirement_id == requirement.id)).all()
    row = RequirementVersion(school_id=school_id, requirement_id=requirement.id, revision_number=len(previous)+1,
        content_digest=digest(values), state='unreviewed', **values)
    requirement.version += 1
    db.add(row); publish(db, actor, school_id, 'governance.requirement.revised', row)
    return row


@transaction
def review_requirement(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.approve')
    row = get_scoped(db, RequirementVersion, school_id, identifier, command.expected_version)
    if row.state != 'unreviewed': raise DomainError('invalid_transition', 'This rule version has already been reviewed.', 409)
    if row.deadline_rule['kind'] == 'unresolved': raise DomainError('unresolved_rule', 'Review and specify the legal timing before approving this version.')
    row.state = 'reviewed'; row.reviewed_by = actor.user_id; row.reviewed_at = utcnow(); row.review_rationale = command.rationale
    publish(db, actor, school_id, 'governance.requirement.reviewed', row)
    return row


@transaction
def create_profile(db, actor, school_id, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.manage')
    requirements = set()
    for identifier in command.requirement_version_ids:
        version = get_scoped(db, RequirementVersion, school_id, identifier)
        if version.requirement_id in requirements: raise DomainError('duplicate_requirement', 'A profile selects one version per requirement.')
        requirements.add(version.requirement_id)
    if command.supersedes_profile_id: get_scoped(db, SchoolRuleProfile, school_id, command.supersedes_profile_id)
    values = command.model_dump(mode='json'); values['valid_from'] = command.valid_from; values['valid_until'] = command.valid_until
    row = SchoolRuleProfile(school_id=school_id, state='draft', content_digest=digest(values), **values)
    db.add(row); publish(db, actor, school_id, 'governance.profile.created', row)
    return row


def profile_impact(db, actor, school_id, identifier):
    authority(db, actor, school_id, 'rules.approve')
    profile = get_scoped(db, SchoolRuleProfile, school_id, identifier)
    selected = {get_scoped(db, RequirementVersion, school_id, rid).requirement_id: str(rid) for rid in profile.requirement_version_ids}
    items = []
    for task in db.scalars(select(ObligationInstance).where(ObligationInstance.school_id == school_id,
            ObligationInstance.state != 'reviewed_satisfied', ObligationInstance.applicability != 'not_applicable')):
        previous = db.get(RequirementVersion, task.requirement_version_id)
        new_id = selected.get(previous.requirement_id)
        if new_id != previous.id:
            items.append({'obligation_id': task.id, 'version': task.version,
                'previous_requirement_version_id': previous.id, 'proposed_requirement_version_id': new_id})
    items.sort(key=lambda i: i['obligation_id'])
    return {'items': items, 'total': len(items), 'impact_digest': digest({'profile':profile.content_digest,'items':items}),
        'historical_tasks_change': False}


@transaction
def activate_profile(db, actor, school_id, identifier, command):
    school = school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.approve')
    profile = get_scoped(db, SchoolRuleProfile, school_id, identifier, command.expected_version)
    if profile.state != 'draft': raise DomainError('invalid_transition', 'Only a draft profile may be activated.', 409)
    impact = profile_impact(db, actor, school_id, identifier)
    if impact['impact_digest'] != command.impact_digest: raise DomainError('impact_changed', 'Review the updated impact before activating.', 409)
    for rid in profile.requirement_version_ids:
        rule = get_scoped(db, RequirementVersion, school_id, rid)
        if rule.state != 'reviewed' or rule.valid_from > profile.valid_from or (rule.valid_until and (profile.valid_until is None or rule.valid_until < profile.valid_until)):
            raise DomainError('unreviewed_or_ineffective_rule', 'Every selected rule must be reviewed and cover the full profile period.')
    # School kind is authoritative identity metadata, not a caller-overridable fact.
    if 'school_kind' in profile.school_inputs and profile.school_inputs['school_kind'] != school.kind:
        raise DomainError('school_profile_conflict', 'The school kind does not match the registered school.')
    for previous in db.scalars(select(SchoolRuleProfile).where(SchoolRuleProfile.school_id == school_id, SchoolRuleProfile.state == 'approved')):
        overlaps = (previous.valid_until is None or profile.valid_from <= previous.valid_until) and (profile.valid_until is None or previous.valid_from <= profile.valid_until)
        if overlaps:
            if previous.id != profile.supersedes_profile_id or profile.valid_from <= previous.valid_from:
                raise DomainError('profile_overlap', 'Select the profile being superseded and a later effective start.', 409)
            previous.state = 'superseded'
            publish(db, actor, school_id, 'governance.profile.superseded', previous)
    if profile.supersedes_profile_id and get_scoped(db, SchoolRuleProfile, school_id, profile.supersedes_profile_id).valid_from >= profile.valid_from:
        raise DomainError('invalid_effective_start', 'A revision starts after the profile it supersedes.')
    profile.state = 'approved'; profile.approved_by = actor.user_id; profile.approved_at = utcnow(); profile.approval_rationale = command.rationale; profile.impact_digest = impact['impact_digest']
    publish(db, actor, school_id, 'governance.profile.activated', profile)
    return profile


def profile_effective(db, profile, occurrence_date):
    if profile.state not in ('approved','superseded') or occurrence_date < profile.valid_from or (profile.valid_until and occurrence_date > profile.valid_until): return False
    successor = db.scalar(select(SchoolRuleProfile).where(SchoolRuleProfile.school_id == profile.school_id,
        SchoolRuleProfile.supersedes_profile_id == profile.id, SchoolRuleProfile.state.in_(['approved','superseded','revoked']), SchoolRuleProfile.valid_from <= occurrence_date))
    return successor is None


def calculate_task(db, task, rule, occurred_at, inputs, timing):
    task.applicability, missing, task.applicability_reasons = evaluate_applicability(rule.conditions, inputs)
    task.evaluated_inputs = inputs; task.unresolved_inputs = missing; task.timing_inputs = timing.model_dump(mode='json')
    task.deadline_kind = rule.deadline_rule['kind']
    try:
        task.deadline_date, task.deadline_at, task.deadline_reasons = resolve_deadline(DeadlineRule.model_validate(rule.deadline_rule), timing, occurred_at, task.timezone)
    except (ValueError, OverflowError) as error:
        raise DomainError('invalid_deadline_input', 'The supplied dates do not resolve to a valid local deadline.') from error
    task.state = 'not_applicable' if task.applicability == 'not_applicable' else ('unresolved' if task.applicability == 'unresolved' or task.deadline_kind == 'unresolved' or (task.deadline_at is None and task.deadline_kind != 'without_undue_delay') else 'due')


@transaction
def trigger_obligations(db, actor, school_id, command):
    school = school_lock(db, actor, school_id); authority(db, actor, school_id, 'tasks.manage')
    learner_id = str(command.learner_id) if command.learner_id else None
    case_id = str(command.case_id) if command.case_id else None
    scope_access(db, actor, school_id, learner_id, case_id)
    fingerprint = digest(command.model_dump(mode='json'))
    receipt = db.scalar(select(TriggerReceipt).where(TriggerReceipt.school_id == school_id, TriggerReceipt.event_key == command.event_key))
    if receipt:
        if receipt.request_digest != fingerprint: raise DomainError('idempotency_conflict', 'This event key already identifies a different trigger.', 409)
        return list(db.scalars(select(ObligationInstance).where(ObligationInstance.school_id == school_id, ObligationInstance.receipt_id == receipt.id).execution_options(populate_existing=True)))
    profile = get_scoped(db, SchoolRuleProfile, school_id, command.profile_id)
    event_date = command.occurred_at.astimezone(ZoneInfo(school.timezone)).date()
    if not profile_effective(db, profile, event_date): raise DomainError('inactive_profile', 'The trigger requires a reviewed profile effective on the occurrence date.')
    # No event input can replace reviewed school facts; grade is read from identity.
    inputs = dict(profile.school_inputs)
    for key, value in command.inputs.items():
        if key in inputs and inputs[key] != value: raise DomainError('profile_input_conflict', 'An event cannot override reviewed school inputs.')
        inputs[key] = value
    inputs['school_kind'] = school.kind
    if learner_id:
        from spesped.contexts.identity.models import Learner
        inputs['learner_grade'] = db.get(Learner, learner_id).grade
    receipt = TriggerReceipt(school_id=school_id, profile_id=profile.id, event_key=command.event_key, request_digest=fingerprint,
        event_type=command.event_type, occurred_at=command.occurred_at)
    db.add(receipt); db.flush()
    tasks = []
    for rid in profile.requirement_version_ids:
        rule = get_scoped(db, RequirementVersion, school_id, rid)
        if rule.state != 'reviewed': raise DomainError('unreviewed_rule', 'The selected rule is not reviewed.')
        if rule.trigger_type != command.event_type: continue
        task = ObligationInstance(school_id=school_id, requirement_version_id=rule.id, receipt_id=receipt.id,
            learner_id=learner_id, case_id=case_id, period_key=command.period_key, timezone=school.timezone)
        calculate_task(db, task, rule, command.occurred_at, inputs, command.timing)
        db.add(task); publish(db, actor, school_id, 'governance.obligation.triggered', task, receipt.id)
        record_applicability(db, actor, task, 'Deterministic evaluation of the accepted trigger')
        tasks.append(task)
    publish(db, actor, school_id, 'governance.trigger.accepted', receipt)
    return tasks


@transaction
def assign_task(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id)
    task = get_scoped(db, ObligationInstance, school_id, identifier, command.expected_version); task_access(db, actor, task, True)
    owner_valid(db, school_id, command.owner_id)
    db.add(ObligationAssignment(school_id=school_id, obligation_id=task.id, actor_id=actor.user_id, previous_owner_id=task.owner_id, owner_id=str(command.owner_id) if command.owner_id else None, internal_planned_date=command.internal_planned_date, reason=command.reason))
    task.owner_id = str(command.owner_id) if command.owner_id else None; task.internal_planned_date = command.internal_planned_date
    # Force a version increment even when a repeated assignment has equal values.
    task.version += 1
    publish(db, actor, school_id, 'governance.obligation.assigned', task)
    return task


@transaction
def resolve_task_inputs(db, actor, school_id, identifier, command):
    school = school_lock(db, actor, school_id)
    task = get_scoped(db, ObligationInstance, school_id, identifier, command.expected_version); task_access(db, actor, task, True)
    if task.state == 'reviewed_satisfied': raise DomainError('invalid_transition', 'Reopen the obligation before reassessing applicability.', 409)
    rule = get_scoped(db, RequirementVersion, school_id, task.requirement_version_id)
    receipt = get_scoped(db, TriggerReceipt, school_id, task.receipt_id)
    profile = get_scoped(db, SchoolRuleProfile, school_id, receipt.profile_id)
    inputs = {**task.evaluated_inputs, **command.inputs}
    if any(inputs.get(k) != v for k,v in profile.school_inputs.items()) or inputs.get('school_kind') != school.kind:
        raise DomainError('profile_input_conflict', 'An event cannot override reviewed school inputs.')
    if task.learner_id:
        from spesped.contexts.identity.models import Learner
        inputs['learner_grade'] = db.get(Learner, task.learner_id).grade
    calculate_task(db, task, rule, receipt.occurred_at, inputs, command.timing)
    task.reviewed_by = None; task.review_rationale = None; task.version += 1
    publish(db, actor, school_id, 'governance.obligation.inputs_resolved', task)
    record_applicability(db, actor, task, command.reason)
    return task


@transaction
def submit_action(db, actor, school_id, identifier, command, evidence_validator=None):
    school_lock(db, actor, school_id)
    task = get_scoped(db, ObligationInstance, school_id, identifier, command.expected_version); task_access(db, actor, task)
    if task.state in ('reviewed_satisfied','not_applicable'): raise DomainError('invalid_transition', 'This obligation is closed; reopen it before submitting new evidence.', 409)
    if command.occurred_at > utcnow(): raise DomainError('future_action', 'A performed action cannot occur in the future.')
    # Keep only authorized immutable metadata, never external pupil prose.
    references = [validate_reference(db, actor, task, str(ref), evidence_validator) for ref in command.evidence_references]
    row = ObligationAction(school_id=school_id, obligation_id=task.id, actor_id=actor.user_id,
        **command.model_dump(mode='json', exclude={'expected_version','occurred_at','evidence_references'}), evidence_references=references, occurred_at=command.occurred_at)
    db.add(row)
    if task.state != 'unresolved': task.state = 'evidence_submitted'
    task.version += 1
    publish(db, actor, school_id, 'governance.obligation.evidence_submitted', task)
    db.flush()
    return row, task


@transaction
def review_task(db, actor, school_id, identifier, command, evidence_validator=None):
    school_lock(db, actor, school_id)
    task = get_scoped(db, ObligationInstance, school_id, identifier, command.expected_version)
    task_access(db, actor, task, True); authority(db, actor, school_id, 'tasks.review')
    if command.decision == 'satisfied':
        if db.get(RequirementVersion, task.requirement_version_id).state != 'reviewed':
            raise DomainError('rule_review_required', 'The historical rule was withdrawn; resolve the rule basis before fulfillment.')
        if task.applicability != 'applicable' or task.state != 'evidence_submitted':
            raise DomainError('unresolved_obligation', 'Resolve applicability and submit performed-action evidence before review.')
        performed = db.scalar(select(ObligationAction).where(ObligationAction.school_id == school_id, ObligationAction.obligation_id == task.id, ObligationAction.kind == 'performed_action').order_by(ObligationAction.recorded_at.desc(), ObligationAction.id.desc()))
        if performed is None: raise DomainError('performed_action_required', 'An uploaded document alone does not demonstrate fulfillment.')
        rule = get_scoped(db, RequirementVersion, school_id, task.requirement_version_id)
        documents = {}
        for a in db.scalars(select(ObligationAction).where(ObligationAction.school_id == school_id, ObligationAction.obligation_id == task.id, ObligationAction.kind == 'document_upload').order_by(ObligationAction.recorded_at, ObligationAction.id)):
            documents[a.action_type] = a
        if not set(rule.required_document_types).issubset(documents): raise DomainError('required_document_missing', 'The reviewed rule also requires the listed documentation.')
        for action in [performed] + [documents[k] for k in rule.required_document_types]:
            for reference in action.evidence_references:
                current = validate_reference(db, actor, task, reference['reference_id'], evidence_validator)
                if current != reference: raise DomainError('evidence_changed', 'Linked evidence changed; submit the current reviewed reference before fulfillment.', 409)
        task.state = 'reviewed_satisfied'
    else:
        if task.applicability == 'not_applicable': raise DomainError('not_applicable', 'Reassess the inputs before reopening a non-applicable duty.')
        task.state = 'unresolved' if task.applicability == 'unresolved' or (task.deadline_at is None and task.deadline_kind != 'without_undue_delay') else 'due'
    task.reviewed_by = actor.user_id; task.review_rationale = command.rationale
    publish(db, actor, school_id, 'governance.obligation.reviewed', task)
    db.add(ObligationReview(school_id=school_id, obligation_id=task.id, obligation_version=task.version, actor_id=actor.user_id, decision=command.decision, rationale=command.rationale))
    return task


def task_status(db, task):
    owner_state = 'no_owner'
    if task.owner_id:
        try: owner_valid(db, task.school_id, task.owner_id); owner_state = 'assigned'
        except DomainError: owner_state = 'inactive_owner'
    closed = task.state in ('not_applicable','reviewed_satisfied')
    return {'state': task.state, 'applicability':task.applicability, 'owner_status':owner_state,
        'overdue': not closed and task.applicability == 'applicable' and task.deadline_at is not None and utcnow() >= task.deadline_at,
        'unknown_rule': task.state == 'unresolved' or db.get(RequirementVersion, task.requirement_version_id).state != 'reviewed', 'requires_timing_assessment':not closed and task.deadline_kind == 'without_undue_delay'}


@transaction
def create_deviation(db, actor, school_id, command):
    school_lock(db, actor, school_id)
    task = get_scoped(db, ObligationInstance, school_id, command.obligation_id); task_access(db, actor, task, True)
    owner_valid(db, school_id, command.owner_id)
    row = ComplianceDeviation(school_id=school_id, state='open', **command.model_dump(mode='json'))
    db.add(row); publish(db, actor, school_id, 'governance.deviation.opened', row)
    return row


@transaction
def follow_deviation(db, actor, school_id, identifier, command, evidence_validator=None):
    school_lock(db, actor, school_id)
    row = get_scoped(db, ComplianceDeviation, school_id, identifier, command.expected_version)
    task = get_scoped(db, ObligationInstance, school_id, row.obligation_id)
    scope_access(db, actor, school_id, task.learner_id, task.case_id)
    if row.owner_id != actor.user_id or command.action != 'followup': authority(db, actor, school_id, 'tasks.manage')
    action = None
    if command.performed_action_id is not None:
        action = get_scoped(db, ObligationAction, school_id, command.performed_action_id)
        if action.obligation_id != task.id or action.kind != 'performed_action': raise DomainError('invalid_action_evidence', 'Select a performed action from this obligation.')
    if command.action == 'resolve':
        authority(db, actor, school_id, 'tasks.review')
        if command.performed_action_id is None: raise DomainError('performed_action_required', 'Resolution requires reviewed evidence of a performed remedial action.')
        if action.recorded_at < row.created_at: raise DomainError('invalid_action_evidence', 'Select a performed action from this obligation.')
        for reference in action.evidence_references:
            current = validate_reference(db, actor, task, reference['reference_id'], evidence_validator)
            if current != reference: raise DomainError('evidence_changed', 'The remedial evidence changed and requires renewed review.', 409)
        if row.state == 'resolved': raise DomainError('invalid_transition', 'This deviation is already resolved.', 409)
        row.state = 'resolved'; row.resolution_rationale = command.explanation
    elif command.action == 'reopen': row.state = 'open'; row.resolution_rationale = None
    elif command.action == 'reassign':
        owner_valid(db, school_id, command.owner_id); row.owner_id = str(command.owner_id) if command.owner_id else None
    elif row.state == 'resolved': raise DomainError('invalid_transition', 'Reopen a resolved deviation before adding follow-up.', 409)
    row.version += 1
    db.add(DeviationFollowup(school_id=school_id, deviation_id=row.id, actor_id=actor.user_id,
        action=command.action, explanation=command.explanation,
        performed_action_id=str(command.performed_action_id) if command.performed_action_id else None))
    publish(db, actor, school_id, 'governance.deviation.followed_up', row)
    return row


def leadership_overview(db, actor, school_id):
    authority(db, actor, school_id, 'overview')
    # One school-wide, unfilterable projection prevents differencing by pupil,
    # group, case or individual staff member. Pupil tasks require a minimum cohort.
    tasks = list(db.scalars(select(ObligationInstance).where(ObligationInstance.school_id == school_id)))
    school_tasks = [t for t in tasks if t.learner_id is None]
    pupil_tasks = [t for t in tasks if t.learner_id is not None]
    pupil_cohort = {t.learner_id for t in pupil_tasks}
    keys = ('overdue','no_owner','inactive_owner','unknown_rule','open_deviations','requires_timing_assessment')
    counters = dict.fromkeys(keys, 0)
    pupil_counts = dict.fromkeys(keys, 0)
    pupil_contributors = {k:set() for k in keys}
    open_deviation_counts = {}
    for d in db.scalars(select(ComplianceDeviation).where(ComplianceDeviation.school_id == school_id, ComplianceDeviation.state != 'resolved')):
        open_deviation_counts[d.obligation_id] = open_deviation_counts.get(d.obligation_id, 0) + 1
    for task in tasks:
        counts = pupil_counts if task.learner_id else counters
        state = task_status(db, task)
        values = dict.fromkeys(keys, 0)
        if task.state not in ('not_applicable','reviewed_satisfied'):
            for key in ('overdue','unknown_rule','requires_timing_assessment'): values[key] = int(state[key])
            if state['owner_status'] in ('no_owner','inactive_owner'): values[state['owner_status']] = 1
        # An unresolved deviation survives a fulfilled obligation and keeps its
        # own review lifecycle and indicator.
        values['open_deviations'] = open_deviation_counts.get(task.id, 0)
        for key, value in values.items():
            counts[key] += value
            if task.learner_id and value: pupil_contributors[key].add(task.learner_id)
    # Cell-level suppression prevents a large school cohort revealing a single
    # identifiable protected case through a category with only one contributor.
    pupil_indicators = {key:(pupil_counts[key] if len(pupil_cohort) >= 5 and
        (pupil_counts[key] == 0 or len(pupil_contributors[key]) >= 5) else None) for key in keys}
    return {'school_obligations': len(school_tasks), 'pupil_cohort_status':'aggregated_with_cell_suppression' if len(pupil_cohort) >= 5 else 'suppressed',
        'indicators': counters, 'indicator_scope':'school_obligations_only', 'pupil_indicators':pupil_indicators,
        'contains_case_details':False}



@transaction
def create_study(db, actor, school_id, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'workload.manage')
    row = WorkloadStudy(school_id=school_id, **command.model_dump(), state='open')
    db.add(row); publish(db, actor, school_id, 'governance.workload.study_created', row)
    return row


@transaction
def participate(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id)
    owner_valid(db, school_id, actor.user_id)
    study = get_scoped(db, WorkloadStudy, school_id, identifier)
    if study.state != 'open': raise DomainError('closed_study', 'This workload study is closed.')
    row = db.scalar(select(WorkloadParticipant).where(WorkloadParticipant.school_id == school_id, WorkloadParticipant.study_id == study.id, WorkloadParticipant.user_id == actor.user_id))
    if row is None:
        if not command.consent: return {'consent':False}
        row = WorkloadParticipant(school_id=school_id, study_id=study.id, user_id=actor.user_id)
        db.add(row)
    elif row.version != command.expected_version: raise DomainError('version_conflict', 'Participation changed. Reload before retrying.', 409)
    elif not command.consent: row.withdrawn_at = utcnow()
    elif row.withdrawn_at is not None: raise DomainError('withdrawn_participation', 'Withdrawn participation cannot be silently reactivated.')
    publish(db, actor, school_id, 'governance.workload.consent_changed', row)
    return {'consent':command.consent, 'version':row.version}


@transaction
def measure(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id)
    owner_valid(db, school_id, actor.user_id)
    study = get_scoped(db, WorkloadStudy, school_id, identifier)
    if study.state != 'open': raise DomainError('closed_study', 'This workload study is closed.')
    participant = db.scalar(select(WorkloadParticipant).where(WorkloadParticipant.school_id == school_id, WorkloadParticipant.study_id == study.id,
        WorkloadParticipant.user_id == actor.user_id, WorkloadParticipant.withdrawn_at.is_(None)))
    if participant is None: raise DomainError('consent_required', 'Voluntary participation is required before recording your own measurement.', 403)
    previous = db.scalar(select(WorkloadMeasurement).where(WorkloadMeasurement.school_id == school_id, WorkloadMeasurement.participant_id == participant.id, WorkloadMeasurement.match_key == command.match_key, WorkloadMeasurement.mode == command.mode).order_by(WorkloadMeasurement.revision_number.desc()))
    if previous is not None and (command.previous_measurement_id is None or str(command.previous_measurement_id) != previous.id):
        raise DomainError('version_conflict', 'Submit the latest measurement reference when correcting this measurement.', 409)
    if previous is None and command.previous_measurement_id is not None: raise DomainError('version_conflict', 'The preceding measurement does not exist in this match.', 409)
    values = command.model_dump(exclude={'previous_measurement_id'})
    row = WorkloadMeasurement(school_id=school_id, participant_id=participant.id, revision_number=previous.revision_number+1 if previous else 1, previous_measurement_id=previous.id if previous else None, **values)
    db.add(row); publish(db, actor, school_id, 'governance.workload.measurement_recorded', row)
    return row


def study_results(db, actor, school_id, identifier):
    authority(db, actor, school_id, 'workload.manage')
    study = get_scoped(db, WorkloadStudy, school_id, identifier)
    participants = list(db.scalars(select(WorkloadParticipant).where(WorkloadParticipant.school_id == school_id, WorkloadParticipant.study_id == study.id, WorkloadParticipant.withdrawn_at.is_(None))))
    measurements = list(db.scalars(select(WorkloadMeasurement).where(WorkloadMeasurement.school_id == school_id,
        WorkloadMeasurement.participant_id.in_([p.id for p in participants])))) if participants else []
    latest = {}
    for m in measurements:
        key = (m.participant_id, m.match_key, m.mode)
        if key not in latest or latest[key].revision_number < m.revision_number: latest[key] = m
    pairs, issues = compare_measurements(study, list(latest.values()))
    # Results never expose participant IDs, individual timing, or staff rankings.
    # Small studies cannot be queried by arbitrary subgroup/filter.
    if len({p[0] for p in pairs}) < 3:
        return {'status':'insufficient_comparable_sample', 'reasons':['At least three consenting participants with complete matched tasks are required'], 'manual_minutes':None,'assisted_minutes':None,'saved_minutes':None,'saving_percent':None}
    manual = sum(p[1] for p in pairs); assisted = sum(p[2] for p in pairs)
    low_quality = any(p[3].quality < study.minimum_quality or p[4].quality < study.minimum_quality or
        (study.task_type == 'assistant_brief' and p[4].comprehension < p[3].comprehension) for p in pairs)
    return {'status':'quality_review_required' if low_quality else 'comparable', 'pair_count':len(pairs),
        'incomplete_or_noncomparable':issues, 'manual_minutes':manual,'assisted_minutes':assisted,
        'saved_minutes':None if low_quality else manual-assisted,
        'saving_percent':None if low_quality or manual == 0 else round((manual-assisted)/manual*100,2),
        'reasons':['Quality or assistant comprehension fell below the agreed comparison'] if low_quality else [],
        'quality_mean':sum(p[4].quality for p in pairs)/len(pairs),
        'usefulness_mean':sum(p[4].usefulness for p in pairs if p[4].usefulness is not None)/sum(p[4].usefulness is not None for p in pairs) if any(p[4].usefulness is not None for p in pairs) else None,
        'comprehension_mean':sum(p[4].comprehension for p in pairs if p[4].comprehension is not None)/sum(p[4].comprehension is not None for p in pairs) if any(p[4].comprehension is not None for p in pairs) else None}


@transaction
def withdraw_rule(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.approve')
    row = get_scoped(db, RequirementVersion, school_id, identifier, command.expected_version)
    if row.state != 'reviewed': raise DomainError('invalid_transition', 'Only reviewed rules may be withdrawn.', 409)
    row.state = 'withdrawn'; row.withdrawn_by = actor.user_id; row.withdrawn_at = utcnow(); row.withdrawal_rationale = command.rationale
    publish(db, actor, school_id, 'governance.requirement.withdrawn', row)
    return row


@transaction
def revoke_profile(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'rules.approve')
    row = get_scoped(db, SchoolRuleProfile, school_id, identifier, command.expected_version)
    if row.state not in ('approved','superseded'): raise DomainError('invalid_transition', 'Only approved profiles may be revoked.', 409)
    row.state = 'revoked'; row.revoked_by = actor.user_id; row.revoked_at = utcnow(); row.revocation_rationale = command.rationale
    publish(db, actor, school_id, 'governance.profile.revoked', row)
    return row


@transaction
def close_study(db, actor, school_id, identifier, command):
    school_lock(db, actor, school_id); authority(db, actor, school_id, 'workload.manage')
    row = get_scoped(db, WorkloadStudy, school_id, identifier, command.expected_version)
    if row.state != 'open': raise DomainError('invalid_transition', 'This study is already closed.', 409)
    row.state = 'closed'; row.closed_by = actor.user_id; row.closed_at = utcnow(); row.closure_rationale = command.rationale
    publish(db, actor, school_id, 'governance.workload.study_closed', row)
    return row


def record_applicability(db, actor, task, reason):
    db.add(ApplicabilityDecision(school_id=task.school_id, obligation_id=task.id, obligation_version=task.version,
        actor_id=actor.user_id, reason=reason, applicability=task.applicability, evaluated_inputs=task.evaluated_inputs,
        reasons=task.applicability_reasons, unresolved_inputs=task.unresolved_inputs, timing_inputs=task.timing_inputs,
        deadline_date=task.deadline_date, deadline_at=task.deadline_at, deadline_reasons=task.deadline_reasons))


def deviation_access(db, actor, row):
    task = get_scoped(db, ObligationInstance, row.school_id, row.obligation_id)
    scope_access(db, actor, row.school_id, task.learner_id, task.case_id)
    if row.owner_id != actor.user_id: authority(db, actor, row.school_id, 'tasks.manage')


def validate_reference(db, actor, task, reference_id, validator):
    if validator is None:
        raise DomainError('evidence_validation_unavailable', 'Configure the authorized source adapter before linking evidence.', 503)
    reference = validator(db, actor, task.school_id, task.learner_id, task.case_id, reference_id)
    if not isinstance(reference, ValidatedEvidenceReference) or reference.reference_id != reference_id or reference.school_id != task.school_id or reference.learner_id != task.learner_id or reference.case_id != task.case_id:
        raise access_denied()
    if type(reference.revision) is not int or reference.revision < 1 or len(reference.digest) != 64 or any(c not in '0123456789abcdef' for c in reference.digest):
        raise DomainError('invalid_evidence_reference', 'The evidence adapter did not resolve an immutable source revision.', 503)
    return {'reference_id':reference.reference_id, 'revision':reference.revision, 'digest':reference.digest}
