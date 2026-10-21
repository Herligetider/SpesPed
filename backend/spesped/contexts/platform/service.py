"""Durable generation workflow. No model operation mutates professional records."""
from datetime import timedelta
import hashlib
import json
import time
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from spesped.audit import record_audit
from spesped.auth import Actor, active_at, require_authority, require_learner_access, school_today
from spesped.contexts.identity.models import School, StaffAssignment
from spesped.db import utcnow
from spesped.errors import DomainError, access_denied
from .contracts import (GatewayRuntime, GenerationRequest, PolicyCommand, ReleaseCommand,
                        ReviewCommand, SourceInput, SourceRef, PURPOSE_CAPABILITIES,
                        TEMPLATE_VERSION, SCHEMA_VERSION)
from .models import GenerationAttempt, GenerationJob, ModelEvaluation, ModelRelease, PlatformEvent, ProcessingPolicy
from .providers import ProviderFailure, invoke, validate_provider


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _event(db, actor, record, action):
    db.flush()
    record_audit(db, actor, record.school_id, action, record.__class__.__name__, record.id)
    db.add(PlatformEvent(school_id=record.school_id, aggregate_id=record.id, aggregate_version=getattr(record, 'version', 1), event_type=action))


def _version(record, expected):
    if record.version != expected:
        raise DomainError('stale_version', 'Refresh this item before retrying.', 409)


def _authorize(db, actor, school_id, learner_id, purpose):
    if purpose not in PURPOSE_CAPABILITIES:
        raise access_denied()
    require_learner_access(db, actor, school_id, learner_id)
    today = school_today(db.get(School, school_id))
    action = 'ai.' + purpose
    assignments = db.scalars(select(StaffAssignment).where(StaffAssignment.school_id == school_id,
        StaffAssignment.learner_id == learner_id, StaffAssignment.user_id == actor.user_id,
        StaffAssignment.purpose == purpose, *active_at(StaffAssignment, today))).all()
    if not any(action in assignment.actions for assignment in assignments):
        require_authority(db, actor, school_id, action, learner_id=learner_id)


def _resolve(db, runtime, actor, school_id, learner_id, purpose, references):
    if runtime.source_resolver is None:
        raise ProviderFailure('source_resolver_unavailable')
    if len({r.key for r in references}) != len(references):
        raise DomainError('duplicate_source', 'Select each source revision once.', 422)
    # Raw intake material is only allowed on its explicitly authorized OCR path.
    if purpose != 'evidence_extraction' and any(r.kind == 'intake' for r in references):
        raise access_denied()
    sources = runtime.source_resolver.resolve(db, actor, school_id, learner_id, purpose, references)
    by_key = {s.reference.key: s for s in sources}
    if len(sources) != len(references) or len(by_key) != len(references) or set(by_key) != {r.key for r in references}:
        raise access_denied()
    ordered = [by_key[r.key] for r in references]
    if any(s.school_id != school_id or s.learner_id != learner_id or s.purpose != purpose for s in ordered):
        raise access_denied()
    return ordered


def _manifest(sources):
    return [{'reference': s.reference.model_dump(mode='json'), 'content_digest': hashlib.sha256(s.content.encode() if isinstance(s.content, str) else s.content).hexdigest(),
             'media_type': s.media_type, 'provenance': s.provenance, 'provenance_reference': s.provenance_reference} for s in sources]


def _current_sources(db, runtime, actor, job):
    sources = _resolve(db, runtime, actor, job.school_id, job.learner_id, job.purpose, [SourceRef.model_validate(s['reference']) for s in job.source_manifest])
    if _manifest(sources) != job.source_manifest:
        raise DomainError('source_revision_changed', 'The source changed. Create a new suggestion from the current revision.', 409)
    return sources


def _load(db, actor, school_id, job_id, *, lock=False):
    statement = select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.id == str(job_id))
    if lock:
        statement = statement.with_for_update()
    job = db.scalar(statement.execution_options(populate_existing=True))
    if job is None:
        raise access_denied()
    _authorize(db, actor, school_id, job.learner_id, job.purpose)
    return job


