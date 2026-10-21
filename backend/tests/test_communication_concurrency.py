"""Actual PostgreSQL locking and process-loss recovery; no external messages."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier,Event,Lock
from communication_fixtures import *
from spesped.auth import Actor
from spesped.contexts.communication import service as svc,schemas as s,models as m
from spesped.errors import DomainError

def test_postgres_simultaneous_release_and_reconcile_submit_once(communication_env,secure_wire,monkeypatch):
    client,factory,app,ids=communication_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('Row-lock race requires actual PostgreSQL')
    configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch);secure_wire.mode='lost_reply'
    command=s.DispatchCommand(**expected(dispatch,reason='Synthetic concurrent exact release'));barrier=Barrier(2)
    # Both callers arrive before the first durable start, but the second command
    # is delayed until the first completes with unknown. Its locked replay must
    # still avoid a second HTTP submission.
    marking=Barrier(2);finished=Event();ordering=Lock();arrivals=[];original=svc.mark_release
    def delayed_second(*args,**kwargs):
        with ordering:index=len(arrivals);arrivals.append(index)
        marking.wait(timeout=10)
        if index:assert finished.wait(timeout=10)
        return original(*args,**kwargs)
    monkeypatch.setattr(svc,'mark_release',delayed_second)
    def run_release(_):
        with factory() as db:
            runtime_info(db,app);barrier.wait(timeout=10)
            try:return svc.release_dispatch(db,Actor(ids['reviewer']),ids['school'],dispatch['id'],command)['state']
            except DomainError as exc:return exc.code
            finally:finished.set()
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run_release,range(2)))
    assert 'unknown' in results and len(secure_wire.submissions)==1,results
    current=client.get(path(ids)+f'/dispatches/{dispatch["id"]}').json();command=s.DispatchCommand(**expected(current,reason='Synthetic concurrent provider reconciliation'));barrier=Barrier(2)
    def run_reconcile(_):
        with factory() as db:
            runtime_info(db,app);barrier.wait(timeout=10)
            try:return svc.reconcile_dispatch(db,Actor(ids['reviewer']),ids['school'],dispatch['id'],command)['state']
            except DomainError as exc:return exc.code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run_reconcile,range(2)))
    assert results==['accepted','accepted'] and len(secure_wire.lookups)==1 and len(secure_wire.submissions)==1

def test_interrupted_before_wire_reconciles_absence_then_explicit_new_attempt(communication_env,secure_wire):
    client,factory,app,ids=communication_env;configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,_=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);dispatch=prepare(client,ids,h,dispatch)
    with factory() as db:
        runtime_info(db,app);started=svc.mark_release(db,Actor(ids['reviewer']),ids['school'],dispatch['id'],s.DispatchCommand(**expected(dispatch,reason='Synthetic durable release interrupted by process loss')))
    # A new app/session factory view recovers persisted facts; no in-memory queue is needed.
    from spesped.main import create_app
    restarted=create_app(app.state.settings,factory);restarted.state.evidence_storage=app.state.evidence_storage;configure_secure(restarted,ids,secure_wire)
    with factory() as db:
        runtime_info(db,restarted);state=svc.read(db,Actor(ids['reviewer']),ids['school'],'dispatch',dispatch['id']);assert state['state']=='unknown'
        state=svc.reconcile_dispatch(db,Actor(ids['reviewer']),ids['school'],dispatch['id'],s.DispatchCommand(**expected(state,reason='Synthetic reconcile after restart')));assert state['state']=='failed' and state['receipts'][-1]['outcome']=='not_found'
    assert secure_wire.submissions==[] and len(secure_wire.lookups)==1
    dispatch=prepare(client,ids,h,state);dispatch=release(client,ids,h,dispatch);assert dispatch['state']=='accepted' and len(secure_wire.submissions)==1 and len(dispatch['attempts'])==2

def test_definitive_provider_rejection_is_failed_and_correction_links_prior(communication_env,secure_wire):
    client,factory,app,ids=communication_env;configure_secure(app,ids,secure_wire);h=login(client);_,_,_,package,selection=setup(client,ids,h,channel='secure_https');package=authorize(client,ids,h,package);_,dispatch=queued(client,ids,h,package);secure_wire.mode='rejected';dispatch=release(client,ids,h,prepare(client,ids,h,dispatch));assert dispatch['state']=='failed' and dispatch['receipts'][-1]['reason_code']=='provider_rejected'
    corrected=post(client,ids,h,'/packages',retry(selection=selection,corrects_dispatch_id=dispatch['id']),201);assert corrected['corrects_dispatch_id']==dispatch['id'] and corrected['state']=='draft'
    retained=client.get(path(ids)+f'/dispatches/{dispatch["id"]}').json();assert retained['state']=='failed' and retained['attempts']==dispatch['attempts']
