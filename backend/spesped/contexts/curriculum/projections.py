"""Reviewed BC06 assessment context for read-only downstream consumers.

The rules are reviewed source text, not executable permission to grade or exempt
a pupil. The assessment owner must obtain those separate decisions explicitly.
"""
from datetime import date

from pydantic import ValidationError
from sqlalchemy import select

from spesped.errors import DomainError
from . import models, schemas, service
from .adapters import digest


@service.read_contract
def reviewed_assessment_scheme(
    db, actor, school_id, scheme_revision_id, *, starts_on: date, ends_on: date,
):
    """Resolve an exact reviewed scheme covering both inclusive period bounds.

    Uses the current caller's school/original-source authority. No source text,
    role-derived grade authority, mutation, audit or transaction ownership is
    transferred to the consumer. Pending dependency edits remain untouched.
    """
    if type(starts_on) is not date or type(ends_on) is not date or starts_on > ends_on:
        raise DomainError('assessment_period', 'Choose an ordered inclusive date period.', 422)
    school_id = str(school_id)
    revision = service.scheme_current(db, actor, school_id, scheme_revision_id, starts_on)
    if ends_on > revision.valid_until:
        raise DomainError('scheme_period', 'The reviewed scheme must cover the entire assessment period.', 409)
    rules = db.scalar(select(models.AssessmentScheme).where(
        models.AssessmentScheme.school_id == school_id,
        models.AssessmentScheme.scheme_revision_id == revision.id,
    ).execution_options(populate_existing=True))
    if rules is None or not revision.reviewed_by or not revision.reviewed_at or not revision.approved_on:
        raise DomainError('scheme_review_required', 'An exact reviewed assessment scheme is required.', 409)
    try:
        content = schemas.SchemeContent(
            title=revision.title, pedagogy=revision.pedagogy,
            valid_from=revision.valid_from, valid_until=revision.valid_until,
            goals=revision.goals, subject_allocations=revision.subject_allocations,
            sources=revision.sources, assessment_rules=rules.rules,
        ).model_dump(mode='json')
    except ValidationError:
        raise DomainError('scheme_review_required', 'The reviewed assessment scheme needs correction.', 409) from None
    if digest(content) != revision.content_digest:
        raise DomainError('scheme_changed', 'The stored scheme no longer matches its reviewed content.', 409)
    value = service.json_view({
        'school_id': school_id, 'scheme_id': revision.scheme_id,
        'scheme_revision_id': revision.id, 'revision': revision.number,
        'content_digest': revision.content_digest, 'state': revision.state,
        'title': content['title'], 'pedagogy': content['pedagogy'],
        'valid_from': content['valid_from'], 'valid_until': content['valid_until'],
        'goals': content['goals'], 'assessment_rules': content['assessment_rules'],
        'source_references': content['sources'],
        'approval': {
            'reviewed_by': revision.reviewed_by, 'reviewed_at': revision.reviewed_at,
            'approved_on': revision.approved_on, 'approval_reference': revision.approval_reference,
        },
        'grading_authority': 'unassessed', 'exemption_authority': 'unassessed',
    })
    return {**value, 'basis_digest': digest(value)}