def _configuration(db, runtime, job):
    policy = db.scalar(select(ProcessingPolicy).where(ProcessingPolicy.school_id == job.school_id, ProcessingPolicy.id == job.policy_id))
    release = db.scalar(select(ModelRelease).where(ModelRelease.school_id == job.school_id, ModelRelease.id == job.release_id))
    if policy is None or policy.state != 'active' or policy.version != job.policy_version:
        raise ProviderFailure('processing_policy_unavailable')
    if (release is None or release.state != 'reviewed' or release.configuration_digest != job.release_digest
            or release.template_version != TEMPLATE_VERSION or release.output_schema_version != SCHEMA_VERSION):
        raise ProviderFailure('reviewed_release_required')
    evaluation = db.get(ModelEvaluation, release.evaluation_id)
    if (evaluation is None or evaluation.school_id != job.school_id or evaluation.release_id != release.id
            or evaluation.state != 'passed' or evaluation.release_digest != release.configuration_digest
            or not release.reviewed_by or not release.reviewed_at):
        raise ProviderFailure('reviewed_release_required')
    if job.purpose not in policy.configuration['purposes'] or PURPOSE_CAPABILITIES[job.purpose] != release.capability or policy.provider_key != release.provider_key:
        raise ProviderFailure('purpose_not_supported')
    provider = runtime.providers.get(policy.provider_key)
    if provider is None:
        raise ProviderFailure('provider_unavailable')
    if provider_digest(provider) != release.provider_digest:
        raise ProviderFailure('provider_configuration_changed')
    current_command = ReleaseCommand(provider_key=release.provider_key, model_version=release.model_version, capability=release.capability, template_version=release.template_version, output_schema_version=release.output_schema_version)
    if release_configuration_digest(current_command, provider) != release.configuration_digest:
        raise ProviderFailure('reviewed_template_required')
    return policy, release, provider


def create_policy(db: Session, actor: Actor, school_id: str, command: PolicyCommand, runtime: GatewayRuntime):
    require_authority(db, actor, school_id, 'platform.manage')
    provider = runtime.providers.get(command.provider_key)
    if provider is None:
        raise DomainError('provider_unavailable', 'The configured provider is unavailable.', 503)
    # Validate local boundary immediately; remote is rechecked with resolved provenance at execution.
    if provider.kind != 'remote_openai':
        try:
            validate_provider(runtime, provider, [])
        except ProviderFailure as exc:
            raise DomainError(exc.code, 'The configured processing boundary is unavailable.', 503) from None
    elif runtime.environment != 'development' or not runtime.remote_synthetic_development:
        raise DomainError('remote_processing_forbidden', 'Remote processing requires explicit synthetic development configuration.', 403)
    policy = ProcessingPolicy(school_id=school_id, provider_key=command.provider_key, configuration=command.model_dump(mode='json'), state='active')
    db.add(policy)
    _event(db, actor, policy, 'ai.policy_created')
    db.commit()
    return policy


def provider_digest(provider):
    return digest({'key': provider.key, 'endpoint': provider.endpoint, 'kind': provider.kind, 'capabilities': sorted(provider.capabilities)})


def release_configuration_digest(command, provider):
    from .contracts import SYSTEM_PROMPT, PURPOSE_INSTRUCTIONS, Suggestion
    return digest({'release': command.model_dump(), 'provider_digest': provider_digest(provider), 'template': SYSTEM_PROMPT, 'purpose_instructions': PURPOSE_INSTRUCTIONS, 'schema': Suggestion.model_json_schema()})


def create_release(db: Session, actor: Actor, school_id: str, command: ReleaseCommand, runtime: GatewayRuntime):
    require_authority(db, actor, school_id, 'platform.manage')
    provider = runtime.providers.get(command.provider_key)
    if provider is None:
        raise DomainError('provider_unavailable', 'Configure the provider before creating a release.', 503)
    binding = provider_digest(provider)
    configuration_digest = release_configuration_digest(command, provider)
    release = ModelRelease(school_id=school_id, **command.model_dump(), provider_digest=binding, configuration_digest=configuration_digest, state='candidate')
    db.add(release)
    _event(db, actor, release, 'ai.release_created')
    db.commit()
    return release


def revoke_configuration(db, actor, school_id, kind, record_id, expected_version):
    require_authority(db, actor, school_id, 'platform.manage')
    model = {'policy': ProcessingPolicy, 'release': ModelRelease}.get(kind)
    if model is None:
        raise DomainError('invalid_configuration', 'Unknown configuration type.', 422)
    record = db.scalar(select(model).where(model.school_id == school_id, model.id == str(record_id)).with_for_update())
    if record is None:
        raise access_denied()
    _version(record, expected_version)
    record.state = 'revoked'
    _event(db, actor, record, 'ai.configuration_revoked')
    db.commit()
    return record


