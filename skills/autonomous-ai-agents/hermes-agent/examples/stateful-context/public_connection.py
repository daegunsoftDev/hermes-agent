"""Scratch public-API policy/client boundary. No native activation.
Uses OpenAI(max_retries=0,http_client=...) and HTTPX BaseTransport only.
Host context and the inspected transport builder are explicit inputs.
"""
from __future__ import annotations
import copy
from types import SimpleNamespace
import httpx
import openai
from validation import Validation,PolicyRejected,make_key,reject,SYNTHETIC_ROUTE

class GuardedTransport(httpx.BaseTransport):
    def __init__(self,inner,validation):
        self.inner=inner;self.validation=validation;self.closed=False
    def handle_request(self,request):
        self.validation._validate_wire(request)
        try:return self.inner.handle_request(request)
        except PolicyRejected as exc:raise self.validation._remember_denial(exc)
    def close(self):
        if not self.closed:
            self.closed=True;self.inner.close()

class OwnedStream:
    """Retain one physical SDK client until exhaustion or explicit cancellation."""
    def __init__(self,stream,raw,owner):
        self.stream=stream;self.raw=raw;self.owner=owner;self.iterator=iter(stream);self.closed=False
        owner.streams.add(self)
    def __iter__(self):return self
    def __next__(self):
        try:return next(self.iterator)
        except BaseException:
            self.close();raise
    def close(self):
        if not self.closed:
            self.closed=True
            try:self.stream.close()
            finally:
                self.raw.close();self.owner.streams.discard(self)
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()

class PublicClient:
    """A logical owner; each create() owns a fresh real SDK+HTTPX client.
    No policy object or cookie jar is attached to a reusable global client/pool.
    """
    def __init__(self,options,context,http_builder,sdk_factory):
        make_key(context)
        self.options=copy.deepcopy(options);self.context=copy.deepcopy(context)
        if str(self.options.get('base_url','')) not in (SYNTHETIC_ROUTE,SYNTHETIC_ROUTE+'/'):reject('route')
        if not isinstance(self.options.get('api_key'),str) or not self.options['api_key']:reject('credential-source')
        if 'http_client' in self.options:reject('unowned-http-client')
        self.options['max_retries']=0
        self.base_url=self.options['base_url'];self.default_headers=self.options.get('default_headers') or {}
        self.http_builder=http_builder;self.sdk_factory=sdk_factory;self.closed=False;self.streams=set()
        self.validation=Validation.__new__(Validation)
        self.validation._raw=SimpleNamespace(base_url=self.base_url,default_headers=self.default_headers)
        self.validation._context=self.context;self.validation._required=True
        self.validation.checks=0;self.validation.wire_checks=0;self.validation.denial=None
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def is_closed(self):return self.closed
    def close(self):
        if not self.closed:
            self.closed=True
            for stream in list(self.streams):stream.close()
    def create(self,**kwargs):
        if self.closed:reject('closed-logical-client')
        self.validation.checks+=1;self.validation._raise_if_denied()
        try:validated=self.validation._validated_kwargs(kwargs)
        except PolicyRejected as exc:raise self.validation._remember_denial(exc)
        owned=[]
        def wrapper(inner):
            transport=GuardedTransport(inner,self.validation);owned.append(transport);return transport
        try:
            http=self.http_builder(str(self.base_url),transport_wrapper=wrapper)
            if http is None or not owned:reject('guard-construction')
        except Exception as exc:
            denial=exc if isinstance(exc,PolicyRejected) else PolicyRejected('SESSION_POLICY_REJECTED:guard-construction')
            raise self.validation._remember_denial(denial) from exc
        raw=None;stream_owned=False
        try:
            raw=self.sdk_factory(**{**self.options,'http_client':http,'max_retries':0})
            result=raw.chat.completions.create(**validated)
            self.validation._raise_if_denied()
            if validated.get('stream'):
                stream_owned=True;return OwnedStream(result,raw,self)
            return result
        except Exception:
            self.validation._raise_if_denied();raise
        finally:
            if not stream_owned:
                if raw is not None:raw.close()
                else:http.close()

def create_client(options,context,http_builder,*,sdk_factory=openai.OpenAI):
    return PublicClient(options,context,http_builder,sdk_factory)
