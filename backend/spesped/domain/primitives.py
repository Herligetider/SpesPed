"""Small immutable values shared across bounded contexts; no persistence or I/O."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware datetime is required")
    return value.astimezone(timezone.utc)


def local_date(value: date) -> None:
    if type(value) is not date:
        raise ValueError("A local date, not a datetime, is required")


def school_zone(value: str) -> ZoneInfo:
    nonempty(value, "timezone")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("An IANA timezone is required") from error


@dataclass(frozen=True)
class OpaqueId:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID) or self.value.int == 0:
            raise ValueError("A non-nil UUID is required")

    @classmethod
    def new(cls):
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str):
        if not isinstance(value, str):
            raise ValueError("An opaque UUID string is required")
        return cls(UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SchoolId(OpaqueId): pass
@dataclass(frozen=True)
class LearnerId(OpaqueId): pass
@dataclass(frozen=True)
class CaseId(OpaqueId): pass
@dataclass(frozen=True)
class RevisionId(OpaqueId): pass
@dataclass(frozen=True)
class SourceItemId(OpaqueId): pass
@dataclass(frozen=True)
class EvidenceItemId(OpaqueId): pass
@dataclass(frozen=True)
class PersonId(OpaqueId): pass
@dataclass(frozen=True)
class UserId(OpaqueId): pass
@dataclass(frozen=True)
class AttachmentId(OpaqueId): pass
@dataclass(frozen=True)
class InstrumentId(OpaqueId): pass
@dataclass(frozen=True)
class ScheduleId(OpaqueId): pass


def identifier(value: OpaqueId, kind: type[OpaqueId]) -> None:
    if type(value) is not kind:
        raise ValueError(f"Expected {kind.__name__}")


@dataclass(frozen=True)
class SubjectScope:
    school_id: SchoolId
    learner_id: LearnerId
    case_id: CaseId | None = None

    def __post_init__(self) -> None:
        identifier(self.school_id, SchoolId)
        identifier(self.learner_id, LearnerId)
        if self.case_id is not None:
            identifier(self.case_id, CaseId)


@dataclass(frozen=True)
class EffectivePeriod:
    """An inclusive start and exclusive end; None means no end."""
    start: datetime
    end: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", instant(self.start))
        if self.end is not None:
            object.__setattr__(self, "end", instant(self.end))
            if self.start >= self.end:
                raise ValueError("start must precede end")

    def contains(self, value: datetime) -> bool:
        value = instant(value)
        return self.start <= value and (self.end is None or value < self.end)


@dataclass(frozen=True)
class SummaryPeriod:
    """Inclusive user-selected local dates in the school's timezone."""
    start: date
    end: date
    timezone: str

    def __post_init__(self) -> None:
        local_date(self.start)
        local_date(self.end)
        school_zone(self.timezone)
        if self.start > self.end or self.end == date.max:
            raise ValueError("Invalid summary date range")

    def to_utc(self) -> EffectivePeriod:
        zone = school_zone(self.timezone)
        return EffectivePeriod(datetime.combine(self.start, time.min, zone),
                               datetime.combine(self.end + timedelta(days=1), time.min, zone))


@dataclass(frozen=True)
class OccurrenceTime:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", instant(self.value))


@dataclass(frozen=True)
class RecordedTime:
    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", instant(self.value))
