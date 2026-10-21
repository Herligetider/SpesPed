"""Native source maintenance contracts consumed by the intake workspace."""
import json
from uuid import uuid4

from plans_fixtures import env, login, base, retry
from test_evidence import SyntheticTestScanner
from spesped.db import utcnow


def test_exact_identity_revision_retry_preserves_original_and_rejects_stale_write(env):
    client, factory, app, ids = env
    app.state.evidence_scanner = SyntheticTestScanner()
    h = login(client)
    metadata = retry(external_scope='synthetic_import', external_id=str(uuid4()),
                     sender='Synthetic sender', document_type='education_document',
                     received_at=utcnow().isoformat(), original_at=None)
    headers = {**h, 'X-Evidence-Filename': 'original.txt', 'X-Evidence-Metadata': json.dumps(metadata)}
    response = client.post(base(ids)+'/intake/files', headers=headers, content=b'Synthetic original')
    assert response.status_code == 201, response.text
    old = response.json()
    current = client.get(base(ids)+f'/intake/{old["id"]}').json()
    assert current['external_scope'] == metadata['external_scope']
    assert current['external_id'] == metadata['external_id']
    new_metadata = {**metadata, 'request_key': str(uuid4()), 'sender': 'Synthetic revised sender'}
    headers.update({'X-Expected-Version': str(current['version']), 'X-Evidence-Filename': 'revised.txt', 'X-Evidence-Metadata': json.dumps(new_metadata)})
    url = base(ids)+f'/intake/{old["id"]}/revisions'
    response = client.post(url, headers=headers, content=b'Synthetic revised original')
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['id'] == old['id'] and saved['revision'] == 2
    assert saved['external_id'] == old['external_id'] and saved['digest'] != old['digest']
    replay = client.post(url, headers=headers, content=b'Synthetic revised original')
    assert replay.status_code == 201 and replay.json()['revision'] == 2
    assert client.get(base(ids)+f'/intake/{old["id"]}/revisions/1/original').content == b'Synthetic original'
    assert client.get(base(ids)+f'/intake/{old["id"]}/revisions/2/original').content == b'Synthetic revised original'
    headers['X-Evidence-Metadata'] = json.dumps({**new_metadata, 'request_key': str(uuid4())})
    assert client.post(url, headers=headers, content=b'Synthetic conflicting original').status_code == 409
    assert client.get(base(ids)+f'/intake/{old["id"]}').json()['current_revision'] == 2
    login(client, 'teacher')
    assert client.get(base(ids)+f'/intake/{old["id"]}').status_code == 403


def test_inspection_retry_uses_expected_version_and_keeps_same_original(env):
    client, factory, app, ids = env
    app.state.evidence_scanner = None
    h = login(client)
    metadata = retry(external_scope='synthetic_import', external_id=str(uuid4()),
                     sender='Synthetic sender', document_type='education_document', received_at=utcnow().isoformat())
    response = client.post(base(ids)+'/intake/files', headers={**h, 'X-Evidence-Filename': 'source.txt', 'X-Evidence-Metadata': json.dumps(metadata)}, content=b'Synthetic delayed scan')
    assert response.status_code == 201, response.text
    old = response.json(); assert old['state'] == 'quarantined'
    url = base(ids)+f'/intake/{old["id"]}/inspect'
    app.state.evidence_scanner = SyntheticTestScanner()
    response = client.post(url, headers=h, json={'expected_version': old['version']})
    assert response.status_code == 200, response.text
    new = response.json()
    assert new['extraction_state'] == 'ready' and new['scan_state'] == 'clean'
    assert new['current_revision'] == old['current_revision'] and new['digest'] == old['digest']
    assert new['version'] > old['version']
    # A retry after a lost success cannot cause a second scan/write.
    assert client.post(url, headers=h, json={'expected_version': old['version']}).status_code == 409
    current = client.get(base(ids)+f'/intake/{old["id"]}').json()
    assert current['version'] == new['version'] and current['page_count'] == 1
