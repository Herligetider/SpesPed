"""Adverse-path verification of source rights, concurrency and transaction ownership."""
from datetime import timedelta,date
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from sqlalchemy import select,func,event,text,inspect as sa_inspect
import pytest
from assessment_fixtures import *
from spesped.auth import Actor
from spesped.contexts.identity.models import UserAccount
from spesped.errors import DomainError
from spesped.contexts.assessment import models as m,service as svc,schemas as s
from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
from spesped.contexts.evidence.models import SourceSubjectLink
from spesped.db import utcnow

def bind(db,app):
    db.info['curriculum_source_port']=EvidenceSourceReadPort(app.state.evidence_storage)
    db.info['assessment_authority_port']=app.state.assessment_authority_port
    db.info['teaching_qualification_port']=getattr(app.state,'teaching_qualification_port',None)

def test_read_adapter_preserves_caller_transaction_and_pending_rows(assessment_env):
    from spesped.contexts.assessment.adapters import owner_reader
    client,factory,app,ids=assessment_env;h=login(client);sc,_=scheme(client,ids,h)
    row=statement(client,ids,h,sc)
    with factory() as db:
        bind(db,app);actor=Actor(ids['reviewer']);retained=db.get(m.Statement,row['id'])
        retained.subject='Pending subject change'
        with pytest.raises(DomainError,match='pending'):svc.statement_view(db,actor,ids['school'],row['id'])
        assert retained.subject=='Pending subject change' and retained in db.dirty
        db.rollback()
        # A caller-owned, flushed business row must survive read-only owners.
        own=m.Instrument(school_id=ids['school'],owner_id=ids['reviewer'],state='active');db.add(own);db.flush();identity=own.id
        tx=db.get_transaction();counts={'commit':0,'rollback':0,'dml':0,'flush':0}
        def count_commit(*args):counts['commit']+=1
        def count_rollback(*args):counts['rollback']+=1
        def count_flush(*args):counts['flush']+=1
        def sql(conn,cursor,statement,params,context,executemany):
            if statement.lstrip().split(' ',1)[0].upper() in {'INSERT','UPDATE','DELETE'}:counts['dml']+=1
        connection=db.connection()
        event.listen(connection,'commit',count_commit);event.listen(connection,'rollback',count_rollback)
        event.listen(connection,'before_cursor_execute',sql);event.listen(db,'before_flush',count_flush)
        try:
            result=svc.statement_view(db,actor,ids['school'],row['id'])
            assert result['scheme']['scheme_revision_id']==sc['content']['id']
            assert db.get_transaction() is tx and tx.is_active
            assert counts=={'commit':0,'rollback':0,'dml':0,'flush':0}
            assert db.get(m.Instrument,identity) is own
        finally:
            event.remove(connection,'commit',count_commit);event.remove(connection,'rollback',count_rollback)
            event.remove(connection,'before_cursor_execute',sql);event.remove(db,'before_flush',count_flush)
        db.rollback()
    with factory() as db:assert db.get(m.Instrument,identity) is None

def test_retained_orm_reads_do_not_bypass_live_source_or_actor_state(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h)
    content=statement_content(basis=[{'reference':{'kind':'evidence','id':binding['evidence_id'],'revision':binding['evidence_revision'],'link_id':binding['link_id']},'curriculum_goal_code':'READ1','role':'subject_competence','relevance':'Synthetic exact source'}])
    row=statement(client,ids,h,sc,content=content)
    with factory() as retained:
        bind(retained,app);actor=Actor(ids['reviewer'])
        before=svc.statement_view(retained,actor,ids['school'],row['id']);assert before['content']['judgement']
        # End the read transaction while retaining its ORM identity map.
        retained.commit()
        with factory.begin() as other:other.get(SourceSubjectLink,binding['link_id']).revoked_at=utcnow()
        current=svc.statement_view(retained,actor,ids['school'],row['id'])
        assert current['source_status']=='unavailable' and current['content'] is None
        retained.commit()
        with factory.begin() as other:other.get(UserAccount,ids['reviewer']).state='disabled'
        with pytest.raises(DomainError) as exc:svc.statement_view(retained,actor,ids['school'],row['id'])
        assert exc.value.status_code==403

