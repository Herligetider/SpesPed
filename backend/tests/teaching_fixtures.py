"""Synthetic teaching HTTP setup layered on the accepted plans fixtures."""
from datetime import date,timedelta
from pathlib import Path
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import select
import pytest
from plans_fixtures import env,login,base,key,retry,expected,plan_payload,activate,evidence
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.contexts.teaching.router import router
from spesped.db import utcnow


@pytest.fixture
def teaching_env(env):
    client,factory,app,ids=env
    url=factory.kw['bind'].url.render_as_string(hide_password=False)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'));config.attributes['database_url']=url
    command.upgrade(config,'heads')
    if not any(getattr(r,'path','').endswith('/teaching/bases') for r in app.routes):app.include_router(router)
    with factory.begin() as db:
        for name in ('reviewer','teacher'):
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.user_id == ids[name],StaffAssignment.school_id == ids['school'])):
                assignment.actions=list(assignment.actions)+['teaching.read','teaching.write','learner.read']
        for action in ('teaching.approve','teaching.brief.approve','teaching.assign','teaching.follow_up','ai.session_planning','platform.manage','platform.review'):
            db.add(AuthorityGrant(school_id=ids['school'],user_id=ids['reviewer'],action=action,valid_from=date.today()-timedelta(days=1),granted_by=ids['leader']))
    yield client,factory,app,ids


def ordinary_goal(client,ids,headers,learner='a',binding=None):
    result=client.post(base(ids)+f'/learners/{ids[learner]}/education-plans',headers=headers,json=plan_payload(binding))
    assert result.status_code == 201,result.text
    row=activate(client,ids,headers,result.json())
    return row['content']['goals'][0]['id'],row


def basis(client,ids,headers,goals,**changes):
    learners=[{'learner_id':ids[l],'goal_revision_ids':[g]} for l,g in goals.items()]
    payload=retry(planned_at=(utcnow()+timedelta(minutes=5)).isoformat(),duration_minutes=30,learners=learners,theme='Synthetic reading theme',arena='Synthetic room',materials=['Synthetic cards'],**changes)
    result=client.post(base(ids)+'/teaching/bases',headers=headers,json=payload)
    assert result.status_code == 201,result.text
    return result.json()


def content(**changes):
    return {'title':'Synthetic reading activity','goal':'Read a word with visual support','preparation':'Prepare synthetic cards','materials':['Synthetic word cards'],'steps':[{'instruction':'Show a card','minutes':5},{'instruction':'Practise a word','minutes':10},{'instruction':'Observe and finish','minutes':5}],'support':'Offer visual cues','simplification':'Use one word at a time','observation_focus':'Record the actual independent attempt',**changes}


def session(client,ids,headers,basis_row,**changes):
    payload=retry(basis_id=basis_row['id'],owner_id=ids['reviewer'],content=content(**changes))
    result=client.post(base(ids)+'/teaching/sessions',headers=headers,json=payload)
    assert result.status_code == 201,result.text
    return result.json()


