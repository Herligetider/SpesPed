from datetime import date,timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from sqlalchemy import select,func
from fastapi.testclient import TestClient
import pytest
from teaching_fixtures import *
from teaching_fixtures import teaching_wire_server,configure_ai
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.contexts.teaching import service
from spesped.contexts.teaching.models import TeachingSession,SessionRevision,SessionDelivery,DeliveryRevision,TeachingCommand,TeachingEvent,TeachingObservation,ObservationRevision,TeachingFollowUp
from spesped.contexts.teaching.schemas import ReviseSession
from spesped.contexts.teaching.common import mutate


def test_complete_manual_teaching_cycle_and_assistant_scope(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h)
    basis_row=basis(client,ids,h,{'a':gid});row=session(client,ids,h,basis_row)
    assert row['delivery_state'] == 'not_recorded'
    row=approve(client,ids,h,row)
    guide,assignment=assigned_brief(client,ids,h,row)
    ah=login(client,'assistant')
    assigned=client.get(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}')
    assert assigned.status_code == 200,assigned.text
    body=assigned.json();assert body['content']['material_location'] == 'Synthetic shelf A'
    assert body['opened_is_completion'] is False and body['understanding_confirmed'] is False
    assert 'source' not in body and 'goal_revision_ids' not in body and 'basis_id' not in body
    for path in (f'/teaching/sessions/{row["id"]}',f'/teaching/bases/{basis_row["id"]}',f'/teaching/briefs/{guide["id"]}',f'/learners/{ids["a"]}/teaching-observations'):
        assert client.get(base(ids)+path).status_code == 403
    q=client.post(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}/messages',headers=ah,json=retry(kind='question',text='Where are the visual cards?'))
    assert q.status_code == 201,q.text
    observe=retry(content={'learner_id':ids['a'],'occurred_at':(utcnow()-timedelta(minutes=20)).isoformat(),'assignment_id':assignment['id'],'session_revision_id':row['revision_id'],'goal_revision_id':gid,'observation':'Read three words with picture cards','support':'A visual cue','interpretation':'May benefit from another short practice','next_step':'Repeat with a new card'})
    saved=client.post(base(ids)+'/teaching/observations',headers=ah,json=observe)
    assert saved.status_code == 201,saved.text
    note=saved.json();assert note['author_id'] == ids['assistant'] and note['confirmed']
    again=client.post(base(ids)+'/teaching/observations',headers=ah,json=observe)
    assert again.json()['id'] == note['id']
    actual_input=client.post(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}/actual-inputs',headers=ah,json=retry(content={'occurred_at':(utcnow()-timedelta(hours=1)).replace(microsecond=0).isoformat(),'duration_minutes':30,'status':'participated','category':'ordinary_teaching','activity':'Practised cards','support':'Visual cue'}))
    assert actual_input.status_code == 201,actual_input.text
    assert actual_input.json()['counts_as_delivery'] is False
    h=login(client)
    answer=client.post(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}/messages',headers=h,json=retry(kind='answer',text='Synthetic shelf A',responds_to_id=q.json()['id']))
    assert answer.status_code == 201,answer.text
    content_actual=actual(ids,{'a':gid},row)
    content_actual['occurred_at']=actual_input.json()['occurred_at']
    result=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=content_actual))
    assert result.status_code == 201,result.text
    delivered=result.json();assert delivered['staff_minutes'] == 30
    reconcile=client.post(base(ids)+f'/teaching/actual-inputs/{actual_input.json()["id"]}/review',headers=h,json=expected(actual_input.json(),outcome='recorded',delivery_revision_id=delivered['revision_id'],reason='Compared the assistant input with the actual teaching record'))
    assert reconcile.status_code == 200,reconcile.text
    notes=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-observations').json()['items']
    assert len(notes) == 1 and notes[0]['observation'] == 'Read three words with picture cards'
    payload=retry(planned_at=(utcnow()+timedelta(days=1)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[gid],'observation_revision_ids':[note['revision_id']]}])
    next_basis=client.post(base(ids)+'/teaching/bases',headers=h,json=payload)
    assert next_basis.status_code == 201,next_basis.text
    assert next_basis.json()['basis']['learners'][0]['observations'][0]['author_id'] == ids['assistant']
    next_session=session(client,ids,h,next_basis.json());assert next_session['content']


def test_group_minutes_corrections_cancellation_and_unplanned(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    ga,_=ordinary_goal(client,ids,h);gb,_=ordinary_goal(client,ids,h,'b')
    br=basis(client,ids,h,{'a':ga,'b':gb});row=approve(client,ids,h,session(client,ids,h,br))
    assert client.get(base(ids)+f'/teaching/sessions/{row["id"]}').json()['delivery_state'] == 'not_recorded'
    payload=retry(content=actual(ids,{'a':ga,'b':gb},row))
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=payload)
    assert response.status_code == 201,response.text
    actual_row=response.json();assert [p['minutes'] for p in actual_row['participants']] == [30,30] and actual_row['staff_minutes'] == 30
    duplicate=client.post(base(ids)+'/teaching/deliveries',headers=h,json=payload);assert duplicate.json()['id'] == actual_row['id']
    duplicate=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload['content']));assert duplicate.status_code == 409
    changed=actual(ids,{'a':ga,'b':gb},row,status='partial',cause='learner_absence',follow_up_owner_id=ids['reviewer'],follow_up='Review missed support')
    changed['participants'][0]['minutes']=20;changed['participants'][0]['status']='partial'
    fixed=client.post(base(ids)+f'/teaching/deliveries/{actual_row["id"]}/corrections',headers=h,json=expected(actual_row,content=changed,reason='Actual participation was twenty minutes'))
    assert fixed.status_code == 200,fixed.text
    hist=client.get(base(ids)+f'/teaching/deliveries/{actual_row["id"]}/revisions').json();assert hist['total'] == 2
    assert sorted(p['minutes'] for p in hist['items'][1]['participants']) == [30,30]
    hteacher=login(client,'teacher')
    assert client.get(base(ids)+f'/teaching/deliveries/{actual_row["id"]}').status_code == 403
    own=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-deliveries')
    assert own.status_code == 200,own.text
    assert len(own.json()['items'][0]['participants']) == 1 and own.json()['items'][0]['staff'] is None and own.json()['items'][0]['activity'] is None
    h=login(client)
    cancelled=actual(ids,{'a':ga},duration_minutes=0,status='cancelled',staff=[],cause='staff_unavailable',follow_up_owner_id=ids['reviewer'],follow_up='Arrange qualified cover')
    cancelled['participants'][0].update(status='absent',minutes=0)
    cancelled_result=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=cancelled))
    assert cancelled_result.status_code == 201,cancelled_result.text
    assert cancelled_result.json()['staff_minutes'] == 0
    future=actual(ids,{'a':ga},occurred_at=(utcnow()+timedelta(hours=1)).isoformat())
    assert client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=future)).status_code == 422
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()}).json()
    assert summary['actual_minutes_by_category']['ordinary_teaching'] == 20 and summary['entitlement_fulfilment'] == 'unassessed'


