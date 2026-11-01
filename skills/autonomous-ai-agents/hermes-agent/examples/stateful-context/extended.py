"""Extended integration acceptance, reused outer fix, in-memory controls.
Original 29-case RED/GREEN harness remains byte-for-byte unchanged.
"""
from pathlib import Path
import ast,dataclasses,hashlib,importlib.util,io,json,sys,types,unittest
R=Path(__file__).resolve().parent;MODE=sys.argv[1]
sys.argv[1]='green-parent'
spec=importlib.util.spec_from_file_location('source_trial',R/'exercise.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.argv[1]=MODE
original_extract=m.extracted
if MODE=='mutation-wire':m.p.GuardedTransport.handle_request=lambda self,request:self.inner.handle_request(request)
def memory_extract(rel,names,env,candidate=True):
    env=original_extract(rel,names,env,candidate)
    target=None
    if MODE=='mutation-main' and rel=='agent/client_lifecycle.py':target='_create_request_openai_client'
    if MODE=='mutation-aux' and rel=='agent/auxiliary_client.py':target='_create_with_progress_once'
    if target and target in names:
        tree=ast.parse((R/'candidate'/rel).read_text(encoding='utf-8'));n=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==target)
        if MODE=='mutation-main':
            assert isinstance(n.body[0],ast.Assign) and isinstance(n.body[1],ast.If)
            assert 'stateful_scope' in ast.unparse(n.body[0]);n.body=n.body[2:]
        else:
            handlers=[x for x in ast.walk(n) if isinstance(x,ast.ExceptHandler)]
            h=handlers[0];assert isinstance(h.body[0],ast.If) and 'PolicyRejected' in ast.unparse(h.body[0]);h.body=h.body[1:]
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),n],type_ignores=[])),'<memory-'+MODE+'>','exec'),env)
    return env
m.extracted=memory_extract
class Extended(m.Connections):
    def outer(self,error):
        events=[]
        def recover(*a,**kw):events.append('recovery-entered');return True,'synthetic-system'
        mod=types.ModuleType('trial_outer_'+MODE);sys.modules[mod.__name__]=mod
        env=mod.__dict__;env.update({'dataclass':dataclasses.dataclass,'recover_before_classification':recover,'PolicyRejected':m.v.PolicyRejected})
        root='snapshot' if MODE=='red-outer' else 'candidate'
        path=R/root/'agent/turn_api_error.py';tree=ast.parse(path.read_text(encoding='utf-8'))
        nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in {'ApiErrorVerdict','handle_api_error'}];assert len(nodes)==2
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+nodes,type_ignores=[])),str(path),'exec'),env)
        result=env['handle_api_error'](types.SimpleNamespace(thinking_callback=None),api_error=error,_retry=types.SimpleNamespace(),thinking_spinner=None,messages=[],api_messages=[],api_kwargs={},system_message={},active_system_prompt='synthetic-system',conversation_history=[],approx_tokens=0,retry_count=0,max_retries=3,compression_attempts=0,max_compression_attempts=1,api_call_count=0,api_request_id='synthetic-request',api_start_time=0,effective_task_id='synthetic-task',turn_id='synthetic-turn')
        return result,events
    def test_outer_policy_no_recovery_or_retry(self):
        result,events=self.outer(m.v.PolicyRejected('SESSION_POLICY_REJECTED:synthetic'))
        self.assertEqual(result.action,'return');self.assertEqual(events,[]);self.assertIs(result.result['failure_retryable'],False);self.assertIs(result.result['failed'],True)
    def test_outer_nonpolicy_control(self):
        result,events=self.outer(OSError('synthetic-only'));self.assertEqual(result.action,'continue');self.assertEqual(events,['recovery-entered'])
    def test_context_frozen_after_handle_creation(self):
        request=self.request();c=self.main_client();self.scope.context['conversation']='other';self.invoke(client=c,request=request);self.assertEqual(self.calls[0]['headers'][0][1],m.KEY)
    def test_two_stream_owners_close_independently(self):
        a=self.main_client();sa=a.chat.completions.create(**{**self.request(),'stream':True})
        self.scope.context={**m.BASE,'child':'child-B'};b=self.main_client();sb=b.chat.completions.create(**{**self.request(),'stream':True})
        a.close();self.assertTrue(self.sdks[0].is_closed());self.assertFalse(self.sdks[1].is_closed());self.assertEqual(next(iter(sb)).choices[0].delta.content,'synthetic');sb.close();self.assertEqual(self.close_calls,0)
    def test_caught_denial_stays_typed_and_sticky(self):
        c=self.main_client();bad=self.request();bad['extra_headers']={'X-Session-Id':'other'}
        errors=[]
        for request in [bad,self.request()]:
            try:c.chat.completions.create(**request)
            except Exception as exc:errors.append(exc)
        self.assertEqual(len(errors),2);self.assertIsInstance(errors[0],m.v.PolicyRejected);self.assertIs(errors[0],errors[1]);self.assertEqual(self.sdks,[])

def add_missing():
    for path in ['main-sync','main-stream','aux-sync','aux-stream']:
        def missing(self,path=path):
            request=self.request();request.pop('extra_headers');self.denied(lambda:self.invoke(path,request=request),'missing-header');self.assertEqual(self.sdks,[])
        setattr(Extended,'test_missing_header_'+path.replace('-','_'),missing)
add_missing()
if __name__=='__main__':
    if MODE=='red-outer':suite=unittest.TestSuite([Extended('test_outer_nonpolicy_control'),Extended('test_outer_policy_no_recovery_or_retry')])
    else:suite=unittest.defaultTestLoader.loadTestsFromTestCase(Extended)
    ids=[t.id() for t in suite];assert ids and len(ids)==len(set(ids))
    out=io.StringIO();result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
    report={'mode':MODE,'optimize':sys.flags.optimize,'tests':result.testsRun,'unique_ids':ids,'failures':[{'id':t.id(),'trace':s} for t,s in result.failures],'errors':[{'id':t.id(),'trace':s} for t,s in result.errors],'skipped':len(result.skipped),'audit':m.AUDIT,'observations':m.OBS,'sdk':m.openai.__version__,'httpx':m.httpx.__version__,'new_after_initial_green':'outer measured RED separately; context/sticky/missing-header/overlapping-stream cases are post-implementation characterization','mutation':MODE if MODE.startswith('mutation-') else None,'source_pins':{f.relative_to(R).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in [R/'exercise.py',R/'extended.py',R/'public_connection.py',R/'validation.py',*(R/'candidate/agent').glob('*.py')]},'native_gateway_and_proxy_wire_acceptance':False}
    with (R/(MODE+'_result.json')).open('x',encoding='utf-8',newline='\n') as f:json.dump(report,f,indent=2)
    sys.stdout.write(out.getvalue());sys.exit(0 if result.wasSuccessful() else 1)
