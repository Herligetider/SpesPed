"""Bounded OpenAI wire adapters; no tools, redirects, proxies or fallback.

Protocol references (inspected 2026-10-21):
https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create
https://developers.openai.com/api/reference/resources/embeddings/methods/create
"""
import base64
import ipaddress
import json
import math
import time
import subprocess
import signal
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from .contracts import GatewayRuntime, ProviderSpec, SourceInput, Suggestion, SYSTEM_PROMPT, PURPOSE_INSTRUCTIONS


class ProviderFailure(Exception):
    def __init__(self, code: str, state: str = 'unavailable', unsupported_sources: int = 0):
        self.code, self.state, self.unsupported_sources = code, state, unsupported_sources
        super().__init__(code)


PRIVATE_RANGES = tuple(ipaddress.ip_network(x) for x in ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128', 'fc00::/7'))


def validate_provider(runtime: GatewayRuntime, provider: ProviderSpec, sources: list[SourceInput]):
    parsed = urlsplit(provider.endpoint)
    if (parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path.rstrip('/') != '/v1'):
        raise ProviderFailure('provider_boundary_rejected')
    try:
        port = parsed.port
    except ValueError:
        raise ProviderFailure('provider_boundary_rejected') from None
    if provider.kind == 'remote_openai':
        if (runtime.environment != 'development' or not runtime.remote_synthetic_development
                or parsed.scheme != 'https' or parsed.hostname != 'api.openai.com' or port not in {None, 443}
                or not sources or any(s.provenance != 'synthetic_fixture' or not s.provenance_reference for s in sources)):
            raise ProviderFailure('remote_processing_forbidden')
        return
    if provider.kind != 'local_openai':
        raise ProviderFailure('unknown_provider')
    try:
        address = ipaddress.ip_address(parsed.hostname)
        configured = [ipaddress.ip_network(n, strict=True) for n in runtime.private_networks]
    except ValueError:
        raise ProviderFailure('provider_boundary_rejected') from None
    # Reject mapped IPv4, link-local metadata and public/ambiguous hostnames even
    # when an operator accidentally supplies an overly broad configured CIDR.
    if (getattr(address, 'ipv4_mapped', None) or address.is_link_local or address.is_unspecified
            or not any(address in n for n in PRIVATE_RANGES)
            or not any(address in n for n in configured)):
        raise ProviderFailure('provider_boundary_rejected')


def _post(provider: ProviderSpec, path: str, *, timeout: int, response_limit: int, **kwargs) -> dict:
    """Overall wall deadline, including headers, with no abandoned network work.

    The isolated child uses the existing httpx protocol adapter. A timeout kills
    and reaps it, closing its socket before this method returns. This also bounds
    synchronous DNS/TLS work that cannot safely be cancelled in a Python thread.
    Credentials and source data never appear in process arguments or logs.
    """
    deadline = time.monotonic() + timeout
    if 'files' in kwargs:
        kwargs['files'] = {name: [entry[0], base64.b64encode(entry[1]).decode('ascii'), entry[2]] for name, entry in kwargs['files'].items()}
    payload = json.dumps({'url': provider.endpoint.rstrip('/') + path, 'api_key': provider.api_key,
                          'timeout': timeout, 'deadline': deadline, 'response_limit': response_limit, 'kwargs': kwargs},
                         ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    if len(payload) > 4_000_000:
        raise ProviderFailure('input_limit_exceeded', 'failed')
    if time.monotonic() >= deadline:
        raise ProviderFailure('provider_timeout')
    child = None
    try:
        child = subprocess.Popen([sys.executable, str(Path(__file__).with_name('http_worker.py'))],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, close_fds=True,
                                 env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
                                      **{key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(child.args, timeout)
        output, _ = child.communicate(payload, timeout=remaining)
        if time.monotonic() > deadline:
            raise subprocess.TimeoutExpired(child.args, timeout)
        if child.returncode == -getattr(signal, 'SIGALRM', 14):
            raise ProviderFailure('provider_timeout')
        if child.returncode != 0:
            raise ProviderFailure('provider_worker_failed')
        if len(output) > response_limit + 128:
            raise ProviderFailure('output_limit_exceeded', 'failed')
        value = json.loads(output)
        if set(value) == {'response'} and isinstance(value['response'], dict):
            return value['response']
        allowed_errors = {'provider_redirect_rejected', 'provider_http_error', 'invalid_output',
                          'output_limit_exceeded', 'input_limit_exceeded', 'provider_timeout',
                          'provider_connection_failed', 'provider_worker_failed', 'invalid_provider_request'}
        if (set(value) == {'error', 'state'} and value['error'] in allowed_errors
                and value['state'] in {'failed', 'unavailable'}):
            raise ProviderFailure(value['error'], value['state'])
        raise ProviderFailure('provider_worker_failed')
    except subprocess.TimeoutExpired:
        raise ProviderFailure('provider_timeout') from None
    except OSError:
        raise ProviderFailure('provider_worker_failed') from None
    except (ValueError, UnicodeError, TypeError):
        raise ProviderFailure('invalid_output', 'failed') from None
    finally:
        if child is not None:
            # Also runs on caller interruption and malformed/error responses.
            # kill + wait reaps the child; no HTTP thread or socket survives it.
            if child.poll() is None:
                child.kill()
            child.wait()
            if child.stdin is not None:
                child.stdin.close()
            if child.stdout is not None:
                child.stdout.close()


def validate_suggestion(value: dict, sources: list[SourceInput]) -> dict:
    try:
        suggestion = Suggestion.model_validate(value)
        if not suggestion.statements and not suggestion.missing_evidence:
            raise ValueError()
        if any(not x.strip() or len(x) > 2000 for x in suggestion.missing_evidence):
            raise ValueError()
        allowed = {s.reference.key for s in sources}
        unknown = sum(1 for st in suggestion.statements for ref in st.source_refs if ref not in allowed)
        if unknown:
            raise ProviderFailure('unsupported_source_reference', 'failed', unknown)
        result = suggestion.model_dump()
        for statement in result['statements']:
            statement['confirmed'] = False
            statement['support_status'] = 'citation_requires_review' if statement['source_refs'] else 'missing_evidence'
        if any(not st.source_refs for st in suggestion.statements):
            result['missing_evidence'].append('One or more suggestions have no supporting source reference.')
        result.update({'unconfirmed': True, 'requires_human_review': True, 'schema_version': 'suggestion.v1'})
        return result
    except (ValidationError, ValueError, TypeError):
        raise ProviderFailure('invalid_output', 'failed') from None


def invoke(runtime: GatewayRuntime, provider: ProviderSpec, release, policy: dict, sources: list[SourceInput]) -> dict:
    validate_provider(runtime, provider, sources)
    capability = release.capability
    if capability not in provider.capabilities:
        raise ProviderFailure('capability_unavailable')
    common = {'timeout': policy['timeout_seconds'], 'response_limit': policy['max_response_bytes']}
    size = sum(len(s.content.encode() if isinstance(s.content, str) else s.content) for s in sources)
    if size > policy['max_input_bytes']:
        raise ProviderFailure('input_limit_exceeded', 'failed')
    if capability == 'speech':
        if len(sources) != 1 or sources[0].media_type not in {'audio/wav', 'audio/mpeg', 'audio/webm'} or not isinstance(sources[0].content, bytes):
            raise ProviderFailure('unsupported_source_type', 'unavailable', len(sources))
        s = sources[0]
        result = _post(provider, '/audio/transcriptions', **common, data={'model': release.model_version, 'response_format': 'json'}, files={'file': ('source.audio', s.content, s.media_type)})
        text = result.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ProviderFailure('invalid_output', 'failed')
        return validate_suggestion({'statements': [{'text': text, 'source_refs': [s.reference.key]}], 'missing_evidence': []}, sources)
    if capability == 'embeddings':
        if any(s.media_type != 'text/plain' or not isinstance(s.content, str) for s in sources):
            raise ProviderFailure('unsupported_source_type', 'unavailable', len(sources))
        result = _post(provider, '/embeddings', **common, json={'model': release.model_version, 'input': [s.content for s in sources], 'encoding_format': 'float'})
        try:
            if result.get('model') != release.model_version:
                raise ValueError()
            vectors = sorted(result['data'], key=lambda v: v['index'])
            if len(vectors) != len(sources) or [v['index'] for v in vectors] != list(range(len(sources))):
                raise ValueError()
            dimension = len(vectors[0]['embedding'])
            if not 1 <= dimension <= 8192:
                raise ValueError()
            for vector in vectors:
                if len(vector['embedding']) != dimension or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector['embedding']):
                    raise ValueError()
            return {'schema_version': 'embeddings.v1', 'vectors': [{'source_ref': s.reference.key, 'values': v['embedding']} for s, v in zip(sources, vectors)], 'unconfirmed': True, 'requires_human_review': True}
        except (KeyError, TypeError, ValueError, IndexError):
            raise ProviderFailure('invalid_output', 'failed') from None
    purpose = sources[0].purpose if sources else None
    if purpose not in PURPOSE_INSTRUCTIONS or any(s.purpose != purpose for s in sources):
        raise ProviderFailure('purpose_not_supported')
    content = [{'type': 'text', 'text': json.dumps({'approved_task': PURPOSE_INSTRUCTIONS[purpose]})}]
    for source in sources:
        if capability == 'ocr':
            if source.media_type not in {'image/png', 'image/jpeg'} or not isinstance(source.content, bytes):
                raise ProviderFailure('unsupported_source_type', 'unavailable', 1)
            content.extend([{'type': 'text', 'text': json.dumps({'source_ref': source.reference.key, 'instruction': 'Extract image text as unconfirmed source-linked statements.'})}, {'type': 'image_url', 'image_url': {'url': f'data:{source.media_type};base64,' + base64.b64encode(source.content).decode()}}])
        elif capability == 'generation':
            if source.media_type != 'text/plain' or not isinstance(source.content, str):
                raise ProviderFailure('unsupported_source_type', 'unavailable', 1)
            content.append({'type': 'text', 'text': json.dumps({'source_ref': source.reference.key, 'untrusted_source_data': source.content}, ensure_ascii=False)})
        else:
            raise ProviderFailure('capability_unavailable')
    payload = {'model': release.model_version, 'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': content}], 'max_tokens': policy['max_output_tokens'], 'stream': False, 'response_format': {'type': 'json_schema', 'json_schema': {'name': 'suggestion', 'strict': True, 'schema': Suggestion.model_json_schema()}}}
    result = _post(provider, '/chat/completions', **common, json=payload)
    try:
        if result.get('model') != release.model_version:
            raise ValueError()
        choice = result['choices'][0]
        if choice['finish_reason'] != 'stop' or choice['message'].get('tool_calls') or choice['message'].get('refusal'):
            raise ValueError()
        output = json.loads(choice['message']['content'])
    except (KeyError, IndexError, ValueError, TypeError):
        raise ProviderFailure('invalid_output', 'failed') from None
    return validate_suggestion(output, sources)