def test_source_correction_stales_brief_history_replay_and_owned_followup(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    gid,_=ordinary_goal(client,ids,h,binding=binding)
    br=basis(client,ids,h,{'a':gid});row=session(client,ids,h,br)
    row=approve(client,ids,h,row);guide,assignment=assigned_brief(client,ids,h,row)
    correct={'expected_version':item['version'],'learner_id':ids['b'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':item['occurred_at'],'topic':'education','content':'Correct pupil association','reason':'The source concerned the other synthetic pupil','excerpt_page':item['source']['page'],'excerpt_start':item['source']['span_start'],'excerpt_end':item['source']['span_end']}
    changed=client.post(base(ids)+f'/evidence/{item["id"]}/corrections',headers=h,json=correct)
    assert changed.status_code == 200,changed.text
    own=client.get(base(ids)+f'/teaching/sessions/{row["id"]}');assert own.status_code == 200,own.text
    assert own.json()['content'] is None and own.json()['state'] == 'review_required'
    hist=client.get(base(ids)+f'/teaching/sessions/{row["id"]}/revisions').json()
    assert hist['items'][0]['content'] is None
    unavailable=client.get(base(ids)+f'/teaching/briefs/{guide["id"]}').json();assert unavailable['content'] is None
    impacts=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    assert {i['target_type'] for i in impacts} >= {'session','brief'} and all(i['owner_id'] == ids['reviewer'] for i in impacts)
    ah=login(client,'assistant')
    stale=client.get(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}').json();assert stale['content'] is None and stale['brief_state'] == 'review_required'
    assert client.get(base(ids)+f'/evidence/{item["id"]}').status_code == 403
    assert client.post(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}/messages',headers=ah,json=retry(kind='feedback',text='Source-derived feedback')).status_code == 409


def test_exact_approval_stale_revision_rights_revocation_csrf_and_rollback(teaching_env,monkeypatch):
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h);br=basis(client,ids,h,{'a':gid});row=session(client,ids,h,br)
    reviewed=client.post(base(ids)+f'/teaching/sessions/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Checked exact content')).json()
    approval=expected(reviewed,revision_id=reviewed['revision_id'],content_digest=reviewed['content_digest'],reason='Approve reviewed content')
    accepted=client.post(base(ids)+f'/teaching/sessions/{row["id"]}/approve',headers=h,json=approval);assert accepted.status_code == 200,accepted.text
    with factory.begin() as db:
        for grant in db.scalars(select(AuthorityGrant).where(AuthorityGrant.user_id == ids['reviewer'],AuthorityGrant.action == 'teaching.approve')):grant.state='revoked'
    assert client.post(base(ids)+f'/teaching/sessions/{row["id"]}/approve',headers=h,json=approval).status_code == 403
    current=accepted.json()
    revised=expected(current,basis_id=br['id'],owner_id=ids['reviewer'],content=content(support='Manually revised support'),reason='Change support after review')
    assert client.post(base(ids)+f'/teaching/sessions/{row["id"]}/revisions',headers={},json=revised).status_code == 403
    result=client.post(base(ids)+f'/teaching/sessions/{row["id"]}/revisions',headers=h,json=revised);assert result.status_code == 201,result.text
    assert result.json()['state'] == 'draft' and not result.json()['approved']
    stale=client.post(base(ids)+f'/teaching/sessions/{row["id"]}/revisions',headers=h,json={**revised,'request_key':key()});assert stale.status_code == 409
    # A failed audit/outbox operation rolls back content, idempotency and event.
    def fail(*args,**kwargs):raise RuntimeError('Synthetic transactional failure')
    with factory() as db:
        before=(db.scalar(select(func.count()).select_from(SessionRevision)),db.scalar(select(func.count()).select_from(TeachingCommand)),db.scalar(select(func.count()).select_from(TeachingEvent)))
    monkeypatch.setattr(service,'event',fail)
    with pytest.raises(RuntimeError):
        client.post(base(ids)+f'/teaching/sessions/{row["id"]}/revisions',headers=h,json=expected(result.json(),basis_id=br['id'],owner_id=ids['reviewer'],content=content(support='Must roll back'),reason='Synthetic failure'))
    with factory() as db:
        after=(db.scalar(select(func.count()).select_from(SessionRevision)),db.scalar(select(func.count()).select_from(TeachingCommand)),db.scalar(select(func.count()).select_from(TeachingEvent)))
    assert before == after


def test_observation_draft_transcription_correction_reuse_and_wrong_pupil(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h)
    details={'learner_id':ids['a'],'occurred_at':(utcnow()-timedelta(minutes=2)).isoformat(),'goal_revision_id':gid,'observation':'Three words independently','support':'Picture cards','interpretation':'A separate interpretation','next_step':'Try four words'}
    draft=client.post(base(ids)+'/teaching/observations',headers=h,json=retry(content={**details,'input_method':'unconfirmed_transcript'},save=False))
    assert draft.status_code == 201,draft.text
    assert not draft.json()['confirmed']
    assert client.get(base(ids)+f'/learners/{ids["a"]}/teaching-observations').json()['total'] == 0
    assert client.post(base(ids)+'/teaching/observations',headers=h,json=retry(content={**details,'input_method':'unconfirmed_transcript'})).status_code == 422
    result=client.post(base(ids)+f'/teaching/observations/{draft.json()["id"]}/corrections',headers=h,json=expected(draft.json(),content=details,reason='Author checked transcript before saving'))
    assert result.status_code == 200,result.text
    saved=result.json()
    br_payload=retry(planned_at=(utcnow()+timedelta(days=1)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[gid],'observation_revision_ids':[saved['revision_id']]}])
    br=client.post(base(ids)+'/teaching/bases',headers=h,json=br_payload);assert br.status_code == 201,br.text
    row=session(client,ids,h,br.json())
    gb,_=ordinary_goal(client,ids,h,'b')
    corrected=client.post(base(ids)+f'/teaching/observations/{saved["id"]}/corrections',headers=h,json=expected(saved,content={**details,'learner_id':ids['b'],'goal_revision_id':gb},reason='Wrong synthetic pupil association'))
    assert corrected.status_code == 200,corrected.text
    assert client.get(base(ids)+f'/teaching/sessions/{row["id"]}').json()['content'] is None
    assert client.get(base(ids)+f'/learners/{ids["a"]}/teaching-observations').json()['total'] == 0
    h=login(client,'teacher')
    assert client.get(base(ids)+f'/teaching/observations/{saved["id"]}').status_code == 403
    assert client.get(base(ids)+f'/teaching/observations/{saved["id"]}/revisions').status_code == 403


