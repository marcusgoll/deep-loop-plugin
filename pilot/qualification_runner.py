"""Explicit trusted no-model qualification; no enrollment or model submission.

An uncertain probe is inspect-only: immutable intent prevents blind resubmission.
Call only from independently reviewed root tooling with an exact frozen plan.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from admission import digest
from private_launch import ACCOUNT,ROOT,DISABLED_FEATURES
from qualification_plan import qualification_plan
from qualification_environment import inspect_environment,require_absent
from qualification_probe import PROBE,wrapper_source,validate_output
from systemd_observer import observe_unit
from strict_configuration import validate_strict

STDIN='Literal $(no shell interpolation) qualification\n'


def raw(store,name,data):
    fd=os.open(store._path(name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    store._sync()
    return store._path(name)


def produce(store,plan,contract):
    """Run literal Python inside native sandbox; publish only verified results."""
    key=digest(contract)
    with store.lock():
        if any((store.root/name).exists() or (store.root/name).is_symlink() for name in ('active-owner.json','enabled-outcome.json')):
            raise ValueError('Qualification requires inactive unenrolled pilot')
        environment=inspect_environment(plan,contract)
        candidate=Path(plan['candidate']);home=Path(ROOT)/'home'
        probe=candidate/'.deep-loop-qualification.py'
        wrapper=candidate/'.deep-loop-qualification-wrapper.py'
        escape=candidate/'.deep-loop-qualification-escape'
        proof=candidate/'.deep-loop-qualification-proof'
        sentinel=home/(key+'.qualification-sentinel')
        require_absent([probe,wrapper,escape,proof,sentinel])
        commands=qualification_plan(plan,contract,str(probe))
        # Inspection runs from the exact candidate; inherited caller cwd is forbidden.
        command=['sudo','-n','-H','-u',ACCOUNT,'/usr/bin/env',
                 '--chdir='+str(candidate),'-u','OPENAI_API_KEY','-u','CODEX_API_KEY',
                 '-u','CODEX_HOME','-u','OPENAI_BASE_URL','-u','NODE_OPTIONS',
                 *commands['features_command']]
        features=subprocess.run(command,capture_output=True,text=True,check=True,timeout=5)
        if features.stderr:raise ValueError('Unexpected strict configuration diagnostic')
        values={line.split()[0]:line.split()[-1] for line in features.stdout.splitlines() if line.split()}
        if any(values.get(name)!='false' for name in DISABLED_FEATURES):
            raise ValueError('Native capability restriction mismatch')
        unit_prefix='deep-loop-pilot-'+key+'-'+str(time.time_ns())
        unit=unit_prefix+'-3'
        sources={probe:PROBE.encode(),wrapper:wrapper_source(commands['sandbox_command'],str(sentinel),str(escape),str(proof)).encode()}
        intent={'contract_digest':key,'unit':unit,'environment':environment,
                'permission_digest':commands['permission_digest'],
                'probe_sha256':{p.name:hashlib.sha256(data).hexdigest() for p,data in sources.items()},
                'strict_unit_prefix':unit_prefix,'strict_command_digest':digest(commands['strict_command']),
                'model_calls':0}
        store.create(key+'.qualification-intent.json',intent)
        strict_evidence=validate_strict(store,plan,commands,unit_prefix,raw)
        # Do not automatically remove files or stop a unit after uncertain launch.
        # A trusted operator must inspect native ownership before any cleanup.
        for path,data in sources.items():
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
            with os.fdopen(fd,'wb') as stream:
                stream.write(data);os.fchmod(stream.fileno(),0o444);stream.flush();os.fsync(stream.fileno())
        fd=os.open(sentinel,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(b'disposable qualification sentinel');os.fchown(stream.fileno(),environment['uid'],environment['gid']);stream.flush();os.fsync(stream.fileno())
        escape.symlink_to(sentinel)
        prompt=raw(store,unit+'.prompt',STDIN.encode())
        capture=raw(store,unit+'.jsonl',b'')
        errors=raw(store,unit+'.stderr',b'')
        properties=dict(plan['properties'],RuntimeMaxSec=20,TimeoutStartSec=5,TimeoutStopSec=5,
                        Slice='system.slice',Description='Deep Loop no-model qualification '+digest(intent),
                        StandardInput='file:'+str(prompt),StandardOutput='append:'+str(capture),
                        StandardError='append:'+str(errors),LimitFSIZE=16777216,LimitCORE=0)
        args=['/usr/bin/systemd-run','--unit='+unit,'--service-type=exec']
        args+=['--property='+name+'='+str(value) for name,value in properties.items()]
        subprocess.run(args+['/usr/bin/python3','-I',str(wrapper)],capture_output=True,text=True,check=True,timeout=5)
        invocation=subprocess.run(['/usr/bin/systemctl','show',unit+'.service','--property=InvocationID','--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        deadline=time.monotonic()+30
        while True:
            observation=observe_unit(unit,invocation)
            if observation['execution_finished']:break
            if time.monotonic()>=deadline:raise ValueError('Probe observation expired; inspect same unit')
            time.sleep(.1)
        status=subprocess.run(['/usr/bin/systemctl','show',unit+'.service','--property=ExecMainStatus','--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        if status!='0':raise ValueError('No-model probe failed')
        fd=store._open(unit+'.jsonl',os.O_RDONLY)
        with os.fdopen(fd,'rb') as stream:data=stream.read(65537)
        observations=validate_output(data.decode(),environment['uid'],str(candidate),str(home),STDIN)
        fd=store._open(unit+'.stderr',os.O_RDONLY)
        with os.fdopen(fd,'rb') as stream:
            if stream.read(1):raise ValueError('Unexpected qualification stderr')
        for path,source in sources.items():
            if path.is_symlink() or path.read_bytes()!=source:raise ValueError('Probe source changed')
        if sentinel.read_text()!='disposable qualification sentinel' or proof.read_text()!='qualified candidate write':
            raise ValueError('Disposable probe evidence changed')
        store.create(key+'.qualification-observation.json',{'intent':intent,'native':observation,'observations':observations,'strict_configuration':strict_evidence})
        subprocess.run(['/usr/bin/systemctl','stop',unit+'.service'],capture_output=True,text=True,check=True,timeout=5)
        for path in (*sources,escape,proof,sentinel):path.unlink()
        if inspect_environment(plan,contract)!=environment:raise ValueError('Environment changed during qualification')
        checks={name:observations[name] for name in ('candidate_write','private_direct_read_denied',
                'private_symlink_read_denied','network_denied','host_parent_descriptor_read_denied','host_parent_memory_read_denied')}
        # Descriptor and capture access are separate observations; both required.
        checks['host_parent_descriptor_read_denied'] &= observations['host_parent_capture_read_denied']
        checks.update(native_config_validated=True,systemd_io_validated=True,external_capabilities_disabled=True)
        receipt={'contract_digest':key,'executor':contract['executor'],
                 'permission_digest':commands['permission_digest'],'candidate':str(candidate),'checks':checks}
        store.create(key+'.qualification.json',receipt)
        return store.read(key+'.qualification.json')
