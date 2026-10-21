"""Native disclosure, confirmed-period history and guardian access across restart."""
from fastapi.testclient import TestClient

from communication_fixtures import (
    communication_env, documents_env, assessment_env, curriculum_env,
    teaching_env, env, login, setup, authorize, queued, prepare, release,
    post, review, expected, path,
)
from documents_fixtures import path as documents_path
from spesped.contexts.communication.adapters import NativeDispatchHistoryPort
from spesped.contexts.communication.transports import TransportRegistry
from spesped.contexts.identity.models import GuardianRelationship
from spesped.main import create_app


def native_app(fixture_app, factory):
    app = create_app(fixture_app.state.settings, factory)
    # Retain original source bytes, never fixture source/authority adapters.
    app.state.evidence_storage = fixture_app.state.evidence_storage
    assert isinstance(app.state.document_dispatch_history_port, NativeDispatchHistoryPort)
    assert isinstance(app.state.communication_transport_registry, TransportRegistry)
    assert "/api/v1/schools/{school_id}/communication/packages" in app.openapi()["paths"]
    return app


def test_native_guardian_release_history_restart_and_current_rights(communication_env):
    _, factory, fixture_app, ids = communication_env
    period_command = {
        "learner_id": ids["a"],
        "recipient_relationship_id": ids["guardian_relation"],
        "purpose": "learning_summary",
        "starts_on": "2026-10-01",
        "ends_on": "2026-10-21",
        "shortcut": "explicit",
    }
    period_url = documents_path(ids) + "/period-resolution"
    with TestClient(native_app(fixture_app, factory)) as client:
        headers = login(client)
        document, _, _, package, _ = setup(client, ids, headers, attachments=True)
        preview = client.get(path(ids) + f'/packages/{package["id"]}/preview')
        assert preview.status_code == 200, preview.text
        expected_payload = preview.json()
        package = authorize(client, ids, headers, package)
        package = post(client, ids, headers, f'/packages/{package["id"]}/export',
                       review(package, mode="copied"))
        _, dispatch = queued(client, ids, headers, package)
        response = client.post(period_url, headers=headers, json=period_command)
        assert response.status_code == 200, response.text
        assert response.json()["dispatch_history"] == "confirmed_records_only"
        assert response.json()["overlaps"] == []
        dispatch = release(client, ids, headers, prepare(client, ids, headers, dispatch))
        assert dispatch["state"] == "accepted"
        assert dispatch["read_acknowledged"] is False
        grant = dispatch["portal_grants"][0]

    with TestClient(native_app(fixture_app, factory)) as client:
        headers = login(client)
        response = client.post(period_url, headers=headers, json=period_command)
        assert response.status_code == 200, response.text
        periods = response.json()["overlaps"]
        assert len(periods) == 1
        assert periods[0]["dispatch_id"] == dispatch["id"]
        assert periods[0]["document_revision_id"] == document["revision_id"]
        assert periods[0]["recipient_relationship_id"] == ids["guardian_relation"]
        assert periods[0]["purpose"] == "learning_summary"

        headers = login(client, "guardian")
        grant_url = path(ids) + f'/portal/grants/{grant["id"]}'
        assert client.get(grant_url + "/payload").status_code == 403
        post(client, ids, headers, f'/portal/grants/{grant["id"]}/open', expected(grant))
        received = client.get(grant_url + "/payload")
        assert received.status_code == 200, received.text
        assert received.json() == expected_payload
        attachment_url = grant_url + f'/attachments/{expected_payload["attachments"][0]["id"]}'
        attachment = client.get(attachment_url)
        assert attachment.status_code == 200
        assert b"Synthetic human text" in attachment.content

        # The persistent grant never supersedes current guardian information rights.
        with factory.begin() as db:
            db.get(GuardianRelationship, ids["guardian_relation"]).information_rights = "unknown"
        assert client.get(grant_url + "/payload").status_code in {403, 409}
        assert client.get(attachment_url).status_code in {403, 409}
