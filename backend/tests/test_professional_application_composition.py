"""Production professional-authority composition and caller transaction isolation."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from administration_fixtures import (
    administration_env, assessment_env, curriculum_env, teaching_env, env,
    instrument, instrument_request, prerequisites, professional_review,
    planned, started, login, expected, path,
)
from assessment_fixtures import path as assessment_path
from spesped.auth import Actor
from spesped.contexts.administration.adapters import (
    NativeAssessmentAuthorityPort, NativeQualificationReadPort,
)
from spesped.contexts.administration.models import ProfessionalRecord
from spesped.contexts.assessment import adapters, service as assessment
from spesped.contexts.curriculum import service as curriculum
from spesped.contexts.teaching.projections import learner_delivery_basis
from spesped.errors import DomainError
from spesped.main import create_app


def native_app(fixture_app, factory):
    app = create_app(fixture_app.state.settings, factory)
    app.state.evidence_storage = fixture_app.state.evidence_storage
    assert isinstance(app.state.assessment_authority_port, NativeAssessmentAuthorityPort)
    assert isinstance(app.state.teaching_qualification_port, NativeQualificationReadPort)
    return app


def test_persisted_authority_survives_application_restart_and_rechecks_recall(administration_env):
    _, factory, fixture_app, ids = administration_env
    with TestClient(native_app(fixture_app, factory)) as client:
        headers = login(client)
        instrument_row, _ = instrument(client, ids, headers)
        qualification, responsibility = prerequisites(client, ids, headers)
        review = professional_review(client, ids, headers,
                                     instrument_request(ids, instrument_row),
                                     qualification, responsibility)
        assert review["eligibility"] == "reviewed_current"
        administration = planned(client, ids, headers, instrument_row)
        assert administration["qualification_status"] == "reviewed_current"
        administration = started(client, ids, headers, administration)

    # Only persisted records and production assembly cross the app boundary.
    with TestClient(native_app(fixture_app, factory)) as client:
        headers = login(client)
        url = assessment_path(ids) + f'/administrations/{administration["id"]}'
        current = client.get(url)
        assert current.status_code == 200, current.text
        assert current.json()["qualification_status"] == "reviewed_current"
        response = client.post(path(ids) + f'/{qualification["id"]}/revoke',
                               headers=headers, json=expected(
                                   qualification, reason="Synthetic certificate recalled"))
        assert response.status_code == 200, response.text
        recalled = client.get(url)
        assert recalled.status_code == 200, recalled.text
        value = recalled.json()
        assert value["qualification_status"] == "unassessed"
        assert value["source_status"] == "review_required"
        assert value["state"] == administration["state"]
        assert value["version"] == administration["version"]


@pytest.mark.parametrize("consumer", ["owner_reader", "assessment", "curriculum", "actual"])
def test_native_consumers_refuse_pending_professional_changes_without_side_effects(
        administration_env, consumer):
    client, factory, _, ids = administration_env
    headers = login(client)
    qualification, _ = prerequisites(client, ids, headers)
    with factory() as db:
        record = db.get(ProfessionalRecord, qualification["id"])
        record.state = "revoked"
        connection = db.connection()
        effects = []

        def flush(*args):
            effects.append("flush")

        def commit(*args):
            effects.append("commit")

        def rollback(*args):
            effects.append("rollback")

        def sql(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                effects.append("write")

        listeners = [(db, "before_flush", flush), (connection, "commit", commit),
                     (connection, "rollback", rollback),
                     (connection, "before_cursor_execute", sql)]
        for target, name, fn in listeners:
            event.listen(target, name, fn)
        try:
            with pytest.raises(DomainError) as raised:
                actor = Actor(ids["reviewer"])
                if consumer == "owner_reader":
                    with adapters.owner_reader(db):
                        pytest.fail("A fresh reader must not hide staged authority changes")
                elif consumer == "assessment":
                    assessment.instrument_view(db, actor, ids["school"], str(uuid4()))
                elif consumer == "curriculum":
                    curriculum.sources(db, actor, ids["school"], [])
                else:
                    learner_delivery_basis(db, actor, ids["school"], ids["a"], str(uuid4()))
            assert raised.value.code == "dependency_pending"
            assert effects == []
            assert db.in_transaction()
            assert record in db.dirty and record.state == "revoked"
        finally:
            for target, name, fn in listeners:
                event.remove(target, name, fn)
    with factory() as db:
        assert db.get(ProfessionalRecord, qualification["id"]).state == "reviewed"
