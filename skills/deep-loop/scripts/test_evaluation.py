import sys,unittest,json,subprocess,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate import evaluate
H='a'*64

def scenario():return {'scenarios':[{'id':'one','required_checks':['A'],'evidence':{'A':{'passed':True,'artifact_sha256':H}}}]}

class EvaluationTests(unittest.TestCase):
    def test_success(self):self.assertEqual(evaluate(scenario())['overall'],'passed')
    def test_missing(self):
        d=scenario();d['scenarios'][0]['evidence']={};self.assertEqual(evaluate(d)['scenarios'][0]['status'],'incomplete')
    def test_failed(self):
        d=scenario();d['scenarios'][0]['evidence']['A']['passed']=False;self.assertEqual(evaluate(d)['scenarios'][0]['status'],'failed')
    def test_missing_hash(self):
        d=scenario();del d['scenarios'][0]['evidence']['A']['artifact_sha256'];self.assertEqual(evaluate(d)['overall'],'not_proven')
    def test_duplicate_scenarios(self):
        d=scenario();d['scenarios'].append(d['scenarios'][0]);self.assertRaises(ValueError,evaluate,d)
    def test_empty(self):self.assertRaises(ValueError,evaluate,{'scenarios':[]})
    def test_partial_score(self):
        d=scenario();d['scenarios'].append({'id':'two','required_checks':['B'],'evidence':{}});r=evaluate(d);self.assertEqual(r['pass_rate'],0.5);self.assertEqual(r['overall'],'not_proven')
    def test_duplicate_required_checks(self):
        d=scenario();d['scenarios'][0]['required_checks']=['A','A'];self.assertRaises(ValueError,evaluate,d)

    def test_unhashable_check_rejected(self):
        d=scenario();d['scenarios'][0]['required_checks']=[{}];self.assertRaises(ValueError,evaluate,d)
    def test_failure_not_hidden_by_missing(self):
        d=scenario();d['scenarios'][0]['required_checks'].append('B');d['scenarios'][0]['evidence']['A']['passed']=False;self.assertEqual(evaluate(d)['scenarios'][0]['status'],'failed')
    def test_nonboolean_pass_fails(self):
        d=scenario();d['scenarios'][0]['evidence']['A']['passed']=1;self.assertEqual(evaluate(d)['overall'],'not_proven')
    def test_cli_incomplete_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';d=scenario();d['scenarios'][0]['evidence']={};source.write_text(json.dumps(d))
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('evaluate.py')),str(source),str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,1);self.assertEqual(json.loads(out.read_text())['overall'],'not_proven')
    def test_cli_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text(json.dumps(scenario()));out.write_text('keep')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('evaluate.py')),str(source),str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertEqual(out.read_text(),'keep')
    def test_cli_invalid_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'in.json';out=root/'out.json';source.write_text('{"scenarios":[null]}')
            r=subprocess.run([sys.executable,str(Path(__file__).with_name('evaluate.py')),str(source),str(out)],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertFalse(out.exists());self.assertNotIn('Traceback',r.stderr)
    def test_malformed_evidence_container_failed(self):
        d=scenario();d['scenarios'][0]['evidence']=[];self.assertEqual(evaluate(d)['scenarios'][0]['status'],'failed')
if __name__=='__main__':unittest.main()
