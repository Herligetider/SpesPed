from datetime import date
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("password", mode="before")
    @classmethod
    def preserve_password(cls, value):
        return value

    model_config = ConfigDict(extra="forbid")


class LearnerCreate(Input):
    display_name: str = Field(min_length=1, max_length=200)
    grade: int = Field(ge=1, le=10, strict=True)
    group_name: str = Field(min_length=1, max_length=100)


class LearnerPatch(Input):
    expected_version: int = Field(ge=1, strict=True)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    grade: int | None = Field(default=None, ge=1, le=10, strict=True)
    group_name: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def nonempty(self):
        changed = self.model_fields_set - {"expected_version"}
        if not changed or any(getattr(self, field) is None for field in changed):
            raise ValueError("Provide at least one non-null change")
        return self


class DatedInput(Input):
    valid_from: date
    valid_until: date | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("The end date precedes the start date")
        return self


class MembershipInput(DatedInput):
    user_id: UUID
    role: Literal["teacher", "special_educator", "assistant", "school_leader", "school_administrator", "technical_administrator", "guardian"]


# Only assignments to ordinary pupil work belong here. Signing and identity management
# always require a separate dated AuthorityGrant; future modules can extend this list.
ASSIGNMENT_ACTIONS = {"learner.read", "learner.update", "brief.read", "observation.create", "evidence.read", "evidence.create", "document.contribute"}


class AssignmentInput(DatedInput):
    learner_id: UUID
    user_id: UUID
    actions: list[str] = Field(min_length=1, max_length=20)
    purpose: str = Field(min_length=1, max_length=100)

    @field_validator("actions")
    @classmethod
    def valid_actions(cls, actions):
        if len(set(actions)) != len(actions) or any(a not in ASSIGNMENT_ACTIONS for a in actions):
            raise ValueError("Unsupported or duplicate assignment action")
        return actions


class AuthorityInput(DatedInput):
    user_id: UUID
    action: str = Field(min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    learner_id: UUID | None = None
    case_id: UUID | None = None


class GuardianInput(DatedInput):
    learner_id: UUID
    guardian_user_id: UUID
    relationship: Literal["parent", "guardian", "representative"]
    source_reference: str = Field(min_length=1, max_length=200)
    parental_responsibility: bool
    information_rights: Literal["unresolved", "restricted", "confirmed"]
    restrictions: str = Field(default="", max_length=1000)


class DatedUpdate(DatedInput):
    expected_version: int = Field(ge=1, strict=True)
    state: Literal["active", "revoked"]
