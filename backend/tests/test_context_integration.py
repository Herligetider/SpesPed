"""Exercise assembled contexts through authenticated HTTP and real local wire calls."""
from datetime import date
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select

from spesped.assembly import EvidenceSourceResolver, SyntheticAttestation, configure_contexts, content_digest, governance_evidence_validator, load_evaluation_suites
from spesped.auth import Actor
from spesped.config import AIProviderSettings, Settings
from spesped.contexts.identity.models import AuthorityGrant, StaffAssignment
from spesped.contexts.platform.contracts import SourceRef
from spesped.errors import DomainError
from spesped.main import create_app

from test_ai_gateway import wire_server
from test_evidence import env, login, note, confirm_first, base, attribution


@pytest.fixture
def integrated(env, wire_server, tmp_path):
    client, factory, app, ids = env
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    cfg.attributes['database_url'] = factory.kw['bind'].url.render_as_string(hide_password=False)
    command.upgrade(cfg, 'head')
    suite = tmp_path / 'synthetic-suite.json'
    suite.write_text(json.dumps({'version': 1, 'suites': {'integration-v1': [{
        'name': 'synthetic-norwegian-observation', 'purpose': 'teaching_suggestion',
        'text': 'Syntetisk elev leste tre ord med støtte.',
        'required_substrings': ['Syntetisk øktforslag'], 'forbidden_substrings': ['AUTOMATICALLY_SENT'],
    }]}}))
    settings = Settings(environment='test', allowed_origins=['http://testserver'],
                        ai_providers=[AIProviderSettings(key='local', endpoint=wire_server.endpoint, capabilities={'generation'})],
                        ai_evaluation_suites=suite, evidence_storage_root=tmp_path / 'assembled-private')
    configure_contexts(app, settings)
    with factory.begin() as db:
        db.add(AuthorityGrant(school_id=ids['school'], user_id=ids['reviewer'], action='platform.manage', valid_from=date.today(), granted_by=ids['leader']))
        for name, pupil in [('reviewer', 'a'), ('teacher', 'a'), ('sibling', 'b')]:
            db.add(StaffAssignment(school_id=ids['school'], user_id=ids[name], learner_id=ids[pupil],
                                   actions=['learner.read', 'ai.teaching_suggestion'], purpose='teaching_suggestion', valid_from=date.today()))
    yield client, factory, app, ids, wire_server


def post(client, url, body, headers, status=201):
    response = client.post(url, json=body, headers=headers)
    assert response.status_code == status, response.text
    return response.json()


def reviewed_generation(client, ids, headers):
    prefix = base(ids) + '/ai'
    policy = post(client, prefix + '/policies', {'provider_key': 'local', 'purposes': ['teaching_suggestion']}, headers)
    release = post(client, prefix + '/releases', {'provider_key': 'local', 'model_version': 'synthetic-local-v1', 'capability': 'generation'}, headers)
    evaluation = post(client, prefix + f'/releases/{release["id"]}/evaluations', {
        'expected_version': release['version'], 'policy_id': policy['id'], 'suite_name': 'integration-v1',
    }, headers)
    assert evaluation['state'] == 'passed'
    release = post(client, prefix + f'/releases/{release["id"]}/review', {
        'expected_version': release['version'], 'evaluation_id': evaluation['id'],
        'professional_quality_confirmed': True, 'rationale': 'Synthetic fixture output checked by the test operator.',
    }, headers, 200)
    return policy, release


def test_confirmed_excerpt_to_reviewed_generation_and_correction(integrated):
    client, factory, app, ids, server = integrated
    headers = login(client)
    source, _ = note(client, ids, headers)
    item = confirm_first(client, ids, headers, source)
    policy, release = reviewed_generation(client, ids, headers)
    request = {'learner_id': ids['a'], 'purpose': 'teaching_suggestion', 'policy_id': policy['id'],
               'release_id': release['id'], 'logical_request_key': str(uuid4()),
               'sources': [{'kind': 'evidence', 'source_id': item['id'], 'revision': item['revision']}]}
    job = post(client, base(ids) + '/ai/jobs', request, headers)
    result = post(client, base(ids) + f'/ai/jobs/{job["id"]}/run', {'expected_version': job['version']}, headers, 200)
    assert result['state'] == 'succeeded' and result['output']['unconfirmed']
    sent = server.requests[-1]['body'].decode()
    assert 'Synthetic pupil A reads fluently' in sent
    assert 'Synthetic sibling B' not in sent
    assert 'reported_information' in sent and 'Synthetic parent' in sent
    assert 'confirmed' in sent and 'occurred_at' in sent
    assert result['source_manifest'][0]['provenance'] == 'school_data'
    login(client, 'sibling')
    assert client.get(base(ids) + f'/ai/jobs/{job["id"]}').status_code == 403
    headers = login(client)
    with factory() as db:
        old = governance_evidence_validator(db, Actor(ids['reviewer']), ids['school'], ids['a'], None, item['id'])
        with pytest.raises(DomainError):
            governance_evidence_validator(db, Actor(ids['reviewer']), ids['school'], ids['b'], None, item['id'])
        with pytest.raises(DomainError, match='Protected case'):
            governance_evidence_validator(db, Actor(ids['reviewer']), ids['school'], ids['a'], str(uuid4()), item['id'])
    post(client, base(ids) + f'/evidence/{item["id"]}/corrections', {
        **attribution(ids), 'expected_version': item['version'], 'content': 'Synthetic pupil needed reading support.',
        'reason': 'Correcting a synthetic observation.',
    }, headers, 200)
    response = client.get(base(ids) + f'/ai/jobs/{job["id"]}')
    assert response.status_code == 409, response.text
    assert 'output' not in response.json()
    with factory() as db:
        new = governance_evidence_validator(db, Actor(ids['reviewer']), ids['school'], ids['a'], None, item['id'])
        assert old.revision != new.revision and old.digest != new.digest


