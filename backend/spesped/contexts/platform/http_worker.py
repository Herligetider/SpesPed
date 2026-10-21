"""One bounded HTTP exchange in an expendable process; no domain/database imports.

The parent owns the elapsed deadline and kills/reaps this process before returning
on timeout or cancellation. OS process termination closes its socket, including
while httpx is waiting for DNS, TLS or incomplete response headers. No descendants
are created. Sensitive request data travels only through the private stdin pipe.
"""
import base64
import json
import sys
import signal
import time

import httpx

MAX_INPUT_BYTES = 4_000_000
MAX_RESPONSE_BYTES = 1_000_000


class WireFailure(Exception):
    def __init__(self, code, state='unavailable'):
        self.code, self.state = code, state


def exchange(command):
    timeout = command['timeout']
    response_limit = command['response_limit']
    if not 0 < timeout <= 120 or not 1 <= response_limit <= MAX_RESPONSE_BYTES:
        raise WireFailure('invalid_provider_request', 'failed')
    kwargs = command['kwargs']
    if 'files' in kwargs:
        kwargs['files'] = {name: (entry[0], base64.b64decode(entry[1], validate=True), entry[2]) for name, entry in kwargs['files'].items()}
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    if command['api_key']:
        headers['Authorization'] = 'Bearer ' + command['api_key']
    limits = httpx.Timeout(float(timeout), connect=min(timeout, 5), read=min(timeout, 1), write=min(timeout, 1), pool=1)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=limits) as client:
        with client.stream('POST', command['url'], headers=headers, **kwargs) as response:
            if 300 <= response.status_code < 400:
                raise WireFailure('provider_redirect_rejected')
            if response.status_code != 200:
                raise WireFailure('provider_http_error')
            if 'application/json' not in response.headers.get('content-type', ''):
                raise WireFailure('invalid_output', 'failed')
            # Refuse unsolicited compression rather than inflate unbounded model output.
            if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise WireFailure('invalid_output', 'failed')
            data = bytearray()
            for chunk in response.iter_raw():
                data.extend(chunk)
                if len(data) > response_limit:
                    raise WireFailure('output_limit_exceeded', 'failed')
    value = json.loads(data)
    if not isinstance(value, dict):
        raise WireFailure('invalid_output', 'failed')
    return value


def main():
    response_limit = MAX_RESPONSE_BYTES
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise WireFailure('input_limit_exceeded', 'failed')
        command = json.loads(raw)
        response_limit = min(command['response_limit'], MAX_RESPONSE_BYTES)
        remaining = command['deadline'] - time.monotonic()
        if remaining <= 0:
            raise WireFailure('provider_timeout')
        # A Unix deployment also enforces the inherited absolute deadline inside
        # the child, so it cannot linger if its parent is killed unexpectedly.
        if hasattr(signal, 'setitimer'):
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.setitimer(signal.ITIMER_REAL, min(remaining, command['timeout']))
        result = {'response': exchange(command)}
    except WireFailure as exc:
        result = {'error': exc.code, 'state': exc.state}
    except httpx.TimeoutException:
        result = {'error': 'provider_timeout', 'state': 'unavailable'}
    except httpx.HTTPError:
        result = {'error': 'provider_connection_failed', 'state': 'unavailable'}
    except (ValueError, UnicodeError, KeyError, TypeError):
        result = {'error': 'invalid_output', 'state': 'failed'}
    except Exception:
        # Exception text can include source prose, endpoints or credentials.
        result = {'error': 'provider_worker_failed', 'state': 'unavailable'}
    encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) > response_limit + 128:
        encoded = b'{"error":"output_limit_exceeded","state":"failed"}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
