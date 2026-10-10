"""Nonroot native verifier primitive; caller owns workflow/result publication.

No CLI or worker integration. A protected stopped-attempt plan/intent is required.
Submission intent precedes side effects; uncertain submissions are never replayed.
The caller must fence competing dispatch until this exact native unit is empty.
"""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

from admission import digest
from authority import require_active
from private_launch import ACCOUNT,ROOT
from systemd_observer import observe_unit
from worker_window import remaining


NETWORK_SYSCALLS=tuple('accept accept4 bind connect getpeername getsockname getsockopt io_uring_enter io_uring_register io_uring_setup listen recv recvfrom recvmmsg recvmmsg_time64 recvmsg send sendmmsg sendmsg sendto setsockopt shutdown socket socketcall socketpair'.split())


def canonical(value):
    if not isinstance(value,str) or not value or any(c.isspace() or c in '\\:' for c in value):
        raise ValueError('Native verifier path cannot contain property separators')
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('Canonical verifier path required')
    return path


def launch_plan(owned,candidate,index):
    """Freeze a single declared command and filesystem policy; no dispatch."""
    if (not isinstance(owned,dict) or set(owned)!={'owner','invocation_id','journal_revision','plan'} or
            type(index) is not int or not 0<=index<128):raise ValueError('Owned verifier plan required')
    parent=owned['plan'];owner=owned['owner'];candidate=canonical(str(candidate))
    if (parent.get('contract_digest')!=owner.get('contract_digest') or parent.get('execution_authorized') is not False or
            parent.get('parent_accepted') is not False or index>=len(parent['definitions'])):
        raise ValueError('Read-only owned verification inputs required')
    row=parent['definitions'][index];verifier=row['verifier'];proof=verifier['proof']
    if (verifier['id']!=parent['verifier_ids'][index] or verifier['gate']!='blocking' or verifier['class']=='human' or
            proof.get('mode')!='bound' or 'readback' in proof):raise ValueError('Unsupported automatic verifier')
    argv=proof['argv']
    if (not isinstance(argv,list) or not argv or len(argv)>256 or
            any(not isinstance(a,str) or not a or '\0' in a for a in argv) or
            len(json.dumps(argv).encode())>65536):raise ValueError('Bounded verifier argv required')
    executable=Path(argv[0])
    if not executable.is_absolute() or '..' in executable.parts:raise ValueError('Absolute verifier executable required')
    base=canonical(row['base']);cwd=canonical(proof.get('working_directory',str(base)))
    if cwd!=candidate and candidate not in cwd.parents:raise ValueError('Verifier cwd must be inside candidate')
    inputs=[canonical(p) for p in row['input_paths']]
    outputs=sorted({str(canonical(str(base/a['path'])).parent) for a in proof['artifacts']})
    if not outputs or len(outputs)>128:raise ValueError('Bounded verifier output directories required')
    for output in map(Path,outputs):
        if candidate not in output.parents or any(output==p or output in p.parents for p in inputs):
            raise ValueError('Verifier output must not contain candidate root or declared inputs')
    core={'contract_digest':owner['contract_digest'],'source_owner':owner,'source_invocation':owned['invocation_id'],
          'owned_plan_digest':digest(owned),'index':index,'argv':list(argv),
          'command':['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent',*argv],'cwd':str(cwd),
          'candidate':str(candidate),'read_write_paths':outputs,'input_paths':list(map(str,inputs)),
          'definition':row,'runtime_seconds':15}
    return {**core,'unit':'deep-loop-pilot-'+digest(core)+'-1-1'}


