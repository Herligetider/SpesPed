"""Approval of exact canonical content, attachments and optional disclosure scope.

Binding checks establish freshness only. Applications must validate the reviewer's
authority at approval, and current recipient rights at every dispatch.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math

from .evidence import digest_value
from .policies import DisclosureChannel, RecipientScope
from .primitives import AttachmentId, RevisionId, SubjectScope, UserId, identifier, instant, nonempty


def _validate_json(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) in (list, tuple):
        for item in value:
            _validate_json(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError("Content must contain only finite JSON values and string object keys")


def canonical_content_digest(content: object) -> str:
    """UTF-8 JSON, sorted keys, compact separators, no NaN or implicit coercions.

    This is a versioned application format, not a claim to RFC 8785 compliance.
    """
    _validate_json(content)
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AttachmentDigest:
    attachment_id: AttachmentId
    digest: str

    def __post_init__(self) -> None:
        identifier(self.attachment_id, AttachmentId)
        digest_value(self.digest)


def _attachments(values: tuple[AttachmentDigest, ...]) -> tuple[AttachmentDigest, ...]:
    if type(values) is not tuple or any(not isinstance(a, AttachmentDigest) for a in values):
        raise ValueError("Immutable attachment digests are required")
    if len({a.attachment_id for a in values}) != len(values):
        raise ValueError("Duplicate attachment identity")
    return tuple(sorted(values, key=lambda a: str(a.attachment_id)))


@dataclass(frozen=True)
class ApprovalBinding:
    scope: SubjectScope
    revision_id: RevisionId
    revision_digest: str
    attachments: tuple[AttachmentDigest, ...]
    reviewer_id: UserId
    authority: str
    approved_at: datetime
    recipient_scope: RecipientScope | None = None
    channel: DisclosureChannel | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, SubjectScope):
            raise ValueError("Approval subject scope is required")
        identifier(self.revision_id, RevisionId)
        identifier(self.reviewer_id, UserId)
        digest_value(self.revision_digest)
        object.__setattr__(self, "attachments", _attachments(self.attachments))
        nonempty(self.authority, "authority")
        object.__setattr__(self, "approved_at", instant(self.approved_at))
        if (self.recipient_scope is None) != (self.channel is None):
            raise ValueError("Disclosure binding requires both recipient scope and channel")
        if self.recipient_scope is not None:
            if not isinstance(self.recipient_scope, RecipientScope) or self.recipient_scope.subject != self.scope:
                raise ValueError("Recipient is outside the approved subject scope")
            if type(self.channel) is not DisclosureChannel:
                raise ValueError("A typed disclosure channel is required")

    @classmethod
    def create(cls, *, scope: SubjectScope, revision_id: RevisionId, content: object,
               attachments: tuple[AttachmentDigest, ...], reviewer_id: UserId, authority: str,
               approved_at: datetime, recipient_scope: RecipientScope | None = None,
               channel: DisclosureChannel | None = None) -> "ApprovalBinding":
        return cls(scope, revision_id, canonical_content_digest(content), attachments, reviewer_id,
                   authority, approved_at, recipient_scope, channel)

    def matches(self, *, scope: SubjectScope, revision_id: RevisionId, content: object,
                attachments: tuple[AttachmentDigest, ...], recipient_scope: RecipientScope | None = None,
                channel: DisclosureChannel | None = None) -> bool:
        identifier(revision_id, RevisionId)
        return (self.scope == scope and self.revision_id == revision_id
                and self.revision_digest == canonical_content_digest(content)
                and self.attachments == _attachments(attachments)
                and self.recipient_scope == recipient_scope and self.channel == channel)

    @property
    def package_digest(self) -> str:
        recipient = self.recipient_scope
        return canonical_content_digest({
            "format": "spesped.approval.v1",
            "school": str(self.scope.school_id), "learner": str(self.scope.learner_id),
            "case": str(self.scope.case_id) if self.scope.case_id else None,
            "revision": str(self.revision_id), "content": self.revision_digest,
            "attachments": [{"id": str(a.attachment_id), "digest": a.digest} for a in self.attachments],
            "recipient": None if recipient is None else {
                "person": str(recipient.person_id), "purpose": recipient.purpose,
                "categories": sorted(recipient.information_categories),
                "restrictions": sorted(recipient.restrictions),
                "relationship_source": str(recipient.relationship_evidence.source_item_id),
                "relationship_revision": recipient.relationship_evidence.revision,
                "relationship_digest": recipient.relationship_evidence.digest,
                "relationship_page": recipient.relationship_evidence.page,
                "relationship_span": recipient.relationship_evidence.span,
            },
            "channel": self.channel.value if self.channel else None,
        })
