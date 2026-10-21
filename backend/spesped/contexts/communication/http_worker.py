"""One bounded HTTPS exchange; no domain, database, or secret-bearing logging.

The parent kills and reaps this child on its absolute wall deadline. The child
also installs a deadline timer so DNS, TLS, incomplete headers and trickled body
cannot outlive a killed parent. Sensitive data uses private stdin, never argv.
"""
import json,signal,ssl,sys,time
import httpx
MAX_INPUT=16_000_000
MAX_RESPONSE=16_384

def exchange(command):
    remaining=command['deadline']-time.monotonic()
    if remaining<=0:raise ValueError()
    if hasattr(signal,'setitimer'):
        signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.setitimer(signal.ITIMER_REAL,remaining)
    if command['ca_pem'] is None:context=ssl.create_default_context()
    else:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if command['ca_pem']:context.load_verify_locations(cadata=command['ca_pem'])
    timeout=httpx.Timeout(remaining,connect=min(remaining,5),read=min(remaining,1),write=min(remaining,1),pool=min(remaining,1))
    headers={'Authorization':'Bearer '+command['secret'],'Idempotency-Key':command['submission_key'],'X-Package-Digest':command['package_digest'],'Accept':'application/json','Accept-Encoding':'identity'}
    with httpx.Client(verify=context,timeout=timeout,follow_redirects=False,trust_env=False) as client:
        with client.stream(command['method'],command['url'],headers=headers,json=command['body']) as response:
            if response.headers.get('content-encoding','identity').lower()!='identity':raise ValueError()
            if 'application/json' not in response.headers.get('content-type','').lower():raise ValueError()
            length=response.headers.get('content-length')
            if length is not None and (not length.isdigit() or int(length)>MAX_RESPONSE):raise ValueError()
            data=bytearray()
            for chunk in response.iter_raw(chunk_size=4096):
                if len(data)+len(chunk)>MAX_RESPONSE:raise ValueError()
                data.extend(chunk)
    return {'status_code':response.status_code,'value':json.loads(data)}
def main():
    try:
        raw=sys.stdin.buffer.read(MAX_INPUT+1)
        if len(raw)>MAX_INPUT:raise ValueError()
        result=exchange(json.loads(raw));encoded=json.dumps(result,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
        if len(encoded)>131_072:raise ValueError()
    except Exception:encoded=b'{"error":"provider_reply_unknown"}'
    sys.stdout.buffer.write(encoded);sys.stdout.buffer.flush()
if __name__=='__main__':main()
