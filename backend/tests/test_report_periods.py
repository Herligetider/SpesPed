"""Native human reporting-period reviews on SQLite and isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select, func, inspect, text
from sqlalchemy.exc import DBAPIError

from test_governance import env as governance_env, rule_setup, profile_setup, trigger_body, post, base, login
from spesped.auth import Actor
from spesped.errors import DomainError
from spesped.contexts.governance import models as m, service as svc
from spesped.contexts.governance.projections import report_obligation_basis
from spesped.contexts.identity.models import AuthorityGrant, Learner, StaffAssignment, AuditRecord

KIND = 'annual_ito_evaluation'
START, END = date(2025, 1, 1), date(2025, 12, 31)


@pytest.fixture
def env(governance_env):
    command.upgrade(governance_env[4], 'j13_report_period')
    return governance_env


def setup(env, documents=None, conditions=None):
    c, f, ids, _, _ = env
    _, rule, h = rule_setup(env, documents=documents or [KIND], conditions=conditions)
    profile = profile_setup(env, rule, h)
    task = post(c, base(ids)+'/triggers', trigger_body(profile, learner_id=ids['learner'], period_key='opaque:2025-is-only-a-label'), h, 201)['items'][0]
    return task, rule, profile, h


def path(ids, task):
    return base(ids)+f'/obligations/{task["id"]}/report-period-reviews'


def review_body(c, ids, task, **changes):
    kind = changes.get('document_kind', KIND)
    response = c.get(path(ids, task), params={'document_kind': kind})
    assert response.status_code == 200, response.text
    context = response.json()
    return {'request_key': str(uuid4()), 'expected_version': context['version'],
        'obligation_basis_digest': context['obligation_basis_digest'], 'document_kind': kind,
        'starts_on': START.isoformat(), 'ends_on': END.isoformat(), 'rationale': 'Synthetic explicit human review', **changes}


def read(f, ids, task, start=START, end=END, actor=None, kind=KIND):
    with f() as db:
        return report_obligation_basis(db, Actor(actor or ids['leader']), ids['school'], ids['learner'], task['id'], kind, start, end)


def test_native_exact_period_manual_review_history_and_no_fulfillment(env):
    c, f, ids, _, _ = env
    task, rule, profile, h = setup(env)
    assert read(f, ids, task)['state'] == 'unresolved'
    assert 'report_period_review_missing' in read(f, ids, task)['unresolved_inputs']
    body = review_body(c, ids, task)
    saved = post(c, path(ids, task), body, h)
    assert saved['version'] == saved['review']['revision'] == 1
    basis = read(f, ids, task)
    assert basis['state'] == 'applicable'
    assert basis['report_period'] == {'starts_on': START, 'ends_on': END}
    assert basis['period_key'] == 'opaque:2025-is-only-a-label'
    assert basis['deadline_kind'] == 'without_undue_delay' and basis['deadline_date'] is None
    assert basis['report_period_review']['id'] == saved['review']['id']
    assert 'required_action' not in str(basis) and 'rationale' not in str(basis)
    history = c.get(path(ids, task), params={'document_kind': KIND}).json()
    assert len(history['history']) == 1 and history['version'] == 1
    with f() as db:
        row = db.get(m.ObligationInstance, task['id'])
        assert row.state == task['state'] == 'due' and row.version == task['version']
        event = db.scalar(select(m.GovernanceEvent).where(m.GovernanceEvent.aggregate_id == saved['review']['id']))
        assert event.aggregate_version == 1 and event.actor_id == ids['leader'] and event.correlation_id and event.occurred_at and event.recorded_at
        assert db.scalar(select(AuditRecord).where(AuditRecord.target_id == saved['review']['id'])) is not None


@pytest.mark.parametrize('start,end', [(date(2026,1,1), date(2026,12,31)), (date(2025,2,1), END), (START, date(2025,12,30)), (date(2024,12,31), END), (START, date(2026,1,1))])
def test_year_month_and_inclusive_dates_must_match_exactly(env, start, end):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    result = read(f, ids, task, start, end)
    assert result['state'] == 'unresolved' and result['report_period'] is None
    assert 'report_period_mismatch' in result['unresolved_inputs']


def test_correction_revocation_and_each_document_kind_has_own_revision(env):
    c, f, ids, _, _ = env
    other = 'local_semester_report'
    task, _, _, h = setup(env, documents=[KIND, other])
    original = post(c, path(ids, task), review_body(c, ids, task), h)
    assert read(f, ids, task, kind=other)['state'] == 'unresolved'
    post(c, path(ids, task), review_body(c, ids, task, document_kind=other), h)
    corrected = review_body(c, ids, task, starts_on='2026-01-01', ends_on='2026-10-21')
    second = post(c, path(ids, task), corrected, h)
    assert second['version'] == 2
    assert read(f, ids, task)['state'] == 'unresolved'
    assert read(f, ids, task, date(2026,1,1), date(2026,10,21))['state'] == 'applicable'
    assert read(f, ids, task, kind=other)['state'] == 'applicable'
    revoked = review_body(c, ids, task, action='revoke', starts_on='2026-01-01', ends_on='2026-10-21')
    post(c, path(ids, task), revoked, h)
    assert 'report_period_review_revoked' in read(f, ids, task, date(2026,1,1), date(2026,10,21))['unresolved_inputs']
    hist = c.get(path(ids, task), params={'document_kind': KIND}).json()['history']
    assert [r['revision'] for r in hist] == [1,2,3] and hist[0] == original['review']


def test_duplicate_key_payload_conflict_revision_conflict_and_fresh_action_auth(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    body = review_body(c, ids, task)
    first = post(c, path(ids, task), body, h)
    assert post(c, path(ids, task), body, h) == first
    post(c, path(ids, task), {**body, 'ends_on': '2025-11-30'}, h, 409)
    post(c, path(ids, task), {**body, 'request_key': str(uuid4())}, h, 409)
    with f.begin() as db:
        grant = db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'], AuthorityGrant.action == 'governance.tasks.review'))
        grant.state = 'revoked'
    post(c, path(ids, task), body, h, 403)
    assert 'report_period_reviewer_unavailable' in read(f, ids, task)['unresolved_inputs']
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.ReportPeriodReview)) == 1


def test_unseen_changed_inputs_digest_rejected_and_existing_review_unresolved(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    body = review_body(c, ids, task)
    post(c, path(ids, task), body, h)
    unseen = review_body(c, ids, task)
    changed = post(c, base(ids)+f'/obligations/{task["id"]}/inputs', {'expected_version': task['version'], 'inputs': {'support_entitlement': 'ITO'}, 'reason': 'Native reassessment', 'timing': {}}, h)
    post(c, path(ids, task), unseen, h, 409)
    assert 'report_period_basis_changed' in read(f, ids, task)['unresolved_inputs']
    post(c, path(ids, task), review_body(c, ids, task), h)
    assert read(f, ids, task)['state'] == 'applicable'
    # Assignment and performed-action recording do not silently replace coverage.
    assigned = post(c, base(ids)+f'/obligations/{task["id"]}/assignment', {'expected_version': changed['version'], 'owner_id': ids['teacher'], 'reason': 'Ordinary assignment'}, h)
    from spesped.db import utcnow
    post(c, base(ids)+f'/obligations/{task["id"]}/actions', {'expected_version': assigned['version'], 'kind': 'performed_action', 'action_type': 'synthetic', 'description': 'Actual action, no coverage inference', 'occurred_at': utcnow().isoformat()}, h, 201)
    assert read(f, ids, task)['state'] == 'applicable'
    assert read(f, ids, task)['report_period_review']['revision'] == 2


@pytest.mark.parametrize('recall', ['rule', 'profile', 'identity', 'source_reviewer', 'reviewer_pupil_scope'])
def test_current_recall_and_stale_orm_are_rechecked_without_overwrite(env, recall):
    c, f, ids, _, _ = env
    task, rule, profile, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    with f() as retained:
        cached = retained.get(m.RequirementVersion, rule['id'])
        assert read(f, ids, task)['state'] == 'applicable'
        if recall == 'rule':
            post(c, base(ids)+f'/requirement-versions/{rule["id"]}/withdraw', {'expected_version': rule['version'], 'rationale': 'Synthetic recall'}, h)
        elif recall == 'profile':
            post(c, base(ids)+f'/profiles/{profile["id"]}/revoke', {'expected_version': profile['version'], 'rationale': 'Synthetic recall'}, h)
        else:
            with f.begin() as db:
                if recall == 'identity': db.get(Learner, ids['learner']).grade = 5
                elif recall == 'source_reviewer':
                    db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'], AuthorityGrant.action == 'governance.rules.approve')).state = 'revoked'
                else:
                    db.scalar(select(StaffAssignment).where(StaffAssignment.user_id == ids['leader'], StaffAssignment.learner_id == ids['learner'])).state = 'revoked'
                    db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['leader'], AuthorityGrant.action == 'learner.read')).state = 'revoked'
        if recall == 'reviewer_pupil_scope':
            # Teacher remains an ordinary pupil reader but original reviewer lost scope.
            result = report_obligation_basis(retained, Actor(ids['teacher']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        else:
            result = report_obligation_basis(retained, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        assert result['state'] == 'unresolved'
        assert cached.state == 'reviewed' and retained.get(m.RequirementVersion, rule['id']) is cached
    with f() as db: assert db.scalar(select(func.count()).select_from(m.ReportPeriodReview)) == 1


def test_read_preserves_transaction_and_rejects_pending_dependencies(env):
    c, f, ids, _, _ = env
    task, rule, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    with f() as db:
        cached = db.get(m.ObligationInstance, task['id'])
        transaction = db.get_transaction()
        assert report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)['state'] == 'applicable'
        assert db.get_transaction() is transaction and db.get(m.ObligationInstance, task['id']) is cached
        cached.period_key = 'pending-unsaved'
        with pytest.raises(DomainError, match='staged'):
            report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        assert cached.period_key == 'pending-unsaved' and cached in db.dirty and db.get_transaction() is transaction
        db.rollback()
    with f() as db:
        pending = AuthorityGrant(school_id=ids['school'], user_id=ids['leader'], action='irrelevant.synthetic', valid_from=START, granted_by=ids['leader'])
        db.add(pending)
        with pytest.raises(DomainError): report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        assert pending in db.new and pending.id is None


def test_scope_and_date_type_fail_closed(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    # Ordinary pupil reader consumes metadata without management or AI authority.
    assert read(f, ids, task, actor=ids['teacher'])['state'] == 'applicable'
    with f() as db:
        for learner in (str(uuid4()), 'bad'):
            with pytest.raises(DomainError) as caught:
                report_obligation_basis(db, Actor(ids['leader']), ids['school'], learner, task['id'], KIND, START, END)
            assert caught.value.status_code == 403
        with pytest.raises(DomainError): report_obligation_basis(db, Actor(ids['outsider']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        for bad in ('2025-01-01', datetime(2025,1,1)):
            with pytest.raises(DomainError): report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, bad, END)
    h = login(c, 'teacher')
    post(c, path(ids, task), {'request_key':'denied', 'expected_version':1,'obligation_basis_digest':'0'*64,'document_kind':KIND,'starts_on':'2025-01-01','ends_on':'2025-12-31','rationale':'Denied'}, h, 403)


def test_unresolved_rule_or_wrong_document_kind_cannot_be_reviewed(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env, conditions=[{'fact':'support_entitlement', 'equals':'ITO'}])
    post(c, path(ids, task), review_body(c, ids, task), h, 409)
    assert read(f, ids, task)['state'] == 'unresolved'
    post(c, path(ids, task), review_body(c, ids, task, document_kind='guardian_email'), h, 409)


def test_atomic_late_outbox_failure_rolls_back_review_receipt_and_audit(env, monkeypatch):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    body = review_body(c, ids, task)
    from sqlalchemy import event
    def fail(mapper, connection, row):
        if row.event_type.startswith('governance.report_period.'):
            raise RuntimeError('Synthetic late outbox failure')
    event.listen(m.GovernanceEvent, 'before_insert', fail)
    try:
        with pytest.raises(RuntimeError, match='late outbox'):
            c.post(path(ids, task), json=body, headers=h)
    finally:
        event.remove(m.GovernanceEvent, 'before_insert', fail)
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.ReportPeriodReview)) == 0
        assert db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.action.like('governance.report_period.%'))) == 0
    assert post(c, path(ids, task), body, h)['version'] == 1


def test_pg_same_key_and_expected_revision_races(env):
    c, f, ids, dialect, _ = env
    if dialect != 'postgres': pytest.skip('PostgreSQL locking verification')
    task, _, _, h = setup(env)
    from spesped.contexts.governance.report_periods import ReportPeriodCommand, review_report_period
    body = review_body(c, ids, task)
    def invoke(body):
        with f() as db:
            try: return review_report_period(db, Actor(ids['leader']), ids['school'], task['id'], ReportPeriodCommand(**body))['review']['id']
            except DomainError as error: return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicate = list(pool.map(invoke, [body,body]))
    assert duplicate[0] == duplicate[1]
    next_body = review_body(c, ids, task)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, [next_body, {**next_body,'request_key':str(uuid4())}]))
    assert results.count('version_conflict') == 1
    with f() as db: assert db.scalar(select(func.count()).select_from(m.ReportPeriodReview)) == 2


def test_static_migration_parity_retained_legacy_and_empty_roundtrip(env):
    c, f, ids, dialect, config = env
    task, _, _, h = setup(env)
    with f() as db:
        old = {column.name: getattr(db.get(m.ObligationInstance, task['id']),column.name) for column in m.ObligationInstance.__table__.columns}
    command.downgrade(config, 'j11_documents')
    command.upgrade(config, 'j13_report_period')
    with f() as db:
        assert old == {column.name:getattr(db.get(m.ObligationInstance,task['id']),column.name) for column in m.ObligationInstance.__table__.columns}
        inspector = inspect(db.connection())
        table = m.ReportPeriodReview.__table__
        columns = inspector.get_columns(table.name)
        assert {v['name']:v['nullable'] for v in columns} == {v.name:v.nullable for v in table.columns}
        assert {v['name']:v['type'].compile(dialect=db.bind.dialect) for v in columns} == {v.name:v.type.compile(dialect=db.bind.dialect) for v in table.columns}
        assert {tuple(v['column_names']) for v in inspector.get_unique_constraints(table.name)} == {tuple(col.name for col in v.columns) for v in table.constraints if type(v).__name__ == 'UniqueConstraint'}
        assert {tuple(v['column_names']) for v in inspector.get_indexes(table.name) if not v.get('duplicates_constraint')} == {tuple(col.name for col in v.columns) for v in table.indexes}
        assert {tuple(v['constrained_columns']) for v in inspector.get_foreign_keys(table.name)} == {tuple(col.name for col in v.columns) for v in table.constraints if type(v).__name__ == 'ForeignKeyConstraint'}
    assert read(f, ids, task)['state'] == 'unresolved'
    post(c, path(ids, task), review_body(c, ids, task), h)
    with pytest.raises(RuntimeError, match='Retained reporting period'): command.downgrade(config,'j11_documents')
    with f() as db:
        assert db.scalar(select(func.count()).select_from(m.ReportPeriodReview)) == 1
    if dialect == 'postgres':
        with f() as db:
            with pytest.raises(DBAPIError): db.execute(text("UPDATE governance_report_period_reviews SET rationale='overwrite'"))
            db.rollback()


def test_deadline_is_context_not_covered_dates_and_full_rule_interval_required(env):
    c, f, ids, _, _ = env
    _, rule, h = rule_setup(env, documents=[KIND], deadline={'kind':'fixed_date','fixed_date':'2025-12-01','legal_basis':'Synthetic submission deadline'})
    profile = profile_setup(env, rule, h)
    task = post(c, base(ids)+'/triggers', trigger_body(profile, learner_id=ids['learner'], period_key='2025'), h, 201)['items'][0]
    assert read(f, ids, task)['state'] == 'unresolved'
    post(c, path(ids, task), review_body(c, ids, task), h)
    result = read(f, ids, task)
    assert result['state'] == 'applicable' and result['deadline_date'] == date(2025,12,1)
    assert result['report_period'] == {'starts_on':START, 'ends_on':END}
    assert read(f, ids, task, date(2026,10,1), date(2026,10,21))['state'] == 'unresolved'
    post(c, path(ids, task), review_body(c, ids, task, starts_on='2019-12-31'), h, 409)
    assert c.get(path(ids, task), params={'document_kind':KIND}).json()['version'] == 1


def test_pending_deletion_and_protected_task_denied(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    with f() as db:
        row = db.get(m.ObligationInstance, task['id'])
        db.delete(row)
        with pytest.raises(DomainError): report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)
        assert row in db.deleted
        db.rollback()
    with f.begin() as db:
        # Protected case reporting requires a future exact owner contract. Current
        # port denies it even for a staff member who owns ordinary pupil scope.
        db.get(m.ObligationInstance, task['id']).case_id = str(uuid4())
    with pytest.raises(DomainError) as caught: read(f, ids, task)
    assert caught.value.status_code == 403
    assert c.get(path(ids, task), params={'document_kind':KIND}).status_code == 403


def test_recalled_review_current_status_visible_in_history(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    assert c.get(path(ids, task), params={'document_kind':KIND}).json()['state'] == 'applicable'
    post(c, path(ids, task), review_body(c, ids, task, action='revoke'), h)
    current = c.get(path(ids, task), params={'document_kind':KIND}).json()
    assert current['state'] == 'unresolved' and current['current']['action'] == 'revoke'
    assert len(current['history']) == 2


def test_period_context_change_needs_new_review_and_read_does_not_rollback_flushed_work(env):
    c, f, ids, _, _ = env
    task, _, _, h = setup(env)
    post(c, path(ids, task), review_body(c, ids, task), h)
    with f.begin() as db:
        db.get(m.ObligationInstance, task['id']).period_key = 'corrected-opaque-period'
    assert 'report_period_basis_changed' in read(f, ids, task)['unresolved_inputs']
    post(c, path(ids, task), review_body(c, ids, task), h)
    with f() as db:
        event = m.GovernanceEvent(school_id=ids['school'], aggregate_id=task['id'], aggregate_version=task['version'], event_type='synthetic.caller.transaction', actor_id=ids['leader'])
        db.add(event)
        db.flush()
        sentinel = event.id
        assert report_obligation_basis(db, Actor(ids['leader']), ids['school'], ids['learner'], task['id'], KIND, START, END)['state'] == 'applicable'
        db.commit()
    with f() as db:
        assert db.get(m.GovernanceEvent, sentinel) is not None
