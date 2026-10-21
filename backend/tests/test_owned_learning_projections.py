"""Real owner-backed read contracts for assessment consumers on both databases."""
from datetime import date
import json

import pytest
from sqlalchemy import event, func, select, update

from curriculum_fixtures import curriculum_env, teaching_env, env, scheme, path
from teaching_fixtures import login, ordinary_goal, actual, SyntheticQualificationPort
from plans_fixtures import base, retry, expected, evidence, support_case, confirmed_decision
from spesped.auth import Actor
from spesped.errors import DomainError
from spesped.contexts.curriculum import models as curriculum
from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
from spesped.contexts.curriculum.projections import reviewed_assessment_scheme
from spesped.contexts.identity.models import AuthorityGrant, StaffAssignment, AuditRecord
from spesped.contexts.teaching import models as teaching
from spesped.contexts.teaching.projections import learner_delivery_basis


def scheme_basis(db, app, ids, row, **changes):
    db.info['curriculum_source_port'] = EvidenceSourceReadPort(app.state.evidence_storage)
    return reviewed_assessment_scheme(
        db, Actor(ids['reviewer']), ids['school'], row['content']['id'],
        **{'starts_on': date(2026, 10, 1), 'ends_on': date(2026, 10, 31), **changes},
    )


@pytest.mark.parametrize('pedagogy', ['public', 'montessori'])
def test_scheme_exact_reviewed_original_period_and_no_inferred_grade(curriculum_env, pedagogy):
    client, factory, app, ids = curriculum_env
    headers = login(client)
    row, content = scheme(client, ids, headers, pedagogy)
    with factory() as db:
        value = scheme_basis(db, app, ids, row)
        assert value['scheme_revision_id'] == row['content']['id']
        assert value['pedagogy'] == pedagogy
        assert value['assessment_rules'] == content['assessment_rules']
        assert value['goals'] == content['goals']
        assert value['content_digest'] == row['content']['content_digest']
        assert value['approval']['reviewed_by'] == ids['reviewer']
        assert value['grading_authority'] == value['exemption_authority'] == 'unassessed'
        assert len(value['basis_digest']) == 64
        assert 'pages' not in json.dumps(value)
        with pytest.raises(DomainError, match='entire assessment period') as error:
            scheme_basis(db, app, ids, row, ends_on=date(2028, 1, 1))
        assert error.value.code == 'scheme_period'
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, row, starts_on=date(2026, 11, 1))
        assert error.value.status_code == 422


def test_scheme_rechecks_cached_permission_and_preserves_pending_source_edits(curriculum_env):
    client, factory, app, ids = curriculum_env
    row, _ = scheme(client, ids, login(client))
    with factory() as db:
        held = db.get(curriculum.SchemeRevision, row['content']['id'])
        scheme_basis(db, app, ids, row)
        grant = db.scalar(select(AuthorityGrant).where(
            AuthorityGrant.user_id == ids['reviewer'],
            AuthorityGrant.action == 'curriculum.source.read',
        ))
        with factory.begin() as other:
            other.get(AuthorityGrant, grant.id).state = 'revoked'
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, row)
        assert error.value.status_code == 403
        assert held.id == row['content']['id']
    with factory.begin() as db:
        db.get(AuthorityGrant, grant.id).state = 'active'
    with factory() as db:
        held = db.get(curriculum.SchemeRevision, row['content']['id'])
        held.title = 'Pending human correction must survive'
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, row)
        assert error.value.code == 'dependency_pending'
        assert held.title == 'Pending human correction must survive' and held in db.dirty


