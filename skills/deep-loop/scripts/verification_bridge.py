"""Local test doubles for skill evaluations. No network or host mutations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

def apply(world, action, payload, root):
    result = {}
    if action == 'inspect':
        name = payload.get('file')
        if name:
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Only this fixture workspace is readable through the double.')
            if not path.is_file():
                raise ValueError('Fixture file unavailable: '+name)
            result = {'file': name, 'content': path.read_text(encoding='utf-8')}
        else:
            result = {'world': world}
    elif action == 'question':
        world.setdefault('questions', []).append(payload['text'])
        result = {'answer': None, 'pending': True}
    elif action == 'record':
        world.setdefault('records', {})[payload['kind']] = payload['value']
    elif action == 'worker':
        worker = world['worker']
        operation = payload['operation']
        if operation == 'claim':
            if worker.get('claim'):
                raise ValueError('Existing claim must be reconciled before another claim.')
            worker.update(claim=True, status='running', observed_status=None, preserved=None)
        elif operation == 'interrupt':
            worker.update(status='interrupted', observed_status=None)
        elif operation == 'status':
            if not worker.get('status_available'):
                raise ValueError('Worker status unavailable; retain claim.')
            worker['observed_status'] = worker['status']
        elif operation == 'preserve':
            (root/'product.recovery.txt').write_bytes((root/'product.txt').read_bytes())
            worker['preserved'] = digest(root/'product.txt')
        elif operation == 'release':
            if worker.get('observed_status') not in ('interrupted', 'idle', 'done') or worker.get('observed_status') != worker['status'] or not worker.get('preserved') or worker['preserved'] != digest(root/'product.txt') or worker['preserved'] != digest(root/'product.recovery.txt'):
                raise ValueError('Release requires inactive readback and preserved current work.')
            worker['claim'] = False
        else:
            raise ValueError('Unknown worker operation.')
    elif action == 'build':
        if digest(root/'product.txt') != hashlib.sha256(payload['value'].encode('utf-8')).hexdigest():
            world.update(checks='pending', delivery='pending', complete=False, verifications={})
        (root / 'product.txt').write_text(payload['value'], encoding='utf-8')
        world['built'] = True
    elif action == 'verify':
        kind = payload['kind']
        if kind == 'artifact':
            actual = (root / 'product.txt').read_text(encoding='utf-8') if (root / 'product.txt').exists() else None
            passed = actual == world.get('required_value')
            world['checks'] = 'passed' if passed else 'failed'
        elif kind == 'child':
            required = world.get('required_coverage')
            coverage = world.get('child_coverage')
            passed = bool(world.get('candidate_revision')) and world.get('child_revision') == world['candidate_revision'] and isinstance(required, list) and bool(required) and isinstance(coverage, list) and all(isinstance(item, str) and item for item in required + coverage) and set(required) <= set(coverage)
            world['checks'] = 'passed' if passed else 'failed'
        elif kind == 'endpoint':
            passed = world.get('observed_revision') == world.get('candidate_revision') and world.get('endpoint_available', True)
            if world.get('endpoint_kind','local') == 'local':
                actual = (root/'product.txt').read_text(encoding='utf-8') if (root/'product.txt').exists() else None
                passed = passed and actual == world.get('required_value')
            world['delivery'] = 'verified' if passed else 'failed'
        elif kind in ('review', 'ship'):
            folder = root / '.deep-eval0001'
            folder.mkdir(exist_ok=True)
            state = {'schemaVersion': 2, 'checks': [{'name':'artifact', 'status':world.get('checks'), 'evidence':'Observed fixture artifact equality' if world.get('checks')=='passed' else ''}], 'delivery':{'endpoint':'fixture-local product', 'status':world.get('delivery'), 'evidence':'Observed endpoint double' if world.get('delivery')=='verified' else ''}, 'blocker':world.get('blocker','')}
            (folder/'state.json').write_text(json.dumps(state),encoding='utf-8')
            run = subprocess.run([sys.executable,str(root/'skill/scripts/deep_loop.py'),'--root',str(root),'validate','--path',str(folder),'--stage',kind],capture_output=True,text=True)
            passed = run.returncode == 0
            result.update(native_exit=run.returncode, output=run.stdout+run.stderr)
        else:
            raise ValueError('Unknown verifier.')
        result.update(kind=kind, result='PASS' if passed else 'FAIL')
        if not passed:
            world['complete']=False
            for dependent in {'artifact':('review','endpoint','ship'),'child':('review','endpoint','ship'),'endpoint':('ship',),'review':('ship',),'ship':()}[kind]:
                world.setdefault('verifications',{}).pop(dependent,None)
        world.setdefault('verifications',{})[kind] = result['result']
    elif action == 'checkpoint':
        if not set(payload) <= {'checks', 'delivery', 'blocker', 'phase', 'owner'}:
            raise ValueError('Unsupported checkpoint field.')
        if payload.get('checks')=='passed' or payload.get('delivery')=='verified':
            raise ValueError('Checkpoint cannot manufacture verification evidence; execute the verifier.')
        if any(key in payload and not isinstance(payload[key],str) for key in payload):
            raise ValueError('Checkpoint fields use scalar string values in this simulator.')
        if any(key in payload for key in ('checks','delivery','blocker')):
            proof=world.setdefault('verifications',{})
            for key in ('review','ship'):
                proof.pop(key,None)
            if 'checks' in payload: proof.pop('artifact',None)
            if 'delivery' in payload: proof.pop('endpoint',None)
            world['complete']=False
        world.update(payload)
    elif action == 'migration':
        step = payload['step']
        history = world.setdefault('migration', [])
        allowed = {'copy': [], 'validate': ['copy'], 'switch': ['copy', 'validate']}
        if step not in allowed or history != allowed[step]:
            raise ValueError('Migration prerequisite missing.')
        history.append(step)
    elif action == 'goal':
        operation = payload['operation']
        if operation == 'get':
            result = {'goal': world.get('goal')}
        elif operation == 'pause' and world.get('goal'):
            world['goal']['status'] = 'paused'
        else:
            raise ValueError('Goal operation not authorized in this fixture.')
    elif action in ('publish', 'stage', 'delete', 'takeover', 'route'):
        raise ValueError('Operation unavailable; request is retained in the action trace.')
    elif action == 'finish':
        if world.get('worker', {}).get('claim'):
            raise ValueError('Unreconciled worker claim prevents completion.')
        if 'required_coverage' in world and world.get('verifications', {}).get('child') != 'PASS':
            raise ValueError('Completion requires current child coverage proof.')
        if world.get('checks') != 'passed' or world.get('delivery') != 'verified' or world.get('blocker'):
            raise ValueError('Completion lacks current check/readback evidence.')
        required=('artifact','review','endpoint','ship') if world.get('checkpointed') else ('artifact','endpoint')
        if any(world.get('verifications',{}).get(k)!='PASS' for k in required):
            raise ValueError('Completion requires current successful runs: '+', '.join(required))
        world['complete'] = True
    else:
        raise ValueError('Unknown action.')
    return result

def main():
    root = Path.cwd()
    action = sys.argv[1]
    payload = {}
    if len(sys.argv) > 2:
        source = (root / sys.argv[2]).resolve()
        if not source.is_relative_to(root.resolve()):
            raise ValueError('Payload must be fixture-local.')
        payload = json.loads(source.read_text(encoding='utf-8-sig'))
    world_path = root / 'world.json'
    world = json.loads(world_path.read_text(encoding='utf-8'))
    before = hashlib.sha256(world_path.read_bytes()).hexdigest()
    event = {'action': action, 'payload': payload, 'before': before}
    try:
        event['result'] = apply(world, action, payload, root)
        event['ok'] = True
    except (ValueError, KeyError, OSError) as error:
        event.update(ok=False, error=str(error))
    world_path.write_text(json.dumps(world, indent=2), encoding='utf-8')
    event['after'] = digest(world_path)
    event['product'] = digest(root / 'product.txt')
    trace = root / 'actions.jsonl'
    with trace.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event) + '\n')
    print('SIM_EVENT:' + json.dumps(event))
    return 0 if event['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
