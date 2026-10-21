"""Explicit unresolved applicability and recipient/purpose scope."""
from dataclasses import dataclass
from enum import Enum

from .evidence import SourceReference
from .primitives import PersonId, SubjectScope, identifier, nonempty


class ApplicabilityStatus(Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ApplicabilityResult:
    status: ApplicabilityStatus
    reasons: tuple[str, ...]
    evaluated_inputs: tuple[tuple[str, str | None], ...]

    def __post_init__(self) -> None:
        if type(self.status) is not ApplicabilityStatus:
            raise ValueError("A typed applicability status is required")
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("Applicability reasons are required")
        for reason in self.reasons:
            nonempty(reason, "reason")
        if type(self.evaluated_inputs) is not tuple:
            raise ValueError("Immutable evaluated inputs are required")
        seen = set()
        for entry in self.evaluated_inputs:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("Evaluated inputs require name/value pairs")
            name, value = entry
            nonempty(name, "input name")
            if name in seen:
                raise ValueError("Duplicate applicability input")
            seen.add(name)
            if value is None:
                if self.status is not ApplicabilityStatus.UNRESOLVED:
                    raise ValueError("Missing inputs leave applicability unresolved")
            else:
                nonempty(value, "input value")


@dataclass(frozen=True)
class RecipientScope:
    """A scoped candidate package; it is never an access or dispatch grant."""
    subject: SubjectScope
    person_id: PersonId
    relationship_evidence: SourceReference
    purpose: str
    information_categories: tuple[str, ...]
    restrictions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectScope):
            raise ValueError("Recipient subject scope is required")
        identifier(self.person_id, PersonId)
        if not isinstance(self.relationship_evidence, SourceReference):
            raise ValueError("Versioned relationship evidence is required")
        if self.relationship_evidence.scope != self.subject:
            raise ValueError("Relationship evidence is outside the subject scope")
        nonempty(self.purpose, "purpose")
        for values, label, required in ((self.information_categories, "information categories", True),
                                         (self.restrictions, "restrictions", False)):
            if type(values) is not tuple or (required and not values):
                raise ValueError(f"Immutable {label} are required")
            for value in values:
                nonempty(value, label)
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate {label}")


class DisclosureChannel(Enum):
    EMAIL = "email"
    SECURE_POST = "secure_post"
    PORTAL = "portal"
