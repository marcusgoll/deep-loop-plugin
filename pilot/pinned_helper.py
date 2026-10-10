"""Hash-pinned isolated checkpoint reader; no model or checkpoint publication.

Production package and interpreter are root protected. The nonroot owner option
exists only for disposable tests. Helper dependencies unavailable under -S fail
closed rather than importing an installed or candidate package. The protected
operating-system standard library remains part of the trusted runtime. This
adapter does not install a snapshot or grant workflow execution authority.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from admission import initialize

METHODS = {'task_records','task_queue','contract_definition_issues','contract_data',
           'prerequisite_issues','accepted_task_state'}
DRIVER = '''import json,os,resource,sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
resource.setrlimit(resource.RLIMIT_CPU,(5,5))
resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912))
sys.dont_write_bytecode=True
root=Path(sys.argv[1])
os.environ['DEEP_LOOP_SKILLS_ROOT']=str(root/'skills')
sys.path[:0]=[str(root/'skills/deep-loop/scripts')]
import deep_loop
request=json.loads(sys.stdin.buffer.read(524289))
method=request['method']
assert method in {'task_records','task_queue','contract_definition_issues','contract_data','prerequisite_issues','accepted_task_state'}
args=request['args']
if method=='contract_data':args[0]=Path(args[0])
result=getattr(deep_loop,method)(*args,**request['kwargs'])
sys.stdout.write(json.dumps(result,allow_nan=False))
'''


class PinnedHelper:
    def __init__(self, configuration, *, owner_uid=0):
        if sys.platform != 'linux':raise ValueError('Pinned helper requires qualified Linux runtime')
        self.configuration, self.owner_uid = configuration, owner_uid
        self._verify()

    def _protected(self, path, *, directory=False):
        if not path.is_absolute() or path.resolve()!=path:
            raise ValueError('Canonical pinned helper path required')
        for item in (path,*path.parents):
            info=item.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid not in {0,self.owner_uid}:
                raise ValueError('Untrusted pinned helper ownership')
            if info.st_mode & 0o022 and not (self.owner_uid!=0 and item==Path('/tmp')):
                raise ValueError('Writable pinned helper path')
        info=path.lstat()
        if directory:
            if not stat.S_ISDIR(info.st_mode):raise ValueError('Pinned helper directory required')
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise ValueError('Regular single-link pinned helper source required')

    def _hash(self,path,limit):
        self._protected(path)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if info.st_size>limit:raise ValueError('Pinned helper file exceeds bound')
            digest=hashlib.sha256();total=0
            while True:
                chunk=os.read(fd,65536)
                if not chunk:break
                total+=len(chunk)
                if total>limit:raise ValueError('Pinned helper file exceeds bound')
                digest.update(chunk)
            return digest.hexdigest()
        finally:os.close(fd)

    def _inventory(self,root):
        inventory=set();count=0
        stack=[(root/folder,0) for folder in ('skills/deep-loop/scripts','skills/verification-contract/scripts')]
        while stack:
            folder,depth=stack.pop();self._protected(folder,directory=True)
            if depth>4:raise ValueError('Pinned helper inventory depth exceeds bound')
            with os.scandir(folder) as entries:
                for entry in entries:
                    count+=1
                    if count>2048:raise ValueError('Pinned helper inventory exceeds bound')
                    path=Path(entry.path)
                    if entry.is_symlink():raise ValueError('Unpinned helper symlink')
                    if entry.is_dir(follow_symlinks=False):stack.append((path,depth+1))
                    elif entry.is_file(follow_symlinks=False):
                        if path.suffix in {'.pyc','.so','.pyd','.pth'}:raise ValueError('Unpinned helper import artifact')
                        if path.suffix=='.py':inventory.add(str(path.relative_to(root)))
                    else:raise ValueError('Unsupported pinned helper entry')
        return inventory

    def _verify(self):
        config=self.configuration
        if not isinstance(config,dict) or set(config)!={'root','files','python'}:
            raise ValueError('Exact pinned helper configuration required')
        root=Path(config['root']);files=config['files'];python=config['python']
        if (not isinstance(files,dict) or not files or len(files)>128 or
                not isinstance(python,dict) or set(python)!={'path','sha256'}):
            raise ValueError('Bounded pinned helper inventory required')
        required={'skills/deep-loop/scripts/deep_loop.py','skills/deep-loop/scripts/proof_binding.py',
                  'skills/verification-contract/scripts/validate_contract.py'}
        if not required<=set(files):raise ValueError('Pinned helper dependencies missing')
        for name,expected in files.items():
            relative=Path(name)
            if (relative.is_absolute() or '..' in relative.parts or not name.endswith('.py') or
                    not name.startswith(('skills/deep-loop/scripts/','skills/verification-contract/scripts/'))):
                raise ValueError('Unsafe pinned helper inventory path')
            initialize(expected);path=root/relative;self._protected(path)
            if self._hash(path,1048576)!=expected:
                raise ValueError('Pinned helper source drift')
        inventory=self._inventory(root)
        if inventory!=set(files):raise ValueError('Unpinned helper Python dependency')
        initialize(python['sha256']);executable=Path(python['path']);self._protected(executable)
        if self._hash(executable,67108864)!=python['sha256']:
            raise ValueError('Pinned helper interpreter drift')
        return root,executable

    def _call(self, method, *args, **kwargs):
        if method not in METHODS:raise ValueError('Unsupported pinned helper operation')
        root,python=self._verify()
        encoded=json.dumps({'method':method,'args':args,'kwargs':kwargs},allow_nan=False).encode()
        if len(encoded)>524288:raise ValueError('Pinned helper request exceeds bound')
        environment={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result=subprocess.run([str(python),'-I','-S','-B','-c',DRIVER,str(root)],input=encoded,
                                  stdout=output,stderr=errors,env=environment,timeout=8,check=False)
            if result.returncode!=0:raise ValueError('Pinned helper operation unavailable or failed')
            output.seek(0);payload=output.read(1048577)
        if len(payload)>1048576:raise ValueError('Pinned helper result exceeds bound')
        return json.loads(payload)

    def task_records(self,state):return self._call('task_records',state)
    def task_queue(self,state):return self._call('task_queue',state)
    def contract_definition_issues(self,state):return self._call('contract_definition_issues',state)
    def contract_data(self,path,verify_files=True):return self._call('contract_data',str(path),verify_files=verify_files)
    def prerequisite_issues(self,state,ids):return self._call('prerequisite_issues',state,ids)
    def accepted_task_state(self,state,task_id,ids,evidence,expected):
        return self._call('accepted_task_state',state,task_id,ids,evidence,expected)
