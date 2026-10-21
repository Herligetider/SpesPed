"""Narrow source validation boundary; no pupil prose crosses into governance."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ValidatedEvidenceReference:
    reference_id: str
    school_id: str
    learner_id: str | None
    case_id: str | None
    revision: int
    digest: str

class EvidenceReferenceValidator(Protocol):
    def __call__(self, db, actor, school_id: str, learner_id: str | None,
                 case_id: str | None, reference_id: str) -> ValidatedEvidenceReference:
        """Reauthorize the exact source and return immutable metadata, or raise.

        The adapter must verify current access, subject classification and revision
        using its owning context. A successful upload or UUID alone is insufficient.
        """
        ...


class CaseScopeResolver(Protocol):
    def __call__(self, db, actor, school_id: str, case_id: str) -> str:
        """Return the case's authorized learner ID from its owning context.

        Register on app.state.governance_case_scope_resolver (HTTP) or
        db.info['governance_case_scope_resolver'] (direct services). Missing
        configuration fails closed; an authority grant alone is not case identity.
        """
        ...
