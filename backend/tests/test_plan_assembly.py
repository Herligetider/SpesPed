"""Source -> real plan -> goal-bound evidence using application-installed ports."""
from fastapi.testclient import TestClient

from spesped.db import utcnow
from spesped.main import create_app
from plans_fixtures import env, login, base, retry, evidence, plan_payload, activate


def test_real_application_validates_goal_binding_without_fixture_callbacks(env, tmp_path):
    _, factory, prior, ids = env
    app = create_app(prior.state.settings.model_copy(update={'evidence_storage_root': tmp_path / 'assembled-source'}), factory)
    with TestClient(app) as client:
        headers = login(client)
        binding, _ = evidence(client, ids, headers)
        response = client.post(base(ids) + f'/learners/{ids["a"]}/education-plans', headers=headers, json=plan_payload(binding))
        assert response.status_code == 201, response.text
        plan = activate(client, ids, headers, response.json())
        goal = plan['content']['goals'][0]
        note = client.post(base(ids) + '/intake/notes', headers=headers, json=retry(
            external_scope='manual', external_id='assembled-observation', sender='Synthetic teacher',
            document_type='observation', received_at=utcnow().isoformat(), text='Synthetic learner used the visual card.'))
        assert note.status_code == 201, note.text
        fields = client.get(base(ids) + '/intake/' + note.json()['id'] + '/proposals').json()['items']
        field = fields[0]
        reviewed = client.post(base(ids) + '/extraction-proposals/' + field['id'] + '/review', headers=headers, json={
            'expected_version': field['version'], 'outcome': 'accepted', 'reason': 'Checked against direct synthetic observation',
        })
        assert reviewed.status_code == 200, reviewed.text
        command = {'expected_version': reviewed.json()['version'], 'learner_id': ids['a'],
            'claim_type': 'observation', 'reporter': 'Synthetic teacher', 'source_type': 'direct_observation',
            'observer': 'Synthetic teacher',
            'certainty': 'confirmed', 'occurred_at': utcnow().isoformat(), 'topic': 'reading',
            'excerpt_page': field['page'], 'excerpt_start': field['span_start'], 'excerpt_end': field['span_end'],
            'goal_revision_id': goal['id']}
        endpoint = base(ids) + '/extraction-proposals/' + field['id'] + '/confirm'
        wrong = client.post(endpoint, headers=headers, json=command | {'learner_id': ids['b']})
        assert wrong.status_code == 403, wrong.text
        confirmed = client.post(endpoint, headers=headers, json=command)
        assert confirmed.status_code == 201, confirmed.text
        assert confirmed.json()['goal_revision_id'] == goal['id']
