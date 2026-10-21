"""A selected profile is independent of its position in a paginated list."""
from datetime import timedelta
import pytest

from plans_fixtures import env, login, base, retry, expected, evidence
from teaching_fixtures import teaching_env, ordinary_goal, session, approve, assigned_brief
from plan_generation_fixtures import post
from spesped.contexts.plans.models import ProfileStatement
from spesped.db import utcnow


@pytest.mark.parametrize('earlier_count', [0, 100])
def test_profile_beyond_first_page_remains_usable_and_reauthorizes(teaching_env, earlier_count):
    client, factory, app, ids = teaching_env
    h = login(client)
    binding, _ = evidence(client, ids, h)
    path = base(ids) + f'/learners/{ids["a"]}/support-profile'
    selected = post(client, path + '/statements', h, retry(category='strength',
        content='Synthetic exact selected statement', source=binding, observed_at=utcnow().isoformat()))
    selected = post(client, path + f'/statements/{selected["id"]}/review', h,
        expected(selected, outcome='confirmed', reason='Synthetic confirmed source'), 200)
    with factory.begin() as db:
        original = db.get(ProfileStatement, selected['id'])
        for index in range(earlier_count):
            db.add(ProfileStatement(school_id=ids['school'], profile_id=original.profile_id,
                category='interest', content=f'Synthetic earlier statement {index}', source=binding,
                observed_at=original.observed_at, proposed_by=ids['reviewer'], confirmed_by=ids['reviewer'],
                reviewed_at=utcnow(), state='confirmed', created_at=original.created_at-timedelta(seconds=index+1)))
    first = client.get(path, params={'limit':100}).json()
    assert first['total'] == earlier_count + 1
    assert (selected['id'] in {p['id'] for p in first['items']}) == (earlier_count == 0)
    goal, _ = ordinary_goal(client, ids, h)
    chosen = {'learner_id':ids['a'], 'goal_revision_ids':[goal], 'profile_statement_ids':[selected['id']]}
    payload = retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(), duration_minutes=30,
        arena='Synthetic classroom', learners=[chosen])
    teaching_basis = post(client, base(ids) + '/teaching/bases', h, payload)
    assert teaching_basis['source_status'] == 'current'
    assert teaching_basis['basis']['learners'][0]['profile'][0]['id'] == selected['id']
    row = approve(client, ids, h, session(client, ids, h, teaching_basis))
    _, assigned = assigned_brief(client, ids, h, row)
    session_path = base(ids) + f'/teaching/sessions/{row["id"]}'
    assert client.get(session_path).json()['content'] is not None
    with factory.begin() as db:
        db.get(ProfileStatement, selected['id']).state = 'disputed'
    assert client.get(session_path).json()['content'] is None
    login(client, 'assistant')
    response = client.get(base(ids) + f'/teaching/brief-assignments/{assigned["id"]}')
    assert response.status_code == 200 and response.json()['content'] is None
