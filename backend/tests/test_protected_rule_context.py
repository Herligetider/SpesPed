"""Real reviewed rule commands and protected case authorization for the read port."""
from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from spesped.auth import Actor
from spesped.contexts.identity.models import AuthorityGrant, AuditRecord
from spesped.contexts.governance import models as gm
from spesped.contexts.governance.projections import case_requirements
from spesped.contexts.safeguarding.service import resolve_case_learner
from spesped.errors import DomainError
from test_safeguarding import env, setup, post


@pytest.fixture
def configured(env):
    case, headers, _ = setup(env, occurred_at='2020-01-01T10:00:00Z')
    client, factory, ids, _, _, app = env
    app.state.governance_case_scope_resolver = resolve_case_learner
    with factory.begin() as db:
        for action in ('rules.manage', 'rules.approve', 'tasks.manage', 'tasks.review'):
            db.add(AuthorityGrant(school_id=ids['school'], user_id=ids['teacher'],
                action='governance.' + action, valid_from=date(2020, 1, 1), granted_by=ids['owner']))
        db.add(AuthorityGrant(school_id=ids['school'], user_id=ids['teacher'],
            action='governance.case.read', learner_id=ids['learner'], case_id=case['id'],
            valid_from=date(2020, 1, 1), granted_by=ids['owner']))
    return env, case, headers


def prefix(ids):
    return f'/api/v1/schools/{ids["school"]}/governance'


def reviewed_profile(env, headers, conditions=None, start='2020-01-01', end=None):
    client, _, ids, _, _, _ = env
    p = prefix(ids)
    definition = post(client, p + '/requirements', {
        'code': 'synthetic-' + uuid4().hex, 'title': 'Synthetic case procedure',
        'source_type': 'local_routine', 'source_reference': 'Synthetic fixture; no legal conclusion',
    }, headers, 201)
    rule = post(client, p + '/requirements/' + definition['id'] + '/versions', {
        'expected_version': definition['version'], 'valid_from': start,
        'conditions': conditions or [], 'trigger_type': 'synthetic_case_event',
        'deadline': {'kind': 'without_undue_delay', 'legal_basis': 'Synthetic test rule'},
        'required_action': 'Review the pupil perspective with a responsible professional',
        'required_document_types': ['perspective_note'], 'accountable_role': 'educator',
        'interpretation_notes': 'A generic reviewed action; not a notification or legal certification.',
    }, headers, 201)
    rule = post(client, p + '/requirement-versions/' + rule['id'] + '/review', {
        'expected_version': rule['version'], 'rationale': 'Reviewed synthetic input',
    }, headers)
    body = {'label': 'Synthetic reviewed profile', 'requirement_version_ids': [rule['id']],
            'valid_from': start, 'valid_until': end}
    profile = post(client, p + '/profiles', body, headers, 201)
    impact = client.get(p + '/profiles/' + profile['id'] + '/impact').json()
    profile = post(client, p + '/profiles/' + profile['id'] + '/activate', {
        'expected_version': profile['version'], 'impact_digest': impact['impact_digest'],
        'rationale': 'Reviewed synthetic profile',
    }, headers)
    return rule, profile


def trigger(env, case, headers, profile, occurred_at='2026-10-01T10:00:00Z'):
    client, _, ids, _, _, _ = env
    return post(client, prefix(ids) + '/triggers', {
        'event_key': uuid4().hex, 'profile_id': profile['id'], 'event_type': 'synthetic_case_event',
        'occurred_at': occurred_at, 'learner_id': ids['learner'], 'case_id': case['id'],
        'period_key': 'synthetic-' + uuid4().hex,
    }, headers, 201)['items'][0]


def projection(env, case, actor='teacher', db=None, **scope):
    _, factory, ids, _, _, _ = env
    if db is None:
        with factory() as session:
            return projection(env, case, actor, db=session, **scope)
    db.info['governance_case_scope_resolver'] = resolve_case_learner
    return case_requirements(db, Actor(ids[actor]), scope.get('school_id', ids['school']),
                             scope.get('learner_id', ids['learner']), scope.get('case_id', case['id']))


