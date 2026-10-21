from datetime import timedelta,date,datetime,time
from sqlalchemy import select,func,event
from spesped.auth import Actor
from spesped.errors import DomainError
from spesped.contexts.administration import models as m,service as svc
from spesped.contexts.assessment.ports import AuthorityRequest
from administration_fixtures import *
from test_professional_authority_native import bound

def test_professional_source_revisions_interval_limits_and_negative_human_review(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h);request=instrument_request(ids,inst)
    qualification=client.get(path(ids)+f'/{q["id"]}?private=true').json()['content']
    today=datetime.combine(date.today(),time.min,ZoneInfo('Europe/Oslo'))
    # Future and elapsed source coverage cannot authorize the actual whole day.
    for start,end in [(today+timedelta(days=1),today+timedelta(days=2)),(today-timedelta(days=2),today-timedelta(seconds=1)),(today,today+timedelta(hours=12))]:
        candidate=approve(client,ids,h,create(client,ids,h,{**qualification,'effective_from':start.isoformat(),'effective_until':end.isoformat()}))
        response=client.post(path(ids),headers=h,json=retry(content={'kind':'assessment_review','request':request,'qualification':ref(candidate),'responsibility':ref(r),'policy':None,'source':source(),**period()}))
        assert response.status_code==409,response.text
    # A current explicit adverse human determination is separate from missing proof.
    content={'kind':'assessment_review','request':request,'qualification':ref(q),'responsibility':ref(r),'policy':None,'source':source(),**period()}
    negative=approve(client,ids,h,create(client,ids,h,content),outcome='ineligible')
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),AuthorityRequest(**request)).state=='ineligible'
    assert client.get(path(ids)+f'/{negative["id"]}').json()['eligibility']=='ineligible'
    # Immutable decisions cannot be edited behind their digest.
    with factory() as db:
        check=db.scalar(select(m.ProfessionalCheck).where(m.ProfessionalCheck.revision_id==negative['revision_id']));check.outcome='eligible'
        with pytest.raises(ValueError,match='immutable'):db.flush()
        db.rollback()

def test_professional_transaction_audit_failure_rolls_back_every_artifact(administration_env,monkeypatch):
    client,factory,app,ids=administration_env;h=login(client)
    content={'kind':'qualification','person_id':ids['reviewer'],'qualification':'Synthetic atomic certificate','purposes':['teaching'],'source':source(),**period()}
    command=retry(content=content)
    def fail(*args,**kwargs):raise RuntimeError('synthetic audit storage failure')
    with monkeypatch.context() as patch:
        patch.setattr(svc,'record_audit',fail)
        with pytest.raises(RuntimeError,match='synthetic audit'):client.post(path(ids),headers=h,json=command)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ProfessionalRecord))==0
        assert db.scalar(select(func.count()).select_from(m.ProfessionalRevision))==0
        assert db.scalar(select(func.count()).select_from(m.ProfessionalEvent))==0
        assert db.scalar(select(func.count()).select_from(m.ProfessionalCommand))==0
    response=client.post(path(ids),headers=h,json=command);assert response.status_code==201,response.text
    same=client.post(path(ids),headers=h,json=command);assert same.status_code==201 and same.json()['id']==response.json()['id']
    conflicting={**command,'content':{**content,'qualification':'Different content'}}
    assert client.post(path(ids),headers=h,json=conflicting).status_code==409

