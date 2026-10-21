"""Explicit, bounded development provisioning for the built-in synthetic fixture.

This is a local provisioning command, never a runtime role or case-access bypass.
The caller owns commit/rollback. All validation runs before any writes.
"""
from sqlalchemy import select

from spesped.audit import record_audit
from spesped.auth import Actor, school_today
from spesped.contexts.identity.models import (
    AuditRecord, AuthorityGrant, Enrollment, IdentityEvent, Learner, School,
    SchoolMembership, StaffAssignment, UserAccount,
)
from spesped.contexts.entitlements.models import SupportCase
from spesped.contexts.entitlements.schemas import CreateCase
from spesped.contexts.entitlements.service import create_case


PUPIL_ACTIONS = (
    "evidence.read", "evidence.write", "profile.read", "profile.write", "profile.confirm",
    "support_case.access", "support_case.create", "plans.read", "plans.write", "plans.approve",
    "teaching.read", "teaching.write", "teaching.approve", "teaching.brief.approve",
    "teaching.assign", "teaching.follow_up", "documents.read", "documents.write",
    "documents.review", "documents.approve", "documents.contribute", "documents.schedule",
    "ai.iep_drafting", "ai.session_planning", "ai.report_drafting", "ai.guardian_email_drafting",
)
CASE_ACTIONS = (
    "support_case.read", "support_case.write", "support_case.confirm", "support_case.submit",
    "education_decision.confirm",
)
GRANTED = "synthetic_demo_access.granted"
UPGRADED = "synthetic_demo_access.upgraded"
CASE_UPGRADED = "synthetic_demo_access.case_upgraded"


def invalid(detail):
    return ValueError(f"Demo access refused: {detail}. Use an intact built-in synthetic development fixture; no changes were made.")


def current(row, today):
    return row.state == "active" and row.valid_from <= today and (row.valid_until is None or row.valid_until >= today)


def _fixture(db):
    # Lock a durable fixture identity before checking receipts or inserting grants.
    # PostgreSQL serializes concurrent upgrades; SQLite serializes its writers.
    schools = db.scalars(select(School).order_by(School.id).with_for_update()).all()
    expected_schools = {"Syntetisk eksempelskole": "public", "Syntetisk annen skole": "montessori"}
    if len(schools) != 2 or {s.name: s.kind for s in schools} != expected_schools:
        raise invalid("the two original demo schools were not recognized")
    if any(s.state != "active" or s.timezone != "Europe/Oslo" for s in schools):
        raise invalid("a demo school is inactive or has changed timezone")
    first = next(s for s in schools if s.kind == "public")
    second = next(s for s in schools if s.kind == "montessori")
    expected_users = {
        "leader": ("Syntetisk skoleleder", "school_leader", first.id),
        "other": ("Syntetisk annen skoleleder", "school_leader", second.id),
        "teacher": ("Syntetisk lærer", "teacher", first.id),
        "assistant": ("Syntetisk assistent", "assistant", first.id),
        "technical": ("Syntetisk driftsbruker", "technical_administrator", first.id),
        "guardian": ("Syntetisk foresatt", "guardian", first.id),
    }
    users = db.scalars(select(UserAccount)).all()
    by_email = {u.email: u for u in users}
    if len(users) != len(expected_users) or set(by_email) != {f"demo.{key}@example.invalid" for key in expected_users}:
        raise invalid("the original demo accounts were not recognized")
    leader = by_email["demo.leader@example.invalid"]
    fixtures = db.scalars(select(AuditRecord).where(AuditRecord.action == "synthetic_fixture.created")).all()
    if len(fixtures) != 1:
        raise invalid("the synthetic_fixture.created provenance record is missing or ambiguous")
    fixture = fixtures[0]
    if (fixture.actor_id, fixture.school_id, fixture.target_type, fixture.target_id, fixture.outcome) != (leader.id, first.id, "school", first.id, "success"):
        raise invalid("the fixture provenance does not identify the original demo leader and school")
    for s in schools:
        owner = by_email[f"demo.{'leader' if s.id == first.id else 'other'}@example.invalid"]
        bootstrap = db.scalars(select(AuditRecord).where(
            AuditRecord.action == "school.bootstrap", AuditRecord.school_id == s.id,
            AuditRecord.actor_id == owner.id, AuditRecord.target_id == s.id,
            AuditRecord.target_type == "school", AuditRecord.outcome == "success",
            AuditRecord.occurred_at <= fixture.occurred_at,
        )).all()
        if len(bootstrap) != 1 or s.created_at > bootstrap[0].occurred_at or owner.created_at > bootstrap[0].occurred_at:
            raise invalid("a school lacks its original bootstrap provenance")
    memberships = db.scalars(select(SchoolMembership)).all()
    if len(memberships) != len(expected_users):
        raise invalid("the original demo memberships changed")
    for key, (label, role, school_id) in expected_users.items():
        user = by_email[f"demo.{key}@example.invalid"]
        matches = [m for m in memberships if m.user_id == user.id]
        if (user.state != "active" or user.display_name != label or user.created_at > fixture.occurred_at
                or len(matches) != 1 or matches[0].school_id != school_id or matches[0].role != role
                or matches[0].created_at > fixture.occurred_at
                or not current(matches[0], school_today(first))):
            raise invalid("an original demo account or membership is changed, inactive or replaced")
    learners = db.scalars(select(Learner)).all()
    expected_pupils = {"Syntetisk elev A": first.id, "Syntetisk elev B": first.id, "Syntetisk elev C": second.id}
    if len(learners) != 3 or {p.display_name: p.school_id for p in learners} != expected_pupils:
        raise invalid("the three original demo pupils were not recognized")
    enrollments = db.scalars(select(Enrollment)).all()
    if len(enrollments) != 3:
        raise invalid("the original demo enrollments changed")
    for pupil in learners:
        matches = [e for e in enrollments if e.learner_id == pupil.id and e.school_id == pupil.school_id]
        if (pupil.state != "active" or pupil.created_at > fixture.occurred_at or len(matches) != 1
                or matches[0].created_at > fixture.occurred_at or not current(matches[0], school_today(first))):
            raise invalid("a demo pupil or enrollment is inactive or replaced")
    # Original assignments are a further fixture fingerprint; never rewrite them.
    assignments = db.scalars(select(StaffAssignment)).all()
    a = next(p for p in learners if p.display_name == "Syntetisk elev A")
    expected_assignments = {
        by_email["demo.teacher@example.invalid"].id: ["learner.read", "learner.update", "document.contribute"],
        by_email["demo.assistant@example.invalid"].id: ["brief.read", "observation.create"],
    }
    if len(assignments) != 2 or {x.user_id for x in assignments} != set(expected_assignments):
        raise invalid("the original demo teaching assignments changed")
    if any(x.school_id != first.id or x.learner_id != a.id or x.actions != expected_assignments[x.user_id]
           or x.purpose != "synthetic_teaching" or x.created_at > fixture.occurred_at
           or not current(x, school_today(first)) for x in assignments):
        raise invalid("an original demo assignment is changed or inactive")
    # The baseline leader read/update grants must still be effective.
    for action in ("learner.read", "learner.update"):
        grants = db.scalars(select(AuthorityGrant).where(
            AuthorityGrant.school_id == first.id, AuthorityGrant.user_id == leader.id,
            AuthorityGrant.action == action, AuthorityGrant.learner_id.is_(None), AuthorityGrant.case_id.is_(None),
        )).all()
        if len(grants) != 1 or not current(grants[0], school_today(first)) or grants[0].created_at > fixture.occurred_at:
            raise invalid("an original leader learner grant was changed or revoked")
    return first, leader, [p for p in learners if p.school_id == first.id], fixture