class NativeVerifier:
    def __init__(self,store,contract_digest):self.store,self.key=store,contract_digest

    def _intent(self,plan):
        if os.geteuid()!=0 or sys.platform!='linux':raise ValueError('Trusted root Linux verifier required')
        owner=plan['source_owner'];prefix=owner['unit']+'.verifier-'+str(plan['index'])
        if (owner['contract_digest']!=self.key or plan['contract_digest']!=self.key or
                self.store.read(prefix+'.intent.json').get('plan_digest')!=digest(plan)):
            raise ValueError('Protected verifier intent changed')
        intent=self.store.read(prefix+'.intent.json')
        if (set(intent)!={'owned_plan','plan','plan_digest'} or intent['plan']!=plan or
                launch_plan(intent['owned_plan'],plan['candidate'],plan['index'])!=plan):
            raise ValueError('Verifier inputs differ from protected owned plan')
        core={k:v for k,v in plan.items() if k!='unit'}
        if plan['unit']!='deep-loop-pilot-'+digest(core)+'-1-1':raise ValueError('Verifier unit identity changed')
        invocation=self.store.read(owner['unit']+'.invocation.json')
        if invocation!={'owner':owner,'invocation_id':plan['source_invocation']}:
            raise ValueError('Verifier parent ownership changed')
        description=subprocess.run(['/usr/bin/systemctl','show',owner['unit']+'.service','--property=Description','--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        if description!='Deep Loop plan '+owner['plan_digest']:raise ValueError('Verifier parent launch changed')
        native=observe_unit(owner['unit'],plan['source_invocation'])
        if not native['execution_finished'] or not native['cgroup_empty']:raise ValueError('Verifier parent still owns processes')
        return prefix

    def _properties(self,plan,prefix):
        return {'User':ACCOUNT,'Group':ACCOUNT,'WorkingDirectory':plan['cwd'],
                'Description':'Deep Loop verifier '+digest(plan),'Slice':'system.slice','KillMode':'control-group',
                'Restart':'no','RemainAfterExit':'yes','RuntimeMaxSec':15,'TimeoutStartSec':5,'TimeoutStopSec':5,
                'PrivateNetwork':'yes','IPAddressDeny':'any','RestrictAddressFamilies':'AF_UNIX',
                'ProtectSystem':'strict','ReadOnlyPaths':plan['candidate'],
                'ReadWritePaths':' '.join(plan['read_write_paths']),
                'InaccessiblePaths':' '.join(['/home','/root',ROOT+'/home',str(self.store.root)]),
                'SystemCallFilter':'~'+' '.join(NETWORK_SYSCALLS),
                'SystemCallArchitectures':'native','SystemCallErrorNumber':'EPERM',
                'PrivateTmp':'yes','PrivateDevices':'yes','NoNewPrivileges':'yes','CapabilityBoundingSet':'',
                'ProtectKernelTunables':'yes','ProtectKernelModules':'yes','ProtectControlGroups':'yes',
                'RestrictSUIDSGID':'yes','LimitCORE':0,'LimitAS':536870912,'LimitCPU':10,'LimitFSIZE':1048576,
                'Environment':'PATH=/usr/bin:/bin HOME=/nonexistent',
                'UnsetEnvironment':'OPENAI_API_KEY CODEX_API_KEY CODEX_HOME OPENAI_BASE_URL NODE_OPTIONS GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM',
                'StandardInput':'null','StandardOutput':'append:'+str(self.store.root/(prefix+'.stdout')),
                'StandardError':'append:'+str(self.store.root/(prefix+'.stderr'))}

    def _candidate_input(self,path,account):
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
                info.st_uid!=account.pw_uid or info.st_gid!=account.pw_gid or
                info.st_mode&0o077 or path.resolve()!=path):
            raise ValueError('Private single-link regular verifier input required')

    def _dispatch_window(self):
        require_active(self.store,self.key)
        # Five seconds dispatch allowance plus startup, runtime and stop.
        if remaining(self.store,self.key)<30:
            raise ValueError('Insufficient immutable verification window')

    def _qualify(self,plan):
        require_active(self.store,self.key)
        try:self.store.read('active-owner.json')
        except FileNotFoundError:pass
        else:raise ValueError('Model owner blocks native verification')
        from pinned_helper import BoundPinnedHelper
        from workflow_gate import WorkflowGate
        from git_journal import GitJournal
        prefix=plan['source_owner']['unit']+'.verifier-'+str(plan['index'])
        owned=self.store.read(prefix+'.intent.json')['owned_plan']
        current=WorkflowGate(self.store,self.key,BoundPinnedHelper(self.store,self.key)).verification_plan(owned['plan']['selection'])
        if current!=owned['plan']:raise ValueError('Verifier bound inputs changed before dispatch')
        revision,state=GitJournal(self.store.root/'journal-work',str(self.store.root/'journal.git'),self.key).read()
        if revision!=owned['journal_revision'] or not state['attempts'] or state['attempts'][-1]['status']!='finished':
            raise ValueError('Verifier parent journal changed before dispatch')
        latest=state['attempts'][-1];owner=plan['source_owner']
        if (latest['run_id'],latest['run_attempt'])!=(owner['run_id'],owner['run_attempt']):
            raise ValueError('Verifier parent attempt changed')
        if remaining(self.store,self.key)<25:raise ValueError('Insufficient immutable verification window')
        account=pwd.getpwnam(ACCOUNT);candidate=canonical(plan['candidate'])
        if account.pw_uid==0 or os.getgrouplist(ACCOUNT,account.pw_gid)!=[account.pw_gid]:
            raise ValueError('Dedicated nonroot verifier identity required')
        if str(candidate)!=ROOT+'/candidate/'+self.key:raise ValueError('Verifier candidate authority changed')
        for path in candidate.parents:
            info=path.lstat()
            if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):raise ValueError('Untrusted verifier candidate ancestry')
        for path in [candidate,*map(Path,plan['read_write_paths'])]:
            info=path.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=account.pw_uid or info.st_gid!=account.pw_gid or
                    stat.S_IMODE(info.st_mode)!=0o700 or path.resolve()!=path):raise ValueError('Private verifier directory required')
        executable=Path(plan['argv'][0])
        resolved=executable.resolve()
        if candidate in resolved.parents:
            if str(resolved) not in plan['input_paths']:raise ValueError('Candidate executable must be a bound input')
        else:
            for path in (executable,*executable.parents,resolved,*resolved.parents):
                info=path.lstat()
                if info.st_uid!=0 or not stat.S_ISLNK(info.st_mode) and info.st_mode&0o022:
                    raise ValueError('Unprotected verifier executable')
        # External inputs must be protected from this account; candidate inputs
        # are mounted read-only and the entire account stream is exclusive.
        for path in map(Path,plan['input_paths']):
            if candidate==path or candidate in path.parents:
                self._candidate_input(path,account)
                continue
            for parent in (path,*path.parents):
                info=parent.lstat()
                if info.st_uid!=0 or info.st_mode&0o022 or stat.S_ISLNK(info.st_mode):
                    raise ValueError('Unprotected external verifier input')
        process=subprocess.run(['/usr/bin/pgrep','-u',str(account.pw_uid)],capture_output=True,text=True,timeout=5)
        if process.returncode!=1 or process.stdout:raise ValueError('Verifier account stream occupied or unavailable')

    def unsubmitted(self,plan):
        """Caller holds stream lock; prove this protocol never crossed dispatch."""
        prefix=self._intent(plan)
        for suffix in ('.submit-intent.json','.invocation.json'):
            try:self.store.read(prefix+suffix)
            except FileNotFoundError:pass
            else:raise ValueError('Submitted verifier requires native ownership inspection')
        account=pwd.getpwnam(ACCOUNT)
        process=subprocess.run(['/usr/bin/pgrep','-u',str(account.pw_uid)],capture_output=True,text=True,timeout=5)
        if process.returncode!=1 or process.stdout:raise ValueError('Verifier account is not empty')
        return {'plan_digest':digest(plan),'submission_intent_absent':True,
                'account_empty':True,'native_dispatched':False}

    def submit(self,plan):
        """Exactly one attempted submission; caller holds credential lock."""
        prefix=self._intent(plan)
        try:self.store.read(prefix+'.cleanup-intent.json')
        except FileNotFoundError:pass
        else:raise ValueError('Verifier cleanup prevents further submission')
        self._qualify(plan)
        self.store.create(prefix+'.submit-intent.json',{'plan_digest':digest(plan)})
        for suffix in ('.stdout','.stderr'):
            fd=os.open(self.store._path(prefix+suffix),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            os.fsync(fd);os.close(fd)
        self.store._sync()
        self._qualify(plan)
        properties=self._properties(plan,prefix)
        command=['/usr/bin/systemd-run','--unit='+plan['unit'],'--service-type=exec']
        command+=['--property='+name+'='+str(value) for name,value in properties.items()]
        self._dispatch_window()
        subprocess.run(command+plan['command'],capture_output=True,text=True,check=True,timeout=5)
        return self.adopt(plan)

    def adopt(self,plan):
        """Inspect only the same planned unit, even after revocation; no replay."""
        prefix=self._intent(plan)
        if self.store.read(prefix+'.submit-intent.json')!={'plan_digest':digest(plan)}:
            raise ValueError('Verifier submission authority changed')
        invocation=subprocess.run(['/usr/bin/systemctl','show',plan['unit']+'.service','--property=InvocationID','--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        native=observe_unit(plan['unit'],invocation)
        properties=self._properties(plan,prefix)
        for name in ('Description','WorkingDirectory','PrivateNetwork','ProtectSystem','ReadOnlyPaths','ReadWritePaths',
                     'InaccessiblePaths','NoNewPrivileges','PrivateTmp','PrivateDevices','RestrictAddressFamilies',
                     'CapabilityBoundingSet','ProtectKernelTunables','ProtectKernelModules','ProtectControlGroups',
                     'RestrictSUIDSGID','Environment','UnsetEnvironment','LimitAS','LimitCPU','LimitFSIZE'):
            value=subprocess.run(['/usr/bin/systemctl','show',plan['unit']+'.service','--property='+name,'--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
            if value!=str(properties[name]):raise ValueError('Native verifier isolation drift: '+name)
        for name,expected in [('RuntimeMaxUSec','15s'),('TimeoutStartUSec','5s'),('TimeoutStopUSec','5s'),('SystemCallErrorNumber','1')]:
            value=subprocess.run(['/usr/bin/systemctl','show',plan['unit']+'.service','--property='+name,'--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
            if value!=expected:raise ValueError('Native verifier deadline drift')
        buspath='/org/freedesktop/systemd1/unit/'+''.join(c if c.isalnum() else '_'+format(ord(c),'02x') for c in plan['unit']+'.service')
        for name,expected in [('SystemCallFilter',{'type':'(bas)','data':[False,list(NETWORK_SYSCALLS)]}),
                              ('SystemCallArchitectures',{'type':'as','data':['native']})]:
            raw_policy=subprocess.run(['/usr/bin/busctl','--json=short','get-property','org.freedesktop.systemd1',buspath,'org.freedesktop.systemd1.Service',name],capture_output=True,text=True,check=True,timeout=5)
            if json.loads(raw_policy.stdout)!=expected:raise ValueError('Native verifier syscall isolation drift')
        raw=subprocess.run(['/usr/bin/busctl','--json=short','get-property','org.freedesktop.systemd1',buspath,'org.freedesktop.systemd1.Service','ExecStart'],capture_output=True,text=True,check=True,timeout=5)
        command=json.loads(raw.stdout)
        if (command.get('type')!='a(sasbttttuii)' or len(command.get('data',[]))!=1 or
                command['data'][0][0]!=plan['command'][0] or command['data'][0][1]!=plan['command']):
            raise ValueError('Native verifier argv changed')
        return {'plan_digest':digest(plan),'invocation_id':invocation,'native':native,
                'exit_code':command['data'][0][-1] if native['execution_finished'] and command['data'][0][-2]==1 else None}

    def stop(self,plan,invocation_id):
        observation=self.adopt(plan)
        if observation['invocation_id']!=invocation_id:raise ValueError('Verifier generation changed before stop')
        subprocess.run(['/usr/bin/systemctl','stop',plan['unit']+'.service'],capture_output=True,text=True,check=True,timeout=5)
        after=self.adopt(plan)
        if after['invocation_id']!=invocation_id:raise ValueError('Verifier generation changed during stop')
        return after
