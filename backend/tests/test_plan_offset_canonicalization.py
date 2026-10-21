"""Plan approvals bind the same persisted content across aware timestamp offsets."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from plans_fixtures import (
    env, login, base, expected, evidence, support_case, confirmed_decision,
    plan_payload, key,
)
from spesped.auth import Actor
from spesped.contexts.plans import service
from spesped.contexts.plans.models import PlanApproval, PlanRevision
from spesped.domain import canonical_content_digest


def post(client, path, headers, payload, status=201):
    response = client.post(path, headers=headers, json=payload)
    assert response.status_code == status, response.text
    return response.json()


def offset(value, minutes):
    return datetime.fromisoformat(value).astimezone(timezone(timedelta(minutes=minutes))).isoformat()


def reload_plan(client, path, row):
    response = client.get(path)
    assert response.status_code == 200, response.text
    loaded = response.json()
    assert loaded['content'] == row['content']
    assert loaded['content_digest'] == row['content_digest']
    assert loaded['clarifications'] == []
    assert canonical_content_digest(loaded['content']) == row['content_digest']
    return loaded


def lifecycle(client, path, headers, row, actions=('review', 'approve', 'activate')):
    for action in actions:
        row = reload_plan(client, path, row)
        row = post(client, path+'/'+action, headers, expected(
            row, revision_id=row['content']['id'], content_digest=row['content_digest'],
            reason='Synthetic exact timestamp content '+action,
        ), 200)
        assert row['clarifications'] == []
    return reload_plan(client, path, row)


@pytest.mark.parametrize('minutes', [120, -330, 0], ids=['positive', 'negative', 'utc'])
def test_native_create_review_reload_activation_for_plan_and_goal_offsets(env, monkeypatch, minutes):
    client, factory, app, ids = env
    headers = login(client)
    now = service.utcnow().replace(microsecond=123456)
    monkeypatch.setattr(service, 'utcnow', lambda: now)
    # Exercise each boundary separately so a goal offset cannot hide a plan bug.
    for target in ('plan', 'goal', 'both'):
        payload = plan_payload()
        payload['effective_from'] = now.isoformat()
        payload['goals'][0]['effective_from'] = now.isoformat()
        if target in {'plan', 'both'}:
            for name in ('effective_from', 'effective_until'):
                payload[name] = offset(payload[name], minutes)
        if target in {'goal', 'both'}:
            for name in ('effective_from', 'effective_until'):
                payload['goals'][0][name] = offset(payload['goals'][0][name], minutes)
        row = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, payload)
        path = base(ids)+f'/education-plans/{row["id"]}'
        row = reload_plan(client, path, row)
        assert row['content']['effective_from'] == now.isoformat()
        assert row['content']['goals'][0]['effective_from'] == now.isoformat()
        wrong = post(client, path+'/review', headers, expected(
            row, revision_id=row['content']['id'], content_digest='0'*64,
            reason='Wrong exact digest must still fail',
        ), 409)
        assert wrong['error']['code'] == 'revision_conflict'
        row = lifecycle(client, path, headers, row)
        assert row['approval_binding']['revision_digest'] == row['content_digest']
        goal_id = row['content']['goals'][0]['id']
        response = client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals', params={'at': offset(now.isoformat(), minutes)})
        assert response.status_code == 200, response.text
        assert [g['id'] for g in response.json()['items']] == [goal_id]
        # Request identity remains exact; offset normalization does not loosen replay.
        replay = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, payload)
        assert replay['id'] == row['id']
        if minutes:
            different = deepcopy(payload)
            different['effective_from'] = offset(payload['effective_from'], 0 if target != 'goal' else minutes)
            conflict = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, different, 409)
            assert conflict['error']['code'] == 'idempotency_conflict'


@pytest.mark.parametrize('minutes', [120, -330], ids=['positive', 'negative'])
def test_allocations_contributions_and_imported_approval_round_trip(env, monkeypatch, minutes):
    client, factory, app, ids = env
    headers = login(client)
    binding, _ = evidence(client, ids, headers)
    case = support_case(client, factory, ids, headers)
    decision = confirmed_decision(client, ids, headers, case, binding)
    now = service.utcnow()
    monkeypatch.setattr(service, 'utcnow', lambda: now)
    original = {'approver': 'Synthetic original approver', 'authority': 'Synthetic recorded responsibility',
                'approved_at': offset((now-timedelta(days=4)).isoformat(), minutes), 'source': binding}
    payload = plan_payload(binding, decision, origin='imported', original_approval=original)
    for value in (payload, payload['goals'][0], payload['allocations'][0]):
        for name in ('effective_from', 'effective_until'):
            value[name] = offset(value[name], minutes)
    payload['contributions'][0]['occurred_at'] = offset(payload['contributions'][0]['occurred_at'], minutes)
    row = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, payload)
    path = base(ids)+f'/education-plans/{row["id"]}'
    row = lifecycle(client, path, headers, row)
    assert row['content']['original_approval']['approved_at'] == original['approved_at']
    assert row['content']['adaptations'][0]['measure'] == payload['adaptations'][0]['measure']
    assert datetime.fromisoformat(row['content']['contributions'][0]['occurred_at']).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(row['content']['allocations'][0]['effective_from']).utcoffset() == timedelta(0)


def test_existing_approved_history_is_unchanged_by_offset_revision(env, monkeypatch):
    client, factory, app, ids = env
    headers = login(client)
    binding, _ = evidence(client, ids, headers)
    now = service.utcnow()
    monkeypatch.setattr(service, 'utcnow', lambda: now)
    payload = plan_payload(binding, origin='imported', original_approval={
        'approver': 'Synthetic old approver', 'authority': 'Synthetic original responsibility',
        'approved_at': offset((now-timedelta(days=5)).isoformat(), 120), 'source': binding,
    })
    # Construct an existing valid record using the previous unnormalized write
    # path. Its UTC columns and offset-bearing JSON approval already had a valid
    # exact digest before the repair; it must retain that content and approval.
    with monkeypatch.context() as legacy:
        legacy.setattr(service, 'new_content_values', lambda command, *, exclude: command.model_dump(exclude=exclude))
        row = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, payload)
        path = base(ids)+f'/education-plans/{row["id"]}'
        row = lifecycle(client, path, headers, row)
    old_content = deepcopy(row['content'])
    old_binding = deepcopy(row['approval_binding'])
    old_digest = row['content_digest']
    old_id = row['content']['id']
    with factory() as db:
        approvals = [(r.id, r.kind, r.digest, r.reason) for r in db.scalars(select(PlanApproval).where(PlanApproval.plan_revision_id == old_id).order_by(PlanApproval.id))]
    payload.pop('kind')
    payload.update(request_key=key(), expected_version=row['version'], effective_from=offset(now.isoformat(), -330))
    payload['goals'][0].update(goal_id=old_content['goals'][0]['goal_id'], effective_from=payload['effective_from'], expected_action='Read two sentences with visual support')
    revised = post(client, path+'/revisions', headers, payload)
    revised = lifecycle(client, path, headers, revised)
    history = client.get(path+'/revisions').json()['items']
    historical = next(item for item in history if item['content']['id'] == old_id)
    assert historical['revision_state'] == 'historical'
    assert historical['content'] == old_content
    assert historical['content_digest'] == old_digest
    assert historical['approval_binding'] == old_binding
    assert historical['clarifications'] == []
    with factory() as db:
        old = db.get(PlanRevision, old_id)
        assert canonical_content_digest(service.snapshot(db, old)) == old_digest
        assert [(r.id, r.kind, r.digest, r.reason) for r in db.scalars(select(PlanApproval).where(PlanApproval.plan_revision_id == old_id).order_by(PlanApproval.id))] == approvals
        ref = service.validate_goal_reference(db, Actor(ids['reviewer']), ids['school'], ids['a'], old_content['goals'][0]['id'])
        assert ref['plan_digest'] == old_digest
    response = client.get(base(ids)+f'/learners/{ids["a"]}/learning-goals/{old_content["goals"][0]["id"]}', params={'historical': True})
    assert response.status_code == 200, response.text


def test_changed_persisted_timestamp_still_invalidates_exact_approval(env):
    client, factory, app, ids = env
    headers = login(client)
    row = post(client, base(ids)+f'/learners/{ids["a"]}/education-plans', headers, plan_payload())
    path = base(ids)+f'/education-plans/{row["id"]}'
    row = lifecycle(client, path, headers, row, actions=('review', 'approve'))
    with factory.begin() as db:
        # Simulate storage corruption bypassing immutable ORM content guards.
        db.execute(update(PlanRevision).where(PlanRevision.id == row['content']['id']).values(
            effective_from=datetime.fromisoformat(row['content']['effective_from'])+timedelta(seconds=1)))
    response = post(client, path+'/activate', headers, expected(
        row, revision_id=row['content']['id'], content_digest=row['content_digest'],
        reason='A changed instant must not inherit the approval',
    ), 409)
    assert response['error']['code'] == 'revision_conflict'
    assert client.get(path).json()['revision_state'] == 'approved'
