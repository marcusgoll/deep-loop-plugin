#!/usr/bin/env python3
"""Durable local checkpoint journal. No external side-effect exactly-once guarantee."""
import argparse, json, sqlite3, sys, time
import re
from pathlib import Path

SCHEMA = '''CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, state TEXT NOT NULL, step INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL, authorization TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS steps(task_id TEXT NOT NULL, idx INTEGER NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, result TEXT, PRIMARY KEY(task_id,idx), UNIQUE(task_id,key));
CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);'''

def event(db, task, name, data):
    db.execute('INSERT INTO journal(task_id,event,payload,created) VALUES(?,?,?,?)',(task,name,json.dumps(data,sort_keys=True),time.time()))

APPLICATION_ID = 0x444c3301


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) - {'steps', 'max_attempts', 'contract_sha256'} or 'steps' not in plan:
        raise ValueError('plan requires steps and optional max_attempts')
    if 'contract_sha256' in plan and (not isinstance(plan['contract_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',plan['contract_sha256'])):
        raise ValueError('invalid optional contract hash')
    steps, limit = plan['steps'], plan.get('max_attempts', 3)
    if not isinstance(steps, list) or not steps or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('invalid plan')
    keys = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'key', 'protected'} or not isinstance(step['key'], str) or not step['key'].strip() or type(step['protected']) is not bool:
            raise ValueError('invalid step')
        keys.append(step['key'])
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate keys')
    return steps, limit


def connect(path, initialize=False, readonly=False, *, application_id=APPLICATION_ID, schema=SCHEMA):
    if path.is_symlink():
        raise ValueError('database symlinks are not supported')
    new = not path.exists()
    if new:
        if not initialize:
            raise ValueError('database does not exist')
        path.open('xb').close()
    if not new:
        probe = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10, isolation_level=None)
        try:
            if probe.execute('PRAGMA application_id').fetchone()[0] != application_id or probe.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('not a supported Deep Loop journal; preserve the existing file')
            if readonly:
                return probe
        except Exception:
            probe.close()
            raise
        probe.close()
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10, isolation_level=None)
    try:
        if new:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript(schema)
            db.execute(f'PRAGMA application_id={application_id}')
            db.execute('PRAGMA user_version=1')
        elif db.execute('PRAGMA application_id').fetchone()[0] != application_id or db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError('not a supported Deep Loop journal; preserve the existing file')
        if not readonly:
            db.execute('PRAGMA synchronous=FULL')
        return db
    except Exception:
        db.close()
        raise

