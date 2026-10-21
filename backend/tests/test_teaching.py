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
    payload['participants'][0].update(category='individually_adapted_education',provision=reference,counting_basis='learner_time')
    payload['staff'][0]['category']='individually_adapted_education'
    recorded=client.post(base(ids)+'/teaching/deliveries',headers=h,json=retry(content=payload));assert recorded.status_code == 201,recorded.text
    summary=client.get(base(ids)+f'/learners/{ids["a"]}/teaching-summary',params={'start':(utcnow()-timedelta(days=1)).isoformat(),'end':utcnow().isoformat()})
    assert summary.status_code == 200,summary.text
    values=summary.json();assert values['provisions'][0]['recorded_minutes'] == 30
    assert values['provisions'][0]['comparison'] == 'different_reference_period' and values['entitlement_fulfilment'] == 'unassessed'
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