def test_postgres_concurrent_revisions_and_same_key_delivery(teaching_env):
    client,factory,app,ids=teaching_env
    if factory.kw['bind'].dialect.name != 'postgresql':pytest.skip('PostgreSQL row-lock verification')
    h=login(client);gid,_=ordinary_goal(client,ids,h);br=basis(client,ids,h,{'a':gid});row=session(client,ids,h,br)
    barrier=Barrier(2)
    def revise(index):
        command=ReviseSession.model_validate(expected(row,basis_id=br['id'],owner_id=ids['reviewer'],content=content(support=f'Synthetic concurrent {index}'),reason='Concurrent revision'))
        with factory() as db:
            barrier.wait()
            try:
                result=mutate(db,lambda:service.save_session(db,Actor(ids['reviewer']),ids['school'],command,row['id']))
                return result.current_revision
            except Exception as exc:return getattr(exc,'status_code',str(exc))
    with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(revise,[1,2]))
    assert sorted(values) == [2,409]
    current=client.get(base(ids)+f'/teaching/sessions/{row["id"]}').json()
    current=approve(client,ids,h,current)
    command=retry(content=actual(ids,{'a':gid},current))
    barrier=Barrier(2)
    def same_delivery(index):
        barrier.wait()
        response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=command)
        return response.status_code,response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(same_delivery,[1,2]))
    assert [status for status,_ in results] == [201,201]
    assert len({value['id'] for _,value in results}) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SessionDelivery)) == 1
        assert db.scalar(select(func.count()).select_from(DeliveryRevision)) == 1
        assert db.scalar(select(func.count()).select_from(TeachingEvent).where(TeachingEvent.event_type == 'teaching.delivery_create')) == 1
    observed={'learner_id':ids['a'],'occurred_at':(utcnow()-timedelta(minutes=2)).isoformat(),'observation':'Synthetic first observation','support':'Synthetic visual cue'}
    note=client.post(base(ids)+'/teaching/observations',headers=h,json=retry(content=observed)).json()
    basis_request=retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[gid],'observation_revision_ids':[note['revision_id']]}])
    next_basis=client.post(base(ids)+'/teaching/bases',headers=h,json=basis_request).json()
    next_row=session(client,ids,h,next_basis)
    correction=client.post(base(ids)+f'/teaching/observations/{note["id"]}/corrections',headers=h,json=expected(note,content={**observed,'observation':'Synthetic corrected observation'},reason='Correct observation used in the new session'))
    assert correction.status_code == 200,correction.text
    barrier=Barrier(2)
    def stale_read(index):
        barrier.wait()
        response=client.get(base(ids)+f'/teaching/sessions/{next_row["id"]}')
        return response.status_code,response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(stale_read,[1,2]))
    assert all(status == 200 and value['content'] is None for status,value in results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TeachingFollowUp).where(TeachingFollowUp.target_id == next_row['id'],TeachingFollowUp.reason_code == 'basis_changed')) == 1


def test_real_local_ai_structured_field_selection_no_overwrite_replay_and_withdrawal(teaching_env,teaching_wire_server):
    from spesped.contexts.platform import service as gateway
    from spesped.contexts.platform.models import ModelRelease
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h);br=basis(client,ids,h,{'a':gid});row=session(client,ids,h,br,support='Human chosen support')
    runtime,policy,release=configure_ai(factory,app,ids,teaching_wire_server)
    path=base(ids)+f'/teaching/sessions/{row["id"]}'
    request=retry(policy_id=policy,release_id=release)
    queued=client.post(path+'/suggestions',headers=h,json=request)
    assert queued.status_code == 201,queued.text
    job=queued.json()
    completed=gateway.run_job(factory,Actor(ids['reviewer']),ids['school'],job['id'],job['version'],runtime)
    assert completed.state == 'succeeded',completed.error_code
    assert completed.output['unconfirmed'] and completed.output['schema_version'] == 'teaching-session.v1'
    assert client.get(path).json()['content']['support'] == 'Human chosen support'
    diff=client.get(path+f'/suggestions/{job["id"]}/diff');assert diff.status_code == 200,diff.text
    assert next(x for x in diff.json()['changes'] if x['field'] == 'support')['before'] == 'Human chosen support'
    select_fields=expected(row,job_id=job['id'],outcome='accepted',selected_fields=['preparation'],reason='Use preparation while retaining manual support')
    applied=client.post(path+'/suggestions/review',headers=h,json=select_fields)
    assert applied.status_code == 200,applied.text
    next_row=applied.json();assert next_row['content']['support'] == 'Human chosen support' and next_row['state'] == 'draft'
    # Nested gateway source resolution has its own trusted runtime binding, not
    # an HTTP teaching request context. Both full and curated lineage use it.
    with factory() as db:
        db.info['ai_gateway_runtime']=runtime
        revision=db.get(SessionRevision,next_row['revision_id'])
        assert service.revision_valid(db,Actor(ids['reviewer']),revision)
        assert service.revision_valid(db,Actor(ids['reviewer']),revision,curated=True)
        assert db.info['ai_gateway_runtime'] is runtime
        assert 'teaching_runtime' not in db.info
    replayed=client.post(path+'/suggestions/review',headers=h,json=select_fields);assert replayed.status_code == 200,replayed.text
    assert replayed.json()['revision_id'] == next_row['revision_id']
    teaching_wire_server.support='A regenerated support proposal'
    queued2=client.post(path+'/suggestions',headers=h,json=retry(policy_id=policy,release_id=release)).json()
    completed2=gateway.run_job(factory,Actor(ids['reviewer']),ids['school'],queued2['id'],queued2['version'],runtime);assert completed2.state == 'succeeded'
    assert client.get(path).json()['content']['support'] == 'Human chosen support'
    rejected=client.post(path+'/suggestions/review',headers=h,json=expected(next_row,job_id=queued2['id'],outcome='rejected',selected_fields=[],reason='Keep professional manual activity'))
    assert rejected.status_code == 200,rejected.text
    assert rejected.json()['revision_id'] == next_row['revision_id']
    approved_row=approve(client,ids,h,next_row);guide,assignment=assigned_brief(client,ids,h,approved_row)
    ah=login(client,'assistant')
    assert client.get(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}').json()['content']
    h=login(client)
    with factory() as db:version=db.get(ModelRelease,release).version
    response=client.post(base(ids)+f'/ai/configuration/release/{release}/revoke',headers=h,json={'expected_version':version})
    assert response.status_code == 200,response.text
    assert client.get(path).json()['content'] is None
    assert client.post(path+'/suggestions/review',headers=h,json=select_fields).status_code in {409,503}
    assert client.post(path+'/suggestions',headers=h,json=request).status_code in {409,503}
    login(client,'assistant')
    assert client.get(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}').json()['content'] is None
    login(client)
    impacts=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items'];assert impacts
    sent=teaching_wire_server.requests[-1]
    assert sent['response_format']['json_schema']['schema']['properties']['content']['$ref']
    assert all('tools' not in request for request in teaching_wire_server.requests)
    h=login(client)
    # Explicit replacement of the affected field removes only that field's
    # model lineage; the previous exact revisions remain retained and gated.
    recovery=client.post(path+'/revisions',headers=h,json=expected(approved_row,basis_id=br['id'],owner_id=ids['reviewer'],content=content(support='Human chosen support',preparation='Independent manual preparation'),manual_replacements=['preparation'],reason='Replace the recalled model field with independent manual work'))
    assert recovery.status_code == 201,recovery.text
    assert recovery.json()['content']['preparation'] == 'Independent manual preparation'
    assert recovery.json()['field_job_ids']['preparation'] == []
    assert approve(client,ids,h,recovery.json())['approved']
    history=client.get(path+'/revisions').json()['items']
    assert any(old['content'] is None and old['field_job_ids']['preparation'] for old in history)