def evaluate_release(db, actor, school_id, release_id, expected_version, policy_id, suite_name, runtime):
    require_authority(db, actor, school_id, 'platform.manage')
    release = db.scalar(select(ModelRelease).where(ModelRelease.school_id == school_id, ModelRelease.id == str(release_id)))
    policy = db.scalar(select(ProcessingPolicy).where(ProcessingPolicy.school_id == school_id, ProcessingPolicy.id == str(policy_id)))
    if release is None or policy is None:
        raise access_denied()
    _version(release, expected_version)
    if release.state != 'candidate' or policy.state != 'active' or policy.provider_key != release.provider_key:
        raise DomainError('evaluation_configuration_invalid', 'Evaluate a candidate with a matching active policy.', 409)
    suite = runtime.evaluation_suites.get(suite_name)
    provider = runtime.providers.get(release.provider_key)
    if not suite or provider is None or provider_digest(provider) != release.provider_digest:
        raise DomainError('evaluation_unavailable', 'Configure fixed synthetic evaluation fixtures and a provider first.', 503)
    if any(not case.sources or any(s.provenance != 'synthetic_fixture' or not s.provenance_reference for s in case.sources) for case in suite):
        raise DomainError('synthetic_evaluation_required', 'Evaluations require trusted synthetic fixtures.', 422)
    suite_manifest = [{'name': c.name, 'purpose': c.purpose, 'sources': _manifest(c.sources), 'required': c.required_substrings, 'forbidden': c.forbidden_substrings} for c in suite]
    passed, failures, unsupported, latency = 0, [], 0, []
    for case in suite:
        started = time.monotonic()
        try:
            if PURPOSE_CAPABILITIES.get(case.purpose) != release.capability:
                raise ProviderFailure('purpose_not_supported')
            output = invoke(runtime, provider, release, policy.configuration, list(case.sources))
            rendered = json.dumps(output, ensure_ascii=False).casefold()
            if any(s.casefold() not in rendered for s in case.required_substrings) or any(s.casefold() in rendered for s in case.forbidden_substrings):
                raise ProviderFailure('evaluation_expectation_failed', 'failed')
            passed += 1
        except ProviderFailure as exc:
            failures.append({'case': case.name, 'error_code': exc.code})
            unsupported += exc.unsupported_sources
        latency.append(round((time.monotonic() - started) * 1000))
    # No model prose or source content is duplicated in operational metrics.
    evaluation = ModelEvaluation(school_id=school_id, release_id=release.id, actor_id=actor.user_id,
        release_digest=release.configuration_digest, suite_name=suite_name, suite_digest=digest(suite_manifest),
        state='passed' if passed == len(suite) else 'failed', metrics={'cases': len(suite), 'passed': passed, 'failure_rate': (len(suite)-passed)/len(suite), 'latency_ms': latency, 'unsupported_source_count': unsupported, 'failures': failures})
    db.add(evaluation)
    _event(db, actor, evaluation, 'ai.evaluated')
    db.commit()
    return evaluation


def review_release(db, actor, school_id, release_id, command: ReviewCommand):
    require_authority(db, actor, school_id, 'platform.manage')
    release = db.scalar(select(ModelRelease).where(ModelRelease.school_id == school_id, ModelRelease.id == str(release_id)).with_for_update())
    if release is None:
        raise access_denied()
    _version(release, command.expected_version)
    evaluation = db.get(ModelEvaluation, str(command.evaluation_id))
    if (release.state != 'candidate' or evaluation is None or evaluation.school_id != school_id
            or evaluation.release_id != release.id or evaluation.release_digest != release.configuration_digest
            or evaluation.state != 'passed' or not command.professional_quality_confirmed):
        raise DomainError('passing_review_required', 'A passing evaluation and explicit professional quality review are required.', 409)
    release.state = 'reviewed'
    release.reviewed_by, release.reviewed_at = actor.user_id, utcnow()
    release.evaluation_id, release.review_rationale = evaluation.id, command.rationale
    _event(db, actor, release, 'ai.release_reviewed')
    db.commit()
    return release


