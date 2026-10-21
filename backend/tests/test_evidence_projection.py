"""Evidence's metadata port must invalidate existing curated projections."""
import json
from uuid import uuid4

from spesped.contexts.evidence.projections import confirmed_binding_is_current
from test_evidence import env, login, note, confirm_first, base, attribution


def current(factory, ids, item, **changes):
    arguments = {
        'school_id': ids['school'], 'learner_id': item['learner_id'],
        'evidence_id': item['id'], 'evidence_revision': item['revision'],
        'link_id': item['source']['link_id'], **changes,
    }
    with factory() as db:
        result = confirmed_binding_is_current(db, **arguments)
    assert type(result) is bool
    return result


def test_binding_checks_all_subject_and_revision_coordinates(env):
    client, factory, _, ids = env
    headers = login(client)
    source, _ = note(client, ids, headers)
    item = confirm_first(client, ids, headers, source)
    sibling = confirm_first(client, ids, headers, source, 'b', 1)
    assert current(factory, ids, item)
    for change in (
        {'school_id': str(uuid4())}, {'learner_id': ids['b']},
        {'evidence_id': sibling['id']}, {'evidence_id': str(uuid4())},
        {'link_id': sibling['source']['link_id']}, {'link_id': str(uuid4())},
        {'evidence_revision': 2}, {'evidence_revision': 0},
        {'evidence_revision': True}, {'evidence_id': 'invalid'},
    ):
        assert not current(factory, ids, item, **change)


def test_correction_dispute_and_reassignment_invalidate_projection(env):
    client, factory, _, ids = env
    headers = login(client)
    source, _ = note(client, ids, headers, 'Synthetic source for scoped projection')
    item = confirm_first(client, ids, headers, source)
    disputed = client.post(base(ids) + f'/evidence/{item["id"]}/corrections', headers=headers, json={
        **attribution(ids), 'expected_version': item['version'],
        'content': 'Synthetic uncertain interpretation', 'certainty': 'disputed',
        'reason': 'Synthetic source disputed by the responsible reviewer',
    })
    assert disputed.status_code == 200, disputed.text
    disputed = disputed.json()
    assert not current(factory, ids, item)
    assert not current(factory, ids, disputed)
    reassigned = client.post(base(ids) + f'/evidence/{item["id"]}/corrections', headers=headers, json={
        **attribution(ids, 'b'), 'expected_version': disputed['version'],
        'content': 'Synthetic corrected pupil attribution',
        'reason': 'Synthetic reviewer confirms the correct pupil',
        'excerpt_page': 1, 'excerpt_start': 0,
        'excerpt_end': len('Synthetic source for scoped projection'),
    })
    assert reassigned.status_code == 200, reassigned.text
    reassigned = reassigned.json()
    assert not current(factory, ids, item)
    assert current(factory, ids, reassigned)
    assert not current(factory, ids, reassigned, learner_id=ids['a'])


def test_new_original_revision_invalidates_unchanged_confirmed_evidence(env):
    client, factory, _, ids = env
    headers = login(client)
    source, payload = note(client, ids, headers, 'Synthetic original source')
    item = confirm_first(client, ids, headers, source)
    assert current(factory, ids, item)
    source = client.get(base(ids) + f'/intake/{source["id"]}').json()
    metadata = {k: v for k, v in payload.items() if k != 'text'}
    metadata['request_key'] = str(uuid4())
    revised = client.post(base(ids) + f'/intake/{source["id"]}/revisions',
        content=b'Synthetic corrected original', headers={
            **headers, 'X-Expected-Version': str(source['version']),
            'X-Evidence-Filename': 'source.txt',
            'X-Evidence-Metadata': json.dumps(metadata),
        })
    assert revised.status_code == 201, revised.text
    assert revised.json()['current_revision'] == 2
    assert not current(factory, ids, item)
