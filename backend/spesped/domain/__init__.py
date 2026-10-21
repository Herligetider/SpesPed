"""Framework-independent immutable domain values and deterministic policies.

These values validate internal consistency. Access, authority, concurrency and
persistence remain application responsibilities; an identifier is never a grant.
"""
from .approval import ApprovalBinding, AttachmentDigest, canonical_content_digest
from .evidence import (Certainty, EvidenceAttribution, EvidenceCutoff, EvidenceRecord,
                       GoalEvidenceResult, GoalEvidenceStatus, SourceReference, SourceType,
                       evaluate_goal_evidence)
from .policies import ApplicabilityResult, ApplicabilityStatus, DisclosureChannel, RecipientScope
from .primitives import (AttachmentId, CaseId, DecisionId, DecisionProvisionId, EffectivePeriod, EvidenceItemId, InstrumentId,
                         LearnerId, OccurrenceTime, OpaqueId, PersonId, RecordedTime, RevisionId,
                         ScheduleId, SchoolId, SourceItemId, SubjectScope, SummaryPeriod, UserId,
                         calendar_date_boundary)
from .quantities import (AssessmentScore, CountingBasis, DecisionProvisionReference, DurationMinutes, EntitlementQuantity,
                         QuantityUnit, ScoreScale, SupportCategory)
from .recurrence import (DraftCadence, DraftPeriodSelection, DraftRecurrence, DraftRequest,
                         IdempotencyIdentity, ManualDraftRequest, MonthEndPolicy, PeriodRule)

__all__ = [
    "ApprovalBinding", "AttachmentDigest", "canonical_content_digest", "Certainty",
    "EvidenceAttribution", "EvidenceCutoff", "EvidenceRecord", "GoalEvidenceResult",
    "GoalEvidenceStatus", "SourceReference", "SourceType", "evaluate_goal_evidence",
    "ApplicabilityResult", "ApplicabilityStatus", "DisclosureChannel", "RecipientScope",
    "AttachmentId", "CaseId", "EffectivePeriod", "EvidenceItemId", "InstrumentId", "LearnerId",
    "OccurrenceTime", "OpaqueId", "PersonId", "RecordedTime", "RevisionId", "ScheduleId", "SchoolId",
    "SourceItemId", "SubjectScope", "SummaryPeriod", "UserId", "AssessmentScore", "CountingBasis",
    "DurationMinutes", "EntitlementQuantity", "QuantityUnit", "ScoreScale", "SupportCategory",
    "DraftCadence", "DraftPeriodSelection", "DraftRecurrence", "DraftRequest", "IdempotencyIdentity",
    "MonthEndPolicy", "PeriodRule", "calendar_date_boundary", "DecisionId", "DecisionProvisionId",
    "DecisionProvisionReference", "ManualDraftRequest",
]