def create_job(db, actor, school_id, command: GenerationRequest, runtime: GatewayRuntime):
    learner_id = str(command.learner_id)
    _authorize(db, actor, school_id, learner_id, command.purpose)
    fingerprint = digest(command.model_dump(mode='json'))
    existing = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.actor_id == actor.user_id, GenerationJob.logical_request_key == command.logical_request_key))
    if existing:
        if existing.request_digest != fingerprint:
            raise DomainError('idempotency_conflict', 'This request key already identifies a different operation.', 409)
        try:
            _current_sources(db, runtime, actor, existing)
        except ProviderFailure as exc:
            raise DomainError(exc.code, 'The source context is currently unavailable.', 503) from None
        return existing
    policy = db.scalar(select(ProcessingPolicy).where(ProcessingPolicy.id == str(command.policy_id), ProcessingPolicy.school_id == school_id).with_for_update())
    release = db.scalar(select(ModelRelease).where(ModelRelease.id == str(command.release_id), ModelRelease.school_id == school_id))
    if policy is None or release is None:
        raise access_denied()
    # Recheck after the policy lock: another same-key creator may have committed
    # while this request waited. Idempotent replay must not consume budget twice.
    existing = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.actor_id == actor.user_id, GenerationJob.logical_request_key == command.logical_request_key))
    if existing:
        if existing.request_digest != fingerprint:
            raise DomainError('idempotency_conflict', 'This request key already identifies a different operation.', 409)
        _current_sources(db, runtime, actor, existing)
        return existing
    # Policy locking serializes daily budget checks across concurrent requests.
    if policy.state != 'active' or command.purpose not in policy.configuration['purposes']:
        raise DomainError('processing_policy_unavailable', 'An active processing policy for this purpose is required.', 409)
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.policy_id == policy.id, GenerationJob.created_at >= today))
    if count >= policy.configuration['max_daily_jobs']:
        raise DomainError('daily_generation_limit', 'The configured daily generation budget is exhausted. Continue manually.', 429)
    try:
        sources = _resolve(db, runtime, actor, school_id, learner_id, command.purpose, command.sources)
    except ProviderFailure as exc:
        raise DomainError(exc.code, 'The source context is currently unavailable. Continue manually.', 503) from None
    job = GenerationJob(school_id=school_id, learner_id=learner_id, actor_id=actor.user_id, purpose=command.purpose,
        policy_id=policy.id, policy_version=policy.version, release_id=release.id, release_digest=release.configuration_digest,
        logical_request_key=command.logical_request_key, request_digest=fingerprint, source_manifest=_manifest(sources), state='queued')
    # Creation also enforces the reviewed release gate, while execution rechecks it.
    try:
        _configuration(db, runtime, job)
    except ProviderFailure as exc:
        raise DomainError(exc.code, 'A reviewed, passing model release and configured provider are required.', 409) from None
    db.add(job)
    try:
        _event(db, actor, job, 'ai.requested')
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.actor_id == actor.user_id, GenerationJob.logical_request_key == command.logical_request_key))
        if existing is None:
            raise
        if existing.request_digest != fingerprint:
            raise DomainError('idempotency_conflict', 'This request key already identifies a different operation.', 409) from None
        _authorize(db, actor, school_id, existing.learner_id, existing.purpose)
        _current_sources(db, runtime, actor, existing)
        return existing
    return job


def get_job(db, actor, school_id, job_id, runtime):
    job = _load(db, actor, school_id, job_id)
    try:
        _current_sources(db, runtime, actor, job)
        if job.output is not None:
            _configuration(db, runtime, job)
    except ProviderFailure as exc:
        raise DomainError(exc.code, 'The reviewed result or its source authorization is currently unavailable.', 503) from None
    record_audit(db, actor, school_id, 'ai.result_read', 'GenerationJob', job.id)
    db.commit()
    return job


def cancel_job(db, actor, school_id, job_id, expected_version, runtime):
    job = _load(db, actor, school_id, job_id, lock=True)
    _version(job, expected_version)
    if job.state in {'succeeded', 'cancelled'}:
        raise DomainError('invalid_job_transition', 'This generation cannot be cancelled in its current state.', 409)
    job.state, job.output, job.lease_expires_at = 'cancelled', None, None
    for attempt in db.scalars(select(GenerationAttempt).where(GenerationAttempt.job_id == job.id, GenerationAttempt.state == 'running')):
        attempt.state, attempt.finished_at, attempt.error_code = 'cancelled', utcnow(), 'cancelled'
    _event(db, actor, job, 'ai.cancelled')
    db.commit()
    return job


def expire_job(db, actor, school_id, job_id, expected_version):
    job = _load(db, actor, school_id, job_id, lock=True)
    _version(job, expected_version)
    if job.state != 'running' or job.lease_expires_at is None or job.lease_expires_at > utcnow():
        raise DomainError('job_not_expired', 'The running generation has not expired.', 409)
    job.state, job.error_code, job.lease_expires_at = 'unavailable', 'worker_lease_expired', None
    for attempt in db.scalars(select(GenerationAttempt).where(GenerationAttempt.job_id == job.id, GenerationAttempt.state == 'running')):
        attempt.state, attempt.finished_at, attempt.error_code = 'unavailable', utcnow(), 'worker_lease_expired'
    _event(db, actor, job, 'ai.expired')
    db.commit()
    return job


