"""Optional read-only reviewed rules adapter; aggregate writes never call governance commands."""
from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class ReviewedRuleContext:
    profile_id: str
    profile_revision: int
    obligation_ids: tuple[str, ...]
    documentation_requirements: tuple[str, ...]
    notification_requirements: tuple[str, ...]

class ReviewedRuleContextResolver(Protocol):
    def __call__(self, db, actor, school_id: str, learner_id: str, case_id: str) -> ReviewedRuleContext:
        """Reauthorize and return actual reviewed effective profile/obligation metadata only.

        Registered as app.state.safeguarding_rule_context or corresponding db.info
        entry. Must not commit, create obligations or infer approval from a file.
        """
        ...
