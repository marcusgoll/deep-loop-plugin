"""Replay caller-declared fixtures through the local journal; no implementation execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from verify_contract import validate
ROOT=Path(__file__).resolve().parents[1]


def call(script,*args):
    if script!='durable_executor.py':raise ValueError('unsupported fixture helper')
    run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=40)
    if run.returncode:raise ValueError(f'{script}: {run.stderr.strip() or run.stdout.strip()}')
    return json.loads(run.stdout)


def execute(spec):
    required={'contract','database','task','steps','authorization'}
    if not isinstance(spec,dict) or set(spec)!=required or spec['authorization'] not in ('not_granted','granted_for_scope'):
        raise ValueError('invalid workflow specification')
    if any(not isinstance(spec[k],str) or not spec[k].strip() for k in ('contract','database','task')):
        raise ValueError('nonblank paths/task required')
    if not Path(spec['contract']).is_absolute() or not Path(spec['database']).is_absolute():
        raise ValueError('absolute contract/database paths required')
    steps=spec['steps']
    if not isinstance(steps,list) or not steps:raise ValueError('nonempty steps required')
    keys=[]
    for step in steps:
        if not isinstance(step,dict) or set(step)!={'key','protected','result'} or not isinstance(step['key'],str) or not step['key'].strip() or type(step['protected']) is not bool or step['result'] not in ('pass','fail'):
            raise ValueError('invalid fixture step')
        keys.append(step['key'])
    if len(keys)!=len(set(keys)):raise ValueError('duplicate step keys')
    contract=Path(spec['contract']).resolve()
    raw=contract.read_bytes();document=json.loads(raw);errors=validate(document)
    if errors:raise ValueError('invalid contract: '+'; '.join(errors))
    if document['blockers'] or document['status']=='blocked':raise ValueError('contract is blocked')
    if spec['authorization']=='granted_for_scope' and document['authorization']!='granted_for_scope':raise ValueError('contract does not record requested scope authority')
    digest=hashlib.sha256(raw).hexdigest()
    db=Path(spec['database']);task=spec['task']
    plan={'steps':[{'key':s['key'],'protected':s['protected']} for s in steps],'contract_sha256':digest}
    if not db.exists():
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'plan.json';source.write_text(json.dumps(plan),encoding='utf-8')
            call('durable_executor.py',db,'init','--task',task,'--plan',source,'--authorization',spec['authorization'])
    journal=call('durable_executor.py',db,'journal','--task',task)
    initial=[row['payload'] for row in journal if row['event']=='initialized']
    if len(initial)!=1 or initial[0].get('steps')!=plan['steps'] or initial[0].get('authorization')!=spec['authorization'] or initial[0].get('contract_sha256')!=digest:
        raise ValueError('persisted fixture binding mismatch; preserve journal')
    if contract.read_bytes()!=raw:raise ValueError('contract drift before fixture replay')
    status=call('durable_executor.py',db,'status','--task',task)
    if status['state']=='running':
        return {'state':'blocked','journal_state':'running','reason':'owner activity unknown; inspect before explicit recovery'}
    if status['state'] in ('blocked','completed'):
        return {'state':status['state'],'steps':status['steps'],'warning':'Fixture state is not acceptance or delivery proof.'}
    for step in steps[status['step']:]:
        try:
            claim=call('durable_executor.py',db,'claim','--task',task,'--key',step['key'])
        except ValueError as exc:
            current=call('durable_executor.py',db,'status','--task',task)
            return {'state':'blocked','journal_state':current['state'],'reason':str(exc)}
        action='complete' if step['result']=='pass' else 'fail'
        result=call('durable_executor.py',db,action,'--task',task,'--key',step['key'],'--attempt',claim['attempt'],'--result','fixture:'+step['result'])
        if action=='fail':return {'state':result['state'],'reason':'declared fixture failed'}
    status=call('durable_executor.py',db,'status','--task',task)
    return {'state':status['state'],'steps':status['steps'],'warning':'Fixture-only replay; completed does not mean independently proven.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        spec=json.loads(args.input.read_bytes())
        if isinstance(spec,dict) and isinstance(spec.get('database'),str):
            forbidden={Path(spec['database']+suffix).resolve() for suffix in ('','-wal','-shm','-journal')}
            if args.output.resolve() in forbidden:raise ValueError('output must not alias database or SQLite sidecars')
        # Reserve before journal effects; rejected collisions cannot advance a fixture.
        with args.output.open('x',encoding='utf-8') as stream:
            result=execute(spec)
            stream.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
    except (ValueError,TypeError,OSError,subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(result['state'])
    return 0 if result['state']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
