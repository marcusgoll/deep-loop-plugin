#!/usr/bin/env python3
"""Local durable task coordinator. Leases fence recorded results, not external side effects."""
import argparse
import json
import math
import os
from worker_identity import validate as validate_worker
from trusted_verifier import validate as validate_proof
from durable_executor import connect
import sqlite3
import sys
import time
from pathlib import Path

DDL = '''
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT NOT NULL, deps TEXT NOT NULL, workspace TEXT NOT NULL UNIQUE, protected INTEGER NOT NULL, authorized INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0, owner TEXT, deadline REAL, implementation TEXT, proof TEXT);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
'''

APPLICATION_ID = 0x444c3401


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'jobs'} or not isinstance(plan['jobs'], list) or not plan['jobs']:
        raise ValueError('plan requires nonempty jobs')
    jobs = plan['jobs']
    ids, spaces = set(), set()
    for job in jobs:
        if not isinstance(job, dict) or set(job) != {'id', 'deps', 'workspace', 'protected', 'authorized'}:
            raise ValueError('invalid job fields')
        if any(not isinstance(job[k], str) or not job[k].strip() for k in ('id', 'workspace')) or type(job['protected']) is not bool or type(job['authorized']) is not bool:
            raise ValueError('invalid job values')
        if job['id'] in ids or job['workspace'] in spaces:
            raise ValueError('duplicate job or workspace identifier')
        ids.add(job['id']); spaces.add(job['workspace'])
        deps = job['deps']
        if not isinstance(deps, list) or any(not isinstance(d, str) or not d.strip() for d in deps) or len(deps) != len(set(deps)):
            raise ValueError('invalid dependencies')
    graph = {j['id']:set(j['deps']) for j in jobs}
    if any(not deps <= ids or key in deps for key,deps in graph.items()):
        raise ValueError('unknown or self dependency')
    remaining = dict(graph)
    while remaining:
        ready = {key for key,deps in remaining.items() if not deps}
        if not ready:
            raise ValueError('dependency cycle')
        remaining = {key:deps-ready for key,deps in remaining.items() if key not in ready}
    return jobs