def approve(client,ids,headers,row):
    for action in ('review','approve'):
        result=client.post(base(ids)+f'/teaching/sessions/{row["id"]}/{action}',headers=headers,json=expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact pedagogical '+action))
        assert result.status_code == 200,result.text
        row=result.json()
    return row


def brief_content():
    return {'simple_goal':'Practise a short word','material_location':'Synthetic shelf A','steps':['Fetch cards','Show one card','Practise and record'],'support':'Offer a visual cue','simplification':'Use a single card','help_when':'Ask when the learner needs more support','contact':'Synthetic responsible teacher','training_guidance':'Use the agreed training and ask the responsible teacher before changing the activity'}


def assigned_brief(client,ids,headers,row,learner='a'):
    result=client.post(base(ids)+'/teaching/briefs',headers=headers,json=retry(session_revision_id=row['revision_id'],learner_id=ids[learner],content=brief_content()))
    assert result.status_code == 201,result.text
    brief=result.json()
    result=client.post(base(ids)+f'/teaching/briefs/{brief["id"]}/review',headers=headers,json=expected(brief,content_digest=brief['content_digest'],reason='Synthetic brief scope and guidance checked'))
    assert result.status_code == 200,result.text
    brief=result.json()
    result=client.post(base(ids)+f'/teaching/briefs/{brief["id"]}/assignments',headers=headers,json=expected(brief,assistant_id=ids['assistant'],valid_from=(utcnow()-timedelta(hours=3)).isoformat(),valid_until=(utcnow()+timedelta(hours=3)).isoformat(),role='Support the agreed activity'))
    assert result.status_code == 201,result.text
    return brief,result.json()


def actual(ids,goals,row=None,**changes):
    return {'session_revision_id':row['revision_id'] if row else None,'occurred_at':(utcnow()-timedelta(hours=1)).replace(microsecond=0).isoformat(),'duration_minutes':30,'status':'delivered','activity':'Synthetic actual group reading','participants':[{'learner_id':ids[l],'goal_revision_ids':[g],'status':'participated','minutes':30,'category':'ordinary_teaching','support':'Synthetic visual cue'} for l,g in goals.items()],'staff':[{'staff_id':ids['reviewer'],'minutes':30,'role':'Teacher','category':'ordinary_teaching'}],**changes}


@pytest.fixture
def teaching_wire_server():
    """Actual loopback model protocol. No external AI or pupil data."""
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from socketserver import TCPServer
    from types import SimpleNamespace
    import threading,json
    state=SimpleNamespace(requests=[],support='Synthetic AI visual support',mode='ok')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['content-length'])))
            state.requests.append(payload)
            if state.mode == 'unavailable':
                self.send_response(503);self.end_headers();return
            refs=[json.loads(v['text'])['source_ref'] for v in payload['messages'][1]['content'] if v['type'] == 'text' and 'source_ref' in json.loads(v['text'])]
            output={'content':content(support=state.support),'source_refs':refs,'missing_evidence':['No prior mastery is asserted by this proposed activity']}
            if state.mode == 'unknown_source':output['source_refs']=['teaching_basis:00000000-0000-0000-0000-000000000001:1']
            result={'model':payload['model'],'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output)}}]}
            raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    class Server(ThreadingHTTPServer):
        def server_bind(self):
            TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
    server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    state.endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(3)


def configure_ai(factory,app,ids,wire):
    from spesped.auth import Actor
    from spesped.assembly import EvidenceSourceResolver
    from spesped.contexts.platform.contracts import GatewayRuntime,ProviderSpec,SourceInput,SourceRef,EvaluationCase,PolicyCommand,ReleaseCommand,ReviewCommand
    from spesped.contexts.platform import service as gateway
    provider=ProviderSpec('teaching-local',wire.endpoint,frozenset({'generation'}))
    source=SourceInput(SourceRef(kind='teaching_basis',source_id=uuid4(),revision=1),ids['school'],ids['a'],'session_planning','Synthetic evaluated teaching basis',provenance='synthetic_fixture',provenance_reference='fixture:j06.session.v1')
    configured=GatewayRuntime(environment='test',providers={provider.key:provider},source_resolver=EvidenceSourceResolver(app.state.evidence_storage),evaluation_suites={'teaching-v1':(EvaluationCase('reviewed-structured-session','session_planning',(source,),('Synthetic AI visual support',),('ENTITLEMENT_GRANTED',)),)})
    with factory() as db:
        actor=Actor(ids['reviewer'])
        policy=gateway.create_policy(db,actor,ids['school'],PolicyCommand(provider_key=provider.key,purposes=['session_planning'],timeout_seconds=2,max_output_tokens=4096),configured)
        release=gateway.create_release(db,actor,ids['school'],ReleaseCommand(provider_key=provider.key,model_version='synthetic-teaching-v1',capability='generation',template_version='teaching-session.v1',output_schema_version='teaching-session.v1'),configured)
        evaluation=gateway.evaluate_release(db,actor,ids['school'],release.id,release.version,policy.id,'teaching-v1',configured)
        assert evaluation.state == 'passed',evaluation.metrics
        release=gateway.review_release(db,actor,ids['school'],release.id,ReviewCommand(expected_version=release.version,evaluation_id=evaluation.id,professional_quality_confirmed=True,rationale='Synthetic structured session fixture reviewed by a professional'))
    app.state.ai_gateway=configured
    return configured,policy.id,release.id


class SyntheticQualificationPort:
    """Contract fixture for future BC01/J19 records, never a production adapter."""
    def __init__(self,ids):
        self.ids=ids;self.mode='reviewed';self.review_id=uuid4();self.source_id=uuid4();self.reviewed_at=utcnow();self.requests=[]

    def resolve(self,db,actor,request):
        from spesped.contexts.teaching.ports import QualificationResult,QualificationSource
        self.requests.append(request)
        if self.mode == 'unavailable' or str(request.staff_id) == self.ids['assistant']:
            return QualificationResult(request=request,state='unavailable')
        result=QualificationResult(request=request,state='reviewed_current',responsibility='responsible_teaching',review_id=self.review_id,reviewed_by=self.ids['reviewer'],reviewed_at=self.reviewed_at,effective_from=self.reviewed_at-timedelta(days=365),effective_until=self.reviewed_at+timedelta(days=365),sources=[QualificationSource(kind='competence_review',source_id=self.source_id,revision=1,digest='a'*64)])
        if self.mode == 'mismatched':return result.model_copy(update={'request':request.model_copy(update={'staff_id':uuid4()})})
        if self.mode == 'missing_sources':return result.model_copy(update={'sources':[]})
        if self.mode == 'future_review':return result.model_copy(update={'reviewed_at':utcnow()+timedelta(days=1)})
        return result
