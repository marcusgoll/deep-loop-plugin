"""Opt-in deterministic receipts and scoped, integrity-checked logical file resolution."""
from contextlib import contextmanager
from contextvars import ContextVar
import datetime, hashlib, json, platform, stat, sys
from pathlib import Path

_CONTEXT=ContextVar('deep_loop_proof_files',default=None)

def mapped_context():
    context = _CONTEXT.get()
    return context is not None and context.get('files') is not None

def logical(path):
    path=Path(path).resolve(); context=_CONTEXT.get()
    if context and context.get('files'):
        for name,record in context['files'].items():
            physical=(context['archive']/record['path']).resolve()
            if path==physical:return Path(name)
    return path

def resolve_file(path):
    name=str(logical(path));context=_CONTEXT.get()
    if context and context.get('files') is not None:
        record=context['files'].get(name)
        if record is None:raise ValueError('Unmapped preserved dependency: '+name)
        relative=Path(record['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Resolution escapes archive')
        raw=context['archive']/relative
        for component in (raw, *raw.parents):
            info=component.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Linked preserved dependency')
            if component == context['archive']:break
        path=raw.resolve()
        if not path.is_relative_to(context['archive'].resolve()):raise ValueError('Resolution escapes archive')
        if not path.is_file():raise ValueError('Preserved dependency is not a regular file')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Preserved dependency changed: '+name)
    else:path=Path(name)
    if context is not None and context.get('trace') is not None:context['trace'].add(name)
    return path

def read(path):return json.loads(resolve_file(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(resolve_file(path).read_bytes()).hexdigest()
def bound(record,base):
    path=logical(base)/record['path']
    if sha(path)!=record['sha256']:raise ValueError('Bound file changed: '+str(path))
    return resolve_file(path)

@contextmanager
def files_context(archive=None,mapping=None,trace=None):
    token=_CONTEXT.set({'archive':Path(archive) if archive else None,'files':mapping,'trace':trace})
    try:yield
    finally:_CONTEXT.reset(token)

def source_identity(path):
    files=read(path)['files']
    if not isinstance(files,dict) or not files:raise ValueError('Source manifest requires nonempty files')
    for name,digest in files.items():bound({'path':name,'sha256':digest},logical(path).parent)
    return sha(path)

def definition(verifier,base):
    proof=verifier.get('proof')
    if proof is None:return None
    if not isinstance(proof,dict):raise ValueError('Verifier proof must be an object')
    if proof.get('mode')=='manual':
        if 'readback' in proof:raise ValueError('Structured readback requires bound proof')
        if not isinstance(proof.get('reason'),str) or not proof['reason'].strip():raise ValueError('Manual proof requires explicit reason')
        return proof
    if proof.get('mode')!='bound':raise ValueError('Proof mode must be bound or manual')
    if 'working_directory' in proof and (not isinstance(proof['working_directory'],str) or not Path(proof['working_directory']).is_absolute()):
        raise ValueError('Bound working_directory must be absolute')
    argv=proof.get('argv')
    if not isinstance(argv,list) or not argv or any(not isinstance(a,str) or not a for a in argv):raise ValueError('Bound proof requires approved argv')
    for key in ('implementation','source_manifest','environment_manifest'):bound(proof[key],base)
    source_identity(bound(proof['source_manifest'],base))
    artifacts=proof.get('artifacts')
    if not isinstance(artifacts,list) or not artifacts or any(not isinstance(a,dict) or not isinstance(a.get('path'),str) or not a['path'] for a in artifacts):raise ValueError('Bound proof requires artifact paths')
    if len({str((logical(base)/a['path']).resolve()) for a in artifacts})!=len(artifacts):raise ValueError('Duplicate proof artifacts')
    readback_definition(verifier, base)
    return proof

def identity(proof,base):
    return {'implementation':sha(bound(proof['implementation'],base)),
            'source':source_identity(bound(proof['source_manifest'],base)),
            'environment':sha(bound(proof['environment_manifest'],base))}

def runtime_identity():
    return {'executable':str(Path(sys.executable).resolve()),'python':sys.version,'platform':platform.platform()}

def artifacts(proof,base):return [{'path':str((logical(base)/a['path']).resolve()),'sha256':sha(logical(base)/a['path'])} for a in proof['artifacts']]


def readback_definition(verifier, base):
    proof=verifier.get('proof',{}); spec=proof.get('readback')
    if spec is None:return None
    if proof.get('mode')!='bound' or verifier.get('gate')!='blocking':raise ValueError('Readback requires blocking bound verifier')
    if not isinstance(spec,dict) or set(spec)!={'endpoint','result','targets'} or not isinstance(spec['endpoint'],str) or not spec['endpoint'].strip():raise ValueError('Invalid readback declaration')
    if not isinstance(spec['result'],str) or not spec['result']:raise ValueError('Readback requires saved result path')
    targets=spec['targets']
    if not isinstance(targets,list) or not targets:raise ValueError('Readback requires target declarations')
    for target in targets:
        if not isinstance(target,dict) or not {'id','artifact'}<=set(target) or set(target)-{'id','artifact','revision_kind'} or any(not isinstance(target[k],str) or not target[k].strip() for k in ('id','artifact')):raise ValueError('Invalid readback target')
    if any(t.get('revision_kind','sha256') not in ('sha256','external') for t in targets):raise ValueError('Readback revision_kind must be sha256 or external')
    if len({t['id'] for t in targets})!=len(targets):raise ValueError('Duplicate readback target IDs')
    paths=[logical(base)/spec['result']]+[logical(base)/t['artifact'] for t in targets]
    names=[str(p.resolve()) for p in paths]
    if len(set(names))!=len(names):raise ValueError('Readback result and target artifacts must be distinct')
    declared={str((logical(base)/a['path']).resolve()) for a in proof['artifacts']}
    if not set(names)<=declared:raise ValueError('Readback files must be declared proof artifacts')
    return spec

def readback_observation(proof,base):
    spec=proof['readback']; result=read(logical(base)/spec['result'])
    if not isinstance(result,dict) or set(result)!={'endpoint','targets'} or result['endpoint']!=spec['endpoint']:raise ValueError('Observed endpoint differs from readback declaration')
    rows=result['targets']; declarations={t['id']:t for t in spec['targets']}
    if not isinstance(rows,list) or len(rows)!=len(declarations):raise ValueError('Observed target set differs')
    seen=set();observed=[]; physical_result=resolve_file(logical(base)/spec['result'])
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'id','revision','artifact'} or not isinstance(row['id'],str) or row['id'] not in declarations or row['id'] in seen:raise ValueError('Invalid or duplicate observed target')
        seen.add(row['id']); target=declarations[row['id']]; name=str((logical(base)/target['artifact']).resolve())
        if row['artifact']!=name or not isinstance(row['revision'],str) or not row['revision'].strip():raise ValueError('Observed artifact/revision differs')
        physical=resolve_file(Path(name)); digest=sha(Path(name))
        if physical==physical_result:raise ValueError('Observed result cannot be delivered artifact')
        if (target.get('revision_kind','sha256')=='sha256' or row['revision'].startswith('sha256:')) and row['revision']!='sha256:'+digest:raise ValueError('Observed local revision differs from artifact bytes')
        observed.append(dict(row,sha256=digest))
    return {'endpoint':result['endpoint'],'targets':sorted(observed,key=lambda r:r['id'])}

def readback_delivery(observation,state):
    delivery=state.get('delivery',{})
    if observation['endpoint']!=delivery.get('endpoint'):raise ValueError('Readback endpoint differs from delivered endpoint')
    subjects=delivery.get('targets',[{'id':'single','revision':delivery.get('revision')}])
    if not isinstance(subjects,list) or any(not isinstance(t,dict) for t in subjects):raise ValueError('Invalid delivered subjects')
    expected={t.get('id'):t.get('revision') for t in subjects}
    if len(expected)!=len(subjects) or expected!={t['id']:t['revision'] for t in observation['targets']}:raise ValueError('Readback exact delivered target/revision mismatch')

def issues(contract,path,state,stage,semantics,verifier_ids=None):
    failures=[];base=logical(path).parent
    checks={c.get('verifierId'):c for c in state.get('checks',[]) if isinstance(c,dict)}
    for verifier in contract['verifiers']:
        try:
            proof=definition(verifier,base)
            if verifier_ids is not None and verifier['id'] not in verifier_ids:continue
            if not proof or proof['mode']=='manual' or stage=='build':continue
            check=checks.get(verifier['id'])
            if verifier.get('gate') == 'advisory' and check is None:
                continue
            if check is None:raise ValueError('Bound verifier lacks checkpoint check')
            if 'readback' in proof and stage not in ('ship','delivery'):continue
            due='readback' in proof or check.get('stage','review')=='review' or stage=='ship' or stage=='delivery' and check.get('stage')=='ship'
            if not due:continue
            receipt_path=bound(check['receipt'],base);rows=read(receipt_path)
            if not isinstance(rows,list):raise ValueError('Bound receipt requires result rows')
            matches=[r for r in rows if isinstance(r,dict) and r.get('verifier_id')==verifier['id']]
            if len(matches)!=1:raise ValueError('Missing or duplicate bound invocation')
            row=matches[0]
            started=datetime.datetime.fromisoformat(row['startedAt'])
            finished=datetime.datetime.fromisoformat(row['finishedAt'])
            if started.tzinfo is None or finished.tzinfo is None or finished < started or type(row.get('exitCode')) is not int:
                raise ValueError('Invalid bound execution interval/exit code')
            expected_cwd=str(Path(proof.get('working_directory',base)).resolve())
            if (row.get('proof_mode')!='bound' or row.get('goal_id')!=state['sessionId'] or row.get('contract_semantics')!=semantics
                or row.get('argv')!=proof['argv'] or row.get('cwd')!=expected_cwd or row.get('identity')!=identity(proof,base)
                or row.get('artifacts')!=artifacts(proof,base) or row.get('exitCode')!=0 or row.get('status')!='passed'
                or check.get('status')!='passed' or not row.get('startedAt') or not row.get('finishedAt')
                or not isinstance(row.get('runtime'),dict) or any(not isinstance(row['runtime'].get(k),str) or not row['runtime'][k] for k in ('executable','python','platform'))):raise ValueError('Bound invocation/result identity mismatch')
            if 'readback' in proof:
                observation=readback_observation(proof,base)
                if row.get('readback')!=observation:raise ValueError('Bound observed readback changed')
                readback_delivery(observation,state)
        except (OSError,ValueError,KeyError,TypeError) as error:failures.append(verifier['id']+': bound proof BLOCKED: '+str(error))
    return failures