def test_ai_unavailable_manual_recovery_and_source_binding_recall(teaching_env,teaching_wire_server):
    from spesped.contexts.platform import service as gateway
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    gid,_=ordinary_goal(client,ids,h)
    payload=retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[gid],'sources':[binding]}])
    result=client.post(base(ids)+'/teaching/bases',headers=h,json=payload);assert result.status_code == 201,result.text
    br=result.json();assert br['basis']['learners'][0]['evidence'][0]['content'] == item['content']
    row=session(client,ids,h,br)
    runtime,policy,release=configure_ai(factory,app,ids,teaching_wire_server)
    path=base(ids)+f'/teaching/sessions/{row["id"]}'
    queued=client.post(path+'/suggestions',headers=h,json=retry(policy_id=policy,release_id=release)).json()
    teaching_wire_server.mode='unavailable'
    failed=gateway.run_job(factory,Actor(ids['reviewer']),ids['school'],queued['id'],queued['version'],runtime)
    assert failed.state in {'failed','unavailable'}
    manual=client.post(path+'/revisions',headers=h,json=expected(row,basis_id=br['id'],owner_id=ids['reviewer'],content=content(support='Manual recovery retains work'),reason='AI unavailable; use human-selected activity'))
    assert manual.status_code == 201,manual.text
    assert approve(client,ids,h,manual.json())['approved']
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == ids['reviewer'])):
            assignment.actions=[a for a in assignment.actions if a != 'evidence.read']
    assert client.get(path).json()['content'] is None
    assert client.get(path+f'/suggestions/{queued["id"]}/diff').status_code in {403,409}


def test_scoped_decision_provision_counting_period_and_goal_change(teaching_env):
    from plans_fixtures import support_case,confirmed_decision
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    case=support_case(client,factory,ids,h);decision=confirmed_decision(client,ids,h,case,binding)
    result=client.post(base(ids)+f'/learners/{ids["a"]}/education-plans',headers=h,json=plan_payload(binding,decision))
    assert result.status_code == 201,result.text
    plan=activate(client,ids,h,result.json());gid=plan['content']['goals'][0]['id']
    br=basis(client,ids,h,{'a':gid});row=approve(client,ids,h,session(client,ids,h,br))
    provision=decision['provisions'][0]
    reference={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':provision['id']}
    payload=actual(ids,{'a':gid},row)
    payload['participants'][0].update(category='individually_adapted_education',provision=reference,counting_basis='learner_time',support_status='unassessed')
    payload.update(status='partial',cause='other',cause_detail='The staffing competence basis is unavailable',follow_up_owner_id=ids['reviewer'],follow_up='Verify the exact staffing competence before counting support')
    payload['staff'][0]['category']='individually_adapted_education'
    recorded=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert recorded.status_code == 201,recorded.text
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()})
    assert summary.status_code == 200,summary.text
    values=summary.json();assert values['provisions'][0]['recorded_minutes'] is None and values['provisions'][0]['unassessed_claimed_minutes'] == 30
    assert values['provisions'][0]['comparison'] == 'support_unassessed' and values['entitlement_fulfilment'] == 'unassessed'
    wrong=actual(ids,{'a':gid});wrong['participants'][0].update(category='personal_assistance',provision=reference,counting_basis='learner_time')
    denied=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=wrong));assert denied.status_code == 409
    # An active replacement goal basis invalidates old session/brief content.
    revised=plan_payload(binding,decision);revised.pop('kind');revised['expected_version']=plan['version']
    revised['effective_from']=utcnow().isoformat();revised['goals'][0]['effective_from']=revised['effective_from']
    revised['goals'][0]['title']='New exact goal version'
    response=client.post(base(ids)+f'/education-plans/{plan["id"]}/revisions',headers=h,json=revised)
    assert response.status_code == 201,response.text
    replacement=activate(client,ids,h,response.json())
    assert client.get(base(ids)+f'/teaching/sessions/{row["id"]}').json()['content'] is None
    # Old actual participation remains an attributed historic event.
    old_actual=client.get(base(ids)+f'/teaching/deliveries/{recorded.json()["id"]}')
    assert old_actual.status_code == 200 and old_actual.json()['participants'][0]['goal_revision_ids'] == [gid]


def test_multiple_support_categories_and_staff_allocation_not_double_counted(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    ga,_=ordinary_goal(client,ids,h);gb,_=ordinary_goal(client,ids,h,'b')
    payload=actual(ids,{'a':ga,'b':gb})
    payload['participants'].append({**payload['participants'][0],'category':'personal_assistance','minutes':10})
    payload['staff']=[{**payload['staff'][0],'minutes':20},{**payload['staff'][0],'category':'personal_assistance','minutes':10}]
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload))
    assert response.status_code == 201,response.text
    assert response.json()['staff_minutes'] == 30 and len(response.json()['participants']) == 3
    over=actual(ids,{'a':ga});over['staff'].append({**over['staff'][0],'category':'personal_assistance','minutes':10})
    assert client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=over)).status_code == 422


def test_assignment_revocation_blocks_replay_and_unassigned_assistant_cannot_write(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h);br=basis(client,ids,h,{'a':gid});row=approve(client,ids,h,session(client,ids,h,br));guide,assigned=assigned_brief(client,ids,h,row)
    ah=login(client,'assistant')
    payload=retry(kind='feedback',text='Actual feedback from the assigned assistant')
    endpoint=base(ids)+f'/teaching/brief-assignments/{assigned["id"]}'
    assert client.post(endpoint+'/messages',headers=ah,json=payload).status_code == 201
    h=login(client)
    revoked=client.post(endpoint+'/revoke',headers=h,json=expected(assigned));assert revoked.status_code == 200,revoked.text
    ah=login(client,'assistant')
    assert client.get(endpoint).status_code == 403
    assert client.post(endpoint+'/messages',headers=ah,json=payload).status_code == 403
    arbitrary=retry(content={'learner_id':ids['b'],'occurred_at':utcnow().isoformat(),'observation':'Unassigned pupil','support':'Unknown'})
    assert client.post(base(ids)+'/teaching/observations',headers=ah,json=arbitrary).status_code == 403
    assert client.post(base(ids)+'/teaching/observations',headers=ah,json={**arbitrary,'content':{**arbitrary['content'],'learner_id':ids['a']}}).status_code == 403


def test_utc_normalization_strict_brief_and_manual_recovery_after_corrected_source(teaching_env):
    from datetime import timezone
    client,factory,app,ids=teaching_env;h=login(client)
    gid,_=ordinary_goal(client,ids,h)
    when=(utcnow()+timedelta(minutes=5)).astimezone(timezone(timedelta(hours=2)))
    command=retry(planned_at=when.isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[gid]}])
    result=client.post(base(ids)+'/teaching/bases',headers=h,json=command);assert result.status_code == 201,result.text
    br=result.json()
    assert client.get(base(ids)+f'/teaching/bases/{br["id"]}').json()['source_status'] == 'current'
    row=approve(client,ids,h,session(client,ids,h,br))
    invalid=retry(session_revision_id=row['revision_id'],learner_id=ids['a'],content={**brief_content(),'steps':['','','']})
    assert client.post(base(ids)+'/teaching/briefs',headers=h,json=invalid).status_code == 422
    assert client.post(base(ids)+'/teaching/sessions',headers=h,json=retry(basis_id=br['id'],owner_id=ids['assistant'],content=content())).status_code == 403
    for user in ('tech','guardian'):
        login(client,user)
        assert client.get(base(ids)+f'/teaching/sessions/{row["id"]}').status_code == 403
    login(client)
    assert client.get(f'/api/v1/schools/{ids["other_school"]}/teaching/sessions/{row["id"]}').status_code == 403


