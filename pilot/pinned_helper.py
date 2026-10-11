"""Hash-pinned isolated checkpoint reader; no model or checkpoint publication.

Production package and interpreter are root protected. The nonroot owner option
exists only for disposable tests. Helper dependencies unavailable under -S fail
closed rather than importing an installed or candidate package. The protected
operating-system standard library remains part of the trusted runtime. This
adapter does not install a snapshot or grant workflow execution authority.
"""
import hashlib
import json
import errno
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import select
import signal
from contextlib import contextmanager

from admission import digest, initialize

_PAIR_CONTAINMENT=None
_PAIR_CAPABILITY=None


def qualify_review_pair_containment(service,invocation,cgroup):
    """Called only after trusted worker unit and actual cgroup qualification."""
    global _PAIR_CONTAINMENT
    _PAIR_CONTAINMENT=(os.getpid(),service,invocation,cgroup)


def _review_pair_available():
    """Select kernel support before starting any review protocol."""
    global _PAIR_CAPABILITY
    if sys.platform!='linux' or not hasattr(os,'fork') or not hasattr(select,'poll'):
        return False
    if _PAIR_CAPABILITY is not None and _PAIR_CAPABILITY[0]==os.getpid():
        return _PAIR_CAPABILITY[1]
    # Probe in an otherwise empty disposable child, never modify the controller's
    # subreaper/death-signal state. A denied optional capability selects legacy.
    import ctypes
    libc=ctypes.CDLL(None,use_errno=True)
    if not hasattr(libc,'prctl'):return False
    parent=os.getpid();pid=os.fork()
    if pid==0:
        try:
            for option,value in ((36,1),(1,signal.SIGKILL)):
                if libc.prctl(option,value,0,0,0)!=0:
                    code=ctypes.get_errno()
                    os._exit(78 if code in {errno.ENOSYS,errno.EINVAL,errno.EPERM,errno.EACCES} else 79)
            os._exit(0 if os.getppid()==parent else 79)
        except BaseException:os._exit(79)
    deadline=time.monotonic()+1
    while True:
        waited,status=os.waitpid(pid,os.WNOHANG)
        if waited:break
        if time.monotonic()>=deadline:
            os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            raise RuntimeError('Review capability probe did not finish')
        time.sleep(.001)
    code=os.waitstatus_to_exitcode(status)
    if code not in {0,78}:raise RuntimeError('Review capability probe failed')
    _PAIR_CAPABILITY=(os.getpid(),code==0)
    return code==0


class PairedReviewWorkerError(RuntimeError):
    """A launched pair failed; its owning worker must exit and be contained."""


