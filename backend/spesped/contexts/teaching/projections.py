"""Read-only learner-specific actual-work facts for assessment/reporting owners."""
from sqlalchemy import select

from spesped.domain.approval import canonical_content_digest
from spesped.errors import DomainError, access_denied
from . import models, service


def learner_delivery_basis(db, actor, school_id, learner_id, delivery_revision_id):
    """Resolve current recorded work, without creating staffing follow-up tasks.

    Actual participation is distinct from qualification/entitlement assessment.
    This projection never exposes another pupil, group narrative, staff totals or
    a historical plan's prose. It does not assert progress or fulfilment.
    """
    dependencies = {
        'spesped.contexts.identity.models', 'spesped.contexts.evidence.models',
        'spesped.contexts.entitlements.models', 'spesped.contexts.plans.models',
        'spesped.contexts.teaching.models', 'spesped.contexts.platform.models',
    }
    excluded = {'AuditRecord', 'IdentityEvent', 'TeachingEvent', 'CommandReceipt'}
    pending = set(db.dirty) | set(db.deleted) | set(db.new)
    if any(type(row).__module__ in dependencies and type(row).__name__ not in excluded for row in pending):
        raise DomainError('dependency_pending', 'Flush or roll back pending dependency changes before resolving actual work.', 409)
    school_id, learner_id = str(school_id), str(learner_id)
    with db.no_autoflush:
        service.access(db, actor, school_id, learner_id)
        revision = service.load(db, models.DeliveryRevision, school_id, delivery_revision_id)
        root = service.load(db, models.SessionDelivery, school_id, revision.delivery_id)
        participants = list(db.scalars(select(models.LearnerParticipation).where(
            models.LearnerParticipation.school_id == school_id,
            models.LearnerParticipation.delivery_revision_id == revision.id,
            models.LearnerParticipation.learner_id == learner_id,
        ).order_by(models.LearnerParticipation.id).execution_options(populate_existing=True)))
        # Do not reveal current-version information for an unrelated pupil.
        if not participants:
            raise access_denied()
        if root.current_revision != revision.revision:
            raise DomainError('actual_changed', 'Select the current recorded delivery revision.', 409)
        value = {
            'school_id': school_id, 'learner_id': learner_id,
            'delivery_id': root.id, 'delivery_version': root.version,
            'delivery_revision_id': revision.id, 'revision': revision.revision,
            **service.row_json(revision, (
                'session_revision_id', 'occurred_at', 'duration_minutes', 'recorded_by',
            )),
            'recorded_at': revision.created_at.isoformat(), 'state': revision.status,
            'cause': revision.cause,
            'participation': [
                {
                    **service.row_json(participant, (
                        'id', 'goal_revision_ids', 'status', 'minutes', 'category',
                        'support', 'provision', 'counting_basis', 'attributed_staff_minutes',
                    )),
                    'reported_support_status': participant.support_status,
                    'support_assessment': 'assessed' if service.support_assessment_current(
                        db, actor, revision, participant,
                    ) else 'unassessed',
                }
                for participant in participants
            ],
        }
        return {**value, 'content_digest': canonical_content_digest(value)}
