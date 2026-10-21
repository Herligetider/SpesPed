"""Metadata-only ports for other contexts' authorized curated projections.

The caller must authorize its own projection before using this port. A true result
does not authorize reading source prose, original documents, evidence or history;
those reads still go through the evidence service's actor-aware access checks.
This module has no HTTP route and returns no source content or identifiers.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EvidenceItem, EvidenceRevision, SourceItem, SourceRevision, SourceSubjectLink


def confirmed_binding_is_current(
    db: Session, school_id: str, learner_id: str, evidence_id: str,
    evidence_revision: int, link_id: str,
) -> bool:
    """Check an exact confirmed binding without granting dossier read access.

    A correction, reassignment, disputed interpretation, revoked link or newer
    original makes the old projection stale. All checks are one metadata query,
    so ORM-cached objects cannot conceal a newer committed source revision.
    """
    if type(evidence_revision) is not int or evidence_revision < 1:
        return False
    try:
        school_id, learner_id, evidence_id, link_id = (
            str(UUID(str(value))) for value in (school_id, learner_id, evidence_id, link_id)
        )
    except (ValueError, TypeError, AttributeError):
        return False
    query = (
        select(EvidenceItem.id)
        .join(EvidenceRevision, (
            (EvidenceRevision.school_id == EvidenceItem.school_id)
            & (EvidenceRevision.evidence_id == EvidenceItem.id)
            & (EvidenceRevision.revision == EvidenceItem.current_revision)
            & (EvidenceRevision.learner_id == EvidenceItem.learner_id)
        ))
        .join(SourceSubjectLink, (
            (SourceSubjectLink.school_id == EvidenceItem.school_id)
            & (SourceSubjectLink.id == EvidenceRevision.link_id)
            & (SourceSubjectLink.evidence_id == EvidenceItem.id)
            & (SourceSubjectLink.learner_id == EvidenceItem.learner_id)
        ))
        .join(SourceItem, (
            (SourceItem.school_id == SourceSubjectLink.school_id)
            & (SourceItem.id == SourceSubjectLink.source_id)
            & (SourceItem.current_revision == SourceSubjectLink.source_revision)
        ))
        .join(SourceRevision, (
            (SourceRevision.school_id == SourceItem.school_id)
            & (SourceRevision.source_id == SourceItem.id)
            & (SourceRevision.revision == SourceItem.current_revision)
            & (SourceRevision.digest == SourceSubjectLink.source_digest)
        ))
        .where(
            EvidenceItem.school_id == school_id,
            EvidenceItem.learner_id == learner_id,
            EvidenceItem.id == evidence_id,
            EvidenceItem.current_revision == evidence_revision,
            EvidenceRevision.certainty == 'confirmed',
            SourceSubjectLink.id == link_id,
            SourceSubjectLink.revoked_at.is_(None),
        )
    )
    return db.scalar(query) is not None
