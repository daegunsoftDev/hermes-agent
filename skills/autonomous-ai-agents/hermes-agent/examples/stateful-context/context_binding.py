"""Proposed scratch Gateway run binding. Not installed and not native admission/authentication."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Callable
from pathlib import Path
import source_defs as native
from validation import make_key,reject,PolicyRejected

@dataclass(frozen=True)
class RunScope:
    profile:str
    runtime_home:str
    workspace:str
    conversation:str
    child:str
    engine:str
    model:str
    revision:str
    epoch:int
    session_source:str
    _check:Callable[[],None]=field(compare=False,repr=False)
    aux_routes:tuple=()
    def assert_current(self):self._check()

def strict_epoch(db,key,source):
    reader=getattr(getattr(db,'_db',db),'latest_conversation_boundary',None)
    if not callable(reader):reject('epoch-reader')
    try:value=reader(key,source)
    except Exception as exc:raise PolicyRejected('SESSION_POLICY_REJECTED:epoch-read') from exc
    if type(value) is not int or value<0:reject('epoch')
    return value

def prepare_run_scope(ctx,inputs,route,db):
    source=getattr(ctx,'source',None);identity=getattr(source,'_identity',None)
    if type(identity) is not native.RoutingIdentity:reject('routing-identity')
    if not isinstance(identity.runtime_home,Path) or not identity.runtime_home.is_absolute():reject('runtime-home')
    if type(identity.runtime_profile) is not str or not identity.runtime_profile:reject('profile')
    current=getattr(ctx,'_run_still_current',None)
    if not callable(current) or current() is not True:reject('stale-run')
    conversation=getattr(ctx,'session_key',None)
    if conversation!=native.build_session_key(source,thread_sessions_per_user=False,profile=identity.session_key_profile):reject('conversation')
    runtime=route.get('runtime') if isinstance(route,dict) else None
    if not isinstance(runtime,dict) or runtime.get('provider')!='custom' or runtime.get('base_url') not in ('https://bridge.invalid/v1','https://bridge.invalid/v1/'):reject('route-contract')
    storage_source=getattr(inputs,'session_source',None)
    if type(storage_source) is not str or not storage_source or storage_source.strip()!=storage_source:reject('session-source')
    epoch=strict_epoch(db,conversation,storage_source)
    values=dict(profile=identity.runtime_profile,workspace=getattr(inputs,'workspace',None),conversation=conversation,child=getattr(inputs,'child',None),lane='primary',engine=getattr(inputs,'engine',None),model=route.get('model'),revision=getattr(inputs,'revision',None),epoch=epoch)
    make_key(values)
    def check():
        if current() is not True or getattr(ctx,'session_key',None)!=conversation or getattr(source,'_identity',None)!=identity:reject('stale-run')
        if strict_epoch(db,conversation,storage_source)!=epoch:reject('stale-epoch')
    auxiliary=getattr(inputs,'auxiliary',{})
    if type(auxiliary) is not dict:reject('auxiliary-contract')
    aux_routes=[]
    for task,contract in auxiliary.items():
        if type(task) is not str or not task or type(contract) is not dict:reject('auxiliary-contract')
        lane='aux-'+task;engine=contract.get('engine');model=contract.get('model')
        make_key({**values,'lane':lane,'engine':engine,'model':model})
        aux_routes.append((lane,engine,model))
    return RunScope(runtime_home=str(identity.runtime_home),session_source=storage_source,_check=check,aux_routes=tuple(aux_routes),**{k:v for k,v in values.items() if k!='lane'})

def bind_agent_scope(agent,scope):
    if type(scope) is not RunScope:reject('run-scope')
    scope.assert_current();agent._stateful_run_scope=scope

# Call-scoped proposed API; no process-global or environment identity fallback.
from contextlib import contextmanager
from contextvars import ContextVar
import public_connection
_POLICY=ContextVar('scratch_stateful_policy',default=None)

@dataclass(frozen=True)
class CallPolicySnapshot:
    run:RunScope=field(repr=False,compare=False)
    lane:str
    engine:str
    model:str
    @property
    def context(self):
        return {**{k:getattr(self.run,k) for k in ('profile','workspace','conversation','child','revision','epoch')},'lane':self.lane,'engine':self.engine,'model':self.model}

def policy_for(run,lane):
    if type(run) is not RunScope:reject('run-scope')
    run.assert_current()
    if lane=='primary':return CallPolicySnapshot(run,lane,run.engine,run.model)
    for selected,engine,model in run.aux_routes:
        if selected==lane:return CallPolicySnapshot(run,lane,engine,model)
    reject('unknown-lane')

@contextmanager
def bind_call(policy):
    if type(policy) is not CallPolicySnapshot:reject('call-policy')
    policy.run.assert_current();token=_POLICY.set(policy)
    try:yield policy
    finally:_POLICY.reset(token)

def current_policy():
    policy=_POLICY.get()
    if type(policy) is not CallPolicySnapshot:reject('missing-call-policy')
    policy.run.assert_current();return policy

from types import SimpleNamespace
import httpx

def run_with_policy(policy,callback,*args,**kwargs):
    with bind_call(policy):return callback(*args,**kwargs)

def require_call_route(policy,provider,model,task,base_url):
    if type(policy) is not CallPolicySnapshot or current_policy() is not policy:reject('call-binding')
    if provider!='custom' or model!=policy.model or policy.lane!='aux-'+str(task) or base_url not in ('https://bridge.invalid/v1','https://bridge.invalid/v1/'):reject('aux-route-contract')

class ScopeTransport(httpx.BaseTransport):
    def __init__(self,inner,policy,denial):self.inner=inner;self.policy=policy;self.denial=denial;self.closed=False
    def handle_request(self,request):
        try:self.policy.run.assert_current()
        except PolicyRejected as exc:
            if self.denial.error is None:self.denial.error=exc
            raise self.denial.error
        return self.inner.handle_request(request)
    def close(self):
        if not self.closed:self.closed=True;self.inner.close()

class PolicyStream:
    def __init__(self,inner,policy,denial):self.inner=inner;self.iterator=iter(inner);self.policy=policy;self.denial=denial;self.closed=False
    def __iter__(self):return self
    def __next__(self):
        try:
            self.policy.run.assert_current();value=next(self.iterator);self.policy.run.assert_current();return value
        except BaseException as exc:
            if isinstance(exc,PolicyRejected) and self.denial.error is None:self.denial.error=exc
            self.close();raise
    def close(self):
        if not self.closed:self.closed=True;self.inner.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class PolicyClient:
    def __init__(self,inner,policy,denial):
        self.inner=inner;self.policy=policy;self.denial=denial;self.base_url=inner.base_url;self.default_headers=inner.default_headers
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def is_closed(self):return self.inner.is_closed()
    def close(self):self.inner.close()
    def create(self,**kwargs):
        if self.denial.error is not None:raise self.denial.error
        if current_policy() is not self.policy:reject('call-binding')
        try:
            result=self.inner.create(**kwargs)
            try:self.policy.run.assert_current()
            except PolicyRejected:
                if kwargs.get('stream'):result.close()
                raise
            return PolicyStream(result,self.policy,self.denial) if kwargs.get('stream') else result
        except Exception as exc:
            if isinstance(exc,PolicyRejected) and self.denial.error is None:self.denial.error=exc
            if self.denial.error is not None:raise self.denial.error
            raise

def create_policy_client(options,context,http_builder,*,sdk_factory):
    policy=current_policy()
    if context!=policy.context:reject('policy-binding')
    denial=SimpleNamespace(error=None)
    def build(url,*,transport_wrapper):
        def wrap(inner):return ScopeTransport(transport_wrapper(inner),policy,denial)
        return http_builder(url,transport_wrapper=wrap)
    inner=public_connection.create_client(options,context,build,sdk_factory=sdk_factory)
    return PolicyClient(inner,policy,denial)
