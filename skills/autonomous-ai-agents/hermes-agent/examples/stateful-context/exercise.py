"""Source-bound public-API connection trial. No native package bootstrap.
Real OpenAI/HTTPX; synthetic host/config/proxy selector/shared-pool views;
actual inspected factory/cache/helper leaves; RAM-only inner transports.
"""
from __future__ import annotations
import ast,builtins,copy,hashlib,importlib.util,io,json,logging,os,sys,threading,time,types,unittest
from pathlib import Path
R=Path(__file__).resolve().parent
L=json.loads((R/'lease.json').read_text(encoding='utf-8'));MODE=sys.argv[1]
AUDIT=[]
def within(path,roots):
    if isinstance(path,int):return True
    try:return any(Path(path).resolve().is_relative_to(p.resolve()) for p in roots)
    except (TypeError,ValueError,OSError):return False
def audit(event,args):
    deny=event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','os.spawn','os.startfile'}
    if event=='open':
        path,mode,flags=args
        writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        deny|=not within(path,(R,) if writing else (R,Path(L['site_packages']),Path(sys.base_prefix)))
        if isinstance(path,(str,bytes)):
            name=os.fsdecode(path).replace('\\','/').lower();deny|=name.endswith(('/auth.json','/config.yaml','/.env')) or '/credentials-index/' in name
    if deny:AUDIT.append(event);raise PermissionError('OFFLINE_BOUNDARY:'+event)
sys.addaudithook(audit)
import httpx,openai
assert openai.__version__==L['openai_version'] and httpx.__version__==L['httpx_version']
sys.path.insert(0,str(R))
import validation as v
BASE={'profile':'synthetic-profile','workspace':'synthetic-workspace','conversation':'thread-A','child':'main','lane':'primary','engine':'claude','model':'synthetic-model','revision':'contract-v1','epoch':1}
KEY=v.make_key(BASE)
BASELINE=MODE.startswith('red')
p=None
if not BASELINE:
    import public_connection as p
    if MODE=='mutation-wire':
        p.GuardedTransport.handle_request=lambda self,request:self.inner.handle_request(request)

def extracted(rel,names,env,candidate=True):
    path=R/('candidate' if candidate and not BASELINE else 'snapshot')/rel
    text=path.read_text(encoding='utf-8');tree=ast.parse(text)
    selected=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(selected)==len(names) and {n.name for n in selected}==set(names)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+selected,type_ignores=[])),str(path),'exec'),env)
    return env

