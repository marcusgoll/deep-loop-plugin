"""Explicit-file active handoff packets; retained bytes confer no execution authority."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import argparse
from urllib.parse import urlsplit
import proof_binding


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_path(value, missing=False):
    """Inspect raw components before normalization; never follow links or junctions."""
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Handoff paths must be absolute and contain no parent traversal')
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Linked/reparse handoff paths are forbidden: ' + str(part))
        if part != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Handoff parent is not a directory')
    return path


def references(data):
    if not isinstance(data, list):
        raise ValueError('References must be an explicit list')
    ids, paths = set(), set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError('Reference must be an object')
        locator = 'path' if 'path' in row else 'url'
        if set(row) != {'id', 'kind', locator, 'required', 'provenance'}:
            raise ValueError('Reference needs id, kind, exactly one path or url, required and provenance')
        if any(not isinstance(row[k], str) or not row[k].strip() for k in ('id', locator, 'provenance')):
            raise ValueError('Reference identity, locator and provenance must be nonempty')
        if row['id'] in ids or row['kind'] not in ('decision', 'contract', 'evidence', 'ownership') or type(row['required']) is not bool:
            raise ValueError('Reference IDs must be unique; kind and required must be valid')
        ids.add(row['id'])
        if locator == 'path':
            path = Path(row['path'])
            if not path.is_absolute() or '..' in path.parts or str(path) != row['path']:
                raise ValueError('Reference path must be a normalized absolute logical identity')
            if row['path'] in paths:
                raise ValueError('Reference paths must be unique')
            paths.add(row['path'])
        else:
            parsed = urlsplit(row['url'])
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('External reference must be an HTTP(S) URL without credentials')
    return data


def read_local(path):
    checked_path(str(path))
    if not path.is_file():
        raise ValueError('Handoff copies regular files only: ' + str(path))
    return path.read_bytes()


def retained_report(packet, saved, dl):
    stream = io.StringIO()
    with proof_binding.files_context(packet, saved['resolution']), redirect_stdout(stream):
        code = dl.recovery_report(argparse.Namespace(root=str(packet), path=str(packet/'snapshot'),
                                  session=None, json=True))
    return code, json.loads(stream.getvalue())


def verify(packet):
    packet = checked_path(str(Path(packet).absolute()))
    manifest_bytes = read_local(packet/'handoff.json')
    saved = json.loads(manifest_bytes)
    if not isinstance(saved, dict) or set(saved) != {'schemaVersion','type','sourceRoot','sourcePath','sessionId',
            'references','files','resolution','referencesSha256'} or saved['schemaVersion'] != 1 or saved['type'] != 'active_handoff':
        raise ValueError('Invalid active handoff manifest')
    root, source = Path(saved['sourceRoot']), Path(saved['sourcePath'])
    sid = saved['sessionId']
    if not root.is_absolute() or not source.is_absolute() or not isinstance(sid,str) or len(sid)!=8 or not sid.isalnum() or source != root/f'.deep-{sid}':
        raise ValueError('Invalid original checkpoint identity')
    files, mapping = saved['files'], saved['resolution']
    if not isinstance(files,dict) or not isinstance(mapping,dict) or 'snapshot/state.json' not in files or 'references.json' not in files:
        raise ValueError('Missing handoff file manifest')
    expected_files = set(files) | {'handoff.json'}
    expected_dirs = {'.'} | {str(parent) for name in expected_files for parent in Path(name).parents}
    actual_files, actual_dirs = set(), {'.'}
    for directory, dirs, names in os.walk(packet, followlinks=False):
        for name in dirs + names:
            item = checked_path(str(Path(directory)/name))
            relative = item.relative_to(packet).as_posix()
            if item.is_dir():actual_dirs.add(relative)
            elif item.is_file():actual_files.add(relative)
            else:raise ValueError('Unsupported retained packet path')
    if actual_files != expected_files or actual_dirs != expected_dirs:
        raise ValueError('Handoff contains unindexed or missing retained files/directories')
    before = {}
    for relative, sha in files.items():
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts or relative != rel.as_posix() or not isinstance(sha,str) or len(sha)!=64:
            raise ValueError('Invalid retained file path or digest')
        before[relative] = read_local(packet/rel)
        if digest(before[relative]) != sha:
            raise ValueError('Retained handoff bytes changed: ' + relative)
    rows = references(json.loads(before['references.json']))
    if not isinstance(saved['references'],list) or digest(before['references.json']) != saved['referencesSha256'] or len(rows) != len(saved['references']):
        raise ValueError('Reference identity differs from its supplied bytes')
    expected = {str(source/'state.json'): {'path':'snapshot/state.json','sha256':files['snapshot/state.json']}}
    if 'snapshot/plan.md' in files:
        expected[str(source/'plan.md')] = {'path':'snapshot/plan.md','sha256':files['snapshot/plan.md']}
    allowed_files = {'snapshot/state.json','references.json'}
    if 'snapshot/plan.md' in files:allowed_files.add('snapshot/plan.md')
    for original, record in zip(rows, saved['references']):
        if not isinstance(record,dict):
            raise ValueError('Retained reference must be an object')
        extra = set(record)-set(original)
        if any(record.get(k)!=v for k,v in original.items()):
            raise ValueError('Retained reference provenance or identity differs')
        if 'url' in original:
            if extra != {'status'} or record['status'] != 'external_not_inspected':
                raise ValueError('External reference cannot claim inspected truth')
        elif record.get('status') == 'retained':
            if extra != {'status','retained','sha256'} or record['retained'] not in files or files[record['retained']] != record['sha256']:
                raise ValueError('Retained reference manifest mismatch')
            expected[original['path']]={'path':record['retained'],'sha256':record['sha256']}
            allowed_files.add(record['retained'])
        elif record.get('status') == 'unavailable':
            if extra != {'status','reason'} or not isinstance(record['reason'],str) or not record['reason']:
                raise ValueError('Unavailable reference requires its diagnostic')
        else:
            raise ValueError('Invalid reference availability')
    if set(files)!=allowed_files or mapping != expected:
        raise ValueError('Resolution map differs from exact selected snapshot and reference allowlist')
    state = json.loads(before['snapshot/state.json'])
    if isinstance(state,dict) and 'proofResolution' in state:
        raise ValueError('Active handoff cannot replace an existing archive resolution binding; retain original recovery state')
    if not isinstance(state,dict) or state.get('schemaVersion') not in (2,3,4) or state.get('phase') not in ('PLAN','BUILD','REVIEW','SHIP') or state.get('sessionId') != sid or state.get('active') is not True or state.get('complete') is not False:
        raise ValueError('Active handoff snapshot identity differs')
    return saved, before, manifest_bytes


def create(args, dl):
    root = checked_path(str(Path(args.root).absolute()))
    source = checked_path(str(Path(args.path).absolute()))
    raw_state = read_local(source/'state.json')
    state = json.loads(raw_state)
    if isinstance(state,dict) and 'proofResolution' in state:
        raise ValueError('Active handoff cannot replace an existing archive resolution binding; retain original recovery state')
    sid = state.get('sessionId')
    if not isinstance(sid,str) or len(sid)!=8 or not sid.isalnum() or source != root/f'.deep-{sid}':
        raise ValueError('Handoff requires the exact selected direct checkpoint')
    if state.get('schemaVersion') not in (2,3,4) or state.get('active') is not True or state.get('complete') is not False or state.get('phase') not in ('PLAN','BUILD','REVIEW','SHIP'):
        raise ValueError('Handoff requires an active incomplete supported checkpoint')
    reference_path = checked_path(str(Path(args.references).absolute()))
    reference_bytes = read_local(reference_path)
    rows = references(json.loads(reference_bytes))
    output = checked_path(str(Path(args.output).absolute()), missing=True)
    if not output.parent.is_dir() or output.exists() or output.is_relative_to(source):
        raise ValueError('Handoff needs a fresh output outside its checkpoint with an existing parent')
    inputs = {str(source/'state.json'):raw_state}
    plan_unavailable = False
    try:
        inputs[str(source/'plan.md')]=read_local(source/'plan.md')
    except (FileNotFoundError,PermissionError):
        plan_unavailable = True  # Existing recovery inspection reports missing plan explicitly.
    retained = []
    for row in rows:
        item=dict(row)
        if 'url' in row:
            item['status']='external_not_inspected'
        else:
            path=Path(row['path'])
            try:
                payload=read_local(path)
            except (FileNotFoundError,PermissionError) as error:
                item.update(status='unavailable',reason=type(error).__name__+': '+str(error))
            else:
                if str(path) in inputs and inputs[str(path)] != payload:
                    raise ValueError('Selected checkpoint changed between reference reads')
                inputs[str(path)]=payload
                item.update(status='retained',sha256=digest(payload))
        retained.append(item)
    lock=output.with_name(output.name+'.handoff.lock')
    checked_path(str(lock),missing=True)
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    staging=None
    try:
        if output.exists():raise FileExistsError('Handoff output already exists')
        staging=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
        (staging/'snapshot').mkdir()
        files={'references.json':digest(reference_bytes)}
        (staging/'references.json').write_bytes(reference_bytes)
        mapping={}
        for index,(logical,payload) in enumerate(inputs.items()):
            relative=('snapshot/'+Path(logical).name if logical in (str(source/'state.json'),str(source/'plan.md')) else f'references/{index}.bin')
            target=staging/relative;target.parent.mkdir(exist_ok=True)
            target.write_bytes(payload);files[relative]=digest(payload)
            mapping[logical]={'path':relative,'sha256':files[relative]}
        for row in retained:
            if row['status']=='retained':row['retained']=mapping[row['path']]['path']
        saved={'schemaVersion':1,'type':'active_handoff','sourceRoot':str(root),'sourcePath':str(source),
               'sessionId':sid,'references':retained,'files':files,'resolution':mapping,
               'referencesSha256':digest(reference_bytes)}
        dl.write_json(staging/'handoff.json',saved)
        verify(staging)
        # Exact selected preimages, plus unavailable references, must remain stable.
        for logical,payload in inputs.items():
            if read_local(Path(logical))!=payload:raise ValueError('Handoff input changed before publication')
        if plan_unavailable:
            try:read_local(source/'plan.md')
            except (FileNotFoundError,PermissionError):pass
            else:raise ValueError('Unavailable checkpoint plan appeared during publication')
        if read_local(reference_path)!=reference_bytes:raise ValueError('Reference declaration changed before publication')
        for row in retained:
            if row['status']=='unavailable':
                try:read_local(Path(row['path']))
                except (FileNotFoundError,PermissionError):pass
                else:raise ValueError('Unavailable reference appeared during publication')
        if output.exists():raise FileExistsError('Handoff output appeared during publication')
        # Cooperative writers serialize; unrelated writers must also respect this lock.
        verify(staging)
        os.rename(staging,output)
        print('Active handoff packet saved and integrity-verified: '+str(output)+'; no execution authority transferred.')
        return 0
    finally:
        os.close(descriptor);lock.unlink()
        # A failed staging directory is retained for diagnosis; never delete source/output.


def inspect(args, dl):
    packet=checked_path(str(Path(args.packet).absolute()))
    saved,before,manifest=verify(packet)
    code,recovery=retained_report(packet,saved,dl)
    missing=[r['id'] for r in saved['references'] if r['required'] and r['status']!='retained']
    report={'schemaVersion':1,'packetType':'active_handoff','packetIntegrity':'verified',
            'sourcePath':saved['sourcePath'],'sessionId':saved['sessionId'],
            'references':saved['references'],'requiredReferences':'unavailable' if missing else 'available',
            'unavailableRequiredReferences':missing,'recovery':recovery,
            'authorityAuthenticity':'not_authenticated','ownership':'unknown','ownerLiveness':'not_inspected',
            'executionAuthority':'not_transferred','liveEndpoint':'not_inspected',
            'nextSafeAction':'Inspect retained scope, missing references, current authority and ownership before any authorized continuation.'}
    current,after,current_manifest=verify(packet)
    if before!=after or manifest!=current_manifest:raise ValueError('Packet changed during read-only inspection')
    print(json.dumps(report,indent=2))
    return int(bool(code or missing))
