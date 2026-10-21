"""Pupil report obligations, with typed human-reviewed period applicability."""
from sqlalchemy import select
from spesped.auth import require_learner_access
from spesped.errors import DomainError
from spesped.contexts.identity.document_choices import reader, bounded, json_member
from . import models as m
from .projections import report_obligation_basis

def obligations(db, actor, school_id, learner_id, kind, starts_on, ends_on, requirement_version_id=None, query=None):
    with reader(db) as fresh:
        require_learner_access(fresh, actor, school_id, learner_id, 'read')
        statement = select(m.ObligationInstance, m.RequirementVersion, m.RequirementDefinition).join(
            m.RequirementVersion, m.RequirementVersion.id == m.ObligationInstance.requirement_version_id).join(
            m.RequirementDefinition, m.RequirementDefinition.id == m.RequirementVersion.requirement_id).where(
            m.ObligationInstance.school_id == school_id, m.ObligationInstance.learner_id == learner_id,
            m.ObligationInstance.case_id.is_(None), json_member(fresh,m.RequirementVersion.required_document_types,kind))
        if requirement_version_id: statement = statement.where(m.ObligationInstance.requirement_version_id == str(requirement_version_id))
        if query: statement = statement.where(m.RequirementDefinition.title.icontains(query, autoescape=True) | m.ObligationInstance.period_key.icontains(query, autoescape=True))
        items = []
        for row, version, definition in bounded(fresh, statement.order_by(m.ObligationInstance.created_at, m.ObligationInstance.id)):
            try:
                basis = report_obligation_basis(fresh, actor, school_id, learner_id, row.id, kind, starts_on, ends_on)
            except DomainError as exc:
                if exc.status_code not in {403, 409}: raise
                continue
            items.append(dict(obligation_id=row.id, label=definition.title, requirement_version_id=version.id,
                period_key=row.period_key, state=basis['state'], report_period=basis['report_period'], unresolved_inputs=basis['unresolved_inputs']))
        return items
