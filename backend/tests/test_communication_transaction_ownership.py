"""Rejected communication preconditions leave the caller's whole unit of work intact."""
from uuid import uuid4
import pytest
from sqlalchemy import event
from communication_fixtures import (
    communication_env,documents_env,assessment_env,curriculum_env,teaching_env,env,
    runtime_info,retry,
)
from spesped.auth import Actor
from spesped.contexts.identity.models import GuardianRelationship,School
from spesped.contexts.communication import service as svc,schemas as s,models as m
from spesped.errors import DomainError

@pytest.mark.parametrize('pending',['restriction','new_context','deleted_context'])
def test_rejected_commands_preserve_pending_contexts_and_flushed_caller_work(communication_env,pending):
    _,factory,app,ids=communication_env
    with factory() as db:
        runtime_info(db,app)
        school=db.get(School,ids['school']);original_name=school.name
        school.name='Synthetic caller-owned flushed school edit';db.flush()
        relationship=db.get(GuardianRelationship,ids['guardian_relation'])
        if pending=='restriction':
            relationship.restrictions='Synthetic pending protective restriction';staged=relationship
        elif pending=='new_context':
            staged=m.ChannelPolicy(school_id=ids['school'],state='active');db.add(staged)
        else:
            staged=relationship;db.delete(staged)
        db.info.update(communication_request_key='synthetic-existing-request',
                       communication_correlation_id='synthetic-existing-correlation',
                       communication_command_replayed=True,caller_state=object())
        before_info=dict(db.info);before_new=set(db.new);before_dirty=set(db.dirty);before_deleted=set(db.deleted)
        transaction=db.get_transaction();connection=db.connection();observed=[]
        def sql(*_):observed.append('sql')
        def flushed(*_):observed.append('flush')
        def committed(*_):observed.append('commit')
        def rolled_back(*_):observed.append('rollback')
        event.listen(connection,'before_cursor_execute',sql)
        for name,callback in [('before_flush',flushed),('after_commit',committed),('after_rollback',rolled_back)]:event.listen(db,name,callback)
        # Exercise every command boundary kind, including the outward release
        # orchestration, before any target lookup or authorization can run.
        revocation=s.Revoke(**retry(expected_version=1,reason='Synthetic caller ownership check'))
        dispatch=s.DispatchCommand(**retry(expected_version=1,reason='Synthetic caller ownership check'))
        portal=s.PortalCommand(**retry(expected_version=1))
        calls=[(svc.revoke_channel,revocation),(svc.revoke_recipient,revocation),
               (svc.revoke_package,revocation),(svc.prepare_dispatch,dispatch),
               (svc.mark_release,dispatch),(svc.release_dispatch,dispatch),
               (svc.reconcile_dispatch,dispatch),(svc.revoke_portal,revocation),
               (svc.open_portal,portal),(svc.acknowledge_portal_read,portal)]
        try:
            for operation,command in calls:
                with pytest.raises(DomainError) as error:
                    operation(db,Actor(ids['reviewer']),ids['school'],str(uuid4()),command)
                assert error.value.code=='dependency_pending' and error.value.status_code==409
                assert db.get_transaction() is transaction and transaction.is_active
                assert db.connection() is connection and db.info==before_info
                assert set(db.new)==before_new and set(db.dirty)==before_dirty and set(db.deleted)==before_deleted
                assert school.name=='Synthetic caller-owned flushed school edit'
                if pending=='restriction':assert relationship.restrictions=='Synthetic pending protective restriction'
                elif pending=='new_context':assert staged.id is None and staged in db.new
                else:assert staged in db.deleted
                assert observed==[]
        finally:
            event.remove(connection,'before_cursor_execute',sql)
            for name,callback in [('before_flush',flushed),('after_commit',committed),('after_rollback',rolled_back)]:event.remove(db,name,callback)
        # The caller still decides the fate of its prior flushed and staged work.
        db.rollback()
    with factory() as db:
        assert db.get(School,ids['school']).name==original_name
        assert db.get(GuardianRelationship,ids['guardian_relation']).restrictions==''