def test_professional_adapter_selects_only_and_preserves_consumer_transaction(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    req=AuthorityRequest(**instrument_request(ids,inst));professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    engine=factory.kw['bind'];statements=[]
    def capture(connection,cursor,statement,parameters,context,executemany):statements.append(statement)
    with factory() as db:
        bound(db,app);db.connection()
        event.listen(engine,'before_cursor_execute',capture)
        try:
            first=NativeAssessmentAuthorityPort().resolve(db,Actor(ids['reviewer']),req)
            second=NativeAssessmentAuthorityPort().resolve(db,Actor(ids['reviewer']),req)
        finally:event.remove(engine,'before_cursor_execute',capture)
        assert first==second and first.state=='reviewed_current'
        assert statements and all(s.lstrip().upper().startswith('SELECT') for s in statements)
        assert db.in_transaction() and not db.new and not db.dirty and not db.deleted

def test_professional_overlapping_responsibility_needs_explicit_reconciliation(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h)
    req=AuthorityRequest(**instrument_request(ids,inst));review=professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    content=client.get(path(ids)+f'/{r["id"]}?private=true').json()['content']
    overlap=approve(client,ids,h,create(client,ids,h,{**content,'responsibility':'assistant_support','source':source()}))
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='unresolved'
    response=client.post(path(ids)+f'/{overlap["id"]}/revoke',headers=h,json=expected(overlap,reason='Synthetic conflicting responsibility explicitly withdrawn'));assert response.status_code==200,response.text
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='reviewed_current'

def test_professional_requested_person_assignment_separate_from_viewer(administration_env):
    client,factory,app,ids=administration_env;h=login(client);inst,_=instrument(client,ids,h);q,r=prerequisites(client,ids,h,person='teacher')
    req=AuthorityRequest(**instrument_request(ids,inst,person='teacher'));professional_review(client,ids,h,req.model_dump(mode='json'),q,r)
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='reviewed_current'
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids['teacher'],StaffAssignment.learner_id==ids['a'])):assignment.state='revoked'
    with factory() as db:assert NativeAssessmentAuthorityPort().resolve(bound(db,app),Actor(ids['reviewer']),req).state=='unresolved'

def test_professional_postgres_concurrent_replay_and_expected_versions(administration_env):
    """Real parallel HTTP requests wait behind a held PostgreSQL tenant lock."""
    from concurrent.futures import ThreadPoolExecutor,TimeoutError
    from threading import Barrier
    from fastapi.testclient import TestClient
    from spesped.contexts.identity.models import School
    client,factory,app,ids=administration_env
    if factory.kw['bind'].dialect.name!='postgresql':pytest.skip('PostgreSQL row-lock concurrency proof; SQLite does not provide equivalent locks')
    h=login(client)
    def parallel(endpoint,commands):
        gate=Barrier(3)
        def worker(command):
            with TestClient(app) as concurrent_client:
                concurrent_client.cookies.update(client.cookies)
                gate.wait(timeout=10)
                return concurrent_client.post(endpoint,headers=h,json=command)
        with ThreadPoolExecutor(max_workers=2) as pool:
            with factory.begin() as blocker:
                blocker.scalar(select(School.id).where(School.id==ids['school']).with_for_update())
                pending=[pool.submit(worker,c) for c in commands]
                gate.wait(timeout=10)
                # Both commands are genuinely in flight while their transaction
                # is blocked; releasing the lock lets them compete at runtime.
                for future in pending:
                    with pytest.raises(TimeoutError):future.result(timeout=0.15)
            return [future.result(timeout=20) for future in pending]
    content={'kind':'qualification','person_id':ids['reviewer'],'qualification':'Synthetic concurrent certificate','purposes':['teaching'],'source':source(),**period()}
    command=retry(content=content)
    responses=parallel(path(ids),[command,command])
    assert [r.status_code for r in responses]==[201,201],[r.text for r in responses]
    assert responses[0].json()['id']==responses[1].json()['id']
    row=responses[0].json()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.ProfessionalCommand).where(m.ProfessionalCommand.request_key==command['request_key']))==1
        assert db.scalar(select(func.count()).select_from(m.ProfessionalEvent).where(m.ProfessionalEvent.causation_id==command['request_key']))==1
    collision=retry(content=content)
    changed={**collision,'content':{**content,'qualification':'Different synthetic certificate'}}
    responses=parallel(path(ids),[collision,changed])
    assert sorted(r.status_code for r in responses)==[201,409],[r.text for r in responses]
    assert next(r for r in responses if r.status_code==409).json()['error']['code']=='idempotency_conflict'
    revisions=[expected(row,content={**content,'qualification':f'Synthetic competing revision {n}'}) for n in (1,2)]
    responses=parallel(path(ids)+f'/{row["id"]}/revisions',revisions)
    assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
    with factory() as db:
        current=db.get(m.ProfessionalRecord,row['id'])
        assert current.version==row['version']+1 and current.current_revision==2
        assert db.scalar(select(func.count()).select_from(m.ProfessionalRevision).where(m.ProfessionalRevision.record_id==row['id']))==2
