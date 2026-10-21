"""Actual historical goal periods for reports without changing teaching bindings."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from plans_fixtures import env, login, evidence, plan_payload, activate, base
from spesped.auth import Actor
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.contexts.plans.models import PlanRevision
from spesped.contexts.plans.projections import reporting_goal_basis, teaching_goal_basis
from spesped.db import utcnow
from spesped.errors import DomainError


def plan(client, ids, headers, binding, starts_at=None):
    command = plan_payload(binding)
    if starts_at is not None:
        command['effective_from'] = starts_at.isoformat()
        command['goals'][0]['effective_from'] = starts_at.isoformat()
    response = client.post(base(ids) + f'/learners/{ids["a"]}/education-plans',
                           headers=headers, json=command)
    assert response.status_code == 201, response.text
    row = activate(client, ids, headers, response.json())
    return row, row['content']['goals'][0]['id']


def test_report_period_follows_supersession_and_preserves_teaching_binding(env):
    client, factory, _, ids = env
    headers = login(client)
    binding, _ = evidence(client, ids, headers)
    original, old_goal = plan(client, ids, headers, binding)
    instant = utcnow()
    boundary = instant + timedelta(days=1)
    actor = Actor(ids['reviewer'])
    with factory() as db:
        before = teaching_goal_basis(db, actor, ids['school'], ids['a'], old_goal,
                                     at=instant, historical=True)
        historical = reporting_goal_basis(db, actor, ids['school'], ids['a'], old_goal,
                                           at=instant - timedelta(days=1))
        assert datetime.fromisoformat(historical['effective_period']['starts_at']) < (
            datetime.fromisoformat(historical['activation_recorded_at']))
    replacement, new_goal = plan(client, ids, headers, binding, boundary)
    with factory() as db:
        after = teaching_goal_basis(db, actor, ids['school'], ids['a'], old_goal,
                                    at=instant, historical=True)
        assert after == before
        old = reporting_goal_basis(db, actor, ids['school'], ids['a'], old_goal, at=instant)
        new = reporting_goal_basis(db, actor, ids['school'], ids['a'], new_goal, at=boundary)
        assert datetime.fromisoformat(old['effective_period']['ends_at_exclusive']) == boundary
        assert datetime.fromisoformat(new['effective_period']['starts_at']) == boundary
        assert old['goal']['plan_revision_id'] == original['content']['id']
        assert new['goal']['plan_revision_id'] == replacement['content']['id']
        with pytest.raises(DomainError) as raised:
            reporting_goal_basis(db, actor, ids['school'], ids['a'], old_goal, at=boundary)
        assert raised.value.code == 'goal_period'


def test_report_goal_rechecks_sources_and_preserves_staged_caller(env):
    client, factory, _, ids = env
    headers = login(client)
    binding, _ = evidence(client, ids, headers)
    original, goal = plan(client, ids, headers, binding)
    actor, instant = Actor(ids['reviewer']), utcnow()
    with factory() as db:
        cached = db.get(PlanRevision, original['content']['id'])
        cached.activation_until = instant + timedelta(days=1)
        effects = []
        connection = db.connection()

        def record(*args):
            effects.append('transaction changed')

        listeners = [(db, 'before_flush'), (connection, 'commit'), (connection, 'rollback')]
        for target, name in listeners:
            event.listen(target, name, record)
        try:
            with pytest.raises(DomainError) as raised:
                reporting_goal_basis(db, actor, ids['school'], ids['a'], goal, at=instant)
            assert raised.value.code == 'dependency_pending'
            assert not effects and cached in db.dirty and db.in_transaction()
        finally:
            for target, name in listeners:
                event.remove(target, name, record)
        db.rollback()
        source = db.get(SourceSubjectLink, binding['link_id'])
        assert reporting_goal_basis(db, actor, ids['school'], ids['a'], goal, at=instant)
        with factory.begin() as writer:
            writer.get(SourceSubjectLink, binding['link_id']).revoked_at = utcnow()
        with pytest.raises(DomainError):
            reporting_goal_basis(db, actor, ids['school'], ids['a'], goal, at=instant)
        assert source.revoked_at is None
        assert db.in_transaction()
