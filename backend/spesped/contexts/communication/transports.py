"""Secure dispatch v1: configured operator destinations, exact keys, no blind retry.

POST {endpoint}/v1/dispatches with Authorization: Bearer <operator secret>,
Idempotency-Key: <submission UUID>, and a JSON envelope with protocol,
submission_key, package_digest, recipient {user_id}, payload {subject, body},
attachments [{filename, content_type, data_base64}]. GET the same base path plus
/{submission_key} to reconcile, with X-Package-Digest on both requests; a 404
with an exact `not_found` JSON binding is
an authoritative absence. Every reply includes protocol, submission_key,
package_digest, status (accepted/rejected/unknown/not_found), provider_reference
(nullable for non-acceptance). HTTP status alone never establishes non-delivery.
The provider MUST durably deduplicate that key and reject changed payloads.
Acceptance is transport acceptance, never proof of reading. No redirects.

The endpoint, TLS trust, and secret resolver are operator-owned runtime settings;
school commands can select only a registered connection key. There is no URL or
secret in persisted policies, metadata audit, or receipt error text. A missing
configuration is unavailable. Loopback TLS is supported with an explicit CA
context for local protocol verification; verification cannot be disabled.
"""
from dataclasses import dataclass,field
import hashlib,json,os,re,ssl,subprocess,sys,time
from pathlib import Path
from typing import Callable,Mapping
from urllib.parse import urlsplit
from spesped.contexts.documents.adapters import digest
from spesped.errors import DomainError
PROTOCOL='spesped.secure-dispatch.v1'
@dataclass(frozen=True)
class TransportOutcome:
    status:str
    provider_reference:str|None=None
    reason_code:str='provider_unknown'
@dataclass(frozen=True)
class HTTPSConnection:
    key:str
    school_id:str
    endpoint:str=field(repr=False)
    secret:Callable[[],str|None]=field(repr=False)
    tls_context:ssl.SSLContext|None=field(default=None,repr=False)
    timeout_seconds:float=5
    def __post_init__(self):
        value=urlsplit(self.endpoint)
        if value.scheme!='https' or not value.hostname or value.username or value.password or value.query or value.fragment:raise ValueError('A configured HTTPS origin/path without credentials is required')
        if not 0.05<=self.timeout_seconds<=30:raise ValueError('Bound the transport timeout')
        if self.tls_context is not None and (self.tls_context.verify_mode!=ssl.CERT_REQUIRED or not self.tls_context.check_hostname):raise ValueError('TLS certificate and hostname verification are required')
    @property
    def configuration_digest(self):
        # Secret rotation does not make a new delivery identity. Endpoint/CA do.
        ca=sorted(hashlib.sha256(v).hexdigest() for v in self.tls_context.get_ca_certs(binary_form=True)) if self.tls_context else ['system-trust']
        return digest({'protocol':PROTOCOL,'key':self.key,'school_id':self.school_id,'endpoint':self.endpoint.rstrip('/'),'ca':ca,'timeout_seconds':self.timeout_seconds})
    def configured(self):return bool(self.secret())
    def call(self,envelope,reconcile=False):
        secret=self.secret()
        if not secret:return TransportOutcome('unknown',reason_code='transport_unavailable')
        key=envelope['submission_key'];url=self.endpoint.rstrip('/')+'/v1/dispatches'+('/'+key if reconcile else '')
        try:
            wire=self._exchange(url,envelope,secret,reconcile)
            if wire is None:return TransportOutcome('unknown',reason_code='provider_reply_unknown')
            response_status=wire['status_code'];value=wire['value']
            if not isinstance(value,dict) or set(value)!={'protocol','submission_key','package_digest','status','provider_reference'}:raise ValueError()
            if value['protocol']!=PROTOCOL or value['submission_key']!=key or value['package_digest']!=envelope['package_digest']:raise ValueError()
            status=value['status'];reference=value['provider_reference']
            if reference is not None and (not isinstance(reference,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',reference)):raise ValueError()
            if status=='accepted' and response_status in {200,201,202} and reference:return TransportOutcome('accepted',reference,'provider_accepted')
            if status=='rejected' and response_status in {200,409,422}:return TransportOutcome('failed',reference,'provider_rejected')
            if reconcile and status=='not_found' and response_status==404 and reference is None:return TransportOutcome('not_found',reason_code='provider_confirmed_absent')
            return TransportOutcome('unknown',reference,'provider_unknown')
        except (ValueError,TypeError,KeyError):return TransportOutcome('unknown',reason_code='provider_reply_unknown')
    def _exchange(self,url,envelope,secret,reconcile):
        # Bound wall time, buffered request/response bytes, and the worker lifetime.
        # A timed-out exchange may already have delivered: always return unknown.
        deadline=time.monotonic()+self.timeout_seconds;child=None
        try:
            ca_pem=''.join(ssl.DER_cert_to_PEM_cert(v) for v in self.tls_context.get_ca_certs(binary_form=True)) if self.tls_context else None
            command={'url':url,'method':'GET' if reconcile else 'POST','body':None if reconcile else envelope,'submission_key':envelope['submission_key'],'package_digest':envelope['package_digest'],'secret':secret,'deadline':deadline,'ca_pem':ca_pem}
            raw=json.dumps(command,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
            if len(raw)>16_000_000 or time.monotonic()>=deadline:return None
            child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('http_worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True,env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONNOUSERSITE':'1',**{v:os.environ[v] for v in ('SYSTEMROOT','WINDIR') if v in os.environ}})
            remaining=deadline-time.monotonic()
            if remaining<=0:return None
            output,_=child.communicate(raw,timeout=remaining)
            if child.returncode!=0 or time.monotonic()>deadline or len(output)>131_072:return None
            value=json.loads(output)
            return value if isinstance(value,dict) and set(value)=={'status_code','value'} else None
        except (OSError,subprocess.TimeoutExpired,ValueError,UnicodeError,TypeError):return None
        finally:
            if child is not None:
                if child.poll() is None:child.kill()
                child.wait()
                for stream in (child.stdin,child.stdout):
                    if stream is not None:stream.close()

class TransportRegistry:
    def __init__(self,connections:Mapping[str,HTTPSConnection]|None=None):self._connections=dict(connections or {})
    def resolve(self,school_id,channel,connection_key):
        if channel=='portal':return None
        connection=self._connections.get(connection_key)
        if channel!='secure_https' or connection is None or connection.school_id!=school_id or not connection.configured():raise DomainError('transport_unavailable','The selected secure transport is not configured for this school.',503)
        return connection
    def binding(self,school_id,channel,connection_key):
        connection=self.resolve(school_id,channel,connection_key)
        return connection.configuration_digest if connection else digest({'protocol':'spesped.portal.v1','school_id':school_id})
