from __future__ import annotations
from collections.abc import Mapping
import copy
import hashlib
import json
from types import SimpleNamespace
FIELDS = ('profile', 'workspace', 'conversation', 'child', 'lane', 'engine', 'model', 'revision', 'epoch')
SYNTHETIC_ROUTE = 'https://bridge.invalid/v1'

class PolicyRejected(PermissionError):
    """Permanent for this proposed policy, not an SDK authentication exception."""

def reject(code):
    raise PolicyRejected('SESSION_POLICY_REJECTED:' + code)

def make_key(context):
    if not isinstance(context, Mapping):
        reject('context')
    canonical = {}
    for field in FIELDS:
        value = context.get(field)
        if field == 'epoch':
            if type(value) is not int or value < 0:
                reject('epoch')
        elif type(value) is not str or not value or value.strip() != value or any((ord(c) < 32 or ord(c) == 127 for c in value)):
            reject('namespace')
        canonical[field] = value
    encoded = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return 'h1-' + hashlib.sha256(encoded).hexdigest()[:48]

def session_header(headers):
    if headers is None:
        return None
    if not isinstance(headers, Mapping):
        reject('headers')
    found = []
    for name, value in headers.items():
        if type(name) is not str:
            reject('headers')
        if name.lower() == 'x-session-id':
            if type(value) is not str:
                reject('header-value')
            found.append(value)
    if len(found) > 1:
        reject('duplicate-header')
    return found[0] if found else None

class Validation:

    def _validated_kwargs(self, kwargs):
        expected = make_key(self._context)
        if str(self._raw.base_url) not in (SYNTHETIC_ROUTE, SYNTHETIC_ROUTE + '/'):
            reject('route')
        if kwargs.get('model') != self._context['model']:
            reject('model')
        extra_body = kwargs.get('extra_body')
        if extra_body is not None:
            if not isinstance(extra_body, Mapping):
                reject('extra-body')
            if 'model' in extra_body and extra_body['model'] != self._context['model']:
                reject('extra-body-model')
        defaults = self._raw.default_headers
        default_key = session_header(defaults)
        request_key = session_header(kwargs.get('extra_headers'))
        if default_key is None and request_key is None:
            reject('missing-header')
        for value in (default_key, request_key):
            if value is not None and value != expected:
                reject('conflicting-header')
        spelling = next((k for k in defaults if k.lower() == 'x-session-id'), 'X-Session-Id')
        result = dict(kwargs)
        result['extra_headers'] = {k: v for k, v in (kwargs.get('extra_headers') or {}).items() if k.lower() != 'x-session-id'}
        result['extra_headers'][spelling] = expected
        return result

    def _remember_denial(self, exc):
        if self.denial is None:
            self.denial = exc
        return self.denial

    def _raise_if_denied(self):
        if self.denial is not None:
            raise self.denial

    def _validate_wire(self, request):
        if not self._required:
            return
        self.wire_checks += 1
        self._raise_if_denied()
        try:
            expected = make_key(self._context)
            if request.method != 'POST' or str(request.url) != SYNTHETIC_ROUTE + '/chat/completions':
                reject('wire-route')
            headers = [value for name, value in request.headers.raw if name.lower() == b'x-session-id']
            if headers != [expected.encode('ascii')]:
                reject('wire-header')
            try:
                body = json.loads(request.content)
            except (ValueError, UnicodeError):
                reject('wire-body')
            if not isinstance(body, dict) or body.get('model') != self._context['model']:
                reject('wire-model')
        except PolicyRejected as exc:
            raise self._remember_denial(exc)