def main():
    p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('action',choices=['init','claim','complete','fail','recover','status','journal']);p.add_argument('--task',required=True);p.add_argument('--plan',type=Path);p.add_argument('--key');p.add_argument('--result');p.add_argument('--attempt',type=int);p.add_argument('--authorization',choices=['not_granted','granted_for_scope'],default='not_granted');a=p.parse_args()
    db=None
    try:
        if not a.task.strip():raise ValueError('task must be nonempty')
        if a.action=='init':
            if a.plan is None:raise ValueError('init requires --plan')
            plan=json.loads(a.plan.read_bytes())
            steps,limit=validate_plan(plan)
        elif a.plan is not None or a.authorization!='not_granted':
            raise ValueError('plan and authorization apply only to init')
        if a.action in ('complete','fail') and (a.attempt is None or a.attempt < 1):
            raise ValueError('complete/fail require positive --attempt from claim')
        readonly=a.action in ('status','journal')
        db=connect(a.database,initialize=a.action=='init',readonly=readonly)
        db.execute('BEGIN' if readonly else 'BEGIN IMMEDIATE')
        row=db.execute('SELECT state,step,max_attempts,authorization FROM tasks WHERE id=?',(a.task,)).fetchone()
        if a.action=='init':
            if row:raise ValueError('task already exists')
            db.execute('INSERT INTO tasks VALUES(?,?,?,?,?)',(a.task,'ready',0,limit,a.authorization))
            for i,s in enumerate(steps):db.execute('INSERT INTO steps(task_id,idx,key,state) VALUES(?,?,?,?)',(a.task,i,s['key'],'pending'))
            # protected flag is encoded in the key metadata journal for durable approval checks
            event(db,a.task,'initialized',{'steps':steps,'max_attempts':limit,'authorization':a.authorization,**({'contract_sha256':plan['contract_sha256']} if 'contract_sha256' in plan else {})})
            result={'state':'ready'}
        elif not row:raise ValueError('unknown task')
        elif a.action in ('status','journal'):
            if a.action=='status':result={'state':row[0],'step':row[1],'steps':[dict(zip(('key','state','attempts','result'),s)) for s in db.execute('SELECT key,state,attempts,result FROM steps WHERE task_id=? ORDER BY idx',(a.task,))]}
            else:result=[{'seq':s[0],'event':s[1],'payload':json.loads(s[2])} for s in db.execute('SELECT seq,event,payload FROM journal WHERE task_id=? ORDER BY seq',(a.task,))]
        elif a.action=='recover':
            # Unknown external side effects must be reconciled manually, never replayed automatically.
            if row[0]=='running':
                db.execute("UPDATE tasks SET state='blocked' WHERE id=?",(a.task,))
                event(db,a.task,'recovery_blocked',{'reason':'in-flight operation requires reconciliation'})
            result={'state':db.execute('SELECT state FROM tasks WHERE id=?',(a.task,)).fetchone()[0]}
        else:
            state,idx,limit,authorization=row
            step=db.execute('SELECT key,state,attempts FROM steps WHERE task_id=? AND idx=?',(a.task,idx)).fetchone()
            if not step:raise ValueError('no remaining step')
            key,sstate,attempts=step
            if a.key!=key:raise ValueError('wrong step key')
            if a.action in ('complete','fail') and a.attempt!=attempts:raise ValueError('stale attempt')
            if a.action=='claim':
                if state not in ('ready','retryable') or sstate not in ('pending','retryable'):raise ValueError('not claimable')
                init=json.loads(db.execute("SELECT payload FROM journal WHERE task_id=? AND event='initialized'",(a.task,)).fetchone()[0]);protected=init['steps'][idx]['protected']
                if protected and authorization!='granted_for_scope':raise ValueError('protected step requires authorization')
                db.execute("UPDATE steps SET state='running',attempts=attempts+1 WHERE task_id=? AND idx=?",(a.task,idx));db.execute("UPDATE tasks SET state='running' WHERE id=?",(a.task,));event(db,a.task,'claimed',{'key':key,'attempt':attempts+1});result={'state':'running','key':key,'attempt':attempts+1}
            elif a.action=='complete':
                if state!='running' or sstate!='running' or not a.result or not a.result.strip():raise ValueError('not running or missing result')
                db.execute("UPDATE steps SET state='completed',result=? WHERE task_id=? AND idx=?",(a.result,a.task,idx));next_step=db.execute('SELECT 1 FROM steps WHERE task_id=? AND idx=?',(a.task,idx+1)).fetchone();new='ready' if next_step else 'completed';db.execute('UPDATE tasks SET step=?,state=? WHERE id=?',(idx+1,new,a.task));event(db,a.task,'completed_step',{'key':key,'result':a.result});result={'state':new}
            else:
                if state!='running' or sstate!='running':raise ValueError('not running')
                new='retryable' if attempts<limit else 'blocked';db.execute('UPDATE tasks SET state=? WHERE id=?',(new,a.task));db.execute('UPDATE steps SET state=? WHERE task_id=? AND idx=?',(new,a.task,idx));event(db,a.task,'failed_step',{'key':key,'state':new,'reason':a.result or 'unspecified','attempts':attempts});result={'state':new,'retry_after_seconds':min(60,2**attempts) if new=='retryable' else None}
        db.execute('COMMIT');print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,KeyError,TypeError,sqlite3.Error,OSError) as e:
        if db is not None and db.in_transaction:db.execute('ROLLBACK')
        print(f'ERROR: {e}',file=sys.stderr);return 1
    finally:
        if db is not None:db.close()
if __name__=='__main__':sys.exit(main())