def test_original_source_cannot_be_used_as_teaching_evidence(integrated):
    client, _, _, ids, server = integrated
    headers = login(client)
    source, _ = note(client, ids, headers)
    confirm_first(client, ids, headers, source)
    policy, release = reviewed_generation(client, ids, headers)
    before = len(server.requests)
    for kind in ['evidence', 'intake']:
        response = client.post(base(ids) + '/ai/jobs', headers=headers, json={
            'learner_id': ids['a'], 'purpose': 'teaching_suggestion', 'policy_id': policy['id'], 'release_id': release['id'],
            'logical_request_key': str(uuid4()), 'sources': [{'kind': kind, 'source_id': source['id'], 'revision': 1}],
        })
        assert response.status_code == 403, response.text
    assert len(server.requests) == before


def test_trusted_fixture_attestation_is_exact_and_not_an_upload_flag(integrated):
    client, factory, app, ids, _ = integrated
    headers = login(client)
    source, _ = note(client, ids, headers)
    item = confirm_first(client, ids, headers, source)
    ref = SourceRef(source_id=item['id'], revision=item['revision'])
    actor = Actor(ids['reviewer'])
    with factory() as db:
        original = app.state.ai_gateway.source_resolver.resolve(db, actor, ids['school'], ids['a'], 'teaching_suggestion', [ref])[0]
        attestation = SyntheticAttestation(fixture_name='trusted-integration-fixture', school_id=ids['school'], learner_id=ids['a'],
            reference=ref, purposes=['teaching_suggestion'], content_digest=content_digest(original.content))
        trusted = EvidenceSourceResolver(attestations=[attestation])
        resolved = trusted.resolve(db, actor, ids['school'], ids['a'], 'teaching_suggestion', [ref])[0]
        assert resolved.provenance == 'synthetic_fixture'
        assert trusted.resolve(db, actor, ids['school'], ids['a'], 'document_draft', [ref])[0].provenance == 'school_data'
        wrong = EvidenceSourceResolver(attestations=[attestation.model_copy(update={'content_digest': '0' * 64})])
        assert wrong.resolve(db, actor, ids['school'], ids['a'], 'teaching_suggestion', [ref])[0].provenance == 'school_data'
    post(client, base(ids) + f'/evidence/{item["id"]}/corrections', {
        **attribution(ids), 'expected_version': item['version'], 'content': 'Corrected synthetic content.', 'reason': 'Fixture correction.',
    }, headers, 200)
    with factory() as db:
        with pytest.raises(DomainError): trusted.resolve(db, actor, ids['school'], ids['a'], 'teaching_suggestion', [ref])


def test_default_assembly_routes_and_processing_boundary(tmp_path):
    app = create_app(Settings(environment='test'))
    paths = list(app.openapi()['paths'])
    for suffix in ['/intake/notes', '/ai/jobs', '/governance/requirements']:
        assert sum(path.endswith(suffix) for path in paths) >= 1
    assert app.state.evidence_storage is None and app.state.ai_gateway.providers == {}
    with pytest.raises(ValueError):
        create_app(Settings(environment='test', ai_providers=[AIProviderSettings(key='bad', endpoint='http://169.254.169.254/v1', capabilities={'generation'})]))
    with pytest.raises(ValueError): Settings(environment='test', ai_remote_synthetic_development=True)
    with pytest.raises(ValueError): Settings(environment='test', ai_synthetic_manifest=tmp_path / 'manifest.json')
    provider = AIProviderSettings(key='local', endpoint='http://127.0.0.1:9999/v1', capabilities={'generation'}, api_key='synthetic-only-secret')
    assert 'synthetic-only-secret' not in repr(provider)


def test_operator_media_evaluations_are_bounded_and_confined(tmp_path):
    from PIL import Image
    import wave
    Image.new('RGB', (80, 40), 'white').save(tmp_path / 'synthetic.png')
    with wave.open(str(tmp_path / 'synthetic.wav'), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\x00' * 1600)
    fixtures = [
        {'name': 'image', 'purpose': 'evidence_extraction', 'file': 'synthetic.png', 'media_type': 'image/png'},
        {'name': 'speech', 'purpose': 'transcription', 'file': 'synthetic.wav', 'media_type': 'audio/wav'},
    ]
    path = tmp_path / 'suites.json'
    path.write_text(json.dumps({'version': 1, 'suites': {'media': fixtures}}))
    cases = load_evaluation_suites(path)['media']
    assert len(cases) == 2 and all(isinstance(case.sources[0].content, bytes) for case in cases)
    assert all(case.sources[0].provenance == 'synthetic_fixture' for case in cases)
    fixtures[0]['file'] = '../outside.png'
    path.write_text(json.dumps({'version': 1, 'suites': {'media': fixtures}}))
    with pytest.raises(ValueError): load_evaluation_suites(path)
    fixtures[0]['file'] = 'synthetic.png'
    path.write_text(json.dumps({'version': 1, 'suites': {'media': fixtures}}))
    path.chmod(0o666)
    with pytest.raises(ValueError): load_evaluation_suites(path)
