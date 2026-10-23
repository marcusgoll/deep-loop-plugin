import unittest,sys,json,subprocess,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark import compare
H='a'*64
def scenario(i,passed):return {'id':i,'required_checks':['check'],'evidence':{'check':{'passed':True,'artifact_sha256':H}} if passed else {}}
class BenchmarkTests(unittest.TestCase):
 def test_delta(self):
  r=compare({'baseline':{'scenarios':[scenario('a',False)]},'candidate':{'scenarios':[scenario('a',True)]}});self.assertEqual(r['pass_rate_delta'],1)
 def test_mismatched_scenarios(self):
  self.assertRaises(ValueError,compare,{'baseline':{'scenarios':[scenario('a',True)]},'candidate':{'scenarios':[scenario('b',True)]}})
 def test_missing_baseline(self):self.assertRaises(ValueError,compare,{'candidate':{'scenarios':[scenario('a',True)]}})
 def test_no_scenarios(self):self.assertRaises(ValueError,compare,{'baseline':{'scenarios':[]},'candidate':{'scenarios':[]}})
 def test_mismatched_checks(self):
  a=scenario('a',True);b=scenario('a',True);b['required_checks']=['other'];b['evidence']={'other':{'passed':True,'artifact_sha256':H}}
  self.assertRaises(ValueError,compare,{'baseline':{'scenarios':[a]},'candidate':{'scenarios':[b]}})
 def test_bad_shape(self):self.assertRaises(ValueError,compare,[])
 def test_check_order_irrelevant(self):
  a=scenario('a',False);b=scenario('a',False);a['required_checks']=['one','two'];b['required_checks']=['two','one'];self.assertEqual(compare({'baseline':{'scenarios':[a]},'candidate':{'scenarios':[b]}})['pass_rate_delta'],0)
 def test_cli_preserves_output(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text(json.dumps({'baseline':{'scenarios':[scenario('a',False)]},'candidate':{'scenarios':[scenario('a',True)]}}));out.write_text('keep')
   r=subprocess.run([sys.executable,str(Path(__file__).with_name('benchmark.py')),str(source),str(out)],capture_output=True);self.assertEqual(r.returncode,2);self.assertEqual(out.read_text(),'keep')
if __name__=='__main__':unittest.main()
