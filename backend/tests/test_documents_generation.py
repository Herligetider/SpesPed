from sqlalchemy import select
from documents_fixtures import generated_documents,document_wire,documents_env,assessment_env,curriculum_env,teaching_env,env,login,path,retry,expected,key,base,revised
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.contexts.platform.models import ModelRelease

def generate(e):
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestions',headers=e.h,json=expected(e.row,revision_id=e.row['revision_id'],policy_id=e.policy,release_id=e.release));assert response.status_code==201,response.text;job=response.json()
    response=e.client.post(base(e.ids)+f'/ai/jobs/{job["id"]}/run',headers=e.h,json={'expected_version':job['version']});assert response.status_code==200,response.text;return response.json()
def diff(e,job):
    response=e.client.get(path(e.ids)+f'/cases/{e.row["id"]}/suggestions/{job["id"]}/diff');assert response.status_code==200,response.text;return response.json()
def selection(e,p):return expected(e.row,revision_id=p['revision_id'],job_id=p['job_id'],proposal_digest=p['proposal_digest'],selected_sections=['body'],select_subject=True,outcome='applied',reason='Human selected exact proposal and reviews factual source manifest')

def test_native_basis_loopback_typed_selection_manual_lineage_recall(generated_documents):
    e=generated_documents;job=generate(e);assert job['state']=='succeeded',job
    p=diff(e,job);command=selection(e,p)
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=command);assert response.status_code==200,response.text;row=response.json()
    assert row['state']=='draft' and row['revision']['content']['subject']=='Synthetic editable period email'
    assert row['revision']['lineage']['body']['job_id']==job['id'] and row['revision']['approval'] is None
    assert row['revision']['content']['sections'][0]['missing_inputs']==['Human professional conclusion required']
    e.row=row;row=revised(e.client,e.ids,e.h,row)
    assert row['revision']['lineage']['body']['job_id']==job['id']
    with e.factory.begin() as db:db.get(ModelRelease,e.release).state='revoked'
    response=e.client.get(path(e.ids)+f'/cases/{row["id"]}');assert response.status_code==200,response.text
    assert response.json()['revision']['content'] is None
    response=e.client.post(path(e.ids)+f'/cases/{row["id"]}/suggestion-review',headers=e.h,json=command)
    assert response.status_code in {403,409} or (response.status_code==200 and response.json()['revision']['content'] is None)
    history=e.client.get(path(e.ids)+f'/cases/{row["id"]}/revisions').json()['items'];assert history[0]['content'] is not None and history[-1]['content'] is None

def test_invalid_missing_provider_and_stale_selection_preserve_manual_draft(generated_documents):
    e=generated_documents;e.wire.mode='rights';job=generate(e);assert job['state']!='succeeded'
    response=e.client.get(path(e.ids)+f'/cases/{e.row["id"]}/suggestions/{job["id"]}/diff');assert response.status_code==409
    assert e.client.get(path(e.ids)+f'/cases/{e.row["id"]}').json()['revision_id']==e.row['revision_id']
    e.wire.mode='foreign_section';job=generate(e);assert job['state']=='succeeded'
    assert e.client.get(path(e.ids)+f'/cases/{e.row["id"]}/suggestions/{job["id"]}/diff').status_code==409
    e.wire.mode='unavailable';job=generate(e);assert job['state']!='succeeded'
    e.wire.mode='ok';job=generate(e);p=diff(e,job);command=selection(e,p);e.row=revised(e.client,e.ids,e.h,e.row)
    assert e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=command).status_code==409

def test_generation_identity_revoked_request_replay_read_and_application(generated_documents):
    e=generated_documents;job=generate(e);p=diff(e,job);command=selection(e,p)
    with e.factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id==e.ids['reviewer'],AuthorityGrant.action=='ai.guardian_email_drafting'));grant.state='revoked'
    assert e.client.get(path(e.ids)+f'/cases/{e.row["id"]}/suggestions/{job["id"]}/diff').status_code==403
    assert e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=command).status_code==403

def ai_schedule(e):
    from test_documents import schedule
    return schedule(e.client,e.ids,e.h,generation_mode='local_ai',policy_id=e.policy,release_id=e.release,owner_id=e.ids['reviewer'])
def run_ai_schedule(e,row):
    response=e.client.post(path(e.ids)+f'/schedules/{row["id"]}/run',headers=e.h,json=expected(row));assert response.status_code==200,response.text
    row=response.json();request=row['runs'][0]['generation_requests'][0]
    assert row['runs'][0]['summary']['ai_generation']=='requested' and request['state']=='pending'
    return row,request