def run_job(factory, actor: Actor | None, school_id: str, job_id: str, expected_version: int, runtime: GatewayRuntime):
    """Worker may pass actor=None; rights of the persisted initiator are rechecked.

    A durable claim commits before the network call. Expired claims must explicitly
    transition through expire_job; retries never hide an earlier attempt.
    """
    started = time.monotonic()
    with factory() as db:
        background = actor is None
        if actor is None:
            row = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.id == str(job_id)))
            if row is None:
                raise access_denied()
            actor = Actor(row.actor_id)
        if background:
            job = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.id == str(job_id)).with_for_update().execution_options(populate_existing=True))
        else:
            job = _load(db, actor, school_id, job_id, lock=True)
        _version(job, expected_version)
        if job.state not in {'queued', 'failed', 'unavailable'}:
            raise DomainError('invalid_job_transition', 'Generation is already running or complete.', 409)
        # Do not keep either model calls or source content in a database transaction.
        policy = db.get(ProcessingPolicy, job.policy_id)
        maximum = policy.configuration['max_attempts'] if policy else 1
        if job.attempts >= maximum:
            raise DomainError('attempt_limit', 'The generation retry limit is exhausted. Continue manually.', 409)
        attempt = GenerationAttempt(school_id=school_id, job_id=job.id, number=job.attempts+1, state='running')
        db.add(attempt)
        failure = None
        try:
            _authorize(db, Actor(job.actor_id), school_id, job.learner_id, job.purpose)
            sources = _current_sources(db, runtime, Actor(job.actor_id), job)
            if actor.user_id != job.actor_id:
                _current_sources(db, runtime, actor, job)
            policy, release, provider = _configuration(db, runtime, job)
            validate_provider(runtime, provider, sources)
            job.lease_expires_at = utcnow() + timedelta(seconds=policy.configuration['timeout_seconds'] + 10)
        except (ProviderFailure, DomainError) as exc:
            failure = exc if isinstance(exc, ProviderFailure) else ProviderFailure('authorization_or_source_changed', 'failed')
            job.lease_expires_at = utcnow() + timedelta(seconds=10)
        job.attempts += 1
        job.state, job.error_code, job.output = 'running', None, None
        _event(db, actor, job, 'ai.started')
        attempt_id, attempt_number = attempt.id, attempt.number
        db.commit()
        # Values remain usable after this session closes (factory contract).
    output = None
    if failure is None:
        try:
            output = invoke(runtime, provider, release, policy.configuration, sources)
        except ProviderFailure as exc:
            failure = exc
    with factory() as db:
        job = db.scalar(select(GenerationJob).where(GenerationJob.school_id == school_id, GenerationJob.id == str(job_id)).with_for_update().execution_options(populate_existing=True))
        attempt = db.get(GenerationAttempt, attempt_id)
        if job.state != 'running' or job.attempts != attempt_number:
            # Cancellation or expired lease/new retry wins; discard old result.
            # Even this branch must not return another attempt's content after
            # the requester loses access during the original network call.
            _authorize(db, actor, school_id, job.learner_id, job.purpose)
            _current_sources(db, runtime, actor, job)
            return job
        try:
            _authorize(db, actor, school_id, job.learner_id, job.purpose)
            _authorize(db, Actor(job.actor_id), school_id, job.learner_id, job.purpose)
            _current_sources(db, runtime, Actor(job.actor_id), job)
            if actor.user_id != job.actor_id:
                _current_sources(db, runtime, actor, job)
            _configuration(db, runtime, job)
        except DomainError:
            failure = ProviderFailure('authorization_or_source_changed', 'failed')
        except ProviderFailure as exc:
            failure = failure or exc
        if job.lease_expires_at is None or job.lease_expires_at <= utcnow():
            failure = ProviderFailure('provider_timeout')
        job.state = failure.state if failure else 'succeeded'
        job.output, job.error_code, job.lease_expires_at = (None if failure else output), (failure.code if failure else None), None
        attempt.state, attempt.finished_at = job.state, utcnow()
        attempt.latency_ms = round((time.monotonic()-started)*1000)
        attempt.error_code = job.error_code
        attempt.unsupported_source_count = failure.unsupported_sources if failure else 0
        _event(db, actor, job, 'ai.'+job.state)
        db.commit()
        return job