def upgrade_demo_access(db, *, environment, confirm_synthetic):
    """Return school/leader/pupil/case IDs and added_grants; never commit.

    Only an intact standard demo identity fixture is accepted. Additional domain
    work is allowed. Existing educational cases are eligible only on A/B, owned
    by the original leader and audited as created by that same leader after the
    fixture. Other cases retain their existing scope. Revocations fail closed.
    """
    if environment != "development":
        raise ValueError("Demo access is available only in the development environment")
    if confirm_synthetic is not True:
        raise ValueError("Demo access requires explicit --confirm-synthetic confirmation")
    if db.new or db.dirty or db.deleted:
        raise ValueError("Demo access requires a clean transaction without pending changes")
    if db.get_bind().dialect.name == "sqlite":
        connection = db.connection()
        # SELECT FOR UPDATE has no effect on SQLite. Reserve its single writer
        # before reading provenance/grants, so concurrent first upgrades cannot
        # both pass the same absent-grant preflight. BEGIN changes no records.
        if connection.connection.driver_connection.in_transaction:
            raise ValueError("Demo access on SQLite requires a fresh transaction; commit or roll back existing work first")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    # A clean Session may still retain identities from an earlier read. Always
    # inspect persisted fixture/revocation state, not those cached attributes.
    db.expire_all()
    school, leader, pupils, fixture = _fixture(db)
    today = school_today(school)
    actor = Actor(leader.id)
    pupil_ids = {p.id for p in pupils}
    cases = []
    for case in db.scalars(select(SupportCase).where(SupportCase.school_id == school.id)):
        if case.learner_id not in pupil_ids or case.owner_id != leader.id or case.purpose != "educational_support":
            continue
        provenance = db.scalar(select(AuditRecord.id).where(
            AuditRecord.action == "support_case.created", AuditRecord.actor_id == leader.id,
            AuditRecord.school_id == school.id, AuditRecord.target_id == case.id,
            AuditRecord.target_type == SupportCase.__tablename__, AuditRecord.outcome == "success",
            AuditRecord.occurred_at >= fixture.occurred_at,
        ))
        if provenance and case.created_at >= fixture.occurred_at:
            cases.append(case)
    scopes = {(action, p.id, None) for p in pupils for action in PUPIL_ACTIONS}
    scopes.add(("evidence.intake", None, None))
    scopes.update((action, c.learner_id, c.id) for c in cases for action in CASE_ACTIONS)
    all_grants = db.scalars(select(AuthorityGrant).where(AuthorityGrant.school_id == school.id, AuthorityGrant.user_id == leader.id)).all()
    prior_records = db.scalars(select(AuditRecord).where(AuditRecord.school_id == school.id, AuditRecord.action == GRANTED)).all()
    by_id = {g.id: g for g in all_grants}
    for record in prior_records:
        grant = by_id.get(record.target_id)
        if (record.actor_id != leader.id or grant is None or (grant.action, grant.learner_id, grant.case_id) not in scopes
                or not current(grant, today)):
            raise invalid("previously provisioned scope was removed, changed or revoked; review it explicitly instead of restoring it")
    for scope in scopes:
        matches = [g for g in all_grants if (g.action, g.learner_id, g.case_id) == scope]
        if len(matches) > 1 or any(not current(g, today) for g in matches):
            raise invalid("a requested demo grant is ambiguous, expired or revoked; review the existing grant explicitly")
    upgraded = db.scalar(select(AuditRecord.id).where(AuditRecord.school_id == school.id, AuditRecord.action == UPGRADED))
    if upgraded and any(not any((g.action, g.learner_id, g.case_id) == scope for g in all_grants)
                        for scope in scopes if scope[2] is None):
        raise invalid("previously provisioned pupil scope is missing; review the removed grant explicitly")
    case_records = db.scalars(select(AuditRecord).where(AuditRecord.school_id == school.id, AuditRecord.action == CASE_UPGRADED)).all()
    upgraded_cases = {r.target_id for r in case_records}
    for record in case_records:
        case = next((c for c in cases if c.id == record.target_id), None)
        if (record.actor_id != leader.id or case is None or any(
                not any((g.action, g.learner_id, g.case_id) == (action, case.learner_id, case.id) for g in all_grants)
                for action in CASE_ACTIONS)):
            raise invalid("previously provisioned case scope was removed or changed; review it explicitly")
    for action, pupil_id, case_id in scopes:
        # A withdrawn school-wide permission must not be revived by creating a
        # narrower pupil grant for the same effective scope.
        if any(g.action == action and g.case_id == case_id and g.learner_id in (None, pupil_id)
               and not current(g, today) for g in all_grants):
            raise invalid("overlapping demo authority is expired or revoked; review it explicitly")

    # No mutation precedes the fixture, provenance and revocation checks above.
    added = 0
    def grant(action, pupil_id=None, case_id=None):
        nonlocal added
        if any((g.action, g.learner_id, g.case_id) == (action, pupil_id, case_id) for g in all_grants):
            return
        row = AuthorityGrant(school_id=school.id, user_id=leader.id, action=action,
                             learner_id=pupil_id, case_id=case_id, valid_from=today, granted_by=leader.id)
        db.add(row); db.flush()
        all_grants.append(row)
        record_audit(db, actor, school.id, GRANTED, "authority_grant", row.id)
        db.add(IdentityEvent(school_id=school.id, aggregate_id=row.id, aggregate_version=row.version, event_type=GRANTED))
        added += 1
    for action, pupil_id, case_id in sorted(scopes, key=lambda value: tuple(v or "" for v in value)):
        grant(action, pupil_id, case_id)
    for pupil in pupils:
        if not any(c.learner_id == pupil.id for c in cases):
            case = create_case(db, actor, school.id, pupil.id, CreateCase(
                request_key=f"synthetic-demo-access-v1:{pupil.id}", owner_id=leader.id,
                concern=f"Syntetisk øvingssak for {pupil.display_name}. Bare fiktive opplysninger.",
            ))
            cases.append(case)
            for action in CASE_ACTIONS:
                grant(action, pupil.id, case.id)
    for case in cases:
        if case.id not in upgraded_cases:
            record_audit(db, actor, school.id, CASE_UPGRADED, "support_case", case.id)
            db.add(IdentityEvent(school_id=school.id, aggregate_id=case.id, aggregate_version=case.version, event_type=CASE_UPGRADED))
    if not upgraded:
        record_audit(db, actor, school.id, UPGRADED, "school", school.id)
        db.add(IdentityEvent(school_id=school.id, aggregate_id=school.id, aggregate_version=school.version, event_type=UPGRADED))
    db.flush()
    return {"school_id": school.id, "leader_id": leader.id,
            "learner_ids": sorted(pupil_ids), "case_ids": sorted(c.id for c in cases), "added_grants": added}