class _ReviewPair:
    """One scoped coordinator; closing can never reuse an opening result."""
    def __init__(self):
        self.process=None;self.calls=0;self.request=None;self.deadline=None
        self.errors=None

    def _transfer(self,fd,data=None,size=None):
        result=bytearray();offset=0
        poll=select.poll();poll.register(fd,select.POLLOUT if data is not None else select.POLLIN)
        while offset<(len(data) if data is not None else size):
            left=self.deadline-time.monotonic()
            if left<=0:raise subprocess.TimeoutExpired('paired helper',self.timeout)
            try:
                if not poll.poll(max(1,int(left*1000))):continue
                if data is not None:
                    offset+=os.write(fd,memoryview(data)[offset:])
                else:
                    block=os.read(fd,min(65536,size-offset))
                    if not block:raise ValueError('Incomplete paired helper frame')
                    result.extend(block);offset+=len(block)
            except (InterruptedError,BlockingIOError):continue
        return bytes(result)

    def exchange(self,root,python,encoded,count,limit):
        request=json.loads(encoded);method=request['method']
        normalized={**request,'method':method.removesuffix('_with_dependencies')}
        if normalized['method'] not in {'review_observation','checkpoint_observation'}:
            raise ValueError('Fixed paired full review required')
        if normalized['method']=='checkpoint_observation' and request['args'][1]!='review_observation':
            raise ValueError('Fixed paired full review required')
        if self.calls>=2:raise ValueError('Paired helper accepts exactly two passes')
        if self.process is None:
            self.request=normalized;self.identity=(str(root),str(python),count)
            self.timeout=count*16;self.deadline=time.monotonic()+self.timeout
            self.errors=tempfile.TemporaryFile()
            try:
                self.process=subprocess.Popen([str(python),'-I','-S','-B','-c',
                    'DRIVER='+repr(DRIVER)+'\n'+PAIR_COORDINATOR,str(root)],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,
                    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'})
                os.set_blocking(self.process.stdin.fileno(),False)
                os.set_blocking(self.process.stdout.fileno(),False)
            except BaseException:
                self.close();raise
        elif normalized!=self.request or self.identity!=(str(root),str(python),count):
            raise ValueError('Paired closing review input changed')
        message=json.dumps({'phase':self.calls,'request':request,'count':count,'limit':limit},allow_nan=False).encode()
        if len(message)>1573376:raise ValueError('Paired helper request exceeds bound')
        self._transfer(self.process.stdin.fileno(),len(message).to_bytes(8,'big')+message)
        length=int.from_bytes(self._transfer(self.process.stdout.fileno(),size=8),'big')
        if length>limit:raise ValueError('Paired helper result exceeds bound')
        payload=self._transfer(self.process.stdout.fileno(),size=length)
        self.calls+=1
        if self.calls==2:
            self.process.stdin.close()
            extra=self._transfer(self.process.stdout.fileno(),size=1)
            if extra!=b'\x00':raise ValueError('Unexpected paired helper trailing frame')
            if self.process.wait(timeout=max(0,self.deadline-time.monotonic()))!=0:
                raise ValueError('Paired helper failed')
            if os.read(self.process.stdout.fileno(),1):raise ValueError('Extra paired helper output')
        return json.loads(payload)

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=.2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            for stream in (self.process.stdin,self.process.stdout):
                if stream is not None:stream.close()
        if self.errors is not None:self.errors.close()


def _pidfd_wait_available():
    """Choose the wait mechanism before launching a helper."""
    if not callable(getattr(os,'pidfd_open',None)):return False
    try:fd=os.pidfd_open(os.getpid())
    except OSError as failure:
        if failure.errno in {errno.ENOSYS,errno.EINVAL,errno.EPERM,errno.EACCES}:return False
        raise
    try:select.select([fd],[],[],0)
    finally:os.close(fd)
    return True


def _run_helper(args,encoded,output,errors,environment,timeout):
    """Fresh child, bounded file-backed input/output, exact deadline and reap.

    pidfd readiness avoids timeout polling delay. Unsupported hosts keep the
    legacy wait on the same single child; no failure can relaunch a helper.
    """
    if not isinstance(encoded,bytes) or len(encoded)>1572864:
        raise ValueError('Bounded helper input required')
    event_wait=_pidfd_wait_available()
    with tempfile.TemporaryFile() as input_file:
        input_file.write(encoded);input_file.seek(0)
        deadline=time.monotonic()+timeout
        process=subprocess.Popen(args,stdin=input_file,stdout=output,stderr=errors,env=environment)
        fd=None
        try:
            if event_wait:
                try:fd=os.pidfd_open(process.pid)
                except ProcessLookupError:
                    if process.poll() is None:raise
                if fd is not None:
                    while True:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise subprocess.TimeoutExpired(args,timeout)
                        try:ready=select.select([fd],[],[],remaining)[0]
                        except InterruptedError:continue
                        if ready:break
                process.wait()
            else:
                process.wait(timeout=max(0,deadline-time.monotonic()))
            return subprocess.CompletedProcess(args,process.returncode)
        except BaseException:
            if process.poll() is None:process.kill()
            process.wait()
            raise
        finally:
            if fd is not None:os.close(fd)

METHODS = {'task_records','task_queue','contract_definition_issues','contract_data',
           'prerequisite_issues','accepted_task_state','verification_definitions','verified_check_state','contract_semantics_sha256','validation_issues','completed_state','verified_delivery_state','definition_observation','review_observation','outcome_observation','checkpoint_observation','review_dependency_cut','review_observation_with_dependencies','checkpoint_observation_with_dependencies'}
DRIVER = '''import json,os,resource,sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912))
sys.dont_write_bytecode=True
root=Path(sys.argv[1])
os.environ['DEEP_LOOP_SKILLS_ROOT']=str(root/'skills')
sys.path[:0]=[str(root/'skills/deep-loop/scripts')]
payload=sys.stdin.buffer.read(1572865)
request=json.loads(payload)
assert len(payload)<=(1572864 if request['method'] in {'checkpoint_observation','checkpoint_observation_with_dependencies'} else 524288)
method=request['method']
assert method in {'task_records','task_queue','contract_definition_issues','contract_data','prerequisite_issues','accepted_task_state','verification_definitions','verified_check_state','contract_semantics_sha256','validation_issues','completed_state','verified_delivery_state','definition_observation','review_observation','outcome_observation','checkpoint_observation','review_dependency_cut','review_observation_with_dependencies','checkpoint_observation_with_dependencies'}
dependency_only=method=='review_dependency_cut'
dependency_wrapped=method in {'review_observation_with_dependencies','checkpoint_observation_with_dependencies'}
dependency_cut=dependency_only or dependency_wrapped
if method in {'review_dependency_cut','review_observation_with_dependencies'}:method='review_observation'
if method=='checkpoint_observation_with_dependencies':method='checkpoint_observation'
composite=method=='checkpoint_observation'
derivation=None
if composite:
 assert len(request['args'])==5 and not request['kwargs']
 state,mode,groups,image_archive_argument,derivation=request['args']
 assert mode in {'definition_observation','review_observation','outcome_observation'}
 assert isinstance(derivation,dict) and set(derivation)=={'before','revision','evidence','terminal'} and type(derivation['terminal']) is bool
 request['args']=[state] if mode=='definition_observation' else [state,groups,image_archive_argument] if mode=='review_observation' else [state,groups]
 method=mode
 assert len(json.dumps({'method':mode,'args':request['args'],'kwargs':{}}).encode())<=524288
 assert len(json.dumps({'method':'verified_delivery_state','args':[derivation['before'],derivation['revision'],derivation['evidence'],image_archive_argument],'kwargs':{}}).encode())<=524288
batch=method in {'definition_observation','review_observation','outcome_observation'}
count=3 if batch else 1
if method in {'review_observation','outcome_observation'}:
 assert len(request['args'])==(3 if method=='review_observation' else 2) and not request['kwargs']
 groups=request['args'][1]
 assert isinstance(groups,list) and 1<=len(groups)<=129
 assert all(isinstance(ids,list) and ids and all(isinstance(i,str) and i for i in ids) and len(ids)==len(set(ids)) for ids in groups)
 count=(4 if method=='review_observation' else 3)+len(groups)
if composite:count+=1+int(derivation['terminal'])
limit=count*1048576+(1024 if batch else 0)+(1048576 if dependency_wrapped else 0)
resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
resource.setrlimit(resource.RLIMIT_CPU,(5 if method in {'review_observation','outcome_observation'} else count*5,count*5))
import signal
signal.alarm(8)
import deep_loop
dependency_records=None
if dependency_cut:
 import proof_binding
 dependency_context=proof_binding.dependency_context()
 dependency_records=dependency_context.__enter__()
args=request['args']
if method=='contract_data':args[0]=Path(args[0])
if method=='validation_issues' and len(args)>2 and args[2] is not None:args[2]=Path(args[2])
if method=='completed_state' and len(args)>1 and args[1] is not None:args[1]=Path(args[1])
if method=='verified_delivery_state' and len(args)>3 and args[3] is not None:args[3]=Path(args[3])
if batch:
 assert not request['kwargs'] and (len(args)==1 if method=='definition_observation' else len(args)==(3 if method=='review_observation' else 2))
 state=args[0]
 # Fixed composition preserves older pinned packages without changing them.
 result={}
 readers=[('records',lambda:deep_loop.task_records(state)),
                     ('issues',lambda:deep_loop.contract_definition_issues(state)),
                     ('contract',lambda:deep_loop.contract_data(Path(state['verificationContract']['path']),verify_files=False))]
 if method in {'review_observation','outcome_observation'}:
  archive=Path(args[2]) if method=='review_observation' and args[2] is not None else None
  readers += [('prerequisite-'+str(index),lambda ids=ids:deep_loop.prerequisite_issues(state,ids)) for index,ids in enumerate(groups)]
  if method=='review_observation':readers.append(('review_issues',lambda:deep_loop.validation_issues(state,'ship' if state.get('complete') is True else 'review',archive)))
 if composite:
  image_archive=Path(image_archive_argument) if image_archive_argument is not None else None
  readers.insert(0,('delivery_image',lambda:deep_loop.verified_delivery_state(derivation['before'],derivation['revision'],derivation['evidence'],image_archive)))
  if derivation['terminal']:
   def terminal_reader():
    assert len(json.dumps({'method':'completed_state','args':[result['delivery_image'],image_archive_argument],'kwargs':{}}).encode())<=524288
    return deep_loop.completed_state(result['delivery_image'],image_archive)
   readers.insert(1,('terminal_image',terminal_reader))
 for name,reader in readers:
  usage=resource.getrusage(resource.RUSAGE_SELF);before=usage.ru_utime+usage.ru_stime
  resource.setrlimit(resource.RLIMIT_CPU,(min(count*5,__import__('math').ceil(before)+5),count*5))
  signal.alarm(8)
  value=reader();usage=resource.getrusage(resource.RUSAGE_SELF)
  assert usage.ru_utime+usage.ru_stime-before<=5
  assert len(json.dumps(value,allow_nan=False).encode())<=1048576
  result[name]=value
 if method in {'review_observation','outcome_observation'}:result['prerequisites']=[result.pop('prerequisite-'+str(index)) for index in range(len(groups))]
else:result=getattr(deep_loop,method)(*args,**request['kwargs'])
signal.alarm(8)
if dependency_cut:
 dependencies=proof_binding.close_dependency_cut(dependency_records)
 assert len(json.dumps(dependencies,allow_nan=False).encode())<=1048576
 result=dependencies if dependency_only else {'observation':result,'dependencies':dependencies}
 dependency_context.__exit__(None,None,None)
sys.stdout.write(json.dumps(result,allow_nan=False))
'''

PAIR_COORDINATOR = '''import ctypes,io,json,math,os,resource,signal,sys,tempfile,time
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS,(536870912,536870912))
sys.dont_write_bytecode=True
root=Path(sys.argv[1]);os.environ['DEEP_LOOP_SKILLS_ROOT']=str(root/'skills')
sys.path[:0]=[str(root/'skills/deep-loop/scripts')]
libc=ctypes.CDLL(None,use_errno=True)
libc.prctl.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
libc.prctl.restype=ctypes.c_int
assert libc.prctl(36,1,0,0,0)==0
child=None
children_path=Path('/proc/self/task')/str(os.getpid())/'children'
def children():
 values=children_path.read_text().split();assert len(values)<=512
 return [int(value) for value in values]
def cleanup():
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 deadline=time.monotonic()+.15
 while True:
  owned=children()
  if not owned:return
  assert time.monotonic()<deadline
  for pid in owned:
   # An unreaped direct child cannot have its PID recycled. This single-threaded
   # coordinator is its only reaper; live children return zero here.
   waited,status=os.waitpid(pid,os.WNOHANG)
   if not waited:
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
  time.sleep(.001)
def stop(*args):
 cleanup()
 raise SystemExit(1)
signal.signal(signal.SIGTERM,stop)
def read_exact(size):
 data=bytearray()
 while len(data)<size:
  chunk=os.read(0,min(65536,size-len(data)))
  if not chunk:raise ValueError('Incomplete review continuation')
  data.extend(chunk)
 return bytes(data)
def frame():
 size=int.from_bytes(read_exact(8),'big')
 assert size<=1573376
 message=json.loads(read_exact(size));assert set(message)=={'phase','request','count','limit'}
 assert type(message['count']) is int and 5<=message['count']<=135
 assert type(message['limit']) is int and 0<message['limit']<=message['count']*1048576+1049600
 assert set(message['request'])=={'method','args','kwargs'}
 return message
def write_all(data):
 view=memoryview(data)
 while view:
  n=os.write(1,view);view=view[n:]
opening=frame();count=opening['count']
# Closing may include its own bounded dependency envelope. Keep import output
# at the opening soft bound while permitting each child to set its exact limit.
resource.setrlimit(resource.RLIMIT_FSIZE,(opening['limit'],count*1048576+1049600))
resource.setrlimit(resource.RLIMIT_CPU,(1,count*10))
signal.alarm(8)
import deep_loop,proof_binding
signal.alarm(0)
normalized=None
try:
 for phase in range(2):
  message=opening if phase==0 else frame()
  assert message['phase']==phase and message['count']==count
  request=message['request'];method=request['method'].removesuffix('_with_dependencies')
  assert method in {'review_observation','checkpoint_observation'}
  assert method!='checkpoint_observation' or request['args'][1]=='review_observation'
  current={**request,'method':method}
  if phase:assert current==normalized
  else:normalized=current
  usage=resource.getrusage(resource.RUSAGE_SELF)
  assert usage.ru_utime+usage.ru_stime<=1
  with tempfile.TemporaryFile() as source,tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
   source.write(json.dumps(request,allow_nan=False).encode());source.seek(0)
   coordinator=os.getpid();child=os.fork()
   if child==0:
    try:
     assert libc.prctl(1,signal.SIGKILL,0,0,0)==0
     if os.getppid()!=coordinator:os._exit(1)
     signal.signal(signal.SIGTERM,signal.SIG_DFL)
     # Descendants must not retain the coordinator's protocol pipes. Otherwise
     # its abrupt death could leave a controller blocked on a grandchild's fd.
     os.dup2(source.fileno(),0);os.dup2(output.fileno(),1);os.dup2(errors.fileno(),2)
     sys.stdin=io.TextIOWrapper(source,encoding='utf-8');sys.stdout=io.TextIOWrapper(output,encoding='utf-8');sys.stderr=io.TextIOWrapper(errors,encoding='utf-8')
     # Reserve one CPU second for the pristine coordinator from the original
     # combined two-invocation budget. Individual reader checks stay unchanged.
     code=DRIVER.replace('count*5','cpu_ceiling')
     code=code.replace('limit=count*1048576','cpu_ceiling=count*5-pair_phase\\nlimit=count*1048576')
     exec(code,{'__name__':'__main__','pair_phase':phase})
     sys.stdout.flush();sys.stderr.flush()
    except BaseException:os._exit(1)
    os._exit(0)
   waited,status=os.waitpid(child,0);child=None
   assert os.waitstatus_to_exitcode(status)==0
   assert not children(), 'Helper left owned descendants'
   output.seek(0);payload=output.read(message['limit']+1)
   assert len(payload)<=message['limit']
   usage=resource.getrusage(resource.RUSAGE_SELF)
   assert usage.ru_utime+usage.ru_stime<=1
   write_all(len(payload).to_bytes(8,'big')+payload)
   # The pristine parent must not carry an opening output allocation into the
   # closing child's unchanged address-space allowance.
   del payload
 assert os.read(0,1)==b''
 write_all(b'\\x00')
finally:
 cleanup()
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
        if len(encoded)>(1572864 if method in {'checkpoint_observation','checkpoint_observation_with_dependencies'} else 524288):raise ValueError('Pinned helper request exceeds bound')
        dependency_only=method=='review_dependency_cut'
        dependency_wrapped=method in {'review_observation_with_dependencies','checkpoint_observation_with_dependencies'}
        dependency_cut=dependency_only or dependency_wrapped
        budget_method='review_observation' if method in {'review_dependency_cut','review_observation_with_dependencies'} else method
        composite=method in {'checkpoint_observation','checkpoint_observation_with_dependencies'}
        if composite:
            if (len(args)!=5 or kwargs or args[1] not in {'definition_observation','review_observation','outcome_observation'} or
                    not isinstance(args[4],dict) or set(args[4])!={'before','revision','evidence','terminal'} or type(args[4]['terminal']) is not bool):
                raise ValueError('Fixed checkpoint observation required')
            original_args=args;method=args[1]
            args=(args[0],) if method=='definition_observation' else (args[0],args[2],args[3]) if method=='review_observation' else (args[0],args[2])
        budget_method='review_observation' if dependency_only or method=='review_observation_with_dependencies' else method
        count=3 if method=='definition_observation' else 1
        if budget_method in {'review_observation','outcome_observation'}:
            if len(args)!=(3 if budget_method=='review_observation' else 2) or not isinstance(args[1],list) or not 1<=len(args[1])<=129:
                raise ValueError('Bounded review prerequisite groups required')
            count=(4 if budget_method=='review_observation' else 3)+len(args[1])
        if composite:count+=1+int(original_args[4]['terminal'])
        limit=count*1048576+(1024 if method in {'definition_observation','review_observation','outcome_observation'} else 0)+(1048576 if dependency_wrapped else 0)
        pair=getattr(self,'_review_pair',None)
        if pair is not None:
            return pair.exchange(root,python,encoded,count,limit)
        environment={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result=_run_helper([str(python),'-I','-S','-B','-c',DRIVER,str(root)],encoded,
                               output,errors,environment,count*8)
            if result.returncode!=0:raise ValueError('Pinned helper operation unavailable or failed')
            output.seek(0);payload=output.read(limit+1)
        if len(payload)>limit:raise ValueError('Pinned helper result exceeds bound')
        return json.loads(payload)

    @contextmanager
    def review_pair(self):
        """Scope exactly two full reads with controller checks between them."""
        if getattr(self,'_review_pair',None) is not None:
            raise ValueError('Nested paired review unavailable')
        pair=_ReviewPair();self._review_pair=pair
        try:
            yield
            if pair.calls!=2:raise ValueError('Incomplete paired full review')
        except BaseException as failure:
            if pair.process is not None:
                raise PairedReviewWorkerError('Paired review failed; owning worker must stop') from failure
            raise
        finally:
            self._review_pair=None;pair.close()

    def supports_review_pair(self):
        boundary=_PAIR_CONTAINMENT
        if boundary is None or boundary[0]!=os.getpid():return False
        if os.environ.get('INVOCATION_ID')!=boundary[2]:
            raise RuntimeError('Qualified worker invocation changed')
        if Path('/proc/self/cgroup').read_text().strip()!='0::'+boundary[3]:
            raise RuntimeError('Qualified worker containment changed')
        return _review_pair_available()

    def review_observation_with_dependencies(self,state,groups,archive=None):
        return self._call('review_observation_with_dependencies',state,groups,str(archive) if archive is not None else None)
    def checkpoint_observation_with_dependencies(self,state,mode,groups,archive,derivation):
        return self._call('checkpoint_observation_with_dependencies',state,mode,groups,str(archive) if archive is not None else None,derivation)

    def review_dependency_cut(self,state,groups,archive=None):
        return self._call('review_dependency_cut',state,groups,str(archive) if archive is not None else None)

    def checkpoint_observation(self,state,mode,groups,archive,derivation):
        return self._call('checkpoint_observation',state,mode,groups,str(archive) if archive is not None else None,derivation)

    def validation_issues(self,state,stage,archive=None):
        return self._call('validation_issues',state,stage,str(archive) if archive is not None else None)
    def verified_delivery_state(self,state,revision,evidence,archive=None):
        return self._call('verified_delivery_state',state,revision,evidence,str(archive) if archive is not None else None)
    def completed_state(self,state,archive=None):
        return self._call('completed_state',state,str(archive) if archive is not None else None)
    def outcome_observation(self,state,groups):return self._call('outcome_observation',state,groups)
    def review_observation(self,state,groups,archive=None):
        return self._call('review_observation',state,groups,str(archive) if archive is not None else None)
    def definition_observation(self,state):return self._call('definition_observation',state)
    def task_records(self,state):return self._call('task_records',state)
    def task_queue(self,state):return self._call('task_queue',state)
    def contract_definition_issues(self,state):return self._call('contract_definition_issues',state)
    def contract_data(self,path,verify_files=True):return self._call('contract_data',str(path),verify_files=verify_files)
    def contract_semantics_sha256(self,contract):return self._call('contract_semantics_sha256',contract)
    def verification_definitions(self,state,ids):return self._call('verification_definitions',state,ids)
    def verified_check_state(self,state,verifier_id,receipt,evidence,expected):
        return self._call('verified_check_state',state,verifier_id,receipt,evidence,expected)
    def prerequisite_issues(self,state,ids):return self._call('prerequisite_issues',state,ids)
    def accepted_task_state(self,state,task_id,ids,evidence,expected):
        return self._call('accepted_task_state',state,task_id,ids,evidence,expected)


class BoundPinnedHelper(PinnedHelper):
    """Resolve protected helper authority only when a proof operation needs it.

    Constructing the controller must remain possible for exact-owner cleanup
    when a package or its configuration is missing. Dispatch/proof calls still
    require the complete binding and freshly verified snapshot on every call.
    """
    def __init__(self,store,contract_digest):
        initialize(contract_digest)
        self.store,self.contract_digest=store,contract_digest
        self.owner_uid=store.owner_uid

    def _verify(self):
        record=self.store.read(self.contract_digest+'.workflow-helper.json')
        binding=self.store.read(self.contract_digest+'.workflow.json')
        if (not isinstance(record,dict) or
                set(record)!={'contract_digest','binding_digest','approval_ref','helper'} or
                record['contract_digest']!=self.contract_digest or
                record['binding_digest']!=digest(binding) or
                record['approval_ref']!=binding.get('approval_ref') or
                not isinstance(record['approval_ref'],str) or not record['approval_ref'].strip()):
            raise ValueError('Pinned helper workflow authority changed')
        intent=self.store.read(self.contract_digest+'.workflow-helper-intent.json')
        completed=self.store.read(self.contract_digest+'.workflow-helper-complete.json')
        if (not isinstance(intent,dict) or set(intent)!={
                'contract_digest','helper_digest','binding_digest','approval_ref','journal_revision'} or
                intent['contract_digest']!=self.contract_digest or intent['helper_digest']!=digest(record) or
                intent['binding_digest']!=record['binding_digest'] or intent['approval_ref']!=record['approval_ref'] or
                completed!={**intent,'activated':False}):
            raise ValueError('Pinned helper enrollment completion changed')
        if sys.platform!='linux':raise ValueError('Pinned helper requires qualified Linux runtime')
        self.configuration=record['helper']
        return super()._verify()
