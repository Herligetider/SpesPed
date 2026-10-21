"""Transaction helpers shared by BC04 and BC05, without implicit authority grants."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from spesped.audit import record_audit
from spesped.auth import require_learner_access
from spesped.db import utcnow
from spesped.domain.approval import canonical_content_digest
from spesped.errors import DomainError
from spesped.contexts.evidence import service as evidence
from spesped.contexts.evidence.models import SourceItem
from spesped.contexts.evidence.schemas import RegisterDerivative
from .models import EntitlementCommand, EntitlementEvent


def conflict(message='The revision changed. Refresh before retrying.'):
    return DomainError('revision_conflict', message, 409)


def expected(row, command):
    if row.version != command.expected_version:
        raise conflict()


def commit(db):
    try:
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise conflict('A concurrent command changed this record or used this request key. Refresh and retry.') from None


def mutate(db, operation):
    try:
        value = operation()
        commit(db)
        return value
    except Exception:
        db.rollback()
        raise


def audit(db, actor, row, action, event_model=EntitlementEvent, **payload):
    db.flush()
    record_audit(db, actor, row.school_id, action, row.__tablename__, row.id)
    db.add(event_model(school_id=row.school_id, aggregate_id=row.id, aggregate_version=row.version, event_type=action, payload=payload))


def replay(db, actor, school_id, operation, command, target=None, command_model=EntitlementCommand):
    digest = canonical_content_digest({'operation':operation, 'target':target, 'command': command.model_dump(mode='json')})
    prior = db.scalar(select(command_model).where(command_model.school_id == school_id, command_model.actor_id == actor.user_id, command_model.request_key == command.request_key))
    if prior:
        if prior.digest != digest or prior.operation != operation:
            raise DomainError('idempotency_conflict', 'This request key was used with different content or scope.', 409)
        return prior.target_id, digest
    return None, digest


def remember(db, actor, school_id, operation, command, digest, target_id, command_model=EntitlementCommand):
    db.add(command_model(school_id=school_id, actor_id=actor.user_id, request_key=command.request_key, digest=digest, operation=operation, target_id=target_id))


def source_binding(db, actor, school_id, learner_id, binding):
    value = binding.model_dump(mode='json') if hasattr(binding,'model_dump') else binding
    item = evidence.evidence(db, actor, school_id, str(value['evidence_id']), 'evidence.read', lock=True)
    revision = evidence.current(db, item)
    if item.learner_id != learner_id or item.current_revision != value['evidence_revision'] or revision.link_id != str(value['link_id']) or revision.certainty != 'confirmed':
        raise DomainError('source_changed', 'The source is changed, disputed or belongs to another pupil. Review its current excerpt.', 409)
    excerpt = evidence.excerpt_view(db, actor, school_id, str(value['link_id']))
    source = db.get(SourceItem, excerpt['source_id'])
    if source.current_revision != excerpt['revision']:
        raise DomainError('source_changed', 'The original source has a newer revision. Review the new source.', 409)
    return value


def sources(db, actor, school_id, learner_id, values):
    return [source_binding(db, actor, school_id, learner_id, v) for v in values]


def source_status(db, actor, school_id, learner_id, values):
    try:
        sources(db, actor, school_id, learner_id, values)
        return 'current'
    except DomainError as exc:
        if exc.status_code in {403,409}:
            return 'review_required'
        raise


def depend(db, actor, school_id, learner_id, bindings, target_type, target_id, revision=1):
    for binding in bindings:
        source_binding(db, actor, school_id, learner_id, binding)
        # Derivative registration requires the evidence owner's write authority;
        # deliberately do not bypass it through an internal table insert.
        evidence.register_derivative(db, actor, school_id, str(binding['evidence_id']), RegisterDerivative(evidence_revision=binding['evidence_revision'], target_type=target_type, target_id=target_id, target_revision=revision, state='draft'))


def touch(row):
    row.updated_at = utcnow()
