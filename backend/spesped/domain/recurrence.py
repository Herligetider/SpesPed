"""Opt-in draft requests. Scheduling never creates a release authorization.

Runs occur at school-local midnight. Days use calendar arithmetic, months stay
anchored to the original day, and `after` is exclusive. Period selection is an
independent rule, not inferred from cadence.
"""
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from enum import Enum

from .approval import canonical_content_digest
from .primitives import (RevisionId, ScheduleId, SchoolId, SubjectScope, SummaryPeriod,
                         identifier, instant, integer, local_date, nonempty, school_zone)


class DraftCadence(Enum):
    MANUAL = "manual"
    DAYS = "days"
    MONTHS = "months"


class MonthEndPolicy(Enum):
    CLAMP = "clamp"
    SKIP = "skip"


class PeriodRule(Enum):
    MANUAL = "manual"
    PREVIOUS_DAYS = "previous_days"
    PREVIOUS_CALENDAR_MONTH = "previous_calendar_month"


@dataclass(frozen=True)
class DraftPeriodSelection:
    rule: PeriodRule
    days: int | None = None

    def __post_init__(self) -> None:
        if type(self.rule) is not PeriodRule:
            raise ValueError("A typed period rule is required")
        if self.rule is PeriodRule.PREVIOUS_DAYS:
            integer(self.days, "summary days", 1)
        elif self.days is not None:
            raise ValueError("Days are only valid with previous_days")

    def resolve(self, run_date: date, timezone: str) -> SummaryPeriod:
        local_date(run_date)
        school_zone(timezone)
        if self.rule is PeriodRule.MANUAL:
            raise ValueError("A manual period must be supplied explicitly")
        try:
            end = run_date - timedelta(days=1)
            if self.rule is PeriodRule.PREVIOUS_DAYS:
                return SummaryPeriod(run_date - timedelta(days=self.days), end, timezone)
            end = run_date.replace(day=1) - timedelta(days=1)
            return SummaryPeriod(end.replace(day=1), end, timezone)
        except OverflowError as error:
            raise ValueError("Summary period exceeds the supported date range") from error


@dataclass(frozen=True)
class IdempotencyIdentity:
    school_id: SchoolId
    action: str
    logical_key: str

    def __post_init__(self) -> None:
        identifier(self.school_id, SchoolId)
        nonempty(self.action, "action")
        nonempty(self.logical_key, "logical_key")

    @property
    def key(self) -> str:
        return canonical_content_digest({"format": "spesped.command.v1", "school": str(self.school_id),
                                         "action": self.action, "logical_key": self.logical_key})


@dataclass(frozen=True)
class DraftRequest:
    schedule_id: ScheduleId
    schedule_revision: RevisionId
    scope: SubjectScope
    period: SummaryPeriod
    requested_for: datetime

    def __post_init__(self) -> None:
        identifier(self.schedule_id, ScheduleId)
        identifier(self.schedule_revision, RevisionId)
        if not isinstance(self.scope, SubjectScope) or not isinstance(self.period, SummaryPeriod):
            raise ValueError("Draft subject and summary period are required")
        object.__setattr__(self, "requested_for", instant(self.requested_for))

    @property
    def idempotency(self) -> IdempotencyIdentity:
        logical_key = canonical_content_digest({
            "schedule": str(self.schedule_id), "revision": str(self.schedule_revision),
            "learner": str(self.scope.learner_id),
            "case": str(self.scope.case_id) if self.scope.case_id else None,
            "start": self.period.start.isoformat(), "end": self.period.end.isoformat(),
            "timezone": self.period.timezone,
        })
        return IdempotencyIdentity(self.scope.school_id, "request_email_draft", logical_key)

    @property
    def authorizes_dispatch(self) -> bool:
        return False


