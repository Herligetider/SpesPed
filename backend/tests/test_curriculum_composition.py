"""Actual app registration and honest unavailable adapters, without test injection."""
from datetime import date, timedelta

from teaching_fixtures import teaching_env, env
from plans_fixtures import login, retry, expected
from curriculum_fixtures import path, scheme, plan_content, class_plan, publish
from spesped.contexts.identity.models import AuthorityGrant
from spesped.db import utcnow
from spesped.config import Settings
from spesped.main import create_app


def test_actual_app_curriculum_sources_and_unavailable_dependency_boundaries(teaching_env):
    client, factory, app, ids = teaching_env
    paths = create_app(Settings(environment='test')).openapi()['paths']
    assert 'get' in paths['/api/v1/schools/{school_id}/curriculum/schemes']
    assert getattr(app.state, 'curriculum_source_port', None) is None
    assert getattr(app.state, 'curriculum_future_session_port', None) is None
    assert getattr(app.state, 'curriculum_material_reservation_port', None) is None
    with factory.begin() as db:
        for action in ('curriculum.read', 'curriculum.manage', 'curriculum.publish',
                       'curriculum.source.read', 'materials.read', 'materials.manage'):
            db.add(AuthorityGrant(school_id=ids['school'], user_id=ids['reviewer'], action=action,
                valid_from=date.today()-timedelta(days=1), granted_by=ids['leader']))
    h = login(client)
    reviewed, _ = scheme(client, ids, h, 'montessori')
    original_content = plan_content(reviewed)
    published = publish(client, ids, h, class_plan(client, ids, h, original_content))
    plan_path = path(ids) + f'/class-plans/{published["id"]}'
    response = client.post(plan_path + '/revisions', headers=h, json=expected(published,
        content=original_content | {'title': 'Synthetic revised class theme'}))
    assert response.status_code == 201, response.text
    draft = response.json()
    response = client.post(plan_path + '/publish', headers=h, json=expected(draft,
        revision_id=draft['content']['id'], content_digest=draft['content']['content_digest'],
        periods_checked=True, references_checked=True, reason='Synthetic reviewed replacement'))
    assert response.status_code == 503, response.text
    assert response.json()['error']['code'] == 'session_impact_unavailable'
    # The app must not report that future teaching was checked by an absent port.
    current = client.get(plan_path).json()
    assert current['version'] == draft['version'] and current['content']['state'] == 'draft'
    history = client.get(plan_path + '/revisions').json()['items']
    assert next(row for row in history if row['id'] == published['content']['id'])['state'] == 'published'
    response = client.post(path(ids) + '/materials', headers=h, json=retry(content={
        'title': 'Synthetic tray', 'material_type': 'beads', 'location': 'Synthetic shelf',
        'count': 2, 'inventory_checked_on': date.today().isoformat(), 'presentation_revision_ids': []}))
    assert response.status_code == 201, response.text
    material = response.json()
    availability = client.post(path(ids) + '/material-availability', headers=h, json={
        'school_id': ids['school'], 'material_id': material['id'], 'material_version': material['version'],
        'count': 1, 'starts_at': utcnow().isoformat(), 'ends_at': (utcnow()+timedelta(hours=1)).isoformat()})
    assert availability.status_code == 200, availability.text
    assert availability.json()['state'] == 'unavailable'
