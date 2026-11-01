"""Context-binding TDD; actual native leaves and SDK, declared host/DB/cache collaborators."""
from __future__ import annotations
import ast,builtins,copy,dataclasses,hashlib,importlib.util,io,json,logging,os,sys,threading,types,unittest
from pathlib import Path
R=Path(__file__).resolve().parent;MODE=sys.argv[1];sys.argv[1]='context-parent'
spec=importlib.util.spec_from_file_location('public_trial',R/'exercise.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.argv[1]=MODE
import source_defs as d
cb=None
if (R/'context_binding.py').exists():
    import context_binding as cb

CONTEXT_OBS=[]
class ContextConnections(m.Connections):
    def setUp(self):
        super().setUp();self.boundary=3;self.boundary_calls=[];self.current=True;self.created=[];self.cache_inits=0
        case=self
        class DB:
            def latest_conversation_boundary(db,key,source):
                case.boundary_calls.append((key,source))
                if isinstance(case.boundary,Exception):raise case.boundary
                return case.boundary
        self.db=DB()
        self.source=d.SessionSource(platform=d.Platform.DISCORD,chat_id='synthetic-channel',chat_type='thread',thread_id='synthetic-thread',user_id='synthetic-author-A')
        self.identity=d.RoutingIdentity('synthetic-profile','synthetic-profile',R/'synthetic-auth-home',R/'synthetic-runtime-home')
        self.source._identity=self.identity
        self.ctx=d.TurnContext(source=self.source,session_id='physical-A',session_key=d.build_session_key(self.source,profile=self.identity.session_key_profile),user_config={},run_generation=101,_run_still_current=lambda:self.current)
        def make_agent(**kw):self.created.append(kw);return self.agent
        self.ctx.AIAgent=make_agent
        self.inputs=types.SimpleNamespace(workspace='trusted-workspace',child='main',engine='claude',revision='contract-v1',session_source='discord')
        self.runner=types.SimpleNamespace(_stateful_policy_inputs=self.inputs,_session_db=self.db,_agent_cache={},_agent_cache_lock=threading.RLock(),_prefill_messages=None,_service_tier=None,_refresh_fallback_model=lambda:None,_apply_fallback_chain_to_agent=lambda *a:None,_agent_config_signature=lambda *a,**kw:('fixture-signature',),_extract_cache_busting_config=lambda c:{},_enforce_agent_cache_cap=lambda:None,_init_cached_agent_for_turn=lambda *a:setattr(self,'cache_inits',self.cache_inits+1))
        self.route={'model':'synthetic-model','runtime':{'provider':'custom','base_url':m.v.SYNTHETIC_ROUTE}}
        original_import=builtins.__import__
        def narrow(name,*a,**kw):
            if name=='gateway.run':return types.SimpleNamespace(_checkpoint_agent_kwargs=lambda c:{})
            return original_import(name,*a,**kw)
        env={'__builtins__':{**vars(builtins),'__import__':narrow},'dataclasses':dataclasses,'suppress':__import__('contextlib').suppress,'logger':logging.getLogger('context-runner')}
        if cb:env.update(prepare_run_scope=cb.prepare_run_scope,bind_agent_scope=cb.bind_agent_scope)
        d.load('gateway/run_turn_runner.py',{'_CachedAgentLookup','_skip_context_files','_lookup_cached_agent','_build_fresh_agent','_resolve_turn_agent'},env,root='candidate-context' if cb else 'candidate')
        class Harness:
            _cached_sid_is_dead=lambda *a:(None,False)
            _current_message_count=lambda *a:0
            _release_evicted_agent=lambda *a:None
            _pop_cached_agent_for_eviction=lambda *a:None
        for name in ['_CachedAgentLookup','_skip_context_files','_lookup_cached_agent','_build_fresh_agent','_resolve_turn_agent']:setattr(Harness,name,env[name])
        self.gateway=Harness();self.gateway._ctx=self.ctx;self.gateway._runner=self.runner
    def resolve(self):return self.gateway._resolve_turn_agent(self.route,'discord',None,5,None,{})
    def test_native_fresh_resolution_control(self):
        agent,reused=self.resolve();self.assertIs(agent,self.agent);self.assertFalse(reused);self.assertEqual(self.created[0]['gateway_session_key'],self.ctx.session_key)
    def test_fresh_agent_receives_run_scope(self):
        agent,_=self.resolve();scope=getattr(agent,'_stateful_run_scope',None)
        self.assertIsNotNone(scope,'fresh Gateway resolution did not bind trusted RunScope')
        self.assertEqual(scope.conversation,self.ctx.session_key);self.assertEqual(scope.epoch,3);self.assertEqual(scope.profile,self.identity.runtime_profile);self.assertEqual(scope.workspace,'trusted-workspace')

    def pre_rejected(self):
        error=None
        try:self.resolve()
        except Exception as exc:error=exc
        self.assertIsInstance(error,m.v.PolicyRejected)
        self.assertEqual(self.created,[]);self.assertEqual(self.sdks,[]);self.assertEqual(self.calls,[])
    def test_cached_agent_gets_new_run_snapshot(self):
        a,_=self.resolve();first=getattr(a,'_stateful_run_scope',None)
        self.inputs.workspace='next-workspace';self.boundary=4;self.ctx.run_generation=500
        b,reused=self.resolve();second=getattr(b,'_stateful_run_scope',None)
        self.assertTrue(reused);self.assertIs(a,b);self.assertIsNot(first,second)
        self.assertEqual(second.workspace,'next-workspace');self.assertEqual(second.epoch,4)
    def test_missing_workspace_has_no_ambient_fallback(self):
        self.inputs.workspace=None;self.pre_rejected()
    def test_wire_profile_is_not_routing_identity(self):
        self.source.profile='model-supplied-profile';self.source._identity=None;self.pre_rejected()
    def test_conversation_must_match_native_key(self):
        self.ctx.session_key='model-supplied-session';self.pre_rejected()
    def test_missing_epoch_not_zero_or_run_generation(self):
        self.boundary=None;self.ctx.run_generation=100;self.pre_rejected()
    def test_boolean_epoch_rejected(self):
        self.boundary=True;self.pre_rejected()
    def test_failed_epoch_lookup_rejected(self):
        self.boundary=OSError('synthetic-db-read-failure');self.pre_rejected()
    def test_engine_not_guessed_from_custom_provider(self):
        self.inputs.engine=None;self.pre_rejected()
    def test_revision_still_explicit_fixture(self):
        self.inputs.revision=None;self.pre_rejected()
    def test_stale_run_rejected_before_agent_resolution(self):
        self.current=False;self.pre_rejected()

    def connect_policy_boundary(self):
        self.assertTrue(callable(getattr(cb,'policy_for',None)),'call-owned policy adapter absent')
        self.sdk_entries=0
        def tracked_factory(**kw):
            raw=self.sdk_factory(**kw);original=raw.chat.completions.create
            def actual_create(**args):self.sdk_entries+=1;return original(**args)
            raw.chat.completions.create=actual_create;return raw
        def create(options,context):return cb.create_policy_client(options,context,self.build,sdk_factory=tracked_factory)
        self.agent._create_request_openai_client.__globals__.update(stateful_scope=cb.current_policy,create_stateful_client=create)
        self.aux.update(stateful_scope=cb.current_policy,create_stateful_client=create)
        if (R/'candidate-context/agent/auxiliary_client.py').exists():
            self.aux['require_call_route']=cb.require_call_route
            d.load('agent/auxiliary_client.py',{'_get_cached_client'},self.aux,root='candidate-context')
    def policy_request(self,policy):
        return {'model':policy.model,'messages':[{'role':'user','content':'synthetic-only'}],'extra_headers':{'X-Session-Id':m.v.make_key(policy.context)}}
    def test_bound_main_policy_reaches_real_sdk(self):
        self.connect_policy_boundary();agent,_=self.resolve();policy=cb.policy_for(agent._stateful_run_scope,'primary')
        with cb.bind_call(policy):result=self.invoke(request=self.policy_request(policy))
        self.assertEqual(result.choices[0].message.content,'synthetic-only');self.assertEqual(self.sdk_entries,1);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0]['headers'][0][1],m.v.make_key(policy.context))

    def run_policy(self,lane='primary'):
        agent,_=self.resolve();error=None;policy=None
        try:policy=cb.policy_for(agent._stateful_run_scope,lane)
        except Exception as exc:error=exc
        self.assertIsNone(error,'host-selected policy failed: '+repr(error));return policy
    def catch_policy(self,fn):
        error=None
        try:fn()
        except Exception as exc:error=exc
        self.assertIsInstance(error,m.v.PolicyRejected);return error
    def aux_for(self,policy,*,model=None,task='title'):
        c,resolved=self.aux['_get_cached_client']('custom',model=policy.model if model is None else model,base_url=m.v.SYNTHETIC_ROUTE,api_key=self.options()['api_key'],task=task)
        if c is not None:self.handles.append(c)
        return c
    def test_main_stream_with_host_policy(self):
        self.connect_policy_boundary();policy=self.run_policy()
        with cb.bind_call(policy):result=self.invoke('main-stream',request=self.policy_request(policy))
        self.assertEqual(result[-1].usage.total_tokens,5);self.assertEqual(self.sdk_entries,1);self.assertEqual(self.close_calls,0)
    def test_aux_policy_uses_its_selected_model(self):
        self.connect_policy_boundary();self.inputs.auxiliary={'title':{'engine':'codex','model':'synthetic-aux-model'}};policy=self.run_policy('aux-title')
        with cb.bind_call(policy):
            client=self.aux_for(policy);result=self.invoke('aux-sync',request=self.policy_request(policy),client=client)
        self.assertEqual(result.model,'synthetic-aux-model');self.assertEqual(self.sdk_entries,1);self.assertEqual(len(self.calls),1);self.assertEqual(policy.engine,'codex');self.assertEqual(policy.lane,'aux-title')
    def test_aux_stream_policy_uses_its_selected_lane(self):
        self.connect_policy_boundary();self.inputs.auxiliary={'title':{'engine':'claude','model':'synthetic-model'}};policy=self.run_policy('aux-title')
        with cb.bind_call(policy):
            client=self.aux_for(policy);result=self.invoke('aux-stream',request=self.policy_request(policy),client=client)
        self.assertEqual(result[-1].usage.total_tokens,5);self.assertEqual(self.sdk_entries,1);self.assertEqual(self.close_calls,0)
    def test_aux_model_mismatch_stops_before_resolver(self):
        self.connect_policy_boundary();self.inputs.auxiliary={'title':{'engine':'claude','model':'synthetic-model'}};policy=self.run_policy('aux-title')
        with cb.bind_call(policy):self.catch_policy(lambda:self.aux_for(policy,model='unselected-model'))
        self.assertEqual(self.resolves,0);self.assertEqual(self.sdk_entries,0);self.assertEqual(self.calls,[])
    def test_aux_task_mismatch_stops_before_resolver(self):
        self.connect_policy_boundary();self.inputs.auxiliary={'title':{'engine':'claude','model':'synthetic-model'}};policy=self.run_policy('aux-title')
        with cb.bind_call(policy):self.catch_policy(lambda:self.aux_for(policy,task='unknown'))
        self.assertEqual(self.resolves,0);self.assertEqual(self.sdk_entries,0);self.assertEqual(self.calls,[])
    def test_missing_binding_has_no_environment_fallback(self):
        self.connect_policy_boundary()
        from unittest.mock import patch
        with patch.dict(os.environ,{'HERMES_SESSION_KEY':self.ctx.session_key,'HERMES_PROFILE':'synthetic-profile'}):self.catch_policy(self.main_client)
        self.assertEqual(self.sdk_entries,0);self.assertEqual(self.sdks,[]);self.assertEqual(self.calls,[])
    def test_shared_author_switch_preserves_wire_key(self):
        self.connect_policy_boundary();a=self.run_policy()
        with cb.bind_call(a):self.invoke(request=self.policy_request(a))
        self.source.user_id='synthetic-author-B';self.source.user_name='not-key-material';b=self.run_policy()
        with cb.bind_call(b):self.invoke(request=self.policy_request(b))
        self.assertEqual(a.context,b.context);self.assertEqual([r['headers'][0][1] for r in self.calls],[m.v.make_key(a.context)]*2)
    def test_namespace_changes_separate_wire_keys(self):
        self.connect_policy_boundary();first=self.run_policy();basekey=m.v.make_key(first.context)
        original_identity=self.identity
        for field in ['profile','workspace','child','engine','model']:
            with self.subTest(field=field):
                if field=='profile':
                    self.source._identity=dataclasses.replace(original_identity,runtime_profile='different-profile');self.ctx.session_key=d.build_session_key(self.source,profile='different-profile')
                elif field=='model':self.route['model']='different-model'
                else:setattr(self.inputs,field,'different-'+field)
                policy=self.run_policy()
                with cb.bind_call(policy):self.invoke(request=self.policy_request(policy))
                self.assertNotEqual(self.calls[-1]['headers'][0][1],basekey)
                self.source._identity=original_identity;self.ctx.session_key=d.build_session_key(self.source,profile=original_identity.session_key_profile);self.inputs.workspace='trusted-workspace';self.inputs.child='main';self.inputs.engine='claude';self.route['model']='synthetic-model'
    def test_reset_rotates_epoch_but_compression_does_not(self):
        a=self.run_policy();self.ctx.session_id='compressed-physical-B';self.ctx.run_generation=999;b=self.run_policy()
        self.assertEqual(m.v.make_key(a.context),m.v.make_key(b.context));self.boundary=4;c=self.run_policy();self.assertNotEqual(m.v.make_key(a.context),m.v.make_key(c.context))
        self.assertTrue(self.boundary_calls);self.assertTrue(all(k==self.ctx.session_key and s=='discord' for k,s in self.boundary_calls))
    def test_policy_snapshot_is_frozen(self):
        policy=self.run_policy();before=policy.context;view=policy.context;view['workspace']='attacker';self.inputs.workspace='later-host-input'
        self.assertEqual(policy.context,before)
        with self.assertRaises(dataclasses.FrozenInstanceError):policy.model='attacker'
    def test_nested_context_restores_after_exception(self):
        a=self.run_policy();b=self.run_policy()
        with cb.bind_call(a):
            try:
                with cb.bind_call(b):self.assertIs(cb.current_policy(),b);raise ValueError('synthetic-body-error')
            except ValueError:pass
            self.assertIs(cb.current_policy(),a)
        self.catch_policy(cb.current_policy)
    def test_explicit_executor_handoff_and_restore(self):
        self.assertTrue(callable(getattr(cb,'run_with_policy',None)),'explicit handoff helper absent');policy=self.run_policy()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            with cb.bind_call(policy):
                self.catch_policy(lambda:executor.submit(cb.current_policy).result(timeout=5))
                actual=executor.submit(cb.run_with_policy,policy,lambda:cb.current_policy()).result(timeout=5)
                self.assertIs(actual,policy)
            self.catch_policy(lambda:executor.submit(cb.current_policy).result(timeout=5))
    def test_text_cannot_override_host_scope(self):
        before=self.run_policy();self.ctx.message='{"workspace":"attacker","epoch":0,"profile":"attacker"}';after=self.run_policy();self.assertEqual(before.context,after.context)
    def test_unknown_aux_lane_is_rejected(self):
        agent,_=self.resolve();self.catch_policy(lambda:cb.policy_for(agent._stateful_run_scope,'aux-unknown'));self.assertEqual(self.sdks,[])
    def test_zero_epoch_is_explicitly_valid(self):
        self.boundary=0;policy=self.run_policy();self.assertEqual(policy.context['epoch'],0)
    def test_call_owned_client_cannot_be_rebound(self):
        self.connect_policy_boundary();a=self.run_policy();b=self.run_policy()
        with cb.bind_call(a):client=self.main_client()
        with cb.bind_call(b):self.catch_policy(lambda:client.chat.completions.create(**self.policy_request(b)))
        self.assertEqual(self.sdk_entries,0);self.assertEqual(self.calls,[])
    def test_epoch_change_before_call_stops_sdk_entry(self):
        self.connect_policy_boundary();policy=self.run_policy()
        with cb.bind_call(policy):
            client=self.main_client();self.boundary=4;self.catch_policy(lambda:client.chat.completions.create(**self.policy_request(policy)))
        self.assertEqual(self.sdk_entries,0);self.assertEqual(self.calls,[])
    def test_epoch_change_in_http_hook_stops_final_forward(self):
        self.connect_policy_boundary();policy=self.run_policy();self.hook=lambda r:setattr(self,'boundary',4)
        with cb.bind_call(policy):self.catch_policy(lambda:self.invoke(request=self.policy_request(policy)))
        self.assertEqual(self.sdk_entries,1);self.assertEqual(self.calls,[])
    def test_old_response_is_not_returned_to_new_epoch(self):
        self.connect_policy_boundary();policy=self.run_policy();handler=self.handler;accepted=[]
        def reset_after_response(request):
            response=handler(request);self.boundary=4;return response
        self.handler=reset_after_response
        def invoke_and_accept():accepted.append(self.invoke(request=self.policy_request(policy)))
        with cb.bind_call(policy):self.catch_policy(invoke_and_accept)
        self.assertEqual(accepted,[]);self.assertEqual(self.sdk_entries,1);self.assertEqual(len(self.calls),1)
    def test_old_stream_is_closed_after_epoch_reset(self):
        self.connect_policy_boundary();policy=self.run_policy()
        with cb.bind_call(policy):
            client=self.main_client();stream=client.chat.completions.create(**{**self.policy_request(policy),'stream':True})
        self.boundary=4;self.catch_policy(lambda:next(iter(stream)))
        self.assertTrue(self.sdks[0].is_closed());self.assertEqual(self.sdk_entries,1);self.assertEqual(len(self.calls),1);self.assertEqual(self.close_calls,0)

    def test_aux_late_epoch_denial_never_falls_back(self):
        self.connect_policy_boundary();self.inputs.auxiliary={'title':{'engine':'claude','model':'synthetic-model'}};policy=self.run_policy('aux-title');self.aux['_aux_progress_active']=lambda:True;self.hook=lambda r:setattr(self,'boundary',4)
        with cb.bind_call(policy):
            client=self.aux_for(policy);self.catch_policy(lambda:self.invoke('aux-sync',request=self.policy_request(policy),client=client))
        self.assertEqual(self.sdk_entries,1);self.assertEqual(self.dispatches,1);self.assertEqual(self.resolves,1);self.assertEqual(self.calls,[])
    def tearDown(self):
        CONTEXT_OBS.append({'case':self.id(),'sdk_entries':getattr(self,'sdk_entries',0),'sdk_instances':len(self.sdks),'forwards':len(self.calls),'aux_dispatches':self.dispatches,'resolver_calls':self.resolves,'sdk_retries':[o['max_retries'] for o in self.sdk_options],'pool_closes':self.close_calls,'boundary_reads':len(self.boundary_calls)})
        super().tearDown()

