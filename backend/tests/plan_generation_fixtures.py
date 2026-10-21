"""Only synthetic sources, real HTTP commands and a loopback model protocol."""
from datetime import date,timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from socketserver import TCPServer
from alembic import command
from alembic.config import Config
import pytest
from plans_fixtures import env,login,base,retry,expected,evidence,support_case,confirmed_decision,plan_payload,period
from spesped.auth import Actor
from spesped.db import utcnow
from spesped.assembly import EvidenceSourceResolver
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from sqlalchemy import select
from spesped.contexts.platform.contracts import GatewayRuntime,ProviderSpec,SourceRef,SourceInput,EvaluationCase,PolicyCommand,ReleaseCommand,ReviewCommand
from spesped.contexts.platform import service as gateway


def post(client,path,h,payload,status=201):
    result=client.post(path,headers=h,json=payload)
    assert result.status_code == status,result.text
    return result.json()


@pytest.fixture
def plan_wire():
    state=SimpleNamespace(mode='ok',requests=[],target=None,title='Synthetic proposed reading plan')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['content-length'])))
            state.requests.append(payload)
            if state.mode == 'unavailable':self.send_response(503);self.end_headers();return
            refs=[json.loads(v['text'])['source_ref'] for v in payload['messages'][1]['content'] if v['type'] == 'text' and 'source_ref' in json.loads(v['text'])]
            goal={'proposal_key':'reading','target_goal_id':state.target,'title':'Synthetic reading proposal','expected_action':'Practise reading a short sentence with a visual cue','arena':'Classroom','support':'Synthetic visual cards','responsibility':'Teacher','evaluation_method':'Record dated observations'}
            output={'title':state.title,'rationale':None,'organization':None,'responsibility':None,'evaluation_method':None,'goals':[goal],'source_refs':refs,'missing_evidence':['Curriculum alignment requires human review']}
            if state.mode == 'rights':output['allocations']=[{'amount':200}]
            if state.mode == 'unknown_source':output['source_refs']=['plan_basis:'+str(uuid4())+':1']
            if state.mode == 'foreign_goal':goal['target_goal_id']=str(uuid4())
            raw=json.dumps({'model':payload['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output)}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    class Server(ThreadingHTTPServer):
        def server_bind(self):TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
    server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();state.endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(3)


@pytest.fixture
def generated_env(env,plan_wire):
    client,factory,app,ids=env
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));cfg.attributes['database_url']=factory.kw['bind'].url.render_as_string(hide_password=False);command.upgrade(cfg,'j05_plan_generation')
    with factory.begin() as db:
        for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == ids['reviewer'])):assignment.actions=list(assignment.actions)+['learner.read']
        for action in ('ai.iep_drafting','platform.manage','platform.review'):
            db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['reviewer'],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    h=login(client);binding,item=evidence(client,ids,h);expert_binding,expert_item=evidence(client,ids,h,text='Synthetic separately sourced expert recommendation');case=support_case(client,factory,ids,h)
    path=base(ids)+f'/support-cases/{case["id"]}/expert-assessments'
    assessment=post(client,path,h,retry(issuer='Synthetic expert',assessment_at=(utcnow()-timedelta(days=70)).isoformat(),source=expert_binding,recommendations=[{'category':'individually_adapted_education','subject':'reading','content':'Synthetic current educational recommendation','source':expert_binding,**period()}]))
    assessment=post(client,path+'/'+assessment['id']+'/confirm',h,expected(assessment,reason='Confirmed synthetic assessment'),200)
    decision=confirmed_decision(client,ids,h,case,binding)
    plan=post(client,base(ids)+f'/learners/{ids["a"]}/education-plans',h,plan_payload(binding,decision))
    profile_path=base(ids)+f'/learners/{ids["a"]}/support-profile/statements'
    statement=post(client,profile_path,h,retry(category='strength',content='Synthetic visual interest',source=expert_binding,observed_at=(utcnow()-timedelta(days=2)).isoformat()))
    statement=post(client,profile_path+'/'+statement['id']+'/review',h,expected(statement,outcome='confirmed',reason='Human confirmation'),200)
    basis=post(client,base(ids)+f'/education-plans/{plan["id"]}/generation-bases',h,expected(plan,plan_revision_id=plan['content']['id'],assessment_ids=[assessment['id']],profile_statement_ids=[statement['id']]))
    provider=ProviderSpec('plans-local',plan_wire.endpoint,frozenset({'generation'}))
    source=SourceInput(SourceRef(kind='plan_basis',source_id=uuid4(),revision=1),ids['school'],ids['a'],'iep_drafting','Synthetic evaluated plan basis',provenance='synthetic_fixture',provenance_reference='fixture:plans.v1')
    runtime=GatewayRuntime(environment='test',providers={provider.key:provider},source_resolver=EvidenceSourceResolver(app.state.evidence_storage),evaluation_suites={'plans-v1':(EvaluationCase('human-iep-proposal','iep_drafting',(source,),('Synthetic proposed reading plan',),('APPROVED',)),)})
    with factory() as db:
        actor=Actor(ids['reviewer'])
        policy=gateway.create_policy(db,actor,ids['school'],PolicyCommand(provider_key=provider.key,purposes=['iep_drafting'],timeout_seconds=2,max_output_tokens=4096),runtime)
        release=gateway.create_release(db,actor,ids['school'],ReleaseCommand(provider_key=provider.key,model_version='synthetic-plans-v1',capability='generation',template_version='iep-draft.v1',output_schema_version='iep-draft.v1'),runtime)
        evaluation=gateway.evaluate_release(db,actor,ids['school'],release.id,release.version,policy.id,'plans-v1',runtime);assert evaluation.state == 'passed',evaluation.metrics
        release=gateway.review_release(db,actor,ids['school'],release.id,ReviewCommand(expected_version=release.version,evaluation_id=evaluation.id,professional_quality_confirmed=True,rationale='Synthetic IEP format checked'))
    app.state.ai_gateway=runtime;plan_wire.target=plan['content']['goals'][0]['goal_id']
    yield SimpleNamespace(client=client,factory=factory,app=app,ids=ids,h=h,plan=plan,basis=basis,assessment=assessment,statement=statement,expert_item=expert_item,policy=policy.id,release=release.id,wire=plan_wire,runtime=runtime)


def generate(e):
    path=base(e.ids)+f'/education-plans/{e.plan["id"]}'
    request=retry(basis_id=e.basis['id'],policy_id=e.policy,release_id=e.release)
    job=post(e.client,path+'/suggestions',e.h,request)
    job=post(e.client,base(e.ids)+f'/ai/jobs/{job["id"]}/run',e.h,{'expected_version':job['version']},200)
    return job


def proposal(e,job):
    result=e.client.get(base(e.ids)+f'/education-plans/{e.plan["id"]}/suggestions/{job["id"]}',params={'basis_id':e.basis['id']})
    assert result.status_code == 200,result.text
    return result.json()


def selection(e,p,**changes):
    values={'expected_version':p['expected_version'],'plan_revision_id':p['plan_revision_id'],'basis_id':p['basis_id'],'job_id':p['job_id'],'proposal_digest':p['proposal_digest'],'outcome':'applied','selected_fields':['title'],'selected_goal_keys':[],'reason':'Human selected exact proposed title'}
    values.update(changes)
    return retry(**values)


def manual(e,row,**changes):
    from spesped.contexts.plans.generation import command_content
    from spesped.contexts.plans.models import PlanRevision
    with e.factory() as db:data=command_content(db,db.get(PlanRevision,row['content']['id']))
    return expected(row,**(data|changes))
