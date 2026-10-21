"""Deterministic applicability, timing and comparable workload calculations."""
import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from .schemas import DeadlineRule, TimingInputs
from spesped.domain.primitives import SummaryPeriod


def evaluate_applicability(conditions, inputs):
    missing, reasons, mismatches = [], [], []
    for condition in conditions:
        key, expected = condition['fact'], condition['equals']
        actual = inputs.get(key)
        if actual is None:
            missing.append(key)
            reasons.append(f'Missing applicability input: {key}')
        elif type(actual) is not type(expected) or actual != expected:
            mismatches.append(key)
    # Incomplete school/case inputs always require an explicit resolution, even
    # when another condition currently fails. They never become a green status.
    if missing: return 'unresolved', missing, reasons + [f'Condition does not match: {k}' for k in mismatches]
    if mismatches:
        return 'not_applicable', [], [f'Condition does not match: {k}' for k in mismatches]
    return 'applicable', [], ['All reviewed conditions match']


def resolve_deadline(rule: DeadlineRule, timing: TimingInputs, occurred_at: datetime, timezone_name: str):
    """Returns a local due date and exclusive due instant, or explicit gaps.

    Without-undue-delay remains qualitative; its internal plan is never declared
    the legal deadline. Immediate uses the occurrence instant, not end of day.
    Calendar periods exclude the start date and include the calculated last date.
    Month ends clamp to their final real date; the reviewer chooses this rule.
    """
    if rule.kind == 'unresolved': return None, None, ['Legal timing has not been reviewed']
    if rule.kind == 'without_undue_delay': return None, None, ['Qualitative legal timing requires continuing human assessment']
    if rule.kind == 'immediate': return occurred_at.astimezone(ZoneInfo(timezone_name)).date(), occurred_at, []
    if rule.kind == 'fixed_date':
        due = rule.fixed_date or timing.deadline_date
        if due is None: return None, None, ['Missing deadline_date']
    else:
        start = occurred_at.astimezone(ZoneInfo(timezone_name)).date() if rule.start == 'event_date' else timing.start_date
        if start is None: return None, None, ['Missing start_date']
        if rule.calendar == 'school_days':
            if not timing.calendar_reference or timing.calendar_valid_from is None or timing.calendar_valid_until is None:
                return None, None, ['Missing reviewed local school calendar']
            if not timing.calendar_valid_from <= start <= timing.calendar_valid_until:
                return None, None, ['Start date lies outside supplied local calendar coverage']
            dates = sorted(d for d in timing.school_dates if d > start)
            if len(dates) < rule.count: return None, None, ['Local school calendar does not cover the complete period']
            due = dates[rule.count - 1]
        elif rule.unit in ('days', 'weeks'):
            due = start + timedelta(days=rule.count * (7 if rule.unit == 'weeks' else 1))
        else:
            month_index = start.year * 12 + start.month - 1 + rule.count
            year, month = divmod(month_index, 12)
            due = date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))
    # SummaryPeriod rejects wholly skipped due dates instead of inventing a time.
    return due, SummaryPeriod(due, due, timezone_name).to_utc().end, []

TIME_FIELDS = ('primary_minutes','review_minutes','correction_minutes','duplicate_entry_minutes','followup_minutes')

def compare_measurements(study, measurements):
    pairs = {}
    for measurement in measurements:
        pairs.setdefault((measurement.participant_id, measurement.match_key), {})[measurement.mode] = measurement
    comparable, issues = [], {}
    def issue(reason): issues[reason] = issues.get(reason, 0) + 1
    for key, modes in pairs.items():
        if set(modes) != {'manual','assisted'}:
            issue('missing_matched_baseline_or_assisted'); continue
        baseline, assisted = modes['manual'], modes['assisted']
        if baseline.scenario != assisted.scenario or baseline.complexity != assisted.complexity:
            issue('noncomparable_task'); continue
        if any(getattr(m, f) is None for m in (baseline, assisted) for f in TIME_FIELDS) or baseline.quality is None or assisted.quality is None:
            issue('incomplete_time_or_quality'); continue
        if study.task_type == 'assistant_brief' and any(m.comprehension is None for m in (baseline, assisted)):
            issue('incomplete_comprehension'); continue
        manual_total = sum(getattr(baseline, f) for f in TIME_FIELDS)
        assisted_total = sum(getattr(assisted, f) for f in TIME_FIELDS)
        comparable.append((key[0], manual_total, assisted_total, baseline, assisted))
    return comparable, issues