from plans_fixtures import support_case,decision_payload

def test_multicategory_delivery_list_duplicates(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    ga,_=ordinary_goal(client,ids,h)
    payload=actual(ids,{'a':ga})
    payload['participants'].append({**payload['participants'][0], 'category':'personal_assistance','minutes':10})
    payload['staff']=[{**payload['staff'][0],'minutes':20},{**payload['staff'][0],'category':'personal_assistance','minutes':10}]
    saved=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload))
    assert saved.status_code == 201,saved.text
    listed=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-deliveries').json()
    assert listed['total'] == 1 and len({x['id'] for x in listed['items']}) == 1,listed
    second=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual(ids,{'a':ga})));assert second.status_code == 201,second.text
    page1=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-deliveries',params={'offset':0,'limit':1}).json()
    page2=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-deliveries',params={'offset':1,'limit':1}).json()
    assert page1['total'] == page2['total'] == 2
    assert {page1['items'][0]['id'],page2['items'][0]['id']} == {saved.json()['id'],second.json()['id']}


def test_absent_learner_stafftime_is_counted_as_support(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    case=support_case(client,factory,ids,h)
    payload=decision_payload(binding)
    payload['provisions'][0].update(category='personal_assistance',counting_basis='staff_time')
    path=base(ids)+f'/support-cases/{case["id"]}/decisions'
    response=client.post(path,headers=h,json=payload);assert response.status_code == 201,response.text
    row=response.json();response=client.post(path+'/'+row['id']+'/confirm',headers=h,json=expected(row,reason='Synthetic staff-time provision reviewed'))
    assert response.status_code == 200,response.text
    decision=response.json()
    ga,_=ordinary_goal(client,ids,h)
    payload=actual(ids,{'a':ga})
    reference={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']}
    payload['participants'][0].update(status='absent',minutes=0,category='personal_assistance',provision=reference,counting_basis='staff_time',attributed_staff_minutes=30)
    payload['staff'][0].update(staff_id=ids['assistant'],category='personal_assistance',role='Assistant')
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload))
    assert response.status_code in {409,422},response.text

def test_only_assistant_staff_can_be_classified_as_ito(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    case=support_case(client,factory,ids,h)
    from plans_fixtures import confirmed_decision
    decision=confirmed_decision(client,ids,h,case,binding)
    ga,_=ordinary_goal(client,ids,h)
    payload=actual(ids,{'a':ga})
    payload['participants'][0].update(provision={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']},counting_basis='learner_time')
    payload['participants'][0]['category']='individually_adapted_education'
    payload['staff'][0].update(staff_id=ids['assistant'],category='individually_adapted_education',role='Assistant')
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload))
    assert response.status_code in {403,409,422},response.text

def test_actual_input_can_reconcile_superseded_delivery(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    ga,_=ordinary_goal(client,ids,h)
    br=basis(client,ids,h,{'a':ga});row=approve(client,ids,h,session(client,ids,h,br));guide,assignment=assigned_brief(client,ids,h,row)
    ah=login(client,'assistant')
    inp=client.post(base(ids)+f'/teaching/brief-assignments/{assignment["id"]}/actual-inputs',headers=ah,json=retry(content={'occurred_at':(utcnow()-timedelta(hours=1)).replace(microsecond=0).isoformat(),'duration_minutes':30,'status':'participated','category':'ordinary_teaching','activity':'Read cards','support':'Visual cue'}))
    assert inp.status_code == 201,inp.text
    h=login(client)
    payload=actual(ids,{'a':ga},row,occurred_at=inp.json()['occurred_at'])
    saved=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert saved.status_code==201,saved.text
    corrected={**payload,'status':'cancelled','duration_minutes':0,'staff':[],'cause':'learner_absence','follow_up_owner_id':ids['reviewer'],'follow_up':'Review absence','participants':[{**payload['participants'][0],'minutes':0,'status':'absent'}]}
    correction=client.post(base(ids)+f'/teaching/deliveries/{saved.json()["id"]}/corrections',headers=h,json=expected(saved.json(),content=corrected,reason='Original entry was incorrect; pupil absent'))
    assert correction.status_code==200,correction.text
    reconciled=client.post(base(ids)+f'/teaching/actual-inputs/{inp.json()["id"]}/review',headers=h,json=expected(inp.json(),outcome='recorded',delivery_revision_id=saved.json()['revision_id'],reason='Reconcile against old revision'))
    assert reconciled.status_code==409,reconciled.text

def test_repaired_session_resurfaces_retired_source_followup_resolution(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h)
    ga,_=ordinary_goal(client,ids,h)
    selected=retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[ga],'sources':[binding]}])
    br=client.post(base(ids)+'/teaching/bases',headers=h,json=selected).json()
    row=session(client,ids,h,br)
    # Revoke the actor's source read while retaining teaching write/read.
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'])):
            assignment.actions=[a for a in assignment.actions if a != 'evidence.read']
    path=base(ids)+f'/teaching/sessions/{row["id"]}'
    assert client.get(path).json()['content'] is None
    followups=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    task=next(x for x in followups if x['target_type']=='session')
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'])):assignment.actions=list(assignment.actions)+['evidence.read']
    result=client.post(base(ids)+f'/teaching/follow-ups/{task["id"]}/resolve',headers=h,json=expected(task,resolution='Source-derived sensitive statement from retired basis'))
    assert result.status_code==200,result.text
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id==ids['reviewer'])):assignment.actions=[a for a in assignment.actions if a!='evidence.read']
    masked=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    assert next(x for x in masked if x['id']==task['id'])['resolution'] is None
    fresh=basis(client,ids,h,{'a':ga})
    revised=client.post(path+'/revisions',headers=h,json=expected(row,basis_id=fresh['id'],owner_id=ids['reviewer'],content=content(),reason='Independent plan without retired source'))
    assert revised.status_code==201,revised.text
    tasks=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    task=next(x for x in tasks if x['id']==task['id'])
    assert task['resolution'] is None
    assert task['source_status']=='review_required'




