"""Recover committed jobs after reload without regenerating or exposing output.

Real authenticated owning workflows, real source resolution and synthetic local
model responses. The fixtures execute each case on SQLite and PostgreSQL.
"""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from plan_generation_fixtures import (
    env, generated_env, plan_wire, post, generate, proposal, selection, manual,
)
from plans_fixtures import base, login, retry, expected
from teaching_fixtures import (
    teaching_env, teaching_wire_server, configure_ai, ordinary_goal, basis, session,
)
from spesped.contexts.platform.models import GenerationJob, ModelRelease
from spesped.contexts.identity.models import AuthorityGrant
from spesped.contexts.plans.models import ProfileStatement


def listing(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    result = response.json()
    for item in result['items']:
        assert set(item) == {'id', 'version', 'state', 'attempts', 'created_at',
            'updated_at', 'basis_id', 'availability', 'review_outcome'}
    return result


def test_plan_request_response_lost_recovered_and_reviewed_once(generated_env):
    e = generated_env
    path = base(e.ids) + f'/education-plans/{e.plan["id"]}/suggestions'
    command = retry(basis_id=e.basis['id'], policy_id=e.policy, release_id=e.release)
    created = post(e.client, path, e.h, command)
    # A new authenticated session has no component state or remembered job ID.
    e.client.cookies.clear()
    h = login(e.client)
    recovered = listing(e.client, path)
    assert recovered['total'] == 1 and recovered['scope'] == 'current_plan_revision'
    item, = recovered['items']
    assert item['id'] == created['id'] and item['basis_id'] == e.basis['id']
    assert item['state'] == 'queued' and item['availability'] == 'current'
    assert post(e.client, path, h, command)['id'] == item['id']
    job = post(e.client, base(e.ids) + f'/ai/jobs/{item["id"]}/run', h,
               {'expected_version': item['version']}, 200)
    diff = proposal(e, job)
    post(e.client, path.replace('/suggestions', '/suggestion-reviews'), h,
         selection(e, diff, outcome='rejected', selected_fields=[], selected_goal_keys=[]), 200)
    recovered = listing(e.client, path)
    assert recovered['items'][0]['state'] == 'succeeded'
    assert recovered['items'][0]['review_outcome'] == 'rejected'
    assert recovered['total'] == 1


def test_plan_current_revision_scope_and_source_or_model_recall(generated_env):
    e = generated_env
    job = generate(e)
    path = base(e.ids) + f'/education-plans/{e.plan["id"]}'
    with e.factory.begin() as db:
        db.get(ModelRelease, e.release).state = 'revoked'
    item, = listing(e.client, path + '/suggestions')['items']
    assert item['id'] == job['id'] and item['state'] == 'succeeded'
    assert item['availability'] == 'review_required'
    assert e.client.get(base(e.ids) + f'/ai/jobs/{job["id"]}').status_code == 503
    with e.factory.begin() as db:
        db.get(ModelRelease, e.release).state = 'reviewed'
        db.get(ProfileStatement, e.statement['id']).state = 'rejected'
    assert listing(e.client, path + '/suggestions')['items'][0]['availability'] == 'review_required'
    # An independent manual revision cannot accidentally recover a proposal for
    # the old revision, even when the pupil and plan identifiers are unchanged.
    post(e.client, path + '/revisions', e.h,
         manual(e, e.plan, title='Synthetic independent manual revision'))
    assert listing(e.client, path + '/suggestions')['total'] == 0


@pytest.mark.parametrize('role', ['assistant', 'guardian', 'tech', 'teacher'])
def test_plan_recovery_does_not_grant_owner_or_ai_access(generated_env, role):
    e = generated_env
    generate(e)
    path = base(e.ids) + f'/education-plans/{e.plan["id"]}/suggestions'
    login(e.client, role)
    assert e.client.get(path).status_code == 403
    assert e.client.get(path.replace(e.ids['school'], e.ids['other_school'])).status_code == 403
    login(e.client)
    with e.factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(
                AuthorityGrant.user_id == e.ids['reviewer'], AuthorityGrant.action == 'ai.iep_drafting')):
            grant.state = 'revoked'
    assert e.client.get(path).status_code == 403