def test_current_rule_metadata_does_not_create_or_fulfill_tasks(configured):
    env, case, headers = configured
    _, factory, _, _, _, _ = env
    rule, profile = reviewed_profile(env, headers)
    empty = projection(env, case)
    assert empty.state == 'unavailable' and empty.legal_completeness == 'not_assessed'
    task = trigger(env, case, headers, profile)
    with factory() as db:
        counts = [db.scalar(select(func.count()).select_from(model))
                  for model in (gm.ObligationInstance, gm.GovernanceEvent, AuditRecord)]
        result = projection(env, case, db=db)
        assert result.state == 'available'
        item, = result.obligations
        assert item.id == task['id'] and item.state == 'due'
        assert item.source.requirement_version_id == rule['id']
        assert item.source.profile_digest == profile['content_digest']
        assert item.required_document_types == ('perspective_note',)
        assert item.required_action == rule['required_action']
        assert 'notification' not in asdict(result)
        assert result.coverage == 'authorized_recorded_obligations_only'
        assert counts == [db.scalar(select(func.count()).select_from(model))
                          for model in (gm.ObligationInstance, gm.GovernanceEvent, AuditRecord)]
        assert not db.new and not db.dirty


def test_rule_withdrawal_refreshes_cached_metadata(configured):
    env, case, headers = configured
    client, factory, ids, _, _, _ = env
    rule, profile = reviewed_profile(env, headers)
    trigger(env, case, headers, profile)
    with factory() as db:
        assert projection(env, case, db=db).state == 'available'
        post(client, prefix(ids) + '/requirement-versions/' + rule['id'] + '/withdraw', {
            'expected_version': rule['version'], 'rationale': 'Synthetic rule withdrawn',
        }, headers)
        result = projection(env, case, db=db)
        assert result.state == 'review_required'
        item, = result.obligations
        assert item.source.state == 'withdrawn'
        assert item.required_action is None and item.required_document_types == ()
        assert item.state == 'due' and item.review_required


def test_unresolved_applicability_has_no_unqualified_action(configured):
    env, case, headers = configured
    _, profile = reviewed_profile(env, headers, [{'fact': 'support_entitlement', 'equals': True}])
    trigger(env, case, headers, profile)
    result = projection(env, case)
    item, = result.obligations
    assert result.state == 'review_required' and item.state == 'unresolved'
    assert item.unresolved_inputs == ('support_entitlement',)
    assert item.required_action is None and item.required_document_types == ()
    assert result.legal_completeness == 'not_assessed'


def test_multiple_actual_profiles_remain_separate_and_recall_is_visible(configured):
    env, case, headers = configured
    client, _, ids, _, _, _ = env
    _, first = reviewed_profile(env, headers, end='2024-12-31')
    _, second = reviewed_profile(env, headers, start='2025-01-01')
    trigger(env, case, headers, first, '2024-10-01T10:00:00Z')
    trigger(env, case, headers, second)
    assert {item.source.profile_id for item in projection(env, case).obligations} == {first['id'], second['id']}
    post(client, prefix(ids) + '/profiles/' + second['id'] + '/revoke', {
        'expected_version': second['version'], 'rationale': 'Synthetic profile withdrawn',
    }, headers)
    result = projection(env, case)
    assert result.state == 'review_required'
    by_profile = {item.source.profile_id: item for item in result.obligations}
    assert by_profile[first['id']].source.state == 'current'
    assert by_profile[first['id']].required_action
    assert by_profile[second['id']].source.state == 'profile_revoked'
    assert by_profile[second['id']].required_action is None


def test_task_ownership_and_exact_case_authority_remain_live(configured):
    env, case, headers = configured
    client, factory, ids, _, _, _ = env
    _, profile = reviewed_profile(env, headers)
    first = trigger(env, case, headers, profile)
    trigger(env, case, headers, profile)
    post(client, prefix(ids) + '/obligations/' + first['id'] + '/assignment', {
        'expected_version': first['version'], 'owner_id': ids['teacher'], 'reason': 'Synthetic scoped assignment',
    }, headers)
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['teacher'],
                AuthorityGrant.action == 'governance.tasks.manage')):
            grant.state = 'revoked'
    result = projection(env, case)
    assert [item.id for item in result.obligations] == [first['id']]
    for scope in ({'learner_id': ids['learner2']}, {'case_id': str(uuid4())}, {'case_id': None},
                  {'school_id': ids['foreign_school']}):
        with pytest.raises(DomainError) as error:
            projection(env, case, **scope)
        assert error.value.status_code == 403
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['teacher'],
                AuthorityGrant.action == 'safeguarding.case.read')):
            grant.state = 'revoked'
    with pytest.raises(DomainError) as error:
        projection(env, case)
    assert error.value.status_code == 403