def test_scheme_rechecks_supersession_and_stored_rule_digest(curriculum_env):
    client, factory, app, ids = curriculum_env
    headers = login(client)
    row, content = scheme(client, ids, headers)
    with factory() as db:
        original = scheme_basis(db, app, ids, row)
        revised = client.post(path(ids) + f'/schemes/{row["id"]}/revisions', headers=headers,
            json=expected(row, content={**content, 'title': 'New draft scheme'}))
        assert revised.status_code == 201, revised.text
        draft = revised.json()
        # An unreviewed successor does not replace the existing reviewed scheme.
        assert scheme_basis(db, app, ids, row) == original
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, draft)
        assert error.value.code == 'scheme_not_current'
        reviewed = client.post(path(ids) + f'/schemes/{row["id"]}/review', headers=headers,
            json=expected(draft, revision_id=draft['content']['id'],
                content_digest=draft['content']['content_digest'], reason='Reviewed corrected scheme',
                approval_reference='Synthetic approval', approved_on=date.today().isoformat()))
        assert reviewed.status_code == 200, reviewed.text
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, row)
        assert error.value.code == 'scheme_not_current'
    # A retained DB change to the rules cannot inherit the old exact approval.
    with factory.begin() as db:
        db.execute(update(curriculum.AssessmentScheme).where(
            curriculum.AssessmentScheme.scheme_revision_id == draft['content']['id'],
        ).values(rules=[{**content['assessment_rules'][0], 'scale_description': 'Changed without review'}]))
    with factory() as db:
        with pytest.raises(DomainError) as error:
            scheme_basis(db, app, ids, reviewed.json())
        assert error.value.code == 'scheme_changed'


def save_actual(client, ids, headers, content):
    response = client.post(base(ids) + '/teaching/deliveries', headers=headers,
        json=retry(content=content))
    assert response.status_code == 201, response.text
    return response.json()


def test_learner_actual_projection_is_scoped_and_rechecks_corrections(teaching_env):
    client, factory, app, ids = teaching_env
    headers = login(client)
    one, _ = ordinary_goal(client, ids, headers)
    two, _ = ordinary_goal(client, ids, headers, learner='b')
    content = actual(ids, {'a': one, 'b': two}, activity='PRIVATE GROUP NARRATIVE')
    content['participants'][1]['support'] = 'PRIVATE SIBLING SUPPORT'
    row = save_actual(client, ids, headers, content)
    with factory() as db:
        actor = Actor(ids['teacher'])  # Has only pupil A's scope.
        held = db.get(teaching.DeliveryRevision, row['revision_id'])
        value = learner_delivery_basis(db, actor, ids['school'], ids['a'], row['revision_id'])
        assert value['state'] == 'delivered'
        assert value['participation'][0]['minutes'] == 30
        assert value['participation'][0]['goal_revision_ids'] == [one]
        serialized = json.dumps(value)
        assert all(secret not in serialized for secret in (ids['b'], two, 'PRIVATE GROUP', 'PRIVATE SIBLING'))
        assert 'staff_minutes' not in value and 'staff' not in value
        with pytest.raises(DomainError) as error:
            learner_delivery_basis(db, actor, ids['school'], ids['b'], row['revision_id'])
        assert error.value.status_code == 403
        for name in ('guardian', 'tech', 'assistant'):
            with pytest.raises(DomainError) as error:
                learner_delivery_basis(db, Actor(ids[name]), ids['school'], ids['a'], row['revision_id'])
            assert error.value.status_code == 403
        content['participants'][0].update(status='absent', minutes=0)
        content.update(status='partial', cause='learner_absence', follow_up_owner_id=ids['reviewer'],
            follow_up='Review missed work')
        corrected = client.post(base(ids) + f'/teaching/deliveries/{row["id"]}/corrections',
            headers=headers, json=expected(row, content=content, reason='Actual absence corrected'))
        assert corrected.status_code == 200, corrected.text
        with pytest.raises(DomainError) as error:
            learner_delivery_basis(db, actor, ids['school'], ids['a'], held.id)
        assert error.value.code == 'actual_changed'
        fresh = learner_delivery_basis(db, actor, ids['school'], ids['a'], corrected.json()['revision_id'])
        assert fresh['participation'][0]['status'] == 'absent'
        assert fresh['participation'][0]['minutes'] == 0
        assert fresh['content_digest'] != value['content_digest']


