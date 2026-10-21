"""Evidence membership distinguishes occurrence, knowledge time and source revision."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re

from .primitives import (
    EvidenceItemId, OccurrenceTime, PersonId, RecordedTime, RevisionId, SourceItemId,
    SubjectScope, SummaryPeriod, identifier, instant, integer, nonempty,
)


def digest_value(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("A lowercase SHA-256 digest is required")


@dataclass(frozen=True)
class SourceReference:
    scope: SubjectScope
    source_item_id: SourceItemId
    revision: int
    digest: str
    page: int | None = None
    span: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, SubjectScope):
            raise ValueError("Source subject scope is required")
        identifier(self.source_item_id, SourceItemId)
        integer(self.revision, "source revision", 1)
        digest_value(self.digest)
        if self.page is not None:
            integer(self.page, "page", 1)
        if self.span is not None:
            if type(self.span) is not tuple or len(self.span) != 2:
                raise ValueError("A half-open source span is required")
            integer(self.span[0], "span start")
            integer(self.span[1], "span end", 1)
            if self.span[0] >= self.span[1]:
                raise ValueError("Span start must precede end")

    @property
    def revision_identity(self) -> tuple:
        """Page/span locators do not alter the identity of a source revision."""
        return self.scope, self.source_item_id, self.revision, self.digest


class SourceType(Enum):
    DIRECT_OBSERVATION = "direct_observation"
    REPORTED_INFORMATION = "reported_information"
    IMPORTED_DOCUMENT = "imported_document"


class Certainty(Enum):
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    DISPUTED = "disputed"


@dataclass(frozen=True)
class EvidenceAttribution:
    reporter: PersonId
    source_type: SourceType
    certainty: Certainty
    observer: PersonId | None = None

    def __post_init__(self) -> None:
        identifier(self.reporter, PersonId)
        if self.observer is not None:
            identifier(self.observer, PersonId)
        if type(self.source_type) is not SourceType or type(self.certainty) is not Certainty:
            raise ValueError("Typed source and certainty markers are required")
        if self.source_type is SourceType.DIRECT_OBSERVATION and self.observer is None:
            raise ValueError("Direct observation must identify the observer")


@dataclass(frozen=True)
class EvidenceRecord:
    id: EvidenceItemId
    source: SourceReference
    occurred: OccurrenceTime
    recorded: RecordedTime
    attribution: EvidenceAttribution
    goal_revision: RevisionId | None = None

    def __post_init__(self) -> None:
        identifier(self.id, EvidenceItemId)
        for value, kind in ((self.source, SourceReference), (self.occurred, OccurrenceTime),
                            (self.recorded, RecordedTime), (self.attribution, EvidenceAttribution)):
            if not isinstance(value, kind):
                raise ValueError(f"Expected {kind.__name__}")
        if self.recorded.value < self.occurred.value:
            raise ValueError("Recorded evidence cannot precede its occurrence")
        if self.goal_revision is not None:
            identifier(self.goal_revision, RevisionId)


@dataclass(frozen=True)
class EvidenceCutoff:
    scope: SubjectScope
    created_at: datetime
    sources: tuple[SourceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, SubjectScope):
            raise ValueError("Snapshot subject scope is required")
        object.__setattr__(self, "created_at", instant(self.created_at))
        if type(self.sources) is not tuple or any(not isinstance(s, SourceReference) for s in self.sources):
            raise ValueError("An immutable source manifest is required")
        seen = {}
        for source in self.sources:
            if source.scope != self.scope:
                raise ValueError("Source is outside the snapshot subject scope")
            if source.source_item_id in seen and seen[source.source_item_id] != source.revision_identity:
                raise ValueError("A snapshot cannot contain conflicting source revisions")
            seen[source.source_item_id] = source.revision_identity

    def includes(self, evidence: EvidenceRecord, period: SummaryPeriod) -> bool:
        if not isinstance(evidence, EvidenceRecord) or not isinstance(period, SummaryPeriod):
            raise ValueError("Evidence and summary period are required")
        return (evidence.source.scope == self.scope
                and period.to_utc().contains(evidence.occurred.value)
                and evidence.recorded.value <= self.created_at
                and evidence.source.revision_identity in {s.revision_identity for s in self.sources})

    def is_late_entry(self, evidence: EvidenceRecord, period: SummaryPeriod) -> bool:
        return (evidence.source.scope == self.scope
                and period.to_utc().contains(evidence.occurred.value)
                and evidence.recorded.value > self.created_at)


class GoalEvidenceStatus(Enum):
    INSUFFICIENT = "insufficient"
    SUPPORTED = "supported"


@dataclass(frozen=True)
class GoalEvidenceResult:
    """Presence of relevant confirmed evidence, not a finding of goal attainment."""
    status: GoalEvidenceStatus
    evidence_ids: tuple[EvidenceItemId, ...]
    reason: str

    def __post_init__(self) -> None:
        if type(self.status) is not GoalEvidenceStatus or type(self.evidence_ids) is not tuple:
            raise ValueError("Typed status and immutable evidence identities are required")
        for evidence_id in self.evidence_ids:
            identifier(evidence_id, EvidenceItemId)
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate supporting evidence identity")
        if (self.status is GoalEvidenceStatus.SUPPORTED) != bool(self.evidence_ids):
            raise ValueError("Supported status requires evidence; insufficient status has none")
        nonempty(self.reason, "reason")


def evaluate_goal_evidence(goal_revision: RevisionId, records: tuple[EvidenceRecord, ...],
                           cutoff: EvidenceCutoff, period: SummaryPeriod) -> GoalEvidenceResult:
    identifier(goal_revision, RevisionId)
    if type(records) is not tuple or any(not isinstance(r, EvidenceRecord) for r in records):
        raise ValueError("Immutable evidence records are required")
    if len({r.id for r in records}) != len(records):
        raise ValueError("Duplicate evidence identities")
    supporting = tuple(r.id for r in records if r.goal_revision == goal_revision
                       and r.attribution.certainty is Certainty.CONFIRMED and cutoff.includes(r, period))
    if supporting:
        return GoalEvidenceResult(GoalEvidenceStatus.SUPPORTED, supporting,
                                  "Relevant confirmed evidence exists; educator judgement is required")
    return GoalEvidenceResult(GoalEvidenceStatus.INSUFFICIENT, (), "No relevant confirmed evidence known at cutoff")