def test_scheduled_ai_durable_restart_lost_reply_one_job_no_auto_application(generated_documents,monkeypatch):
    from sqlalchemy import func
    from spesped.contexts.documents import generation,models as m
    from spesped.contexts.platform import service as gateway
    from spesped.contexts.platform.models import GenerationJob
    from spesped.db import make_session_factory
    e=generated_documents;row,request=run_ai_schedule(e,ai_schedule(e));original=gateway.create_job;calls=[]
    def lost(*args,**kwargs):
        job=original(*args,**kwargs);calls.append(job.id)
        raise RuntimeError('Synthetic acknowledgement lost after durable gateway commit')
    monkeypatch.setattr(gateway,'create_job',lost)
    first=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime)
    assert first['state']=='pending' and first['reason_code']=='gateway_reply_unknown'
    monkeypatch.setattr(gateway,'create_job',original)
    restarted=make_session_factory(e.factory.kw['bind'].url.render_as_string(hide_password=False))
    try:
        outcome=generation.process_scheduled_generation(restarted,e.ids['school'],request['id'],e.runtime);assert outcome['state']=='succeeded',outcome
        repeated=generation.process_scheduled_generation(restarted,e.ids['school'],request['id'],e.runtime);assert repeated['job_id']==outcome['job_id'] and repeated['state']=='succeeded'
        assert calls==[outcome['job_id']]
        with restarted() as db:
            assert db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.logical_request_key==request['logical_key']))==1
            rev=db.get(m.DocumentRevision,request['revision_id']);assert rev.content['sections'][0]['text'] is None and not rev.lineage
        # The processor requests/generates only. A human can inspect and select
        # the exact completed output through the ordinary document proposal API.
        response=e.client.get(path(e.ids)+f'/cases/{request["document_id"]}/suggestions/{outcome["job_id"]}/diff');assert response.status_code==200,response.text
    finally:restarted.kw['bind'].dispose()

def test_scheduled_ai_enqueue_atomic_and_recalled_release_keeps_manual_editor(generated_documents,monkeypatch):
    import pytest
    from sqlalchemy import func
    from spesped.contexts.documents import service as svc,generation,models as m
    from spesped.contexts.identity.models import AuditRecord
    e=generated_documents;row=ai_schedule(e);original=svc.event
    models=(m.DocumentCase,m.DocumentRevision,m.EvidenceSnapshot,m.DraftRun,m.ScheduledGenerationRequest,m.DocumentCommand,m.DocumentEvent,AuditRecord)
    with e.factory() as db:before=tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    def fail(db,actor,aggregate,action,**payload):
        if action=='documents.scheduled_generation.requested':raise RuntimeError('Synthetic durable handoff audit failure')
        return original(db,actor,aggregate,action,**payload)
    monkeypatch.setattr(svc,'event',fail)
    with pytest.raises(RuntimeError):run_ai_schedule(e,row)
    with e.factory() as db:after=tuple(db.scalar(select(func.count()).select_from(model)) for model in models)
    assert before==after
    monkeypatch.setattr(svc,'event',original);row,request=run_ai_schedule(e,row)
    with e.factory.begin() as db:db.get(ModelRelease,e.release).state='revoked'
    outcome=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime);assert outcome['state']=='blocked',outcome
    current=e.client.get(path(e.ids)+f'/cases/{request["document_id"]}').json();assert current['state']=='draft' and current['revision']['content'] is not None and current['revision']['approval'] is None
    response=e.client.get(path(e.ids)+f'/schedules/{row["id"]}');assert response.status_code==200,response.text
    assert response.json()['runs'][0]['generation_requests'][0]['state']=='blocked'

def test_scheduled_ai_changed_plan_owner_or_source_blocks_before_execution(generated_documents):
    from spesped.contexts.documents import generation
    from spesped.contexts.identity.models import UserAccount
    e=generated_documents;row,request=run_ai_schedule(e,ai_schedule(e))
    with e.factory.begin() as db:db.get(UserAccount,e.ids['reviewer']).state='inactive'
    outcome=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime);assert outcome['state']=='blocked' and outcome['job_id'] is None,outcome

