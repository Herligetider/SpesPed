"""Restarted production document application, using native source owners."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from documents_fixtures import (
    documents_env, assessment_env, curriculum_env, teaching_env, env,
    login, template, evidence, ordinary_goal, observation, create, revised,
    transition, path,
)
from spesped.auth import Actor
from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
from spesped.contexts.documents.service import frozen_revision
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.db import utcnow
from spesped.errors import DomainError
from spesped.main import create_app


def native_app(fixture_app, factory):
    app = create_app(fixture_app.state.settings, factory)
    # Preserve original bytes, but never fixture authority or source readers.
    app.state.evidence_storage = fixture_app.state.evidence_storage
    assert "/api/v1/schools/{school_id}/documents/cases" in app.openapi()["paths"]
    return app


def test_native_report_restart_and_original_withdrawal(documents_env):
    _, factory, fixture_app, ids = documents_env
    with TestClient(native_app(fixture_app, factory)) as client:
        headers = login(client)
        report_template = template(client, ids, headers)
        binding, _ = evidence(client, ids, headers)
        goal, _ = ordinary_goal(client, ids, headers, binding=binding)
        observation(client, ids, headers, goal,
                    occurred_at=(utcnow() - timedelta(days=1)).isoformat())
        row = create(client, ids, headers, kind="local_semester_report",
                     starts_on=(date.today() - timedelta(days=30)).isoformat(),
                     ends_on=date.today().isoformat(),
                     template_revision_id=report_template["revision_id"],
                     selection={"references": [{
                         "kind": "evidence", "id": binding["evidence_id"],
                         "revision": binding["evidence_revision"],
                         "link_id": binding["link_id"],
                     }]})
        manifest = row["revision"]["snapshot"]["manifest"]
        assert manifest["entries"]
        row = revised(client, ids, headers, row)
        row = transition(client, ids, headers, row, "review")
        row = transition(client, ids, headers, row, "approve")
        assert row["state"] == "approved"
        original_content = row["revision"]["content"]
        revision_id = row["revision_id"]

    with TestClient(native_app(fixture_app, factory)) as client:
        login(client)
        url = path(ids) + f'/cases/{row["id"]}'
        response = client.get(url)
        assert response.status_code == 200, response.text
        restored = response.json()
        assert restored["revision_id"] == revision_id
        assert restored["revision"]["content"] == original_content
        assert restored["revision"]["approval"]["state"] == "current"
        assert restored["dispatch"]["automatic_send"] is False

        with factory.begin() as db:
            db.get(SourceSubjectLink, binding["link_id"]).revoked_at = utcnow()
        response = client.get(url)
        assert response.status_code == 200, response.text
        recalled = response.json()
        assert recalled["revision_id"] == revision_id
        assert recalled["revision"]["source_status"] == "unavailable"
        assert recalled["revision"]["content"] is None

    # A later disclosure consumer must fail at the same native source boundary.
    with factory() as db:
        db.info["curriculum_source_port"] = EvidenceSourceReadPort(
            fixture_app.state.evidence_storage)
        with pytest.raises(DomainError):
            frozen_revision(db, Actor(ids["reviewer"]), ids["school"], ids["a"],
                            revision_id, "learning_summary")