def test_absence_records_staff_expenditure_without_delivered_support(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h)
    payload=decision_payload(binding);payload['provisions'][0].update(category='personal_assistance',counting_basis='staff_time')
    path=base(ids)+f'/support-cases/{case["id"]}/decisions'
    result=client.post(path,headers=h,json=payload);assert result.status_code == 201,result.text
    decision=client.post(path+'/'+result.json()['id']+'/confirm',headers=h,json=expected(result.json(),reason='Reviewed the synthetic assistance provision')).json()
    goal,_=ordinary_goal(client,ids,h)
    actual_work=actual(ids,{'a':goal})
    actual_work['participants'][0].update(status='absent',minutes=0,category='personal_assistance',counting_basis='staff_time',attributed_staff_minutes=0,provision={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']})
    actual_work['staff'][0].update(staff_id=ids['assistant'],category='personal_assistance',role='Waited at the agreed location')
    assert client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual_work)).status_code == 422
    actual_work.update(status='partial',cause='learner_absence',follow_up_owner_id=ids['reviewer'],follow_up='Review the missed pupil support separately from actual staff cost')
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual_work));assert response.status_code == 201,response.text
    assert response.json()['staff_minutes'] == 30 and response.json()['participants'][0]['minutes'] == 0
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()}).json()
    assert summary['provisions'][0]['recorded_minutes'] == 0
    assert summary['provisions'][0]['unassessed_claimed_minutes'] == 0
    actual_work['participants'][0].update(status='partial',minutes=10,attributed_staff_minutes=30)
    assert client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=actual_work)).status_code == 422
    assert client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['total'] == 1


def test_reconciliation_reopens_after_correction_and_keeps_exact_review_history(teaching_env):
    client,factory,app,ids=teaching_env;h=login(client)
    goal,_=ordinary_goal(client,ids,h);br=basis(client,ids,h,{'a':goal});row=approve(client,ids,h,session(client,ids,h,br));_,assigned=assigned_brief(client,ids,h,row)
    ah=login(client,'assistant');when=(utcnow()-timedelta(hours=1)).replace(microsecond=0).isoformat()
    result=client.post(base(ids)+f'/teaching/brief-assignments/{assigned["id"]}/actual-inputs',headers=ah,json=retry(content={'occurred_at':when,'duration_minutes':30,'status':'participated','category':'ordinary_teaching','activity':'Actually read the cards','support':'A visual cue'}));assert result.status_code == 201,result.text
    entry=result.json();h=login(client)
    payload=actual(ids,{'a':goal},row,occurred_at=when)
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert response.status_code == 201,response.text
    delivered=response.json()
    command=expected(entry,outcome='recorded',delivery_revision_id=delivered['revision_id'],reason='Exact original actual record checked')
    response=client.post(base(ids)+f'/teaching/actual-inputs/{entry["id"]}/review',headers=h,json=command);assert response.status_code == 200,response.text
    assert response.json()['currently_reconciled'] and len(response.json()['review_history']) == 1
    cancellation={**payload,'status':'cancelled','duration_minutes':0,'staff':[],'cause':'learner_absence','follow_up_owner_id':ids['reviewer'],'follow_up':'Review the incorrect recorded event','participants':[{**payload['participants'][0],'status':'absent','minutes':0}]}
    corrected=client.post(base(ids)+f'/teaching/deliveries/{delivered["id"]}/corrections',headers=h,json=expected(delivered,content=cancellation,reason='The actual event was cancelled'));assert corrected.status_code == 200,corrected.text
    assert client.post(base(ids)+f'/teaching/actual-inputs/{entry["id"]}/review',headers=h,json=command).status_code == 409
    listed=client.get(base(ids)+f'/teaching/brief-assignments/{assigned["id"]}/actual-inputs').json()['items'][0]
    assert listed['state'] == 'needs_clarification' and not listed['currently_reconciled']
    assert listed['delivery_revision_id'] == delivered['revision_id'] and listed['invalidated_by_revision_id'] == corrected.json()['revision_id']
    assert listed['review_history'][0]['reason'] == 'Exact original actual record checked' and listed['review_history'][0]['historical']
    # A deliberate new matching actual correction can be reconciled anew; its
    # review supplements rather than overwrites the historical review.
    restored=client.post(base(ids)+f'/teaching/deliveries/{delivered["id"]}/corrections',headers=h,json=expected(corrected.json(),content=payload,reason='Verified the actual work with the original participant'));assert restored.status_code == 200,restored.text
    reviewed=client.post(base(ids)+f'/teaching/actual-inputs/{entry["id"]}/review',headers=h,json=expected(listed,outcome='recorded',delivery_revision_id=restored.json()['revision_id'],reason='Exact replacement actual record checked'));assert reviewed.status_code == 200,reviewed.text
    assert reviewed.json()['currently_reconciled'] and len(reviewed.json()['review_history']) == 2
    assert reviewed.json()['review_history'][0]['delivery_revision_id'] == delivered['revision_id']


def test_ito_requires_exact_reviewed_qualification_port_and_supports_unassessed_recovery(teaching_env):
    from plans_fixtures import confirmed_decision
    from teaching_fixtures import SyntheticQualificationPort
    client,factory,app,ids=teaching_env;h=login(client)
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h);decision=confirmed_decision(client,ids,h,case,binding)
    goal,_=ordinary_goal(client,ids,h)
    payload=actual(ids,{'a':goal});ref={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']}
    payload['participants'][0].update(category='individually_adapted_education',provision=ref,counting_basis='learner_time')
    payload['staff'][0].update(category='individually_adapted_education',role='Claimed qualified professional')
    endpoint=base(ids)+'/teaching/deliveries'
    assert client.post(endpoint,headers=h,json=retry(content=payload)).status_code == 409
    port=SyntheticQualificationPort(ids);app.state.teaching_qualification_port=port
    for mode in ('mismatched','missing_sources','future_review'):
        port.mode=mode
        bad=client.post(endpoint,headers=h,json=retry(content=payload));assert bad.status_code == 409,bad.text
    port.mode='reviewed'
    response=client.post(endpoint,headers=h,json=retry(content=payload));assert response.status_code == 201,response.text
    recorded=response.json();assert recorded['participants'][0]['support_assessment'] == 'assessed'
    request=port.requests[-1]
    assert str(request.school_id) == ids['school'] and str(request.staff_id) == ids['reviewer'] and str(request.provision_id) == ref['provision_id']
    assert str(request.decision_revision_id) == ref['decision_revision_id'] and request.occurred_at.isoformat() == payload['occurred_at']
    params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()}
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params=params).json()
    assert summary['provisions'][0]['recorded_minutes'] == 30
    port.mode='unavailable'
    stale=client.get(base(ids)+f'/teaching/deliveries/{recorded["id"]}').json()
    assert stale['participants'][0]['support_assessment'] == 'unassessed'
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params=params).json()
    assert summary['provisions'][0]['recorded_minutes'] is None and summary['provisions'][0]['unassessed_claimed_minutes'] == 30
    # A caller's forged professional title cannot override the owning record.
    port.mode='reviewed';payload['staff'][0]['staff_id']=ids['assistant']
    assert client.post(endpoint,headers=h,json=retry(content=payload)).status_code == 409
    payload['participants'][0]['support_status']='unassessed'
    payload.update(status='partial',cause='staff_unavailable',follow_up_owner_id=ids['reviewer'],follow_up='Obtain the staffing competence basis and assess missed teaching separately')
    unassessed=client.post(endpoint,headers=h,json=retry(content=payload));assert unassessed.status_code == 201,unassessed.text
    assert unassessed.json()['staff_minutes'] == 30 and not unassessed.json()['staff_labels_prove_qualification']
    assert unassessed.json()['participants'][0]['support_assessment'] == 'unassessed'
    tasks=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    assert {t['reason_code'] for t in tasks} == {'delivery_deviation','staffing_basis_changed'}