def test_native_report_template_sources_are_resolved_in_fresh_gateway_worker(generated_documents):
    from dataclasses import replace
    from uuid import uuid4
    from documents_fixtures import template,create
    from spesped.auth import Actor
    from spesped.contexts.platform import service as gateway
    from spesped.contexts.platform.contracts import SourceRef,SourceInput,EvaluationCase,PolicyCommand,ReleaseCommand,ReviewCommand
    e=generated_documents;t=template(e.client,e.ids,e.h,sections=[{'key':'body','label':'Human report','required':True}]);e.row=create(e.client,e.ids,e.h,kind='local_semester_report',template_revision_id=t['revision_id'])
    provider=next(iter(e.runtime.providers.values()));purpose='report_drafting'
    source=SourceInput(SourceRef(kind='document_basis',source_id=uuid4(),revision=1),e.ids['school'],e.ids['a'],purpose,'Synthetic report basis',provenance='synthetic_fixture',provenance_reference='fixture:report.v1')
    e.runtime=replace(e.runtime,evaluation_suites={'report-v1':(EvaluationCase('human-report',purpose,(source,),('Synthetic editable period email',)),)})
    with e.factory() as db:
        actor=Actor(e.ids['reviewer']);policy=gateway.create_policy(db,actor,e.ids['school'],PolicyCommand(provider_key=provider.key,purposes=[purpose]),e.runtime)
        release=gateway.create_release(db,actor,e.ids['school'],ReleaseCommand(provider_key=provider.key,model_version='synthetic-report-v1',capability='generation',template_version='document-draft.v1',output_schema_version='document-draft.v1'),e.runtime)
        evaluation=gateway.evaluate_release(db,actor,e.ids['school'],release.id,release.version,policy.id,'report-v1',e.runtime);assert evaluation.state=='passed'
        release=gateway.review_release(db,actor,e.ids['school'],release.id,ReviewCommand(expected_version=release.version,evaluation_id=evaluation.id,professional_quality_confirmed=True,rationale='Synthetic report purpose evaluated separately'))
    e.app.state.ai_gateway=e.runtime;e.policy=policy.id;e.release=release.id
    job=generate(e);assert job['state']=='succeeded',job
    p=diff(e,job);assert p['proposed']['sections'][0]['key']=='body'
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=selection(e,p));assert response.status_code==200,response.text
    assert response.json()['revision']['content']['sections'][0]['text'].startswith('Synthetic source-backed')

def test_purpose_matching_assignment_authorizes_generation_lineage_and_revocation(generated_documents):
    from datetime import date
    e=generated_documents
    with e.factory.begin() as db:
        grant=db.scalar(select(AuthorityGrant).where(AuthorityGrant.user_id==e.ids['reviewer'],AuthorityGrant.action=='ai.guardian_email_drafting'));grant.state='revoked'
        assignment=StaffAssignment(school_id=e.ids['school'],learner_id=e.ids['a'],user_id=e.ids['reviewer'],purpose='guardian_email_drafting',actions=['ai.guardian_email_drafting'],valid_from=date(2020,1,1));db.add(assignment);db.flush();identity=assignment.id
    job=generate(e);assert job['state']=='succeeded',job;p=diff(e,job)
    response=e.client.post(path(e.ids)+f'/cases/{e.row["id"]}/suggestion-review',headers=e.h,json=selection(e,p));assert response.status_code==200,response.text
    row=response.json();assert row['revision']['content'] is not None and row['revision']['source_status']=='current'
    with e.factory.begin() as db:db.get(StaffAssignment,identity).state='revoked'
    response=e.client.get(path(e.ids)+f'/cases/{e.row["id"]}');assert response.status_code==200,response.text;assert response.json()['revision']['content'] is None

def test_scheduled_ai_late_source_and_pause_block_frozen_request(generated_documents):
    from datetime import timedelta
    from documents_fixtures import ordinary_goal,observation
    from spesped.contexts.documents import generation
    from spesped.db import utcnow
    e=generated_documents;goal,_=ordinary_goal(e.client,e.ids,e.h);row,request=run_ai_schedule(e,ai_schedule(e))
    observation(e.client,e.ids,e.h,goal,occurred_at=(utcnow()-timedelta(days=1)).isoformat())
    outcome=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime)
    assert outcome['state']=='blocked' and outcome['job_id'] is None,outcome
    before=e.client.get(path(e.ids)+f'/cases/{request["document_id"]}').json();assert before['revision']['source_status']=='review_required'
    row2,request2=run_ai_schedule(e,ai_schedule(e))
    response=e.client.post(path(e.ids)+f'/schedules/{row2["id"]}/state',headers=e.h,json=expected(row2,action='pause'));assert response.status_code==200,response.text
    paused=generation.process_scheduled_generation(e.factory,e.ids['school'],request2['id'],e.runtime);assert paused['state']=='blocked' and paused['job_id'] is None

def test_scheduled_ai_provider_failure_visible_manual_draft_and_explicit_same_job_retry(generated_documents):
    from spesped.contexts.documents import generation
    e=generated_documents;row,request=run_ai_schedule(e,ai_schedule(e));e.wire.mode='unavailable'
    failed=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime);assert failed['state']=='failed' and failed['job_id'],failed
    calls=len(e.wire.requests)
    replay=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime);assert replay['state']=='failed' and replay['job_id']==failed['job_id'] and len(e.wire.requests)==calls
    draft=e.client.get(path(e.ids)+f'/cases/{request["document_id"]}').json();assert draft['revision']['content'] is not None and draft['state']=='draft'
    e.wire.mode='ok';retried=generation.process_scheduled_generation(e.factory,e.ids['school'],request['id'],e.runtime,retry_failed=True)
    assert retried['state']=='succeeded' and retried['job_id']==failed['job_id'],retried