def test_recovery_pages_past_100_without_selecting_output_or_invoking_model(generated_env):
    e = generated_env
    job = generate(e)
    path = base(e.ids) + f'/education-plans/{e.plan["id"]}/suggestions'
    with e.factory.begin() as db:
        original = db.get(GenerationJob, job['id'])
        values = {c.name: deepcopy(getattr(original, c.name)) for c in GenerationJob.__table__.columns
                  if c.name not in {'id', 'logical_request_key'}}
        for _ in range(102):
            db.add(GenerationJob(**values, id=str(uuid4()), logical_request_key=str(uuid4())))
        # Wrong exact reference must never join the current owner's job list.
        wrong = deepcopy(values)
        wrong['source_manifest'][0]['reference']['source_id'] = str(uuid4())
        db.add(GenerationJob(**wrong, id=str(uuid4()), logical_request_key=str(uuid4())))
    requests_before = len(e.wire.requests)
    queries = []
    engine = e.factory.kw['bind']
    def capture(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT') and 'platform_generation_jobs' in statement:
            queries.append(statement)
            assert 'platform_generation_jobs.output' not in statement
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        pages = [listing(e.client, path, offset=offset, limit=50) for offset in (0, 50, 100, 103)]
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert [len(p['items']) for p in pages] == [50, 50, 3, 0]
    assert all(p['total'] == 103 for p in pages)
    assert len({item['id'] for p in pages for item in p['items']}) == 103
    assert queries and len(e.wire.requests) == requests_before


def test_teaching_recovery_is_exact_basis_and_review_is_session_scoped(teaching_env, teaching_wire_server):
    client, factory, app, ids = teaching_env
    runtime, policy, release = configure_ai(factory, app, ids, teaching_wire_server)
    h = login(client)
    goal, _ = ordinary_goal(client, ids, h)
    selected = basis(client, ids, h, {'a': goal})
    row = session(client, ids, h, selected)
    other = session(client, ids, h, selected)
    different = session(client, ids, h, basis(client, ids, h, {'a': goal}))
    path = base(ids) + f'/teaching/sessions/{row["id"]}/suggestions'
    created = post(client, path, h, retry(policy_id=policy, release_id=release))
    client.cookies.clear()
    h = login(client)
    recovered = listing(client, path)
    item, = recovered['items']
    assert recovered['scope'] == 'current_basis' and item['id'] == created['id']
    assert listing(client, path.replace(row['id'], other['id']))['total'] == 1
    assert listing(client, path.replace(row['id'], different['id']))['total'] == 0
    job = post(client, base(ids) + f'/ai/jobs/{item["id"]}/run', h,
               {'expected_version': item['version']}, 200)
    post(client, path + '/review', h, expected(row, job_id=job['id'], outcome='rejected',
        selected_fields=[], reason='Synthetic review after reload'), 200)
    assert listing(client, path)['items'][0]['review_outcome'] == 'rejected'
    assert listing(client, path.replace(row['id'], other['id']))['items'][0]['review_outcome'] is None
    app.state.ai_gateway = replace(runtime, providers={})
    unavailable = listing(client, path)['items'][0]
    assert unavailable['state'] == 'succeeded' and unavailable['availability'] == 'review_required'
    login(client, 'assistant')
    assert client.get(path).status_code == 403


def test_teaching_queued_job_tracks_configuration_recall_and_resumes_same_job(teaching_env, teaching_wire_server):
    client, factory, app, ids = teaching_env
    _, policy, release = configure_ai(factory, app, ids, teaching_wire_server)
    h = login(client)
    goal, _ = ordinary_goal(client, ids, h)
    row = session(client, ids, h, basis(client, ids, h, {'a': goal}))
    path = base(ids) + f'/teaching/sessions/{row["id"]}/suggestions'
    job = post(client, path, h, retry(policy_id=policy, release_id=release))
    with factory.begin() as db:
        db.get(ModelRelease, release).state = 'revoked'
    item, = listing(client, path)['items']
    assert item['id'] == job['id'] and item['state'] == 'queued'
    assert item['availability'] == 'review_required'
    with factory.begin() as db:
        db.get(ModelRelease, release).state = 'reviewed'
    current = listing(client, path)['items'][0]
    assert current['availability'] == 'current'
    resumed = post(client, base(ids) + f'/ai/jobs/{current["id"]}/run', h,
                   {'expected_version': current['version']}, 200)
    assert resumed['id'] == job['id'] and resumed['state'] == 'succeeded'
    assert listing(client, path)['total'] == 1