def test_ito_stafftime_cannot_include_unqualified_assistant_cost(teaching_env):
    from teaching_fixtures import SyntheticQualificationPort
    client,factory,app,ids=teaching_env;h=login(client)
    binding,_=evidence(client,ids,h);case=support_case(client,factory,ids,h)
    decision_request=decision_payload(binding);decision_request['provisions'][0]['counting_basis']='staff_time'
    path=base(ids)+f'/support-cases/{case["id"]}/decisions'
    result=client.post(path,headers=h,json=decision_request);assert result.status_code == 201,result.text
    decision=client.post(path+'/'+result.json()['id']+'/confirm',headers=h,json=expected(result.json(),reason='Checked the exact synthetic staff-time ITO basis')).json()
    goal,_=ordinary_goal(client,ids,h);payload=actual(ids,{'a':goal})
    payload['participants'][0].update(category='individually_adapted_education',provision={'decision_id':decision['id'],'decision_revision_id':decision['content']['id'],'provision_id':decision['provisions'][0]['id']},counting_basis='staff_time',attributed_staff_minutes=60)
    payload['staff'][0]['category']='individually_adapted_education'
    payload['staff'].append({**payload['staff'][0],'staff_id':ids['assistant'],'role':'Assistant support'})
    app.state.teaching_qualification_port=SyntheticQualificationPort(ids)
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert response.status_code == 409,response.text
    payload['participants'][0]['attributed_staff_minutes']=30
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert response.status_code == 201,response.text
    assert response.json()['staff_minutes'] == 60
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()}).json()
    assert summary['provisions'][0]['recorded_minutes'] == 30


@pytest.mark.parametrize('change',['source_correction','goal_replacement','model_recall','policy_recall'])
def test_follow_up_resolution_keeps_original_dependencies_after_independent_revision(teaching_env,teaching_wire_server,change):
    from spesped.contexts.platform import service as gateway
    from spesped.contexts.platform.models import ModelRelease,ProcessingPolicy
    client,factory,app,ids=teaching_env;h=login(client)
    binding,item=evidence(client,ids,h);goal,plan=ordinary_goal(client,ids,h)
    command=retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(),duration_minutes=30,arena='Synthetic room',learners=[{'learner_id':ids['a'],'goal_revision_ids':[goal],'sources':[binding]}])
    result=client.post(base(ids)+'/teaching/bases',headers=h,json=command);assert result.status_code == 201,result.text
    original=session(client,ids,h,result.json());path=base(ids)+f'/teaching/sessions/{original["id"]}'
    if change in {'model_recall','policy_recall'}:
        runtime,policy,release=configure_ai(factory,app,ids,teaching_wire_server)
        queued=client.post(path+'/suggestions',headers=h,json=retry(policy_id=policy,release_id=release)).json()
        completed=gateway.run_job(factory,Actor(ids['reviewer']),ids['school'],queued['id'],queued['version'],runtime);assert completed.state == 'succeeded'
        applied=client.post(path+'/suggestions/review',headers=h,json=expected(original,job_id=queued['id'],outcome='accepted',selected_fields=['preparation'],reason='Explicitly selected AI preparation'))
        assert applied.status_code == 200,applied.text
        original=applied.json()
    def source_permission(enabled):
        with factory.begin() as db:
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == ids['reviewer'])):
                values=[a for a in assignment.actions if a != 'evidence.read']
                assignment.actions=values+(['evidence.read'] if enabled else [])
    source_permission(False)
    assert client.get(path).json()['content'] is None
    tasks=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    task=next(t for t in tasks if t['target_type'] == 'session')
    assert task['dependency_binding']['session_revision_id'] == original['revision_id']
    source_permission(True)
    resolve_command=expected(task,resolution='Sensitive historical source interpretation reviewed in the exact original session context')
    resolved=client.post(base(ids)+f'/teaching/follow-ups/{task["id"]}/resolve',headers=h,json=resolve_command)
    assert resolved.status_code == 200 and resolved.json()['resolution'],resolved.text
    if change == 'source_correction':
        correction={'expected_version':item['version'],'learner_id':ids['b'],'claim_type':'report','reporter':'Synthetic authority','source_type':'imported_document','certainty':'confirmed','occurred_at':item['occurred_at'],'topic':'education','content':'Correct association for the other synthetic pupil','reason':'Correct the original pupil association','excerpt_page':item['source']['page'],'excerpt_start':item['source']['span_start'],'excerpt_end':item['source']['span_end']}
        changed=client.post(base(ids)+f'/evidence/{item["id"]}/corrections',headers=h,json=correction);assert changed.status_code == 200,changed.text
    elif change == 'goal_replacement':
        revised=plan_payload();revised.pop('kind');revised['expected_version']=plan['version']
        revised['effective_from']=utcnow().isoformat();revised['goals'][0]['effective_from']=revised['effective_from']
        revised['goals'][0]['title']='Independent replacement goal'
        changed=client.post(base(ids)+f'/education-plans/{plan["id"]}/revisions',headers=h,json=revised);assert changed.status_code == 201,changed.text
        replacement=activate(client,ids,h,changed.json());goal=replacement['content']['goals'][0]['id']
    else:
        model,record_id=(ModelRelease,release) if change == 'model_recall' else (ProcessingPolicy,policy)
        with factory() as db:version=db.get(model,record_id).version
        kind='release' if change == 'model_recall' else 'policy'
        changed=client.post(base(ids)+f'/ai/configuration/{kind}/{record_id}/revoke',headers=h,json={'expected_version':version});assert changed.status_code == 200,changed.text
    fresh=basis(client,ids,h,{'a':goal})
    replaced=client.post(path+'/revisions',headers=h,json=expected(original,basis_id=fresh['id'],owner_id=ids['reviewer'],content=content(),manual_replacements=list(content()),reason='Independent manually selected content with a fresh basis'))
    assert replaced.status_code == 201 and replaced.json()['content'],replaced.text
    listed=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-follow-ups').json()['items']
    historical=next(t for t in listed if t['id'] == task['id'])
    assert historical['dependency_binding']['session_revision_id'] == original['revision_id']
    assert historical['resolution'] is None and historical['source_status'] == 'review_required'
    replayed=client.post(base(ids)+f'/teaching/follow-ups/{task["id"]}/resolve',headers=h,json=resolve_command)
    assert replayed.status_code == 200 and replayed.json()['resolution'] is None,replayed.text


