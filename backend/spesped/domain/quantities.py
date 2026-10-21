"""Quantities retain their unit, decision category and counting basis."""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .primitives import EffectivePeriod, InstrumentId, integer, identifier, nonempty


def decimal_value(value: Decimal, name: str) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")


@dataclass(frozen=True)
class DurationMinutes:
    value: int

    def __post_init__(self) -> None:
        integer(self.value, "minutes")


class QuantityUnit(Enum):
    MINUTES = "minutes"
    HOURS = "hours"


class CountingBasis(Enum):
    LEARNER_TIME = "learner_time"
    STAFF_TIME = "staff_time"


class SupportCategory(Enum):
    INDIVIDUALLY_ADAPTED_EDUCATION = "individually_adapted_education"
    PERSONAL_ASSISTANCE = "personal_assistance"
    PHYSICAL_ADAPTATION = "physical_adaptation"


@dataclass(frozen=True)
class EntitlementQuantity:
    amount: Decimal
    unit: QuantityUnit
    reference_period: EffectivePeriod
    category: SupportCategory
    decision_clause: str
    counting_basis: CountingBasis

    def __post_init__(self) -> None:
        decimal_value(self.amount, "amount")
        if self.amount < 0:
            raise ValueError("amount cannot be negative")
        if type(self.unit) is not QuantityUnit or type(self.category) is not SupportCategory:
            raise ValueError("Unsupported quantity unit or support category")
        if type(self.counting_basis) is not CountingBasis:
            raise ValueError("A staff/learner counting basis is required")
        if not isinstance(self.reference_period, EffectivePeriod):
            raise ValueError("A reference period is required")
        nonempty(self.decision_clause, "decision_clause")

    def total_minutes(self) -> Decimal:
        return self.amount * (60 if self.unit is QuantityUnit.HOURS else 1)

    def add(self, other: "EntitlementQuantity") -> "EntitlementQuantity":
        if not isinstance(other, EntitlementQuantity):
            raise ValueError("An entitlement quantity is required")
        if (self.reference_period, self.category, self.decision_clause, self.counting_basis) != (
                other.reference_period, other.category, other.decision_clause, other.counting_basis):
            raise ValueError("Quantities with different decision or counting scope cannot be combined")
        return EntitlementQuantity(self.total_minutes() + other.total_minutes(), QuantityUnit.MINUTES,
                                   self.reference_period, self.category, self.decision_clause,
                                   self.counting_basis)


@dataclass(frozen=True)
class ScoreScale:
    id: str
    minimum: Decimal
    maximum: Decimal

    def __post_init__(self) -> None:
        nonempty(self.id, "scale id")
        decimal_value(self.minimum, "minimum")
        decimal_value(self.maximum, "maximum")
        if self.minimum >= self.maximum:
            raise ValueError("Scale minimum must precede maximum")


@dataclass(frozen=True)
class AssessmentScore:
    instrument_id: InstrumentId
    instrument_version: int
    scale: ScoreScale
    raw_value: Decimal

    def __post_init__(self) -> None:
        identifier(self.instrument_id, InstrumentId)
        integer(self.instrument_version, "instrument_version", 1)
        if not isinstance(self.scale, ScoreScale):
            raise ValueError("An identified score scale is required")
        decimal_value(self.raw_value, "raw_value")
        if not self.scale.minimum <= self.raw_value <= self.scale.maximum:
            raise ValueError("Score is outside its instrument scale")

    def difference_from(self, earlier: "AssessmentScore") -> Decimal:
        """Numeric difference only, never an inferred progress judgement."""
        if not isinstance(earlier, AssessmentScore) or (
                self.instrument_id, self.instrument_version, self.scale) != (
                earlier.instrument_id, earlier.instrument_version, earlier.scale):
            raise ValueError("Scores from different instruments, versions or scales are incomparable")
        return self.raw_value - earlier.raw_value
