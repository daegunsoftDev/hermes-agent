"""One post-implementation retry characterization and its setting mutation.
No existing population rerun; changes only in-memory max_retries values.
"""
from pathlib import Path
import hashlib,importlib.util,io,json,sys,unittest
R=Path(__file__).resolve().parent;MODE=sys.argv[1]
sys.argv[1]='retry-characterization-parent'
s=importlib.util.spec_from_file_location('extended_parent',R/'extended.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e);sys.argv[1]=MODE
p=e.m.p;mutated=None
if MODE=='mutation-retry-setting':
    source=(R/'public_connection.py').read_text(encoding='utf-8')
    assert source.count("self.options['max_retries']=0")==1 and source.count("'max_retries':0")==1
    mutated=source.replace("self.options['max_retries']=0","self.options['max_retries']=2").replace("'max_retries':0","'max_retries':2")
    exec(compile(mutated,'<memory-retry-setting>','exec'),p.__dict__)
    assert p.PolicyRejected is e.m.v.PolicyRejected
class Retry(e.m.Connections):
    def test_denied_transport_is_not_prepared_again(self):
        self.inner_fault=e.m.v.PolicyRejected('SESSION_POLICY_REJECTED:synthetic-transport')
        client=self.main_client();self.denied(lambda:self.invoke(client=client))
        self.assertEqual(client.validation.wire_checks,1)
if __name__=='__main__':
    suite=unittest.TestSuite([Retry('test_denied_transport_is_not_prepared_again')]);out=io.StringIO();r=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
    report={'mode':MODE,'tests':r.testsRun,'failures':[{'id':t.id(),'trace':s} for t,s in r.failures],'errors':[{'id':t.id(),'trace':s} for t,s in r.errors],'skipped':len(r.skipped),'audit':e.m.AUDIT,'observations':e.m.OBS,'mutated_source_sha256':None if mutated is None else hashlib.sha256(mutated.encode()).hexdigest(),'tested_public_source_sha256':hashlib.sha256((R/'public_connection.py').read_bytes()).hexdigest(),'characterization_not_retroactive_RED':True}
    with (R/(MODE+'_result.json')).open('x',encoding='utf-8',newline='\n') as f:json.dump(report,f,indent=2)
    print(out.getvalue());sys.exit(0 if r.wasSuccessful() else 1)
