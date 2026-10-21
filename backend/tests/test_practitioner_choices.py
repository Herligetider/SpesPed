"""Real authenticated choice/read ports for the planning and teaching screens."""
from dataclasses import replace
from datetime import date, timedelta

from sqlalchemy import select

from plan_generation_fixtures import generated_env, plan_wire, env, post
from plans_fixtures import base, login, retry
from teaching_fixtures import (teaching_env, teaching_wire_server, configure_ai,
    ordinary_goal, basis, session, approve, assigned_brief, actual)
from spesped.auth import Actor
from spesped.contexts.identity.models import AuthorityGrant, SchoolMembership, UserAccount
from spesped.contexts.platform.models import ProcessingPolicy, ModelRelease
from spesped.contexts.teaching import service
from spesped.errors import DomainError
from spesped.db import utcnow
import pytest


def remove_admin(factory, ids):
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(
                AuthorityGrant.user_id == ids['reviewer'],
                AuthorityGrant.action.in_(['platform.manage', 'platform.review']))):
            grant.state = 'revoked'


def test_iep_choices_without_admin_are_purpose_bound_current_and_paginated(generated_env):
    e = generated_env
    remove_admin(e.factory, e.ids)
    path = base(e.ids) + '/ai/choices'
    params = {'learner_id': e.ids['a'], 'purpose': 'iep_drafting'}
    assert e.client.get(base(e.ids) + '/ai/configuration').status_code == 403
    response = e.client.get(path, params=params)
    assert response.status_code == 200, response.text
    choice, = response.json()['items']
    assert set(choice) == {'policy_id', 'release_id', 'label', 'model_version', 'reviewed_at'}
    assert choice['policy_id'] == e.policy and choice['release_id'] == e.release
    assert e.client.get(path, params=params | {'offset': 1, 'limit': 1}).json() == {'items': [], 'total': 1}
    assert e.client.get(path, params=params | {'purpose': 'intake_structuring'}).status_code == 422
    assert e.client.get(path, params=params | {'purpose': 'session_planning'}).status_code == 403
    assert e.client.get(path.replace(e.ids['school'], e.ids['other_school']), params=params).status_code == 403
    with e.factory.begin() as db:
        db.get(ModelRelease, e.release).state = 'revoked'
    assert e.client.get(path, params=params).json() == {'items': [], 'total': 0}
    login(e.client, 'assistant')
    assert e.client.get(path, params=params).status_code == 403


def test_teaching_choices_track_runtime_and_policy_without_admin(teaching_env, teaching_wire_server):
    client, factory, app, ids = teaching_env
    configured, policy, release = configure_ai(factory, app, ids, teaching_wire_server)
    login(client)
    remove_admin(factory, ids)
    path = base(ids) + '/ai/choices'
    params = {'learner_id': ids['a'], 'purpose': 'session_planning'}
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['release_id'] == release
    app.state.ai_gateway = replace(configured, providers={})
    assert client.get(path, params=params).json() == {'items': [], 'total': 0}
    app.state.ai_gateway = configured
    with factory.begin() as db:
        db.get(ProcessingPolicy, policy).state = 'revoked'
    assert client.get(path, params=params).json() == {'items': [], 'total': 0}


def test_staff_choices_limit_data_and_recheck_membership_and_scope(teaching_env):
    client, factory, app, ids = teaching_env
    login(client)
    path = base(ids) + f'/learners/{ids["a"]}/teaching-staff'
    response = client.get(path, params={'purpose': 'owner'})
    assert response.status_code == 200, response.text
    people = response.json()
    assert ids['assistant'] in {p['id'] for p in people['items']}
    assert not {ids['guardian'], ids['tech']} & {p['id'] for p in people['items']}
    assert all(set(p) == {'id', 'display_name'} for p in people['items'])
    pages = [client.get(path, params={'purpose': 'owner', 'offset': i, 'limit': 1}).json()['items'][0]
             for i in range(people['total'])]
    assert pages == people['items']
    with factory.begin() as db:
        db.get(UserAccount, ids['teacher']).state = 'suspended'
        membership = db.scalar(select(SchoolMembership).where(SchoolMembership.user_id == ids['assistant']))
        membership.valid_until = date.today() - timedelta(days=1)
    choices = client.get(path, params={'purpose': 'owner'}).json()['items']
    assert not {ids['teacher'], ids['assistant']} & {p['id'] for p in choices}
    with factory.begin() as db:
        db.get(UserAccount, ids['teacher']).state = 'active'
    login(client, 'teacher')
    assert client.get(path, params={'purpose': 'delivery'}).status_code == 200
    assert client.get(path, params={'purpose': 'assistant'}).status_code == 403
    assert client.get(path.replace(ids['a'], ids['b']), params={'purpose': 'owner'}).status_code == 403


def test_staff_mutation_does_not_trust_cached_active_user(teaching_env):
    _, factory, _, ids = teaching_env
    with factory() as stale:
        service.validate_owner(stale, ids['school'], ids['teacher'])
        with factory.begin() as fresh:
            fresh.get(UserAccount, ids['teacher']).state = 'suspended'
        with pytest.raises(DomainError) as error:
            service.validate_owner(stale, ids['school'], ids['teacher'])
        assert error.value.code == 'owner_unavailable'


