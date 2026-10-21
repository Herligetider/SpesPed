"""Pupil-scoped observation, actual-work and future-plan coordinates."""
from sqlalchemy import select
from spesped.errors import DomainError
from spesped.contexts.identity.document_choices import reader, bounded
from . import models as m, service
from .projections import learner_delivery_basis

def actuals(db, actor, school_id, learner_id, start, end):
    with reader(db) as fresh:
        service.access(fresh, actor, school_id, learner_id)
        participation = select(m.LearnerParticipation.delivery_revision_id).where(
            m.LearnerParticipation.school_id == school_id, m.LearnerParticipation.learner_id == learner_id)
        rows = bounded(fresh, select(m.DeliveryRevision).join(m.SessionDelivery,
            m.SessionDelivery.id == m.DeliveryRevision.delivery_id).where(
            m.DeliveryRevision.school_id == school_id, m.DeliveryRevision.id.in_(participation),
            m.DeliveryRevision.revision == m.SessionDelivery.current_revision,
            m.DeliveryRevision.occurred_at >= start, m.DeliveryRevision.occurred_at < end).order_by(m.DeliveryRevision.occurred_at, m.DeliveryRevision.id))
        items = []
        for (revision,) in rows:
            value = learner_delivery_basis(fresh, actor, school_id, learner_id, revision.id)
            participation = [dict(category=p['category'],status=p['status'],minutes=p['minutes'])
                for p in sorted(value['participation'],key=lambda p:p['category'])]
            # Category entries can cover the same pupil-time. Preserve their
            # individual meaning rather than adding overlapping support time.
            detail = '; '.join(f"{p['category']}: {p['status']} ({p['minutes']} minutes)" for p in participation)
            prefix = 'Recorded pupil participation by category (overlap not summed)' if len(participation)>1 else 'Recorded pupil participation'
            items.append(dict(delivery_revision_id=revision.id, revision=revision.revision,
                label=f'{prefix}: {detail}', participation=participation, occurred_at=revision.occurred_at, state=value['state'],
                classification='actual_delivery_not_learning_progress'))
        return items

def future_plans(db, actor, school_id, learner_id, start, end):
    with reader(db) as fresh:
        service.access(fresh, actor, school_id, learner_id)
        # JSON membership is filtered in SQL before the bounded inventory. A
        # single-pupil basis is required, so group prose cannot enter this port.
        member = m.TeachingBasis.learners[0]['learner_id'].as_string()
        from sqlalchemy import func
        rows = bounded(fresh, select(m.SessionRevision, m.TeachingSession, m.TeachingBasis).join(
            m.TeachingSession, m.TeachingSession.id == m.SessionRevision.session_id).join(
            m.TeachingBasis, m.TeachingBasis.id == m.SessionRevision.basis_id).where(
            m.SessionRevision.school_id == school_id, m.SessionRevision.revision == m.TeachingSession.current_revision,
            m.TeachingBasis.planned_at >= start, m.TeachingBasis.planned_at < end, func.json_array_length(m.TeachingBasis.learners) == 1,
            member == learner_id).order_by(m.TeachingBasis.planned_at, m.SessionRevision.id))
        items = []
        for revision, root, basis in rows:
            try:
                service.session(fresh, actor, school_id, root.id)
                if not service.revision_valid(fresh, actor, revision): continue
            except DomainError as exc:
                if exc.status_code not in {403, 409}: raise
                continue
            items.append(dict(session_revision_id=revision.id, revision=revision.revision,
                title=revision.content.get('title') or basis.theme[:200], planned_at=basis.planned_at,
                state=root.state, classification='future_plan_not_actual'))
        return items

def observations(db, actor, school_id, learner_id, start, end):
    with reader(db) as fresh:
        service.access(fresh, actor, school_id, learner_id)
        conditions = [m.ObservationRevision.school_id == school_id, m.ObservationRevision.learner_id == learner_id,
            m.ObservationRevision.revision == m.TeachingObservation.current_revision, m.ObservationRevision.saved.is_(True)]
        if start is not None: conditions.append(m.ObservationRevision.occurred_at >= start)
        if end is not None: conditions.append(m.ObservationRevision.occurred_at < end)
        rows = bounded(fresh, select(m.ObservationRevision).join(m.TeachingObservation,
            m.TeachingObservation.id == m.ObservationRevision.observation_id).where(*conditions).order_by(m.ObservationRevision.occurred_at, m.ObservationRevision.id))
        items = []
        for (revision,) in rows:
            try:
                value = service.read_observation(fresh, actor, school_id, learner_id, revision.id)
                if not value['confirmed'] or not value['current']: continue
            except DomainError as exc:
                if exc.status_code not in {403, 409}: raise
                continue
            items.append(dict(reference={'kind':'observation','id':revision.id,'revision':revision.revision},
                label=revision.observation[:200], source_type='observation', occurred_at=revision.occurred_at, state='current'))
        return items