def test_forward_migration_keeps_legacy_follow_up_lineage_unknown(env,tmp_path):
    from alembic import command as migrations
    from alembic.config import Config
    from pathlib import Path
    from sqlalchemy import text,inspect,create_engine
    from sqlalchemy.engine import make_url
    from spesped.cli import provision_school
    from spesped.contexts.identity.models import Learner
    from spesped.db import make_session_factory
    _,original_factory,_,_=env
    admin=None;schema=None
    if original_factory.kw['bind'].dialect.name == 'postgresql':
        original_url=original_factory.kw['bind'].url
        assert original_url.database == 'spesped_test'
        admin=create_engine(original_url);schema='j06_legacy_'+uuid4().hex
        with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=original_url.update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    else:url=f'sqlite:///{tmp_path}/legacy-migration.db'
    factory=make_session_factory(url)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    try:
        migrations.upgrade(config,'j06_teaching')
        task_id=str(uuid4());now=utcnow()
        with factory.begin() as db:
            school,leader=provision_school(db,school_name='Synthetic legacy repair',kind='public',timezone='Europe/Oslo',email='legacy@example.invalid',display_name='Synthetic legacy reviewer',password='synthetic-migration-passphrase')
            learner=Learner(school_id=school.id,display_name='Synthetic legacy pupil',grade=4,group_name='Synthetic');db.add(learner);db.flush()
            sid,lid,uid=school.id,learner.id,leader.id
            db.add(AuthorityGrant(school_id=sid,user_id=uid,action='teaching.read',learner_id=lid,valid_from=date.today()-timedelta(days=1),granted_by=uid))
            db.execute(text('INSERT INTO teaching_follow_ups (id,school_id,learner_id,target_type,target_id,reason_code,owner_id,action,resolution,version,state,created_at,updated_at) VALUES (:id,:school,:learner,:type,:target,:reason,:owner,:action,:resolution,1,:state,:now,:now)'),{'id':task_id,'school':sid,'learner':lid,'type':'session','target':str(uuid4()),'reason':'basis_changed','owner':uid,'action':'Review the historical affected session','resolution':'Legacy sensitive statement with an unknown original basis','state':'resolved','now':now.isoformat()})
        from sqlalchemy import Table,MetaData
        delivery_id,actual_revision_id,participation_id=str(uuid4()),str(uuid4()),str(uuid4())
        with factory.begin() as db:
            metadata=MetaData()
            root=Table('teaching_deliveries',metadata,autoload_with=db.connection())
            actual_revision=Table('teaching_delivery_revisions',metadata,autoload_with=db.connection())
            participation=Table('teaching_learner_participation',metadata,autoload_with=db.connection())
            staff=Table('teaching_staff_participation',metadata,autoload_with=db.connection())
            db.execute(root.insert().values(id=delivery_id,school_id=sid,version=1,state='delivered',current_revision=1,created_at=now,updated_at=now))
            db.execute(actual_revision.insert().values(id=actual_revision_id,school_id=sid,delivery_id=delivery_id,revision=1,occurred_at=now-timedelta(hours=1),duration_minutes=30,status='delivered',activity='Legacy actual work without qualification evidence',cause_detail='',reason='Original legacy entry',recorded_by=uid,created_at=now))
            db.execute(participation.insert().values(id=participation_id,school_id=sid,delivery_revision_id=actual_revision_id,learner_id=lid,goal_revision_ids=[],status='participated',minutes=30,category='individually_adapted_education',support='Legacy reported visual support',created_at=now))
            db.execute(staff.insert().values(id=str(uuid4()),school_id=sid,delivery_revision_id=actual_revision_id,staff_id=uid,minutes=30,role='Legacy claimed professional teacher',category='individually_adapted_education',created_at=now))
        migrations.upgrade(config,'j06_teaching_repairs')
        with factory() as db:
            from spesped.contexts.teaching.models import LearnerParticipation
            legacy=db.get(LearnerParticipation,participation_id)
            assert legacy.support_status == 'unassessed' and legacy.qualification_binding is None
            summary=service.delivery_summary(db,Actor(uid),sid,lid,now-timedelta(days=1),now)
            assert summary['unassessed_claimed_minutes_by_category']['individually_adapted_education'] == 30
            assert not summary['assessed_minutes_by_category']
            task=db.get(TeachingFollowUp,task_id)
            assert task.dependency_binding is None and task.dependency_key == 'legacy:'+task_id
            view=service.follow_up_view(db,Actor(uid),task)
            assert view['resolution'] is None and view['source_status'] == 'review_required'
            checks=inspect(db.connection()).get_check_constraints('teaching_follow_ups')
            assert any('resolved' in c['sqltext'] for c in checks)
            checks=inspect(db.connection()).get_check_constraints('teaching_learner_participation')
            assert any('minutes' in c['sqltext'] for c in checks)
        migrations.downgrade(config,'j06_teaching')
        migrations.upgrade(config,'j06_teaching_repairs')
        with factory() as db:
            assert db.get(TeachingFollowUp,task_id).dependency_binding is None
            assert 'teaching_actual_input_reviews' in inspect(db.connection()).get_table_names()
        with factory() as db:
            mutate(db,lambda:service.follow_up(db,Actor(uid),sid,lid,'delivery_revision',actual_revision_id,'staffing_basis_changed',uid,'Review the unassessed historical staffing basis'))
        with pytest.raises(RuntimeError,match='cannot be discarded'):
            migrations.downgrade(config,'j06_teaching')
    finally:
        factory.kw['bind'].dispose()
        if admin:
            with admin.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def test_postgres_actual_correction_and_reconciliation_serialize(teaching_env):
    client,factory,app,ids=teaching_env
    if factory.kw['bind'].dialect.name != 'postgresql':pytest.skip('PostgreSQL actual/reconciliation lock ordering')
    h=login(client);goal,_=ordinary_goal(client,ids,h)
    br=basis(client,ids,h,{'a':goal});row=approve(client,ids,h,session(client,ids,h,br));_,assigned=assigned_brief(client,ids,h,row)
    ah=login(client,'assistant');when=(utcnow()-timedelta(hours=1)).replace(microsecond=0).isoformat()
    response=client.post(base(ids)+f'/teaching/brief-assignments/{assigned["id"]}/actual-inputs',headers=ah,json=retry(content={'occurred_at':when,'duration_minutes':30,'status':'participated','category':'ordinary_teaching','activity':'Read the cards','support':'Visual cue'}));assert response.status_code == 201,response.text
    entry=response.json();h=login(client)
    payload=actual(ids,{'a':goal},row,occurred_at=when)
    response=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert response.status_code == 201,response.text
    delivered=response.json();barrier=Barrier(2)
    cancelled={**payload,'status':'cancelled','duration_minutes':0,'staff':[],'participants':[{**payload['participants'][0],'status':'absent','minutes':0}],'cause':'learner_absence','follow_up_owner_id':ids['reviewer'],'follow_up':'Review the incorrect actual record'}
    def correction():
        barrier.wait()
        return client.post(base(ids)+f'/teaching/deliveries/{delivered["id"]}/corrections',headers=h,json=expected(delivered,content=cancelled,reason='Verified cancellation'))
    def review():
        barrier.wait()
        return client.post(base(ids)+f'/teaching/actual-inputs/{entry["id"]}/review',headers=h,json=expected(entry,outcome='recorded',delivery_revision_id=delivered['revision_id'],reason='Review the exact original actual revision'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(correction);b=pool.submit(review);changed,reviewed=a.result(),b.result()
    assert changed.status_code == 200,changed.text
    assert reviewed.status_code in {200,409},reviewed.text
    listed=client.get(base(ids)+f'/teaching/brief-assignments/{assigned["id"]}/actual-inputs').json()['items'][0]
    assert not listed['currently_reconciled'] and listed['state'] != 'recorded'
    assert client.get(base(ids)+f'/teaching/deliveries/{delivered["id"]}').json()['state'] == 'cancelled'
