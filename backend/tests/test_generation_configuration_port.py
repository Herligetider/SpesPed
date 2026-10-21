"""Configuration reads must preserve the document owner's atomic transaction."""
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from spesped.audit import record_audit
from spesped.contexts.identity.models import AuditRecord, AuthorityGrant, Learner
from spesped.contexts.platform import service
from spesped.contexts.platform.models import (
    GenerationJob, ModelEvaluation, ModelRelease, PlatformEvent, ProcessingPolicy,
)
from spesped.errors import DomainError
from test_document_gateway import draft, env, wire_server


def validate(draft, db, **overrides):
    values = dict(actor=draft.actor, school_id=draft.ids['school'],
        learner_id=draft.ids['learner'], purpose=draft.purpose,
        policy_id=draft.ids['policy'], release_id=draft.ids['document_release'],
        runtime=draft.runtime)
    values.update(overrides)
    return service.validate_generation_configuration(db, **values)


def counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model))
                 for model in (AuditRecord, PlatformEvent, GenerationJob))


def test_metadata_read_preserves_unflushed_and_flushed_caller_transaction(draft):
    calls = len(draft.server.requests)
    with draft.factory() as db:
        before = counts(db)
        release = db.get(ModelRelease, draft.ids['document_release'])
        expected = {'policy_version': 1, 'release_digest': release.configuration_digest}
        pending = record_audit(db, draft.actor, draft.ids['school'],
                               'synthetic.owner_pending', 'learner', draft.ids['learner'])
        writes = []
        connection = db.connection()
        def capture(_connection, _cursor, statement, *_):
            if statement.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
                writes.append(statement)
        event.listen(connection, 'before_cursor_execute', capture)
        try:
            assert validate(draft, db) == expected
            assert pending in db.new and pending.id is None
            assert not writes and db.in_transaction()
        finally:
            event.remove(connection, 'before_cursor_execute', capture)
        db.flush()
        pending_id = pending.id
        assert validate(draft, db) == expected
        assert db.get(AuditRecord, pending_id) is pending
        assert counts(db) == (before[0] + 1, *before[1:])
        db.rollback()
    with draft.factory() as db:
        assert db.get(AuditRecord, pending_id) is None
        assert counts(db) == before
    assert len(draft.server.requests) == calls


@pytest.mark.parametrize('target', ['policy', 'release', 'evaluation', 'authority', 'learner'])
def test_pending_dependency_changes_are_never_flushed_or_overwritten(draft, target):
    with draft.factory() as db:
        if target == 'policy': row = db.get(ProcessingPolicy, draft.ids['policy'])
        elif target == 'release': row = db.get(ModelRelease, draft.ids['document_release'])
        elif target == 'evaluation':
            row = db.get(ModelEvaluation, db.get(ModelRelease, draft.ids['document_release']).evaluation_id)
        elif target == 'learner': row = db.get(Learner, draft.ids['learner'])
        else:
            row = db.scalar(select(AuthorityGrant).where(
                AuthorityGrant.user_id == draft.actor.user_id,
                AuthorityGrant.action == 'ai.' + draft.purpose))
        row.state = 'revoked'
        with pytest.raises(DomainError) as exc:
            validate(draft, db)
        assert exc.value.code == 'dependency_pending'
        assert row.state == 'revoked' and row in db.dirty
        db.rollback()
        assert validate(draft, db)['policy_version'] == 1


@pytest.mark.parametrize('target', ['policy', 'release', 'evaluation', 'authority', 'learner'])
def test_committed_recall_is_current_without_refreshing_caller_cache(draft, target):
    with draft.factory() as caller:
        if target == 'policy': cached = caller.get(ProcessingPolicy, draft.ids['policy'])
        elif target == 'release': cached = caller.get(ModelRelease, draft.ids['document_release'])
        elif target == 'evaluation':
            cached = caller.get(ModelEvaluation, caller.get(ModelRelease, draft.ids['document_release']).evaluation_id)
        elif target == 'learner': cached = caller.get(Learner, draft.ids['learner'])
        else:
            cached = caller.scalar(select(AuthorityGrant).where(
                AuthorityGrant.user_id == draft.actor.user_id,
                AuthorityGrant.action == 'ai.' + draft.purpose))
        old_state = cached.state
        with draft.factory.begin() as writer:
            writer.get(type(cached), cached.id).state = 'revoked'
        with pytest.raises(DomainError): validate(draft, caller)
        assert cached.state == old_state and cached not in caller.dirty


def test_scope_purpose_and_missing_runtime_fail_without_side_effects(draft):
    calls = len(draft.server.requests)
    with draft.factory() as db:
        before = counts(db)
        for changes in (
            {'school_id': str(uuid4())}, {'learner_id': str(uuid4())},
            {'learner_id': None}, {'purpose': 'unsupported'},
            {'policy_id': str(uuid4())}, {'release_id': str(uuid4())},
            {'purpose': next(p for p in service.DOCUMENT_PURPOSES if p != draft.purpose)},
            {'runtime': None},
        ):
            with pytest.raises(DomainError): validate(draft, db, **changes)
        assert counts(db) == before and not db.new and not db.dirty
    assert len(draft.server.requests) == calls


def test_current_operator_runtime_boundary_is_rechecked(draft):
    with draft.factory() as db:
        denied_network = replace(draft.runtime, private_networks=())
        with pytest.raises(DomainError) as exc:
            validate(draft, db, runtime=denied_network)
        assert exc.value.code == 'provider_boundary_rejected'
        changed_provider = replace(draft.runtime.providers['local'], endpoint='http://127.0.0.1:1/v1')
        with pytest.raises(DomainError) as exc:
            validate(draft, db, runtime=replace(draft.runtime, providers={'local': changed_provider}))
        assert exc.value.code == 'provider_configuration_changed'