def test_cross_school_and_cross_pupil_exact_references_fail_closed(assessment_env):
    client,factory,app,ids=assessment_env;h=login(client);sc,_=scheme(client,ids,h);binding,_=evidence(client,ids,h,learner='b')
    ref={'kind':'evidence','id':binding['evidence_id'],'revision':binding['evidence_revision'],'link_id':binding['link_id']}
    content=statement_content(basis=[{'reference':ref,'curriculum_goal_code':'READ1','role':'subject_competence','relevance':'Wrong pupil source'}])
    payload=retry(learner_id=ids['a'],scheme_revision_id=sc['content']['id'],subject='reading',assessment_type='ordinary',starts_on='2026-10-01',ends_on='2026-10-21',content=content)
    response=client.post(path(ids)+'/statements',headers=h,json=payload);assert response.status_code==403,response.text
    row=statement(client,ids,h,sc)
    response=client.get(f'/api/v1/schools/{ids["other_school"]}/assessment/statements/{row["id"]}');assert response.status_code==403

def test_actual_postgresql_concurrent_same_key_and_same_version(assessment_env):
    client,factory,app,ids=assessment_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('Actual row-lock/concurrency proof uses PostgreSQL')
    h=login(client);ins,_=instrument(client,ids,h)
    command=s.AdministrationPlan(**retry(learner_id=ids['a'],instrument_revision_id=ins['revision_id'],planned_on=date.today(),purpose='Synthetic concurrent plan',conditions=conditions()))
    barrier=Barrier(2)
    def create():
        with factory() as db:
            bind(db,app);barrier.wait(timeout=5)
            return svc.plan_administration(db,Actor(ids['reviewer']),ids['school'],command)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(create) for _ in range(2)];values=[f.result(timeout=20) for f in futures]
    assert values[0]['id']==values[1]['id']
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.AssessmentCommand).where(m.AssessmentCommand.request_key==command.request_key))==1
        assert db.scalar(select(func.count()).select_from(m.AssessmentEvent).where(m.AssessmentEvent.aggregate_id==values[0]['id']))==1
    row=values[0];barrier=Barrier(2)
    def start():
        with factory() as db:
            bind(db,app);cmd=s.AdministrationStart(**expected(row,occurred_at=utcnow()-timedelta(hours=1)));barrier.wait(timeout=5)
            try:return svc.start_administration(db,Actor(ids['reviewer']),ids['school'],row['id'],cmd)['state']
            except DomainError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(start) for _ in range(2)];states=[f.result(timeout=20) for f in futures]
    assert sorted(states)==['assessment_conflict','started']

def test_business_audit_outbox_and_receipt_rollback_together(assessment_env,monkeypatch):
    client,factory,app,ids=assessment_env;h=login(client);ins,_=instrument(client,ids,h)
    with factory() as db:
        before={model:db.scalar(select(func.count()).select_from(model)) for model in (m.Administration,m.AssessmentEvent,m.AssessmentCommand)}
    real=svc.event
    def fail(db,*args,**kwargs):real(db,*args,**kwargs);raise RuntimeError('Synthetic transaction fault after audit/outbox flush')
    monkeypatch.setattr(svc,'event',fail)
    with factory() as db:
        bind(db,app)
        with pytest.raises(RuntimeError):svc.plan_administration(db,Actor(ids['reviewer']),ids['school'],s.AdministrationPlan(**retry(learner_id=ids['a'],instrument_revision_id=ins['revision_id'],planned_on=date.today(),purpose='Synthetic failure recovery',conditions=conditions())))
    with factory() as db:
        assert {model:db.scalar(select(func.count()).select_from(model)) for model in before}==before