def test_actual_pending_edits_and_revoked_permissions_are_not_overwritten(teaching_env):
    client, factory, app, ids = teaching_env
    headers = login(client)
    goal, _ = ordinary_goal(client, ids, headers)
    row = save_actual(client, ids, headers, actual(ids, {'a': goal}))
    with factory() as db:
        held = db.get(teaching.DeliveryRevision, row['revision_id'])
        held.activity = 'Pending local actual correction'
        with pytest.raises(DomainError) as error:
            learner_delivery_basis(db, Actor(ids['reviewer']), ids['school'], ids['a'], held.id)
        assert error.value.code == 'dependency_pending'
        assert held.activity == 'Pending local actual correction' and held in db.dirty
    with factory() as db:
        actor = Actor(ids['teacher'])
        learner_delivery_basis(db, actor, ids['school'], ids['a'], row['revision_id'])
        assignment = db.scalar(select(StaffAssignment).where(
            StaffAssignment.user_id == ids['teacher'], StaffAssignment.learner_id == ids['a'],
        ))
        with factory.begin() as other:
            other.get(StaffAssignment, assignment.id).state = 'revoked'
        with pytest.raises(DomainError) as error:
            learner_delivery_basis(db, actor, ids['school'], ids['a'], row['revision_id'])
        assert error.value.status_code == 403


def test_unavailable_ito_basis_is_read_only_and_does_not_create_follow_up(teaching_env, monkeypatch):
    client, factory, app, ids = teaching_env
    headers = login(client)
    binding, _ = evidence(client, ids, headers)
    case = support_case(client, factory, ids, headers)
    decision = confirmed_decision(client, ids, headers, case, binding)
    goal, _ = ordinary_goal(client, ids, headers)
    content = actual(ids, {'a': goal})
    content['participants'][0].update(category='individually_adapted_education',
        provision={'decision_id': decision['id'], 'decision_revision_id': decision['content']['id'],
            'provision_id': decision['provisions'][0]['id']}, counting_basis='learner_time')
    content['staff'][0]['category'] = 'individually_adapted_education'
    port = SyntheticQualificationPort(ids)
    app.state.teaching_qualification_port = port
    row = save_actual(client, ids, headers, content)
    with factory() as db:
        db.info['teaching_qualification_port'] = port
        actor = Actor(ids['reviewer'])
        prior = learner_delivery_basis(db, actor, ids['school'], ids['a'], row['revision_id'])
        assert prior['participation'][0]['support_assessment'] == 'assessed'
        before = {
            model: db.scalar(select(func.count()).select_from(model))
            for model in (AuditRecord, teaching.TeachingEvent, teaching.TeachingFollowUp)
        }
        def forbidden(*args, **kwargs):
            raise AssertionError('A consumer read must not flush, commit or roll back')
        # SQLAlchemy may call flush internally only when autoflush is enabled.
        monkeypatch.setattr(db, 'commit', forbidden)
        monkeypatch.setattr(db, 'rollback', forbidden)
        original_flush = db.flush
        monkeypatch.setattr(db, 'flush', forbidden)
        statements = []
        connection = db.connection()
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().split()[0].upper())
        event.listen(connection, 'before_cursor_execute', capture)
        port.mode = 'unavailable'
        current = learner_delivery_basis(db, actor, ids['school'], ids['a'], row['revision_id'])
        event.remove(connection, 'before_cursor_execute', capture)
        monkeypatch.setattr(db, 'flush', original_flush)
        assert current['participation'][0]['reported_support_status'] == 'assessed'
        assert current['participation'][0]['support_assessment'] == 'unassessed'
        assert current['content_digest'] != prior['content_digest']
        assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
        assert not db.new and not db.dirty and not db.deleted
        for model, count in before.items():
            assert db.scalar(select(func.count()).select_from(model)) == count
