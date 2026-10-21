"""Fresh application composition, using native sources and no fixture authority."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from assessment_fixtures import (
    assessment_env, curriculum_env, teaching_env, env,
    instrument, observation, path, planned, progress, statement, statement_content,
)
from curriculum_fixtures import scheme
from plans_fixtures import base, evidence, expected, login, retry
from teaching_fixtures import actual, ordinary_goal
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.db import utcnow
from spesped.main import create_app


def fresh_app(fixture_app, factory):
    app = create_app(fixture_app.state.settings, factory)
    # Reuse only the original-file store. Routers and readers come from production
    # composition, and the fixture's synthetic authority ports are not copied.
    app.state.evidence_storage = fixture_app.state.evidence_storage
    for name in ("assessment_authority_port", "curriculum_source_port",
                 "curriculum_future_session_port", "teaching_qualification_port"):
        assert getattr(app.state, name, None) is None
    return app


def test_native_progress_survives_new_app_and_rechecks_original_authority(assessment_env):
    _, factory, fixture_app, ids = assessment_env
    app = fresh_app(fixture_app, factory)
    with TestClient(app) as client:
        headers = login(client)
        binding, _ = evidence(client, ids, headers)
        goal_id, _ = ordinary_goal(client, ids, headers, binding=binding)
        observed = observation(client, ids, headers, goal_id)
        response = client.post(base(ids) + "/teaching/deliveries", headers=headers,
                               json=retry(content=actual(ids, {"a": goal_id})))
        assert response.status_code == 201, response.text
        delivery = response.json()
        row = progress(client, ids, headers, goal_id,
                       delivery_revision_ids=[delivery["revision_id"]])
        snapshot = row["snapshot"]
        assert snapshot["observations"][0]["revision_id"] == observed["revision_id"]
        assert snapshot["actual_deliveries"][0]["delivery_revision_id"] == delivery["revision_id"]
        assert snapshot["actual_deliveries"][0]["learner_id"] == ids["a"]
        assert snapshot["planned_activity_is_evidence"] is False
        assert snapshot["universal_pupil_score"] is None
        assert snapshot["drafting"] == "manual_grounded_source_review"
        assert snapshot["ai_generation"] == "not_integrated"

    # A separate app and login must read persisted work, with no borrowed fixture
    # cache or custom owner reader. Revoking the original still redacts the prose.
    with TestClient(fresh_app(fixture_app, factory)) as client:
        login(client)
        url = path(ids) + f'/progress-reviews/{row["id"]}'
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["snapshot_digest"] == row["snapshot_digest"]
        assert response.json()["content"] == row["content"]
        with factory.begin() as db:
            db.get(SourceSubjectLink, binding["link_id"]).revoked_at = utcnow()
        recalled = client.get(url)
        assert recalled.status_code == 200, recalled.text
        assert recalled.json()["source_status"] == "unavailable"
        assert recalled.json()["snapshot"] is None
        assert recalled.json()["content"] is None


def test_native_statement_and_instrument_do_not_invent_professional_authority(assessment_env):
    _, factory, fixture_app, ids = assessment_env
    with TestClient(fresh_app(fixture_app, factory)) as client:
        headers = login(client)
        reviewed_scheme, _ = scheme(client, ids, headers, pedagogy="montessori")
        binding, _ = evidence(client, ids, headers)
        competence = {
            "reference": {"kind": "evidence", "id": binding["evidence_id"],
                          "revision": binding["evidence_revision"], "link_id": binding["link_id"]},
            "curriculum_goal_code": "READ1", "role": "subject_competence",
            "relevance": "Synthetic human selection of subject evidence",
        }
        row = statement(client, ids, headers, reviewed_scheme,
                        starts_on=(date.today() - timedelta(days=21)).isoformat(),
                        ends_on=date.today().isoformat(),
                        content=statement_content(basis=[competence]))
        assert row["scheme"]["pedagogy"] == "montessori"
        assert row["scheme"]["scheme_revision_id"] == reviewed_scheme["content"]["id"]
        assert row["content"]["ai_generation"] == "not_integrated"
        assert row["unresolved"] == []
        assert row["source_status"] == "current"
        url = path(ids) + f'/statements/{row["id"]}'
        response = client.post(url + "/finalize", headers=headers, json=expected(
            row, revision_id=row["revision_id"], content_digest=row["content_digest"],
            reason="Synthetic attempted finalization without reviewed authority",
            contribution_ids=[]))
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "assessment_authority_unresolved"
        current = client.get(url).json()
        assert current["version"] == row["version"]
        assert current["state"] == "under_work"
        assert current["finalization"] is None
        assert current["communications"] == []
        assert current["external_send_performed"] is False

        instrument_row, _ = instrument(client, ids, headers)
        administration = planned(client, ids, headers, instrument_row)
        assert administration["qualification_status"] == "unavailable"
        url = path(ids) + f'/administrations/{administration["id"]}'
        response = client.post(url + "/start", headers=headers, json=expected(
            administration, occurred_at=(utcnow() - timedelta(hours=1)).isoformat()))
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "assessment_authority_unresolved"
        current = client.get(url).json()
        assert current["state"] == "planned"
        assert current["version"] == administration["version"]
