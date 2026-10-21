"""Synthetic HTTP documents over native accepted source contexts."""
from datetime import date,timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from assessment_fixtures import assessment_env,curriculum_env,teaching_env,env,login,ordinary_goal,source,observation,progress
from plans_fixtures import base,key,retry,expected,evidence
from spesped.contexts.documents.router import router
from spesped.contexts.identity.models import StaffAssignment,AuthorityGrant,GuardianRelationship
from spesped.db import utcnow
@pytest.fixture
def documents_env(assessment_env):
    client,factory,app,ids=assessment_env
    assert '/api/v1/schools/{school_id}/documents/cases' in app.openapi()['paths']
    with factory.begin() as db:
        for name in ('reviewer','teacher'):
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids[name])):
                assignment.actions=list(set(assignment.actions)|{'documents.read','documents.write','documents.review','documents.contribute','documents.schedule','documents.schedule.run'})
            for action in ('documents.approve','documents.annual_ito.approve','documents.local_report.approve','documents.subject_report.approve','documents.templates.manage','documents.templates.review','ai.report_drafting','ai.guardian_email_drafting'):
                db.add(AuthorityGrant(school_id=ids['school'],user_id=ids[name],action=action,granted_by=ids['leader'],valid_from=date(2020,1,1)))
        relationship=db.scalar(select(GuardianRelationship).where(GuardianRelationship.school_id==ids['school'],GuardianRelationship.learner_id==ids['a']))
        if relationship is None:
            relationship=GuardianRelationship(school_id=ids['school'],learner_id=ids['a'],guardian_user_id=ids['guardian'],relationship='parent',source_reference='synthetic-record-reviewed',parental_responsibility=True,information_rights='full',restrictions='',valid_from=date(2020,1,1));db.add(relationship);db.flush()
        relationship.state='active';relationship.parental_responsibility=True;relationship.information_rights='full';relationship.restrictions='';ids['guardian_relation']=relationship.id
    return client,factory,app,ids

def path(ids):return base(ids)+'/documents'
def payload(ids,**changes):
    return retry(**{'learner_id':ids['a'],'kind':'guardian_email','purpose':'learning_summary','starts_on':'2026-10-01','ends_on':'2026-10-21','owner_id':ids['reviewer'],'recipient_relationship_ids':[ids['guardian_relation']],**changes})
def create(client,ids,h,**changes):
    response=client.post(path(ids)+'/cases',headers=h,json=payload(ids,**changes));assert response.status_code==201,response.text;return response.json()
def filled(row,**changes):
    snap=row['revision']['snapshot']['manifest']
    return {'subject':'Synthetic period summary','sections':[{'key':v['key'],'text':'Synthetic human text; no unsupported progress asserted','source_keys':[],'missing_inputs':[]} for v in row['revision']['content']['sections']],'handled_gaps':{v:'Synthetic responsible human records the missing source; no positive conclusion' for v in snap['gaps']},**changes}
def revised(client,ids,h,row,**changes):
    doc={**row['revision']['configuration'],'request_key':key(),'content':filled(row)};doc.update(changes)
    response=client.post(path(ids)+f'/cases/{row["id"]}/revisions',headers=h,json=expected(row,document=doc,reason='Synthetic human reviewed new exact content'));assert response.status_code==201,response.text;return response.json()
def transition(client,ids,h,row,action,code=200):
    response=client.post(path(ids)+f'/cases/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact content checked by responsible human',action=action));assert response.status_code==code,response.text;return response.json()
def template(client,ids,h,kind='local_semester_report',**changes):
    ref,_=source(client,ids,h,'Synthetic school reviewed report template policy')
    content={'kind':kind,'title':'Synthetic local report','effective_from':'2020-01-01','effective_until':'2035-12-31','approval_action':'documents.local_report.approve','sections':[{'key':'summary','label':'Summary','required':True}],'sources':[ref],**changes}
    response=client.post(path(ids)+'/templates',headers=h,json=retry(content=content));assert response.status_code==201,response.text;row=response.json()
    response=client.post(path(ids)+f'/templates/{row["id"]}/review',headers=h,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic school template applicability and action reviewed'));assert response.status_code==200,response.text
    return response.json()

@pytest.fixture
def document_wire():
    from types import SimpleNamespace
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from socketserver import TCPServer
    import threading,json
    state=SimpleNamespace(mode='ok',requests=[])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['content-length'])));state.requests.append(payload)
            if state.mode=='unavailable':self.send_response(503);self.end_headers();return
            refs=[json.loads(v['text'])['source_ref'] for v in payload['messages'][1]['content'] if 'source_ref' in json.loads(v['text'])]
            output={'subject':'Synthetic editable period email','sections':[{'key':'body','text':'Synthetic source-backed review text; no invented progress.','source_refs':refs,'missing_evidence':[]}],'missing_evidence':['Human professional conclusion required']}
            if state.mode=='foreign_section':output['sections'][0]['key']='unconfigured'
            if state.mode=='rights':output['approved']=True
            raw=json.dumps({'model':payload['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output)}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    class Server(ThreadingHTTPServer):
        def server_bind(self):TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
    server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();state.endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(3)

@pytest.fixture
def generated_documents(documents_env,document_wire):
    from types import SimpleNamespace
    from spesped.auth import Actor
    from spesped.assembly import EvidenceSourceResolver
    from spesped.contexts.platform.contracts import GatewayRuntime,ProviderSpec,SourceRef,SourceInput,EvaluationCase,PolicyCommand,ReleaseCommand,ReviewCommand
    from spesped.contexts.platform import service as gateway
    client,factory,app,ids=documents_env;h=login(client);row=create(client,ids,h)
    provider=ProviderSpec('documents-local',document_wire.endpoint,frozenset({'generation'}));purpose='guardian_email_drafting'
    source=SourceInput(SourceRef(kind='document_basis',source_id=uuid4(),revision=1),ids['school'],ids['a'],purpose,'Synthetic evaluated frozen document basis',provenance='synthetic_fixture',provenance_reference='fixture:documents.v1')
    runtime=GatewayRuntime(environment='test',providers={provider.key:provider},source_resolver=EvidenceSourceResolver(app.state.evidence_storage),evaluation_suites={'documents-v1':(EvaluationCase('human-period-email',purpose,(source,),('Synthetic editable period email',)),)})
    with factory() as db:
        actor=Actor(ids['reviewer'])
        policy=gateway.create_policy(db,actor,ids['school'],PolicyCommand(provider_key=provider.key,purposes=[purpose],timeout_seconds=2,max_output_tokens=4096),runtime)
        release=gateway.create_release(db,actor,ids['school'],ReleaseCommand(provider_key=provider.key,model_version='synthetic-documents-v1',capability='generation',template_version='document-draft.v1',output_schema_version='document-draft.v1'),runtime)
        evaluation=gateway.evaluate_release(db,actor,ids['school'],release.id,release.version,policy.id,'documents-v1',runtime);assert evaluation.state=='passed',evaluation.metrics
        release=gateway.review_release(db,actor,ids['school'],release.id,ReviewCommand(expected_version=release.version,evaluation_id=evaluation.id,professional_quality_confirmed=True,rationale='Synthetic document typed output reviewed'))
    app.state.ai_gateway=runtime
    return SimpleNamespace(client=client,factory=factory,app=app,ids=ids,h=h,row=row,wire=document_wire,policy=policy.id,release=release.id,runtime=runtime)