def main():
    p=argparse.ArgumentParser()
    p.add_argument('database',type=Path)
    p.add_argument('action',choices=['init','lease','submit','verify','expire','status','events'])
    p.add_argument('--plan',type=Path)
    p.add_argument('--job');p.add_argument('--worker');p.add_argument('--token',type=int)
    p.add_argument('--result');p.add_argument('--ttl',type=float,default=60)
    p.add_argument('--now',type=float)
    p.add_argument('--capability');p.add_argument('--contract',type=Path);p.add_argument('--manifest',type=Path);p.add_argument('--proof-plan',type=Path)
    a=p.parse_args()
    db=None
    try:
        now=time.time() if a.now is None else a.now
        if not math.isfinite(now) or now < 0:raise ValueError('now must be finite and nonnegative')
        if a.action=='init':
            if a.plan is None:raise ValueError('init requires --plan')
            jobs=validate_plan(json.loads(a.plan.read_bytes()))
        elif a.plan is not None:raise ValueError('plan applies only to init')
        if a.action in ('lease','submit','verify') and (not a.worker or not a.worker.strip()):raise ValueError('worker must be nonempty')
        if a.action=='lease' and (not math.isfinite(a.ttl) or not 0 < a.ttl <= 3600 or not math.isfinite(now+a.ttl)):raise ValueError('invalid ttl/deadline')
        if a.action in ('submit','verify') and (not a.job or not a.job.strip() or a.token is None or a.token < 1 ):raise ValueError('job and current token required')
        if a.action=='submit' and (not a.result or not a.result.strip()):raise ValueError('implementation reference required')
        if a.action=='verify' and (a.now is not None or not a.capability or a.contract is None or a.manifest is None or a.proof_plan is None):raise ValueError('verify requires capability, contract, manifest, proof-plan and real clock')
        readonly=a.action in ('status','events')
        db=connect(a.database,initialize=a.action=='init',readonly=readonly,application_id=APPLICATION_ID,schema=DDL)
        def log(job,kind,data):db.execute('INSERT INTO events(job,kind,data) VALUES(?,?,?)',(job,kind,json.dumps(data,sort_keys=True)))
        db.execute('BEGIN' if readonly else 'BEGIN IMMEDIATE')
        if a.now is None:now=time.time()
        if not math.isfinite(now) or now < 0:raise ValueError('now must be finite and nonnegative')
        if a.action=='lease' and not math.isfinite(now+a.ttl):raise ValueError('invalid deadline')
        if a.action=='init':
            if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]:raise ValueError('graph already initialized')
            for j in jobs:
                db.execute('INSERT INTO jobs(id,state,deps,workspace,protected,authorized) VALUES(?,?,?,?,?,?)',(j['id'],'ready',json.dumps(j['deps']),j['workspace'],int(j['protected']),int(j['authorized'])))
                log(j['id'],'initialized',{})
            result={'jobs':len(jobs)}
        elif a.action=='lease':
            if not a.worker or a.ttl<=0 or a.ttl>3600:raise ValueError('invalid worker or ttl')
            candidates=db.execute("SELECT id,deps,workspace,protected,authorized,generation FROM jobs WHERE state='ready' ORDER BY id").fetchall()
            result=None
            for jid,deps,space,protected,authorized,gen in candidates:
                if protected and not authorized:continue
                if any(db.execute('SELECT state FROM jobs WHERE id=?',(d,)).fetchone()[0]!='proven' for d in json.loads(deps)):continue
                db.execute("UPDATE jobs SET state='leased',owner=?,deadline=?,generation=generation+1 WHERE id=?",(a.worker,now+a.ttl,jid))
                log(jid,'leased',{'worker':a.worker,'generation':gen+1})
                result={'job':jid,'workspace':space,'token':gen+1,'deadline':now+a.ttl};break
        elif a.action=='expire':
            rows=db.execute("SELECT id FROM jobs WHERE state='leased' AND deadline<=?",(now,)).fetchall()
            for (jid,) in rows:
                db.execute("UPDATE jobs SET state='blocked',owner=NULL,deadline=NULL,generation=generation+1 WHERE id=?",(jid,))
                log(jid,'expired_blocked',{'reason':'possible external side effect; reconcile before retry'})
            result={'blocked':[r[0] for r in rows]}
        elif a.action in ('submit','verify'):
            row=db.execute('SELECT state,owner,deadline,generation FROM jobs WHERE id=?',(a.job,)).fetchone()
            if not row:raise ValueError('unknown job')
            state,owner,deadline,gen=row
            if a.action=='submit':
                if state!='leased' or owner!=a.worker or gen!=a.token or deadline<=now or not a.result:raise ValueError('invalid or stale lease')
                db.execute("UPDATE jobs SET state='awaiting_proof',owner=NULL,deadline=NULL,implementation=? WHERE id=?",(a.result,a.job))
                log(a.job,'submitted',{'implementation':a.result});result={'state':'awaiting_proof'}
            else:
                if state!='awaiting_proof' or gen!=a.token or a.worker in (None,''):raise ValueError('not awaiting independent proof')
                # Proof is an independently supplied manifest reference; caller must validate it with verify_evidence.
                if a.worker==db.execute("SELECT json_extract(data,'$.worker') FROM events WHERE job=? AND kind='leased' ORDER BY seq DESC LIMIT 1",(a.job,)).fetchone()[0]:raise ValueError('builder cannot verify own result')
                bindings=validate_proof(a.contract,a.manifest,a.proof_plan)
                secret=os.environ.get('DEEP_LOOP_VERIFIER_SECRET','').encode('utf-8')
                if validate_worker(secret,a.capability,a.job,'verifier',generation=gen,bindings=bindings)!=a.worker:
                    raise ValueError('verifier capability identity mismatch')
                a.result='validated-sha256:'+bindings['manifest_sha256']
                db.execute("UPDATE jobs SET state='proven',proof=? WHERE id=?",(a.result,a.job))
                log(a.job,'verified',{'verifier':a.worker,'proof':a.result,'bindings':bindings,'generation':gen});result={'state':'proven'}
        elif a.action=='status':
            result=[dict(zip(('id','state','workspace','generation','owner','implementation','proof'),r)) for r in db.execute('SELECT id,state,workspace,generation,owner,implementation,proof FROM jobs ORDER BY id')]
        elif a.action=='events':result=[dict(zip(('seq','job','kind','data'),r)) for r in db.execute('SELECT seq,job,kind,data FROM events ORDER BY seq')]
        db.execute('COMMIT');print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as e:
        if db is not None and db.in_transaction:db.execute('ROLLBACK')
        print('ERROR:',e,file=sys.stderr);return 1
    finally:
        if db is not None:db.close()
if __name__=='__main__':sys.exit(main())