def test_persisted_brief_choices_and_curated_names_keep_assignment_scope(teaching_env):
    client, factory, app, ids = teaching_env
    h = login(client)
    goal, _ = ordinary_goal(client, ids, h)
    row = approve(client, ids, h, session(client, ids, h, basis(client, ids, h, {'a': goal})))
    guide, assigned = assigned_brief(client, ids, h, row)
    prefix = base(ids)
    briefs = client.get(prefix + f'/teaching/sessions/{row["id"]}/briefs').json()
    assert briefs['items'][0]['id'] == guide['id']
    assignments = client.get(prefix + f'/teaching/briefs/{guide["id"]}/assignments').json()
    value = assignments['items'][0]
    assert value['assistant_name'] == 'Synthetic assistant'
    assert value['learner_name'] == 'Synthetic a'
    assert value['follow_up_owner_name'] == 'Synthetic reviewer'
    assert client.get(prefix + f'/teaching/briefs/{guide["id"]}/assignments', params={'offset': 1}).json()['items'] == []
    login(client, 'assistant')
    own = client.get(prefix + f'/teaching/brief-assignments/{assigned["id"]}')
    assert own.status_code == 200 and own.json()['learner_name'] == 'Synthetic a'
    assert client.get(prefix + f'/learners/{ids["a"]}/support-profile').status_code == 403
    assert client.get(prefix + f'/teaching/briefs/{guide["id"]}/assignments').status_code == 403
    with factory.begin() as db:
        from spesped.contexts.teaching.models import BriefAssignment
        db.get(BriefAssignment, assigned['id']).state = 'revoked'
    assert client.get(prefix + f'/teaching/brief-assignments/{assigned["id"]}').status_code == 403


def test_actual_correction_can_recover_owned_follow_up_without_group_leak(teaching_env):
    client, factory, app, ids = teaching_env
    h = login(client)
    goal, _ = ordinary_goal(client, ids, h)
    payload = actual(ids, {'a': goal}, status='partial', cause='other',
        cause_detail='Synthetic deviation', follow_up_owner_id=ids['reviewer'],
        follow_up='Synthetic dated owned action')
    row = post(client, base(ids) + '/teaching/deliveries', h, retry(content=payload))
    assert row['follow_up_owner_id'] == ids['reviewer']
    assert row['follow_up'] == 'Synthetic dated owned action'
    assert row['follow_up_source_status'] == 'current'
    recovered = client.get(base(ids) + f'/teaching/deliveries/{row["id"]}').json()
    assert recovered['follow_up'] == row['follow_up']
    learner = client.get(base(ids) + f'/learners/{ids["a"]}/teaching-deliveries').json()['items'][0]
    assert learner['follow_up_owner_id'] is None and learner['follow_up'] is None
    assert learner['follow_up_source_status'] == 'not_exposed'


def test_attributed_history_names_require_existing_teacher_or_assignment_access(teaching_env):
    client, factory, app, ids = teaching_env
    h = login(client)
    goal, _ = ordinary_goal(client, ids, h)
    row = approve(client, ids, h, session(client, ids, h, basis(client, ids, h, {'a': goal})))
    _, assigned = assigned_brief(client, ids, h, row)
    h = login(client, 'assistant')
    prefix = base(ids)
    observation = post(client, prefix + '/teaching/observations', h, retry(content={
        'learner_id':ids['a'], 'assignment_id':assigned['id'],
        'occurred_at':(utcnow()-timedelta(minutes=30)).isoformat(),
        'observation':'Synthetic attributed fact', 'support':'Synthetic cue',
        'interpretation':'Needs another observation', 'next_step':'Repeat'}))
    assert observation['author_name'] == 'Synthetic assistant'
    assignment_path = prefix + f'/teaching/brief-assignments/{assigned["id"]}'
    post(client, assignment_path + '/actual-inputs', h, retry(content={
        'occurred_at':(utcnow()-timedelta(minutes=30)).isoformat(),
        'duration_minutes':10, 'status':'participated', 'category':'ordinary_teaching',
        'activity':'Synthetic actual input', 'support':'Synthetic cue'}))
    assert client.get(assignment_path + '/actual-inputs').json()['items'][0]['author_name'] == 'Synthetic assistant'
    observation_path = prefix + f'/teaching/observations/{observation["id"]}'
    login(client, 'guardian')
    assert client.get(observation_path).status_code == 403
    assert client.get(assignment_path + '/actual-inputs').status_code == 403
    login(client)
    assert client.get(observation_path + '/revisions').json()['items'][0]['author_name'] == 'Synthetic assistant'
    assert client.get(assignment_path + '/actual-inputs').json()['items'][0]['author_name'] == 'Synthetic assistant'
    login(client, 'assistant')
    with factory.begin() as db:
        from spesped.contexts.teaching.models import BriefAssignment
        db.get(BriefAssignment, assigned['id']).state = 'revoked'
    assert client.get(observation_path).status_code == 403
    assert client.get(assignment_path + '/actual-inputs').status_code == 403
