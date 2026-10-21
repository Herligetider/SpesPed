"""Cross-context adverse examples, using only synthetic identities and stdlib."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest
from uuid import UUID
from zoneinfo import ZoneInfo

from spesped.domain import (
    ApprovalBinding, ApplicabilityResult, ApplicabilityStatus, AssessmentScore, AttachmentDigest,
    AttachmentId, CaseId, Certainty, CountingBasis, DecisionId, DecisionProvisionId,
    DecisionProvisionReference, DisclosureChannel, DraftCadence, DraftPeriodSelection,
    DraftRecurrence, DurationMinutes, EffectivePeriod, EntitlementQuantity, EvidenceAttribution,
    EvidenceCutoff, EvidenceItemId, EvidenceRecord, GoalEvidenceResult, GoalEvidenceStatus,
    IdempotencyIdentity, InstrumentId, LearnerId, ManualDraftRequest, MonthEndPolicy, OccurrenceTime, PeriodRule,
    PersonId, QuantityUnit, RecipientScope, RecordedTime, RevisionId, ScheduleId, SchoolId,
    ScoreScale, SourceItemId, SourceReference, SourceType, SubjectScope, SummaryPeriod,
    SupportCategory, UserId, calendar_date_boundary, canonical_content_digest, evaluate_goal_evidence,
)

UTC = timezone.utc
OSLO = ZoneInfo("Europe/Oslo")


def at(day: int, hour: int = 12, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


class DomainCase(unittest.TestCase):
    def setUp(self):
        self.scope = SubjectScope(SchoolId.new(), LearnerId.new())
        self.source = SourceReference(self.scope, SourceItemId.new(), 1, "a" * 64, 2, (0, 10))
        self.person = PersonId.new()
        self.attribution = EvidenceAttribution(self.person, SourceType.DIRECT_OBSERVATION,
                                               Certainty.CONFIRMED, self.person)
        self.goal = RevisionId.new()
        self.period = SummaryPeriod(date(2026, 10, 1), date(2026, 10, 20), "Europe/Oslo")

    def evidence(self, *, occurred=None, recorded=None, **kwargs):
        return EvidenceRecord(EvidenceItemId.new(), kwargs.pop("source", self.source),
                              OccurrenceTime(occurred or at(10)), RecordedTime(recorded or at(11)),
                              kwargs.pop("attribution", self.attribution), kwargs.pop("goal_revision", self.goal))

    def recurrence(self, **kwargs):
        values = dict(schedule_id=ScheduleId.new(), revision_id=RevisionId.new(), scope=self.scope,
                      cadence=DraftCadence.MONTHS, anchor=date(2026, 1, 31), timezone="Europe/Oslo",
                      period_selection=DraftPeriodSelection(PeriodRule.PREVIOUS_CALENDAR_MONTH))
        return DraftRecurrence(**(values | kwargs))

    def test_identifiers_are_opaque_typed_and_immutable(self):
        school = SchoolId.new()
        self.assertEqual(SchoolId.parse(str(school)), school)
        self.assertNotEqual(LearnerId(school.value), school)
        with self.assertRaises(ValueError):
            SubjectScope(school, school)
        for value in (True, "not-a-uuid", UUID(int=0)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SchoolId(value)
        with self.assertRaises(FrozenInstanceError):
            school.extra = "mutable"

    def test_same_day_local_period_is_half_open(self):
        period = SummaryPeriod(date(2026, 10, 20), date(2026, 10, 20), "Europe/Oslo").to_utc()
        self.assertEqual(period.start, datetime(2026, 10, 19, 22, tzinfo=UTC))
        self.assertEqual(period.end, datetime(2026, 10, 20, 22, tzinfo=UTC))
        self.assertTrue(period.contains(period.start))
        self.assertFalse(period.contains(period.end))

    def test_oslo_spring_day_has_23_hours(self):
        period = SummaryPeriod(date(2026, 3, 29), date(2026, 3, 29), "Europe/Oslo").to_utc()
        self.assertEqual(period.end - period.start, timedelta(hours=23))
        self.assertEqual(period.start, datetime(2026, 3, 28, 23, tzinfo=UTC))

    def test_oslo_fall_day_has_25_hours_and_both_folds(self):
        period = SummaryPeriod(date(2026, 10, 25), date(2026, 10, 25), "Europe/Oslo").to_utc()
        self.assertEqual(period.end - period.start, timedelta(hours=25))
        for fold in (0, 1):
            self.assertTrue(period.contains(datetime(2026, 10, 25, 2, 30, tzinfo=OSLO, fold=fold)))

    def test_santiago_midnight_gap_resolves_to_first_real_instant(self):
        zone = ZoneInfo("America/Santiago")
        previous = SummaryPeriod(date(2026, 9, 5), date(2026, 9, 5), zone.key).to_utc()
        period = SummaryPeriod(date(2026, 9, 6), date(2026, 9, 6), zone.key).to_utc()
        following = SummaryPeriod(date(2026, 9, 7), date(2026, 9, 7), zone.key).to_utc()
        self.assertEqual(period.start, datetime(2026, 9, 6, 4, tzinfo=UTC))
        self.assertEqual(period.start.astimezone(zone).hour, 1)
        self.assertEqual(period.end, datetime(2026, 9, 7, 3, tzinfo=UTC))
        self.assertEqual(period.end - period.start, timedelta(hours=23))
        self.assertEqual(previous.end, period.start)
        self.assertEqual(period.end, following.start)
        self.assertTrue(period.contains(period.start))
        self.assertFalse(period.contains(period.end))
        for constructor in (OccurrenceTime, RecordedTime, EffectivePeriod):
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor(datetime(2026, 9, 6, 0, 30, tzinfo=zone))

    def test_midnight_overlap_chooses_earliest_instant(self):
        zone = ZoneInfo("America/Havana")
        day = date(2026, 11, 1)
        first = datetime(2026, 11, 1, tzinfo=zone, fold=0)
        second = datetime(2026, 11, 1, tzinfo=zone, fold=1)
        self.assertNotEqual(first.utcoffset(), second.utcoffset())
        boundary = calendar_date_boundary(day, zone.key)
        self.assertEqual(boundary, first.astimezone(UTC))
        period = SummaryPeriod(day, day, zone.key).to_utc()
        self.assertTrue(period.contains(second))
        self.assertEqual(period.end - period.start, timedelta(hours=25))

    def test_entirely_skipped_date_is_not_an_accepted_empty_period(self):
        zone = "Pacific/Apia"
        with self.assertRaises(ValueError):
            SummaryPeriod(date(2011, 12, 30), date(2011, 12, 30), zone)
        combined = SummaryPeriod(date(2011, 12, 29), date(2011, 12, 31), zone).to_utc()
        self.assertEqual(combined.end - combined.start, timedelta(hours=48))
        recurrence = self.recurrence(cadence=DraftCadence.DAYS, anchor=date(2011, 12, 29), timezone=zone,
                                     period_selection=DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, 7)).activate()
        first = recurrence.next_run(datetime(2011, 12, 28, tzinfo=UTC))
        second = recurrence.next_run(first)
        self.assertEqual(second.astimezone(ZoneInfo(zone)).date(), date(2011, 12, 31))

    def test_time_validation_and_open_ended_period(self):
        naive = datetime(2026, 1, 1)
        for constructor in (OccurrenceTime, RecordedTime, EffectivePeriod):
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor(naive)
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor(datetime(2026, 3, 29, 2, 30, tzinfo=OSLO))
        with self.assertRaises(ValueError):
            EffectivePeriod(at(10), at(10))
        with self.assertRaises(ValueError):
            EffectivePeriod(at(11), at(10))
        self.assertTrue(EffectivePeriod(at(10)).contains(at(20)))
        self.assertEqual(OccurrenceTime(datetime(2026, 10, 20, 12, tzinfo=OSLO)).value, at(20, 10))
        # Direct datetime comparison in one zone mishandles folds; normalization prevents it.
        first = datetime(2026, 10, 25, 2, 30, tzinfo=OSLO, fold=0)
        second = datetime(2026, 10, 25, 2, 30, tzinfo=OSLO, fold=1)
        self.assertEqual(EffectivePeriod(first, second).end - EffectivePeriod(first, second).start,
                         timedelta(hours=1))

    def test_bad_summary_dates_and_timezone_rejected(self):
        for args in ((date(2026, 2, 2), date(2026, 2, 1), "Europe/Oslo"),
                     (date(2026, 2, 1), date(2026, 2, 1), "Moon/School"),
                     (at(1), date(2026, 10, 2), "Europe/Oslo"),
                     (date.max, date.max, "Europe/Oslo")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                SummaryPeriod(*args)

    def test_known_evidence_uses_occurrence_and_cutoff(self):
        cutoff = EvidenceCutoff(self.scope, at(21), (self.source,))
        self.assertTrue(cutoff.includes(self.evidence(recorded=at(20)), self.period))
        late = self.evidence(recorded=at(22))
        self.assertFalse(cutoff.includes(late, self.period))
        self.assertTrue(cutoff.is_late_entry(late, self.period))
        outside = self.evidence(occurred=at(21), recorded=at(21))
        self.assertFalse(cutoff.includes(outside, self.period))
        self.assertFalse(cutoff.is_late_entry(outside, self.period))

    def test_source_revisions_and_scope_are_frozen(self):
        cutoff = EvidenceCutoff(self.scope, at(21), (self.source,))
        corrected = replace(self.source, revision=2, digest="b" * 64)
        self.assertFalse(cutoff.includes(self.evidence(source=corrected), self.period))
        page = replace(self.source, page=3, span=None)
        self.assertTrue(cutoff.includes(self.evidence(source=page), self.period))
        with self.assertRaises(ValueError):
            EvidenceCutoff(self.scope, at(21), (self.source, corrected))
        foreign = replace(self.source, scope=replace(self.scope, school_id=SchoolId.new()))
        with self.assertRaises(ValueError):
            EvidenceCutoff(self.scope, at(21), (foreign,))
        self.assertFalse(cutoff.includes(self.evidence(source=foreign), self.period))

    def test_source_locators_and_attribution_are_validated(self):
        for changes in (dict(revision=True), dict(revision=0), dict(page=True), dict(span=(2, 2)),
                        dict(span=(True, 2)), dict(digest="unknown"), dict(span=[0, 1])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.source, **changes)
        with self.assertRaises(ValueError):
            replace(self.attribution, observer=None)
        with self.assertRaises(ValueError):
            self.evidence(occurred=at(12), recorded=at(11))
        with self.assertRaises(ValueError):
            replace(self.attribution, certainty="confirmed")

    def test_goal_evidence_gap_is_not_progress(self):
        cutoff = EvidenceCutoff(self.scope, at(21), (self.source,))
        relevant = self.evidence()
        result = evaluate_goal_evidence(self.goal, (relevant,), cutoff, self.period)
        self.assertEqual(result.status, GoalEvidenceStatus.SUPPORTED)
        self.assertEqual(result.evidence_ids, (relevant.id,))
        for records in ((), (replace(relevant, goal_revision=RevisionId.new()),),
                        (replace(relevant, recorded=RecordedTime(at(22))),),
                        (replace(relevant, attribution=replace(self.attribution, certainty=Certainty.DISPUTED)),)):
            with self.subTest(records=records):
                self.assertEqual(evaluate_goal_evidence(self.goal, records, cutoff, self.period).status,
                                 GoalEvidenceStatus.INSUFFICIENT)
        with self.assertRaises(ValueError):
            GoalEvidenceResult(GoalEvidenceStatus.SUPPORTED, (), "no evidence")
        with self.assertRaises(ValueError):
            evaluate_goal_evidence(self.goal, (relevant, relevant), cutoff, self.period)

    def test_duration_rejects_missing_boolean_fractional_negative(self):
        self.assertEqual(DurationMinutes(0).value, 0)
        self.assertEqual(DurationMinutes(45).value, 45)
        for value in (None, True, -1, 1.5, "60"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DurationMinutes(value)

    def test_entitlements_preserve_category_basis_and_reference(self):
        quantity = EntitlementQuantity(Decimal("1.5"), QuantityUnit.HOURS,
                                       EffectivePeriod(at(1), at(20)), SupportCategory.PERSONAL_ASSISTANCE,
                                       "decision-1/clause-2", CountingBasis.LEARNER_TIME,
                                       DecisionProvisionReference(self.scope, DecisionId.new(), RevisionId.new(),
                                                                  DecisionProvisionId.new()))
        self.assertEqual(quantity.total_minutes(), Decimal("90"))
        self.assertEqual(quantity.add(replace(quantity, amount=Decimal("30"), unit=QuantityUnit.MINUTES)).amount,
                         Decimal("120"))
        for changes in (dict(counting_basis=CountingBasis.STAFF_TIME),
                        dict(category=SupportCategory.INDIVIDUALLY_ADAPTED_EDUCATION),
                        dict(decision_clause="clause-3"), dict(reference_period=EffectivePeriod(at(2), at(20)))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                quantity.add(replace(quantity, **changes))
        for changes in (dict(amount=True), dict(amount=Decimal("NaN")), dict(amount=Decimal("-1")),
                        dict(unit="lesson"), dict(category="support"), dict(counting_basis="staff")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(quantity, **changes)

    def test_entitlement_addition_rejects_same_label_from_other_subject_or_decision(self):
        reference = DecisionProvisionReference(self.scope, DecisionId.new(), RevisionId.new(), DecisionProvisionId.new())
        quantity = EntitlementQuantity(Decimal(60), QuantityUnit.HOURS, EffectivePeriod(at(1), at(20)),
                                       SupportCategory.PERSONAL_ASSISTANCE, "Clause 1",
                                       CountingBasis.LEARNER_TIME, reference)
        other = replace(quantity, amount=Decimal(30))
        total = quantity.add(other)
        self.assertEqual(total.amount, Decimal(5400))
        self.assertEqual(total.unit, QuantityUnit.MINUTES)
        self.assertEqual(total.decision_provision, reference)
        for changes in (
            dict(scope=replace(self.scope, school_id=SchoolId.new())),
            dict(scope=replace(self.scope, learner_id=LearnerId.new())),
            dict(scope=replace(self.scope, case_id=CaseId.new())),
            dict(decision_id=DecisionId.new()), dict(decision_revision=RevisionId.new()),
            dict(provision_id=DecisionProvisionId.new()),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                quantity.add(replace(other, decision_provision=replace(reference, **changes)))
        for changes in (dict(scope=None), dict(decision_id=RevisionId.new()),
                        dict(decision_revision=1), dict(provision_id=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(reference, **changes)
        with self.assertRaises(ValueError):
            replace(quantity, decision_provision=None)

    def test_scores_are_instrument_scale_specific(self):
        score = AssessmentScore(InstrumentId.new(), 1, ScoreScale("raw", Decimal(0), Decimal(20)), Decimal(10))
        self.assertEqual(replace(score, raw_value=Decimal(12)).difference_from(score), Decimal(2))
        for other in (replace(score, instrument_version=2), replace(score, instrument_id=InstrumentId.new()),
                      replace(score, scale=ScoreScale("percentile", Decimal(0), Decimal(100))),
                      replace(score, scale=ScoreScale("raw", Decimal(0), Decimal(30)))):
            with self.subTest(other=other), self.assertRaises(ValueError):
                score.difference_from(other)
        for changes in (dict(raw_value=Decimal(21)), dict(raw_value=True), dict(instrument_version=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(score, **changes)

    def test_canonical_content_and_exact_approval(self):
        content = {"subject": "Uke", "body": "Øving", "metadata": {"b": 2, "a": 1}}
        reordered = {"metadata": {"a": 1, "b": 2}, "body": "Øving", "subject": "Uke"}
        self.assertEqual(canonical_content_digest(content), canonical_content_digest(reordered))
        first = AttachmentDigest(AttachmentId.new(), "b" * 64)
        second = AttachmentDigest(AttachmentId.new(), "c" * 64)
        revision = RevisionId.new()
        binding = ApprovalBinding.create(scope=self.scope, revision_id=revision, content=content,
                                          attachments=(first, second), reviewer_id=UserId.new(),
                                          authority="document_review", approved_at=at(21))
        args = dict(scope=self.scope, revision_id=revision, content=reordered, attachments=(second, first))
        self.assertTrue(binding.matches(**args))
        self.assertEqual(binding.package_digest, replace(binding, attachments=(second, first)).package_digest)
        for changes in (dict(content=content | {"body": "changed"}), dict(revision_id=RevisionId.new()),
                        dict(attachments=(first,)), dict(attachments=(replace(first, digest="d" * 64), second)),
                        dict(scope=replace(self.scope, learner_id=LearnerId.new()))):
            with self.subTest(changes=changes):
                self.assertFalse(binding.matches(**(args | changes)))
        with self.assertRaises(ValueError):
            replace(binding, attachments=(first, first))

    def test_non_json_nonfinite_and_ambiguous_keys_rejected(self):
        for content in ({"score": float("nan")}, {1: "one", "1": "one"}, {"x": Decimal(1)}, {"x": object()}):
            with self.subTest(content=content), self.assertRaises(ValueError):
                canonical_content_digest(content)

    def test_disclosure_binds_recipient_purpose_channel_relationship_and_categories(self):
        recipient = RecipientScope(self.scope, PersonId.new(), self.source, "parent_update", ("learning",))
        revision = RevisionId.new()
        binding = ApprovalBinding.create(scope=self.scope, revision_id=revision, content={"body": "reviewed"},
                                          attachments=(), reviewer_id=UserId.new(), authority="disclose",
                                          approved_at=at(21), recipient_scope=recipient, channel=DisclosureChannel.PORTAL)
        args = dict(scope=self.scope, revision_id=revision, content={"body": "reviewed"}, attachments=(),
                    recipient_scope=recipient, channel=DisclosureChannel.PORTAL)
        self.assertTrue(binding.matches(**args))
        for changes in (dict(person_id=PersonId.new()), dict(purpose="different"),
                        dict(relationship_evidence=replace(self.source, revision=2)),
                        dict(information_categories=("learning", "attendance")), dict(restrictions=("restricted",))):
            changed = replace(recipient, **changes)
            with self.subTest(changes=changes):
                self.assertFalse(binding.matches(**(args | dict(recipient_scope=changed))))
                self.assertNotEqual(binding.package_digest, replace(binding, recipient_scope=changed).package_digest)
        self.assertFalse(binding.matches(**(args | dict(channel=DisclosureChannel.EMAIL))))
        with self.assertRaises(ValueError):
            replace(binding, channel=None)
        with self.assertRaises(ValueError):
            replace(recipient, subject=replace(self.scope, learner_id=LearnerId.new()))

    def test_applicability_missing_inputs_cannot_succeed(self):
        unresolved = ApplicabilityResult(ApplicabilityStatus.UNRESOLVED, ("Approval unknown",), (("approval", None),))
        self.assertEqual(unresolved.status, ApplicabilityStatus.UNRESOLVED)
        for status in (ApplicabilityStatus.APPLICABLE, ApplicabilityStatus.NOT_APPLICABLE):
            with self.subTest(status=status), self.assertRaises(ValueError):
                replace(unresolved, status=status)
        self.assertEqual(ApplicabilityResult(ApplicabilityStatus.NOT_APPLICABLE, ("Wrong school type",),
                                              (("school_type", "public"),)).status,
                         ApplicabilityStatus.NOT_APPLICABLE)

    def test_recurrence_needs_explicit_activation_and_pause(self):
        recurrence = self.recurrence()
        self.assertIsNone(recurrence.next_request(at(1, month=1)))
        activated = recurrence.activate()
        request = activated.next_request(at(1, month=1))
        self.assertEqual(request.requested_for, datetime(2026, 1, 30, 23, tzinfo=UTC))
        self.assertFalse(request.authorizes_dispatch)
        self.assertIsNone(activated.pause().next_request(at(1, month=1)))
        self.assertFalse(recurrence.active)

    def test_month_end_clamps_without_anchor_drift(self):
        recurrence = self.recurrence().activate()
        february = recurrence.next_request(datetime(2026, 1, 31, tzinfo=UTC))
        self.assertEqual(february.requested_for.astimezone(OSLO).date(), date(2026, 2, 28))
        march = recurrence.next_request(february.requested_for)
        self.assertEqual(march.requested_for.astimezone(OSLO).date(), date(2026, 3, 31))
        self.assertEqual(march.period.start, date(2026, 2, 1))
        self.assertEqual(march.period.end, date(2026, 2, 28))

    def test_month_end_skip_and_end_condition(self):
        recurrence = self.recurrence(month_end_policy=MonthEndPolicy.SKIP).activate()
        run = recurrence.next_run(datetime(2026, 1, 31, tzinfo=UTC))
        self.assertEqual(run.astimezone(OSLO).date(), date(2026, 3, 31))
        self.assertIsNone(replace(recurrence, end_date=date(2026, 2, 28)).next_run(datetime(2026, 1, 31, tzinfo=UTC)))
        self.assertIsNone(replace(recurrence, anchor=date(9999, 12, 31)).next_run(datetime(9999, 12, 31, tzinfo=UTC)))

    def test_leap_year_month_end_and_interval(self):
        recurrence = self.recurrence(anchor=date(2028, 1, 31)).activate()
        self.assertEqual(recurrence.next_run(datetime(2028, 2, 1, tzinfo=UTC)).astimezone(OSLO).date(), date(2028, 2, 29))
        self.assertEqual(replace(recurrence, interval=2).next_run(datetime(2028, 2, 1, tzinfo=UTC)).astimezone(OSLO).date(),
                         date(2028, 3, 31))

    def test_daily_runs_follow_local_dates_across_dst(self):
        for anchor, expected_hours in ((date(2026, 3, 29), 23), (date(2026, 10, 25), 25)):
            recurrence = self.recurrence(cadence=DraftCadence.DAYS, anchor=anchor,
                                         period_selection=DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, 7)).activate()
            before = datetime.combine(anchor, datetime.min.time(), OSLO) - timedelta(hours=1)
            first = recurrence.next_request(before)
            second = recurrence.next_request(first.requested_for)
            self.assertEqual(second.requested_for - first.requested_for, timedelta(hours=expected_hours))
            self.assertEqual((second.period.end - second.period.start).days, 6)

    def test_santiago_midnight_recurrence_has_one_run_per_date(self):
        recurrence = self.recurrence(cadence=DraftCadence.DAYS, anchor=date(2026, 9, 5), timezone="America/Santiago",
                                     period_selection=DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, 1)).activate()
        first = recurrence.next_request(datetime(2026, 9, 4, tzinfo=UTC))
        gap = recurrence.next_request(first.requested_for)
        following = recurrence.next_request(gap.requested_for)
        self.assertEqual(gap.requested_for, datetime(2026, 9, 6, 4, tzinfo=UTC))
        self.assertEqual(following.requested_for, datetime(2026, 9, 7, 3, tzinfo=UTC))
        self.assertEqual(following.period.start, date(2026, 9, 6))
        self.assertEqual(following.period.to_utc().start, gap.requested_for)
        self.assertEqual(following.period.to_utc().end, following.requested_for)
        retry = recurrence.next_request(first.requested_for + timedelta(hours=1))
        self.assertEqual(retry.idempotency.key, gap.idempotency.key)
        self.assertNotEqual(gap.idempotency.key, following.idempotency.key)
        # A completed boundary cannot be emitted again, including within its gap day.
        self.assertEqual(recurrence.next_run(gap.requested_for + timedelta(minutes=1)), following.requested_for)
        self.assertFalse(gap.authorizes_dispatch)

    def test_period_selection_is_independent_of_cadence(self):
        selection = DraftPeriodSelection(PeriodRule.PREVIOUS_CALENDAR_MONTH)
        period = selection.resolve(date(2026, 10, 20), "Europe/Oslo")
        self.assertEqual((period.start, period.end), (date(2026, 9, 1), date(2026, 9, 30)))
        recurrence = self.recurrence(cadence=DraftCadence.DAYS, anchor=date(2026, 10, 20), interval=14,
                                     period_selection=DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, 3)).activate()
        request = recurrence.next_request(at(19))
        self.assertEqual((request.period.start, request.period.end), (date(2026, 10, 17), date(2026, 10, 19)))

    def test_manual_schedule_chosen_period_and_deduplication(self):
        recurrence = self.recurrence(cadence=DraftCadence.MANUAL, anchor=date(2026, 10, 1),
                                     period_selection=DraftPeriodSelection(PeriodRule.MANUAL))
        with self.assertRaises(ValueError):
            recurrence.request_manual(self.period, at(21))
        activated = recurrence.activate()
        self.assertIsNone(activated.next_request(at(1)))
        first = activated.request_manual(self.period, at(21))
        retry = activated.request_manual(self.period, at(22))
        self.assertEqual(first.idempotency.key, retry.idempotency.key)
        changed = replace(activated, revision_id=RevisionId.new()).request_manual(self.period, at(22))
        self.assertNotEqual(first.idempotency.key, changed.idempotency.key)
        changed_period = activated.request_manual(replace(self.period, end=date(2026, 10, 19)), at(22))
        self.assertNotEqual(first.idempotency.key, changed_period.idempotency.key)
        changed_school = replace(first, scope=replace(self.scope, school_id=SchoolId.new()))
        self.assertNotEqual(first.idempotency.key, changed_school.idempotency.key)
        with self.assertRaises(ValueError):
            activated.request_manual(replace(self.period, timezone="UTC"), at(22))

    def test_one_off_draft_needs_no_schedule_and_preserves_command_identity(self):
        first = ManualDraftRequest(self.scope, self.period, at(21), "manual-command-1")
        retry = replace(first, requested_at=at(22))
        self.assertEqual(first.idempotency.key, retry.idempotency.key)
        self.assertEqual(first.request_digest, retry.request_digest)
        self.assertFalse(hasattr(first, "schedule_id"))
        self.assertFalse(hasattr(first, "schedule_revision"))
        self.assertFalse(first.authorizes_dispatch)
        # A later deliberate order for the same dates is a separate command.
        deliberate = replace(retry, logical_request_key="manual-command-2")
        self.assertNotEqual(first.idempotency.key, deliberate.idempotency.key)
        # Reusing one command key with a changed payload is detectable as a conflict.
        changed_period = replace(first, period=replace(self.period, end=date(2026, 10, 19)))
        self.assertEqual(first.idempotency.key, changed_period.idempotency.key)
        self.assertNotEqual(first.request_digest, changed_period.request_digest)
        scheduled = self.recurrence().activate().next_request(datetime(2026, 1, 1, tzinfo=UTC))
        self.assertNotEqual(first.idempotency.action, scheduled.idempotency.action)
        for scope in (replace(self.scope, school_id=SchoolId.new()),
                      replace(self.scope, learner_id=LearnerId.new()),
                      replace(self.scope, case_id=CaseId.new())):
            self.assertNotEqual(first.idempotency.key, replace(first, scope=scope).idempotency.key)

    def test_one_off_draft_rejects_invalid_identity_scope_period_and_instant(self):
        request = ManualDraftRequest(self.scope, self.period, at(21), "manual-command")
        for changes in (dict(logical_request_key=" "), dict(logical_request_key=True),
                        dict(scope=self.scope.school_id), dict(period=None),
                        dict(requested_at=datetime(2026, 10, 21)),
                        dict(requested_at=datetime(2026, 9, 6, 0, 30, tzinfo=ZoneInfo("America/Santiago")))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(request, **changes)

    def test_schedule_and_idempotency_inputs_validated(self):
        for changes in (dict(interval=True), dict(interval=0), dict(active=1), dict(cadence="months"),
                        dict(anchor=at(1)), dict(end_date=date(2025, 1, 1)), dict(month_end_policy="clamp")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.recurrence(**changes)
        with self.assertRaises(ValueError):
            DraftPeriodSelection(PeriodRule.PREVIOUS_DAYS, True)
        with self.assertRaises(ValueError):
            DraftPeriodSelection(PeriodRule.PREVIOUS_CALENDAR_MONTH, 30)
        with self.assertRaises(ValueError):
            IdempotencyIdentity(self.scope.school_id, "", "logical")


if __name__ == "__main__":
    unittest.main()
