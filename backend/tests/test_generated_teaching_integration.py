"""A generated IEP remains a live dependency throughout the real teaching API."""
from dataclasses import replace
from datetime import timedelta

import pytest

from spesped.config import Settings
from spesped.db import utcnow
from spesped.main import create_app
from plan_generation_fixtures import generated_env, plan_wire, env, generate, proposal, selection, post
from plans_fixtures import activate, base, expected, login, retry
from teaching_fixtures import teaching_env, teaching_wire_server, configure_ai, basis, session, approve, assigned_brief, actual


def test_default_application_registers_teaching_without_fixture_route_injection():
    paths = create_app(Settings(environment='test')).openapi()['paths']
    for suffix in ('/teaching/bases', '/teaching/sessions', '/teaching/briefs',
                   '/teaching/deliveries', '/teaching/observations'):
        assert sum(path.endswith(suffix) for path in paths) == 1


@pytest.mark.parametrize('recall', ['iep_model', 'expert_source'])
def test_generated_goal_to_session_brief_actual_note_and_transitive_recall(
        generated_env, teaching_env, teaching_wire_server, recall):
    e = generated_env
    assert teaching_env[1] is e.factory
    teaching_runtime, teaching_policy, teaching_release = configure_ai(
        e.factory, e.app, e.ids, teaching_wire_server)
    e.app.state.ai_gateway = replace(e.runtime,
        providers=e.runtime.providers | teaching_runtime.providers,
        evaluation_suites=e.runtime.evaluation_suites | teaching_runtime.evaluation_suites)
    prefix = base(e.ids)
    plan_path = prefix + f'/education-plans/{e.plan["id"]}'
    selected = selection(e, proposal(e, generate(e)))
    selected.update(selected_fields=[], selected_goal_keys=['reading'])
    plan = post(e.client, plan_path + '/suggestion-reviews', e.h, selected, 200)
    assert plan['revision_state'] == 'draft' and plan['active_revision_id'] is None
    plan = activate(e.client, e.ids, e.h, plan)
    goal = plan['content']['goals'][0]['id']
    assert plan['content']['goals'][0]['expected_action'] == 'Practise reading a short sentence with a visual cue'

    teaching_basis = basis(e.client, e.ids, e.h, {'a': goal})
    row = session(e.client, e.ids, e.h, teaching_basis, support='Human selected support')
    session_path = prefix + f'/teaching/sessions/{row["id"]}'
    job = post(e.client, session_path + '/suggestions', e.h,
               retry(policy_id=teaching_policy, release_id=teaching_release))
    job = post(e.client, prefix + f'/ai/jobs/{job["id"]}/run', e.h,
               {'expected_version': job['version']}, 200)
    assert job['state'] == 'succeeded', job
    row = post(e.client, session_path + '/suggestions/review', e.h,
               expected(row, job_id=job['id'], outcome='accepted', selected_fields=['preparation'],
                        reason='Use proposed preparation and keep the human support choice'), 200)
    assert row['content']['support'] == 'Human selected support'
    assert row['delivery_state'] == 'not_recorded'
    row = approve(e.client, e.ids, e.h, row)
    guide, assignment = assigned_brief(e.client, e.ids, e.h, row)
    assignment_path = prefix + f'/teaching/brief-assignments/{assignment["id"]}'
    assistant_headers = login(e.client, 'assistant')
    assigned = e.client.get(assignment_path)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['content'] and not assigned.json()['opened_is_completion']
    assert e.client.get(plan_path).status_code == 403

    note = post(e.client, prefix + '/teaching/observations', assistant_headers, retry(content={
        'learner_id': e.ids['a'], 'occurred_at': (utcnow() - timedelta(minutes=20)).isoformat(),
        'assignment_id': assignment['id'], 'session_revision_id': row['revision_id'],
        'goal_revision_id': goal, 'observation': 'Read one short sentence using two visual cues',
        'support': 'Two visual cues', 'interpretation': 'Further observation is needed',
        'next_step': 'Repeat with another sentence'}))
    e.h = login(e.client)
    allocation = plan['content']['allocations'][0]
    delivery = actual(e.ids, {'a': goal}, row, status='partial', cause='other',
        cause_detail='Reviewed staffing qualification source is unavailable in this integration',
        follow_up_owner_id=e.ids['reviewer'], follow_up='Review the actual staffing basis')
    delivery['participants'][0].update(category='individually_adapted_education',
        support_status='unassessed', counting_basis=allocation['counting_basis'],
        provision={k: allocation[k] for k in ('decision_id', 'decision_revision_id', 'provision_id')})
    delivery['staff'][0]['category'] = 'individually_adapted_education'
    delivered = post(e.client, prefix + '/teaching/deliveries', e.h, retry(content=delivery))
    assert delivered['staff_minutes'] == 30
    assert delivered['participants'][0]['support_assessment'] == 'unassessed'
    summary = e.client.get(prefix + f'/learners/{e.ids["a"]}/teaching-summary', params={
        'start': (utcnow() - timedelta(days=1)).isoformat(), 'end': utcnow().isoformat()})
    assert summary.status_code == 200, summary.text
    assert summary.json()['entitlement_fulfilment'] == 'unassessed'
    assert summary.json()['actual_minutes_by_category']['individually_adapted_education'] == 30
    assert not summary.json()['assessed_minutes_by_category'].get('individually_adapted_education')
    assert summary.json()['unassessed_claimed_minutes_by_category']['individually_adapted_education'] == 30
    next_basis = post(e.client, prefix + '/teaching/bases', e.h, retry(
        planned_at=(utcnow() + timedelta(days=1)).isoformat(), duration_minutes=30,
        arena='Synthetic classroom', learners=[{'learner_id': e.ids['a'],
            'goal_revision_ids': [goal], 'observation_revision_ids': [note['revision_id']]}]))
    next_row = session(e.client, e.ids, e.h, next_basis)
    assert next_row['delivery_state'] == 'not_recorded'

    if recall == 'iep_model':
        config = e.client.get(prefix + '/ai/configuration').json()
        release = next(r for r in config['releases']['items'] if r['id'] == e.release)
        post(e.client, prefix + f'/ai/configuration/release/{e.release}/revoke', e.h,
             {'expected_version': release['version']}, 200)
    else:
        item = e.expert_item
        post(e.client, prefix + f'/evidence/{item["id"]}/corrections', e.h, {
            'expected_version': item['version'], 'learner_id': e.ids['b'],
            'claim_type': 'report', 'reporter': 'Synthetic authority',
            'source_type': 'imported_document', 'certainty': 'confirmed',
            'occurred_at': item['occurred_at'], 'topic': 'education',
            'content': 'The expert source concerned another synthetic learner',
            'reason': 'Correcting the learner association', 'excerpt_page': item['source']['page'],
            'excerpt_start': item['source']['span_start'], 'excerpt_end': item['source']['span_end']}, 200)
    current = e.client.get(session_path)
    assert current.status_code == 200, current.text
    assert current.json()['content'] is None and current.json()['state'] == 'review_required'
    next_current = e.client.get(prefix + f'/teaching/sessions/{next_row["id"]}')
    assert next_current.status_code == 200, next_current.text
    assert next_current.json()['content'] is None
    login(e.client, 'assistant')
    recalled = e.client.get(assignment_path)
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()['content'] is None
