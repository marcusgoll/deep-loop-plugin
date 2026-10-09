"""Install reviewed pinned worker units, disabled; never enroll or start work."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from admission import digest
from private_controller import TrustedStore
from private_launch import ROOT
from worker_units import units

CONTROL = Path(ROOT)/'control'
SYSTEM_UNITS = Path('/etc/systemd/system')


def plan(bundle_digest):
    configuration = units(bundle_digest)
    return {'bundle_digest':bundle_digest, 'units':configuration,
            'sha256':{name:hashlib.sha256(data.encode()).hexdigest() for name,data in configuration.items()},
            'enabled':False, 'started':False, 'model_calls':0}


def native(*args):
    return subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,text=True,check=True,timeout=10).stdout.strip()


def apply(bundle_digest, expected_digest):
    expected = plan(bundle_digest)
    if os.geteuid()!=0 or sys.platform!='linux' or digest(expected)!=expected_digest:
        raise ValueError('Explicit root Linux exact reviewed unit plan required')
    store=TrustedStore(CONTROL)
    with store.lock():
        if list(CONTROL.glob('*.approval.json')) or any((CONTROL/name).exists() or (CONTROL/name).is_symlink()
                for name in ('active-owner.json','enabled-outcome.json')):
            raise ValueError('Unit installation requires an unenrolled inactive pilot')
        bundle=CONTROL/('bundle-'+bundle_digest)
        manifest=TrustedStore(bundle).read('manifest.json')
        if digest(manifest)!=bundle_digest:
            raise ValueError('Installed bundle manifest changed')
        for name, expected_hash in manifest['modules'].items():
            path=bundle/name;info=path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o444 or
                    info.st_nlink!=1 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash):
                raise ValueError('Installed bundle changed')
        if not {'private_worker.py','worker_window.py','worker_units.py'} <= set(manifest['modules']):
            raise ValueError('Worker modules absent from bundle')
        for parent in (SYSTEM_UNITS,*SYSTEM_UNITS.parents):
            info=parent.lstat()
            if parent.resolve()!=parent or not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
                raise ValueError('Untrusted system unit directory')
        for name in expected['units']:
            path=SYSTEM_UNITS/name
            if path.exists() or path.is_symlink() or native('show',name,'--property=LoadState','--value')!='not-found':
                raise ValueError('Existing or partial worker installation requires inspection')
        # Validate the exact generated unit sources before publishing either.
        staging=CONTROL/('units-staging-'+expected_digest)
        staging.mkdir(mode=0o700);store._sync()
        for name,data in expected['units'].items():
            with (staging/name).open('x') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
        subprocess.run(['/usr/bin/systemd-analyze','verify',*[str(staging/name) for name in expected['units']]],
                       capture_output=True,text=True,check=True,timeout=15)
        for name,data in expected['units'].items():
            fd,temporary=tempfile.mkstemp(prefix='deep-loop-install-',dir=SYSTEM_UNITS)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(data.encode());stream.flush();os.fchmod(stream.fileno(),0o644);os.fsync(stream.fileno())
                os.link(temporary,SYSTEM_UNITS/name,follow_symlinks=False)
            finally:
                os.unlink(temporary)
        fd=os.open(SYSTEM_UNITS,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        native('daemon-reload')
        for name,expected_hash in expected['sha256'].items():
            path=SYSTEM_UNITS/name;info=path.lstat()
            if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o644 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                raise ValueError('Installed unit readback changed')
            if native('show',name,'--property=LoadState','--value')!='loaded' or native('show',name,'--property=ActiveState','--value')!='inactive':
                raise ValueError('Installed unit unexpectedly active or unavailable')
        result=subprocess.run(['/usr/bin/systemctl','is-enabled','deep-loop-private-worker.timer'],capture_output=True,text=True,timeout=5)
        if result.returncode!=1 or result.stdout.strip()!='disabled':
            raise ValueError('Worker timer must remain disabled')
        store.create(expected_digest+'.units.json',expected)
        return store.read(expected_digest+'.units.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('bundle_digest')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-digest')
    args=parser.parse_args()
    if args.apply:
        if not args.expected_digest:parser.error('--apply requires reviewed --expected-digest')
        result=apply(args.bundle_digest,args.expected_digest)
    else:
        result=plan(args.bundle_digest)
    print(json.dumps({'plan_digest':digest(result),'plan':result},indent=2))
