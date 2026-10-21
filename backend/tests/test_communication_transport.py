"""Verified HTTPS protocol contracts with loopback only."""
from uuid import uuid4
import ssl
import pytest
from communication_fixtures import secure_wire
from spesped.contexts.communication.transports import HTTPSConnection,TransportRegistry,PROTOCOL
from spesped.errors import DomainError
@pytest.mark.parametrize('mode,outcome',[('accepted','accepted'),('rejected','failed'),('unknown','unknown'),('lost_reply','unknown'),('bad_digest','unknown'),('server_error','unknown')])
def test_verified_https_exact_bindings_and_definitive_outcomes(secure_wire,mode,outcome):
    secure_wire.mode=mode;connection=HTTPSConnection('synthetic',str(uuid4()),secure_wire.endpoint,lambda:'synthetic-only-protocol-token',secure_wire.tls_context,1)
    envelope={'protocol':PROTOCOL,'submission_key':str(uuid4()),'package_digest':'a'*64,'recipient':{'user_id':str(uuid4())},'payload':{'subject':'Synthetic','body':'Synthetic secure transport contract'},'attachments':[]}
    result=connection.call(envelope);assert result.status==outcome and len(secure_wire.submissions)==1
    state=connection.call(envelope,reconcile=True);assert state.status in {'accepted','failed'} and len(secure_wire.submissions)==1 and secure_wire.lookups==[envelope['submission_key']]
    absent=connection.call({**envelope,'submission_key':str(uuid4())},reconcile=True);assert absent.status=='not_found'

def test_trusted_operator_configuration_has_no_insecure_or_cross_school_fallback(secure_wire):
    school=str(uuid4())
    with pytest.raises(ValueError):HTTPSConnection('synthetic',school,'http://127.0.0.1',lambda:'synthetic')
    unverified=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);unverified.check_hostname=False;unverified.verify_mode=ssl.CERT_NONE
    with pytest.raises(ValueError):HTTPSConnection('synthetic',school,secure_wire.endpoint,lambda:'synthetic',unverified)
    missing=HTTPSConnection('synthetic',school,secure_wire.endpoint,lambda:None,secure_wire.tls_context)
    with pytest.raises(DomainError,match='not configured'):TransportRegistry({'synthetic':missing}).resolve(school,'secure_https','synthetic')
    configured=HTTPSConnection('synthetic',school,secure_wire.endpoint,lambda:'synthetic-only-protocol-token',secure_wire.tls_context)
    with pytest.raises(DomainError):TransportRegistry({'synthetic':configured}).resolve(str(uuid4()),'secure_https','synthetic')
    assert 'synthetic-only-protocol-token' not in repr(configured) and secure_wire.submissions==[]

@pytest.mark.parametrize('mode',['oversized','trickle_headers','trickle_body'])
def test_actual_tls_response_bytes_and_total_deadline_reap_worker(secure_wire,mode,monkeypatch):
    import subprocess,time
    original=subprocess.Popen;children=[]
    def tracked(*args,**kwargs):
        child=original(*args,**kwargs);children.append(child);return child
    monkeypatch.setattr(subprocess,'Popen',tracked);secure_wire.mode=mode
    connection=HTTPSConnection('synthetic',str(uuid4()),secure_wire.endpoint,lambda:'synthetic-only-protocol-token',secure_wire.tls_context,.6)
    envelope={'protocol':PROTOCOL,'submission_key':str(uuid4()),'package_digest':'b'*64,'recipient':{'user_id':str(uuid4())},'payload':{'subject':'Synthetic','body':'Synthetic bounded transport'},'attachments':[]}
    start=time.monotonic();result=connection.call(envelope);elapsed=time.monotonic()-start
    assert result.status=='unknown' and elapsed<1.5 and len(secure_wire.submissions)==1
    assert len(children)==1 and children[0].poll() is not None

def test_empty_configured_tls_trust_does_not_gain_system_fallback(secure_wire):
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);assert context.get_ca_certs()==[]
    connection=HTTPSConnection('synthetic',str(uuid4()),secure_wire.endpoint,lambda:'synthetic-only-protocol-token',context,1)
    result=connection.call({'protocol':PROTOCOL,'submission_key':str(uuid4()),'package_digest':'c'*64,'recipient':{'user_id':str(uuid4())},'payload':{'subject':'Synthetic','body':'Synthetic no trust fallback'},'attachments':[]})
    assert result.status=='unknown' and secure_wire.submissions==[]