@dataclass(frozen=True)
class DraftRecurrence:
    schedule_id: ScheduleId
    revision_id: RevisionId
    scope: SubjectScope
    cadence: DraftCadence
    anchor: date
    timezone: str
    period_selection: DraftPeriodSelection
    interval: int = 1
    month_end_policy: MonthEndPolicy = MonthEndPolicy.CLAMP
    end_date: date | None = None
    active: bool = False

    def __post_init__(self) -> None:
        identifier(self.schedule_id, ScheduleId)
        identifier(self.revision_id, RevisionId)
        if not isinstance(self.scope, SubjectScope):
            raise ValueError("Draft subject scope is required")
        if type(self.cadence) is not DraftCadence or type(self.month_end_policy) is not MonthEndPolicy:
            raise ValueError("Typed cadence and month-end policy are required")
        local_date(self.anchor)
        school_zone(self.timezone)
        integer(self.interval, "recurrence interval", 1)
        if type(self.active) is not bool:
            raise ValueError("Activation must be explicit")
        if not isinstance(self.period_selection, DraftPeriodSelection):
            raise ValueError("A summary period selection rule is required")
        if (self.cadence is DraftCadence.MANUAL) != (self.period_selection.rule is PeriodRule.MANUAL):
            raise ValueError("Manual cadence and manual period selection must be used together")
        if self.end_date is not None:
            local_date(self.end_date)
            if self.end_date < self.anchor:
                raise ValueError("End date cannot precede anchor")

    def activate(self) -> "DraftRecurrence":
        return replace(self, active=True)

    def pause(self) -> "DraftRecurrence":
        return replace(self, active=False)

    def _run_date(self, index: int) -> date | None:
        try:
            if self.cadence is DraftCadence.DAYS:
                return self.anchor + timedelta(days=index * self.interval)
            month_index = self.anchor.year * 12 + self.anchor.month - 1 + index * self.interval
            year, month = divmod(month_index, 12)
            month += 1
            if year > 9999:
                return None
            last_day = monthrange(year, month)[1]
            if self.anchor.day > last_day and self.month_end_policy is MonthEndPolicy.SKIP:
                return None
            return date(year, month, min(self.anchor.day, last_day))
        except (OverflowError, ValueError):
            return None

    def next_run(self, after: datetime) -> datetime | None:
        after = instant(after)
        if not self.active or self.cadence is DraftCadence.MANUAL:
            return None
        zone = school_zone(self.timezone)
        after_date = after.astimezone(zone).date()
        if self.end_date is not None and after_date > self.end_date:
            return None
        if self.cadence is DraftCadence.DAYS:
            index = max(0, (after_date - self.anchor).days // self.interval)
        else:
            months = (after_date.year - self.anchor.year) * 12 + after_date.month - self.anchor.month
            index = max(0, months // self.interval)
        while True:
            # Guard the finite datetime range even when every candidate is skipped.
            if self.cadence is DraftCadence.MONTHS and (
                    self.anchor.year * 12 + self.anchor.month - 1 + index * self.interval >= 10000 * 12):
                return None
            candidate = self._run_date(index)
            if candidate is None and self.cadence is DraftCadence.DAYS:
                return None
            if candidate is not None:
                if self.end_date is not None and candidate > self.end_date:
                    return None
                run = instant(datetime.combine(candidate, time.min, zone))
                if run > after:
                    return run
            index += 1

    def next_request(self, after: datetime) -> DraftRequest | None:
        run = self.next_run(after)
        if run is None:
            return None
        period = self.period_selection.resolve(run.astimezone(school_zone(self.timezone)).date(), self.timezone)
        return DraftRequest(self.schedule_id, self.revision_id, self.scope, period, run)

    def request_manual(self, period: SummaryPeriod, requested_at: datetime) -> DraftRequest:
        if not self.active or self.cadence is not DraftCadence.MANUAL:
            raise ValueError("Manual drafts require an explicitly active manual schedule")
        if not isinstance(period, SummaryPeriod) or period.timezone != self.timezone:
            raise ValueError("Manual summary period must use the school timezone")
        requested_at = instant(requested_at)
        local = requested_at.astimezone(school_zone(self.timezone)).date()
        if local < self.anchor or (self.end_date is not None and local > self.end_date):
            raise ValueError("Manual request is outside the schedule's active dates")
        return DraftRequest(self.schedule_id, self.revision_id, self.scope, period, requested_at)
