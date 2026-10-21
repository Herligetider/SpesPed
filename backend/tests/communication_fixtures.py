"""Synthetic BC11 over actual approved BC10 and native source workflows."""
from datetime import date,timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select
from documents_fixtures import documents_env,assessment_env,curriculum_env,teaching_env,env,login,create,revised,transition,source
from plans_fixtures import base,key,retry,expected
from spesped.contexts.identity.models import AuthorityGrant,StaffAssignment
from spesped.db import utcnow
ACTIONS=('communication.read','communication.write','communication.content.review','communication.authorize','communication.send','communication.reconcile','communication.export','communication.recipient.manage','communication.recipient.review')
@pytest.fixture
def communication_env(documents_env):
    client,factory,app,ids=documents_env
    assert '/api/v1/schools/{school_id}/communication/packages' in app.openapi()['paths']
    with factory.begin() as db:
        for name in ('reviewer','teacher'):
            for assignment in db.scalars(select(StaffAssignment).where(StaffAssignment.school_id==ids['school'],StaffAssignment.user_id==ids[name])):assignment.actions=list(set(assignment.actions)|set(ACTIONS))
            for action in ('communication.content.review','communication.authorize','communication.recipient.review','communication.policy.manage','communication.policy.review','communication.policy.read'):
                db.add(AuthorityGrant(school_id=ids['school'],user_id=ids[name],action=action,granted_by=ids['leader'],valid_from=date(2020,1,1)))
    return client,factory,app,ids

def path(ids):return base(ids)+'/communication'
def post(client,ids,h,route,command,code=200):
    response=client.post(path(ids)+route,headers=h,json=command);assert response.status_code==code,response.text;return response.json()
def review(row,**changes):return expected(row,revision_id=row['revision_id'],content_digest=row['content_digest'],reason='Synthetic exact review of content, sources and scope',**changes)
def setup(client,ids,h,channel='portal',attachments=False):
    ref,_=source(client,ids,h,'Synthetic school channel policy and explicitly checked guardian information-rights source')
    settings={'channel':channel,'connection_key':'synthetic-secure' if channel=='secure_https' else None,'purposes':['learning_summary'],'document_kinds':['guardian_email'],'allow_attachments':attachments,'portal_lifetime_hours':24,'expires_at':(utcnow()+timedelta(days=30)).isoformat(),'sources':[ref]}
    policy=post(client,ids,h,'/channels',retry(settings=settings),201);policy=post(client,ids,h,f'/channels/{policy["id"]}/review',review(policy))
    clearance=post(client,ids,h,'/recipients',retry(learner_id=ids['a'],relationship_id=ids['guardian_relation'],settings={'purposes':['learning_summary'],'expires_at':(utcnow()+timedelta(days=30)).isoformat(),'sources':[ref]}),201)
    clearance=post(client,ids,h,f'/recipients/{clearance["id"]}/review',review(clearance))
    doc=create(client,ids,h);doc=revised(client,ids,h,doc);doc=transition(client,ids,h,doc,'review');doc=transition(client,ids,h,doc,'approve')
    selection={'learner_id':ids['a'],'document_revision_id':doc['revision_id'],'recipient_revision_id':clearance['revision_id'],'channel_revision_id':policy['revision_id'],'purpose':'learning_summary','section_keys':[v['key'] for v in doc['revision']['content']['sections']],'attachments':[{'document_revision_id':doc['revision_id'],'filename':'synthetic-summary.txt'}] if attachments else []}
    package=post(client,ids,h,'/packages',retry(selection=selection),201)
    return doc,policy,clearance,package,selection

def authorize(client,ids,h,package):
    package=post(client,ids,h,f'/packages/{package["id"]}/content-review',review(package))
    return post(client,ids,h,f'/packages/{package["id"]}/authorize',review(package))
def queued(client,ids,h,package):
    package=post(client,ids,h,f'/packages/{package["id"]}/dispatches',review(package),201);return package,package['dispatches'][-1]