MUTATIONS={
 'mutation-no-rebind':['test_cached_agent_gets_new_run_snapshot'],
 'mutation-author-key':['test_shared_author_switch_preserves_wire_key'],
 'mutation-epoch-ignore':['test_reset_rotates_epoch_but_compression_does_not'],
 'mutation-final-scope':['test_epoch_change_in_http_hook_stops_final_forward'],
 'mutation-post-response':['test_old_response_is_not_returned_to_new_epoch'],
 'mutation-context-restore':['test_nested_context_restores_after_exception'],
 'mutation-aux-route':['test_aux_model_mismatch_stops_before_resolver','test_aux_task_mismatch_stops_before_resolver'],
}
def mutate():
    if MODE=='mutation-no-rebind':
        original=cb.bind_agent_scope
        cb.bind_agent_scope=lambda a,s:original(a,s) if getattr(a,'_stateful_run_scope',None) is None else None
    elif MODE=='mutation-author-key':
        original=cb.prepare_run_scope
        def wrong(ctx,*args):
            scope=original(ctx,*args);return dataclasses.replace(scope,conversation=scope.conversation+':'+ctx.source.user_id)
        cb.prepare_run_scope=wrong
    elif MODE=='mutation-epoch-ignore':cb.strict_epoch=lambda *a:3
    elif MODE=='mutation-final-scope':cb.ScopeTransport.handle_request=lambda self,request:self.inner.handle_request(request)
    elif MODE=='mutation-post-response':
        tree=ast.parse((R/'context_binding.py').read_text(encoding='utf-8'));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PolicyClient');node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='create');changed=0
        for n in ast.walk(node):
            if isinstance(n,ast.Try) and len(n.body)==1 and isinstance(n.body[0],ast.Expr) and ast.unparse(n.body[0])=='self.policy.run.assert_current()':n.body=[ast.Pass()];changed+=1
        if changed!=1:raise ValueError('mutation seam')
        env=dict(cb.__dict__);exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])),'<memory-post-response>','exec'),env);cb.PolicyClient.create=env['create']
    elif MODE=='mutation-context-restore':
        from contextlib import contextmanager
        @contextmanager
        def leak(policy):cb._POLICY.set(policy);yield policy
        cb.bind_call=leak
    elif MODE=='mutation-aux-route':cb.require_call_route=lambda *a:None

if __name__=='__main__':
    names=['test_native_fresh_resolution_control','test_fresh_agent_receives_run_scope'] if MODE=='red-binding' else sorted(n for n in ContextConnections.__dict__ if n.startswith('test_'))
    if MODE in MUTATIONS:mutate();names=MUTATIONS[MODE]
    suite=unittest.TestSuite(ContextConnections(n) for n in names);ids=[t.id() for t in suite]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('population')
    out=io.StringIO();result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
    report={'mode':MODE,'optimize':sys.flags.optimize,'tests':result.testsRun,'unique_ids':ids,'failures':[{'id':t.id(),'trace':s} for t,s in result.failures],'errors':[{'id':t.id(),'trace':s} for t,s in result.errors],'skips':len(result.skipped),'audit':m.AUDIT,'observations':m.OBS,'context_observations':CONTEXT_OBS,'mutation':MODE if MODE in MUTATIONS else None,'source_bound_subset':True,'native_activation':False}
    with (R/(MODE+'_result.json')).open('x',encoding='utf-8',newline='\n') as f:json.dump(report,f,indent=2)
    print(out.getvalue());sys.exit(0 if result.wasSuccessful() else 1)