class SSE(httpx.SyncByteStream):
    def __init__(self):self.closed=0
    def close(self):self.closed+=1
    def __iter__(self):
        rows=[{'id':'synthetic','object':'chat.completion.chunk','created':1,'model':'synthetic-model','choices':[{'index':0,'delta':{'role':'assistant','content':'synthetic'},'finish_reason':None}]},{'id':'synthetic','object':'chat.completion.chunk','created':1,'model':'synthetic-model','choices':[],'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}}]
        raw=b''.join(b'data: '+json.dumps(x).encode()+b'\n\n' for x in rows)+b'data: [DONE]\n\n'
        for i in range(0,len(raw),7):yield raw[i:i+7]

OBS=[]
class Connections(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.sdks=[];self.sdk_options=[];self.statuses=[];self.streams=[];self.handles=[];self.dispatches=0;self.resolves=0;self.factory_failure=False;self.hook=None;self.proxy=None;self.inner_fault=None;self.pools={};self.views=[];self.close_calls=0
        self.active=True;self.ctx=copy.deepcopy(BASE)
        self.scope=types.SimpleNamespace(enabled=True,context=self.ctx)
        case=self
        class Pool(httpx.MockTransport):
            def close(inner):case.close_calls+=1;super().close()
        self.Pool=Pool
        class View(httpx.BaseTransport):
            def __init__(inner,pool):inner.pool=pool;inner.closed=0;case.views.append(inner)
            def handle_request(inner,request):return inner.pool.handle_request(request)
            def close(inner):inner.closed+=1
        fake=types.SimpleNamespace(Limits=httpx.Limits,Timeout=httpx.Timeout,HTTPTransport=lambda **kw:Pool(self.handler),AsyncHTTPTransport=lambda **kw:Pool(self.handler))
        def ctor(**kw):
            if self.factory_failure:raise ValueError('synthetic-constructor-failure')
            # Declared RAM-only substitution for HTTPX's implicit proxy transport.
            if kw.pop('proxy',None):kw['transport']=Pool(self.handler)
            kw['trust_env']=False
            if self.hook:kw['event_hooks']={'request':[self.hook]}
            return httpx.Client(**kw)
        fake.Client=ctor;fake.AsyncClient=ctor
        original_import=builtins.__import__
        def narrow_import(name,*args,**kw):
            if name=='httpx':return fake
            if name=='agent.codex_headers':return types.SimpleNamespace(codex_request_compression_hooks=lambda *a,**k:None)
            if name=='agent.auxiliary_local_runtime':return types.SimpleNamespace(bare_llamacpp_endpoint=lambda *a:None)
            if name=='agent.auxiliary_stream_watchdog':return types.SimpleNamespace(chat_stream_windows=lambda *a:None)
            return original_import(name,*args,**kw)
        bi={**vars(builtins),'__import__':narrow_import}
        def shared(key,builder):
            if key not in self.pools:self.pools[key]=builder()
            return self.pools[key]
        benv={'__builtins__':bi,'_get_proxy_for_base_url':lambda url:self.proxy,'_uses_codex_cloud_transport':lambda url:False,'_shared_transport_key':lambda *a:('synthetic',),'_shared_transport_cls':lambda:View,'_get_shared_transport':shared,'_enable_happy_eyeballs':lambda t:None}
        self.build=extracted('agent/process_bootstrap.py',{'build_keepalive_http_client'},benv)['build_keepalive_http_client']
        def sdk_factory(**kw):
            self.sdk_options.append({k:kw.get(k) for k in ['max_retries','base_url']})
            raw=openai.OpenAI(**kw);self.sdks.append(raw);return raw
        self.sdk_factory=sdk_factory
        def plain(options):
            opts=dict(options);http=self.build(str(opts['base_url']))
            if http is None:raise RuntimeError('fixture refuses unsafe SDK-default fallback')
            return sdk_factory(**{**opts,'http_client':http})
        def stateful(options,context):
            return p.create_client(options,context,self.build,sdk_factory=sdk_factory)
        self.plain=plain;self.stateful=stateful
        def get_scope():return self.scope if self.active else None
        self.get_scope=get_scope
        env={'__builtins__':bi,'PolicyRejected':v.PolicyRejected,'stateful_scope':get_scope,'create_stateful_client':stateful,'require_stateful_context':lambda c:v.make_key(c),'_OPENAI_SLOT':'slot','base_url_host_matches':lambda *a:False}
        env=extracted('agent/client_lifecycle.py',{'_create_request_openai_client','_close_request_openai_client'},env)
        class Agent:
            provider='custom';api_mode='chat_completions';base_url=v.SYNTHETIC_ROUTE
            def __init__(agent):agent._client_kwargs=case.options();agent.cached=None;agent.cached_in_use=False;agent.checkouts=0;agent.stores=0
            def _ensure_primary_openai_client(agent,**kw):return None
            def _openai_client_lock(agent):return threading.RLock()
            def _checkout_request_slot(agent,*a):
                agent.checkouts+=1
                if agent.cached is not None and not agent.cached_in_use:agent.cached_in_use=True;return agent.cached,None
                return None,None
            def _store_request_slot(agent,slot,client,key):agent.cached=client;agent.cached_in_use=True;agent.stores+=1
            def _create_openai_client(agent,opts,**kw):return plain(opts)
            def _close_openai_client(agent,client,**kw):client.close()
            def _release_request_slot(agent,slot,client,reason):
                if client is agent.cached:agent.cached_in_use=False;return True
                return False
        Agent._create_request_openai_client=env['_create_request_openai_client'];Agent._close_request_openai_client=env['_close_request_openai_client']
        self.agent=Agent()
        def notify():self.dispatches+=1
        auxenv={'__builtins__':bi,'Any':object,'PolicyRejected':v.PolicyRejected,'stateful_scope':get_scope,'create_stateful_client':stateful,'require_stateful_context':lambda c:v.make_key(c),'_aux_probe_active':lambda:False,'_openai_http_client_kwargs':lambda url:{'http_client':self.build(url)},'_apply_required_codex_headers':lambda *a,**kw:None,'OpenAI':sdk_factory,'_client_cache':{},'_client_cache_lock':threading.RLock(),'_CLIENT_CACHE_MAX_SIZE':8,'_normalize_main_runtime':lambda r:r or {},'_current_event_loop':lambda:None,'_client_cache_key':lambda *a,**k:('synthetic-cache',),'_compat_model':lambda c,m,d:m or d,'_peek_pool_entry':lambda *a:None,'_normalize_aux_provider':lambda x:x,'_close_cached_client':lambda c,**kw:c.close(),'bypass_chat_sdk_request_transform':lambda kw,c:kw,'_notify_aux_dispatch':notify,'_aux_progress_active':lambda:False,'_client_streams_internally':lambda c:False,'_notify_aux_provider_response':lambda:None,'_stream_request_plan':lambda kw,c:({**kw,'stream':True},kw['model'],30),'_is_transient_transport_error':lambda e:False,'_is_auth_error':lambda e:False,'_is_payment_error':lambda e:False,'_is_rate_limit_error':lambda e:False,'logger':logging.getLogger('public-trial'),'_aggregate_chat_stream':lambda chunks,**kw:list(chunks)}
        self.aux=extracted('agent/auxiliary_client.py',{'_create_openai_client','_get_cached_client','_create_with_progress_once'},auxenv)
        def resolve(provider,model,async_mode,**kw):
            self.resolves+=1
            return self.aux['_create_openai_client'](api_key=kw['explicit_api_key'],base_url=kw['explicit_base_url']),model
        self.aux['resolve_provider_client']=resolve
        self.helpers=extracted('agent/chat_completion_helpers.py',{'_dispatch_nonstreaming_api_request','_open_chat_stream'},{'time':time,'bypass_chat_sdk_request_transform':lambda kw,c:kw,'is_native_gemini_base_url':lambda u:False},candidate=False)
    def tearDown(self):
        for h in self.handles:
            try:h.close()
            except Exception:pass
        for c in self.sdks:c.close()
        OBS.append({'case':self.id(),'sdk_instances':len(self.sdks),'sdk_options':self.sdk_options,'requests':copy.deepcopy(self.calls),'aux_dispatches':self.dispatches,'resolver_calls':self.resolves,'pool_closes':self.close_calls})
    def handler(self,request):
        if self.inner_fault:raise self.inner_fault
        body=json.loads(request.content)
        self.calls.append({'url':str(request.url),'headers':[(k.decode(),val.decode()) for k,val in request.headers.raw if k.lower()==b'x-session-id'],'model':body.get('model'),'stream':bool(body.get('stream'))})
        status=self.statuses.pop(0) if self.statuses else 200
        if status!=200:return httpx.Response(status,json={'error':{'message':'synthetic-only','type':'synthetic'}})
        if body.get('stream'):
            s=SSE();self.streams.append(s);return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=s)
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':1,'model':body.get('model'),'choices':[{'index':0,'message':{'role':'assistant','content':'synthetic-only'},'finish_reason':'stop'}]})
    def options(self):return {'api_key':'SYNTHETIC-ONLY-NOT-A-CREDENTIAL','base_url':v.SYNTHETIC_ROUTE,'organization':'synthetic-org','project':'synthetic-project','max_retries':0}
    def request(self):return {'model':(self.scope.context or BASE)['model'],'messages':[{'role':'user','content':'synthetic-only'}],'extra_headers':{'X-Session-Id':v.make_key(self.scope.context or BASE)}}
    def main_client(self):
        c=self.agent._create_request_openai_client(reason='synthetic');self.handles.append(c);return c
    def aux_client(self,**kw):
        c,m=self.aux['_get_cached_client']('custom',model='synthetic-model',base_url=v.SYNTHETIC_ROUTE,api_key='SYNTHETIC-ONLY-NOT-A-CREDENTIAL',**kw)
        if c is not None:self.handles.append(c)
        return c
    def invoke(self,path='main-sync',request=None,client=None):
        kw=self.request() if request is None else request
        c=client if client is not None else (self.aux_client() if path.startswith('aux') else self.main_client())
        if path=='main-sync':return self.helpers['_dispatch_nonstreaming_api_request'](self.agent,kw,make_client=lambda *a,**k:c)
        if path=='main-stream':
            stream=types.SimpleNamespace(agent=types.SimpleNamespace(base_url=v.SYNTHETIC_ROUTE,_create_request_openai_client=lambda **k:c,_touch_activity=lambda *a:None),clients=types.SimpleNamespace(set_client=lambda c:c),last_chunk_time={})
            return list(self.helpers['_open_chat_stream'](stream,{**kw,'stream':True}))
        return self.aux['_create_with_progress_once'](c,kw,force_stream=path=='aux-stream')
    def denied(self,fn,reason=None):
        error=None
        try:fn()
        except Exception as exc:error=exc
        self.assertIsInstance(error,v.PolicyRejected)
        if reason:self.assertIn(reason,str(error))
        self.assertEqual(self.calls,[])
    def test_main_missing_context(self):
        self.scope.context=None;self.denied(self.main_client,'context');self.assertEqual(self.sdks,[])
    def test_aux_missing_context_before_resolver(self):
        self.scope.context=None;self.denied(self.aux_client,'context');self.assertEqual(self.resolves,0)
    def test_aux_async_fail_closed(self):
        self.denied(lambda:self.aux_client(async_mode=True),'async');self.assertEqual(self.resolves,0)
    def test_main_case_variant_defaults(self):
        self.agent._client_kwargs['default_headers']={'x-session-id':KEY};self.invoke();self.assertEqual([val for k,val in self.calls[0]['headers']],[KEY])
    def test_extra_body_model_override(self):
        kw=self.request();kw['extra_body']={'model':'other'};self.denied(lambda:self.invoke(request=kw),'model');self.assertEqual(self.sdks,[])
    def test_conflicting_header(self):
        kw=self.request();kw['extra_headers']['X-Session-Id']='other';self.denied(lambda:self.invoke(request=kw),'conflicting');self.assertEqual(self.sdks,[])
    def test_duplicate_header(self):
        kw=self.request();kw['extra_headers']['x-session-id']=KEY;self.denied(lambda:self.invoke(request=kw),'duplicate');self.assertEqual(self.sdks,[])
    def test_late_header_mutation(self):
        self.hook=lambda r:r.headers.__setitem__('X-Session-Id','other');self.denied(self.invoke,'wire-header');self.assertEqual(len(self.sdks),1)
    def test_late_model_mutation(self):
        def mutate(r):r.stream=httpx.ByteStream(b'{"model":"other","messages":[]}');r._content=b'{"model":"other","messages":[]}'
        self.hook=mutate;self.denied(self.invoke,'wire-model')
    def test_late_http_mount_route_mutation(self):
        self.hook=lambda r:setattr(r,'url',httpx.URL('http://bridge.invalid/v1/chat/completions'));self.denied(self.invoke,'wire-route')
    def test_proxy_route_mutation(self):
        self.proxy='http://synthetic-proxy.invalid:8123';self.hook=lambda r:r.headers.__setitem__('X-Session-Id','other');self.denied(self.invoke,'wire-header')
    def test_proxy_positive_control(self):
        self.proxy='http://synthetic-proxy.invalid:8123';self.invoke();self.assertEqual(len(self.calls),1)
    def test_factory_failure_has_no_sdk_default_fallback(self):
        self.factory_failure=True;self.denied(self.invoke,'construction');self.assertEqual(self.sdks,[])
    def test_aux_denial_no_stream_fallback(self):
        self.aux['_aux_progress_active']=lambda:True
        self.hook=lambda r:r.headers.__setitem__('X-Session-Id','other')
        self.denied(lambda:self.invoke('aux-sync'));self.assertEqual(self.dispatches,1);self.assertEqual(len(self.sdks),1)
    def test_aux_explicit_retry_override_is_clamped(self):
        c=self.aux['_create_openai_client'](api_key=self.options()['api_key'],base_url=v.SYNTHETIC_ROUTE,max_retries=2);self.handles.append(c);self.invoke('aux-sync',client=c);self.assertEqual([x['max_retries'] for x in self.sdk_options],[0])
    def test_nonpolicy_500_is_not_typed_denial_or_sdk_retry(self):
        self.statuses=[500,200];error=None
        try:self.invoke()
        except Exception as exc:error=exc
        self.assertIsInstance(error,openai.InternalServerError);self.assertEqual(len(self.calls),1)
    def test_typed_transport_denial_survives_sdk_wrapper(self):
        self.inner_fault=v.PolicyRejected('SESSION_POLICY_REJECTED:synthetic-transport');self.denied(self.invoke,'synthetic-transport');self.assertEqual(len(self.sdks),1)
    def test_stream_exhaustion_closes_owned_client_not_pool(self):
        result=self.invoke('main-stream');self.assertEqual(len(result),2);self.assertTrue(all(c.is_closed() for c in self.sdks));self.assertEqual(self.close_calls,0)
    def test_partial_stream_cancel_closes_owned_client_not_pool(self):
        c=self.main_client();stream=c.chat.completions.create(**{**self.request(),'stream':True});next(iter(stream));stream.close();self.assertTrue(self.sdks[0].is_closed());self.assertEqual(self.close_calls,0)
    def test_main_selected_cache_is_bypassed(self):
        a=self.main_client();self.agent._close_request_openai_client(a,reason='complete');b=self.main_client();self.assertIsNot(a,b);self.assertEqual(self.agent.checkouts,0);self.assertEqual(self.agent.stores,0)
    def test_aux_selected_cache_is_bypassed(self):
        a=self.aux_client();b=self.aux_client();self.assertIsNot(a,b);self.assertEqual(self.aux['_client_cache'],{})
    def test_ordinary_main_cache_control(self):
        self.active=False;a=self.main_client();self.agent._close_request_openai_client(a,reason='complete');b=self.main_client();self.assertIs(a,b);self.assertEqual(self.agent.stores,1)
    def test_ordinary_aux_cache_control(self):
        self.active=False;a=self.aux_client();b=self.aux_client();self.assertIs(a,b);self.assertEqual(self.resolves,1)
    def test_each_aux_fallback_call_owns_fresh_sdk(self):
        self.aux['_aux_progress_active']=lambda:True;self.statuses=[400,200];result=self.invoke('aux-sync');self.assertEqual(result.choices[0].message.content,'synthetic-only');self.assertEqual(len(self.sdks),2);self.assertEqual([r['stream'] for r in self.calls],[True,False]);self.assertTrue(all(c.is_closed() for c in self.sdks))
    def test_child_lane_separation_shared_author_policy(self):
        self.invoke();first=self.calls[-1]['headers'][0][1]
        self.scope.context={**BASE,'author':'synthetic-other'};self.invoke();self.assertEqual(self.calls[-1]['headers'][0][1],first)
        self.scope.context={**BASE,'child':'child-B','lane':'aux-title'};self.invoke('aux-sync');self.assertNotEqual(self.calls[-1]['headers'][0][1],first)

def add_valid():
    for path in ['main-sync','main-stream','aux-sync','aux-stream']:
        def valid(self,path=path):
            result=self.invoke(path);self.assertEqual(len(self.calls),1);self.assertEqual([val for k,val in self.calls[0]['headers']],[KEY]);self.assertTrue(all(type(c) is openai.OpenAI for c in self.sdks))
            if path.endswith('stream'):self.assertEqual(result[-1].usage.total_tokens,5)
            else:self.assertEqual(result.choices[0].message.content,'synthetic-only')
        setattr(Connections,'test_valid_'+path.replace('-','_'),valid)
add_valid()
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Connections)
    if MODE=='red-first':suite=unittest.TestSuite([Connections('test_valid_main_sync'),Connections('test_main_missing_context')])
    ids=[t.id() for t in suite];assert ids and len(ids)==len(set(ids))
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    report={'mode':MODE,'sdk':openai.__version__,'httpx':httpx.__version__,'tests':result.testsRun,'unique_ids':ids,'failures':[{'id':t.id(),'trace':s} for t,s in result.failures],'errors':[{'id':t.id(),'trace':s} for t,s in result.errors],'skipped':len(result.skipped),'audit':AUDIT,'observations':OBS,'source_bound_subset':True,'native_bootstrap_gateway_proxy_wire_and_auth_tested':False,'fixture_collaborators':['synthetic host scope and identity','main cache helper callbacks','aux provider resolver and cache key','proxy selection and HTTPTransport constructors replaced by RAM pools','shared-pool views','stream aggregation/window callbacks','Codex compression hook disabled for ChatCompletions fixture']}
    with (R/(MODE+'_result.json')).open('x',encoding='utf-8',newline='\n') as f:json.dump(report,f,indent=2)
    sys.stdout.write(output.getvalue());sys.exit(0 if result.wasSuccessful() else 1)