def prepare(client,ids,h,dispatch):return post(client,ids,h,f'/dispatches/{dispatch["id"]}/prepare',expected(dispatch,reason='Synthetic explicit sender prepares delivery'))
def release(client,ids,h,dispatch):return post(client,ids,h,f'/dispatches/{dispatch["id"]}/release',expected(dispatch,reason='Synthetic explicit sender releases exact package'))

@pytest.fixture
def secure_wire(tmp_path):
    """Real verified loopback HTTPS with durable synthetic provider key state."""
    import json,ssl,threading,subprocess,socket,time
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from types import SimpleNamespace
    from spesped.contexts.communication.transports import PROTOCOL
    cert=tmp_path/'cert.pem';private=tmp_path/'private.pem';config=tmp_path/'tls.cnf'
    config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=localhost\n[ext]\nsubjectAltName=IP:127.0.0.1,DNS:localhost\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\n')
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(private),'-out',str(cert),'-days','1','-config',str(config)],check=True,capture_output=True)
    state=SimpleNamespace(mode='accepted',submissions=[],lookups=[],stored={})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,value):
            data=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            assert self.headers['Authorization']=='Bearer synthetic-only-protocol-token'
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state.submissions.append(value);key=value['submission_key']
            reply={'protocol':PROTOCOL,'submission_key':key,'package_digest':value['package_digest'],'status':'rejected' if state.mode=='rejected' else 'accepted','provider_reference':'synthetic:'+key}
            state.stored[key]=reply
            if state.mode in {'oversized','trickle_headers','trickle_body'}:
                try:
                    if state.mode=='oversized':
                        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length','2000000');self.end_headers()
                        for _ in range(500):self.wfile.write(b'x'*4096);self.wfile.flush()
                    elif state.mode=='trickle_headers':
                        self.connection.sendall(b'HTTP/1.1 200 OK\r\nX-Synthetic: ')
                        for _ in range(100):self.connection.sendall(b'x');time.sleep(.05)
                    else:
                        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length','1000');self.end_headers()
                        for _ in range(100):self.wfile.write(b' ');self.wfile.flush();time.sleep(.05)
                except OSError:pass
                return
            if state.mode=='lost_reply':self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            if state.mode=='unknown':reply={**reply,'status':'unknown'}
            if state.mode=='bad_digest':reply={**reply,'package_digest':'0'*64}
            if state.mode=='server_error':self.reply(503,reply);return
            self.reply(422 if state.mode=='rejected' else 202,reply)
        def do_GET(self):
            key=self.path.rsplit('/',1)[-1];state.lookups.append(key);value=state.stored.get(key)
            if value is None:self.reply(404,{'protocol':PROTOCOL,'submission_key':key,'package_digest':self.headers['X-Package-Digest'],'status':'not_found','provider_reference':None})
            else:self.reply(200,value)
    from socketserver import TCPServer
    class Server(ThreadingHTTPServer):
        def server_bind(self):TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
    server=Server(('127.0.0.1',0),Handler);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(cert),str(private));server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();state.endpoint=f'https://127.0.0.1:{server.server_port}';state.tls_context=ssl.create_default_context(cafile=str(cert))
    try:yield state
    finally:server.shutdown();server.server_close();thread.join(3)
def configure_secure(app,ids,wire):
    from spesped.contexts.communication.transports import HTTPSConnection,TransportRegistry
    app.state.communication_transport_registry=TransportRegistry({'synthetic-secure':HTTPSConnection('synthetic-secure',ids['school'],wire.endpoint,lambda:'synthetic-only-protocol-token',wire.tls_context,1)})

def runtime_info(db,app):
    for name in ('curriculum_source_port','document_dispatch_history_port','assessment_authority_port','teaching_qualification_port','governance_case_scope_resolver','communication_transport_registry'):db.info[name]=getattr(app.state,name,None)
    db.info['documents_runtime']=getattr(app.state,'ai_gateway',None);db.info['plans_runtime']=db.info['documents_runtime'];db.info['teaching_runtime']=db.info['documents_runtime']
    # Fixtures replace private storage after create_app, just like the established document dependency.
    from spesped.contexts.curriculum.adapters import EvidenceSourceReadPort
    db.info['curriculum_source_port']=getattr(app.state,'curriculum_source_port',None) or EvidenceSourceReadPort(app.state.evidence_storage)
