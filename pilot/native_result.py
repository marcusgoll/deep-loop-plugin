"""Protected native evidence sealing; no checkpoint mutation or acceptance."""
import datetime
import hashlib
import os
import platform
import sys
from pathlib import Path
import stat
import subprocess

from admission import digest
from authority import require_active
from worker_window import remaining


def read_regular(path,owners,limit=1048576,mode=None):
    """Bounded nofollow walk; reject aliases, special files and writable outsiders."""
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('Absolute evidence path required')
    directory=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or
                    before.st_uid not in owners or before.st_mode&0o022 or
                    mode is not None and stat.S_IMODE(before.st_mode)!=mode):
                raise ValueError('Untrusted regular evidence file')
            data=stream.read(limit+1)
            after=os.fstat(stream.fileno())
            if (len(data)>limit or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=
                    (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
                raise ValueError('Evidence oversized or changed during read')
            return data
    finally:os.close(directory)


def interval(observation):
    values=observation['execution_interval']
    if (set(values)!={'start_wall_us','start_monotonic_us','end_wall_us','end_monotonic_us'} or
            any(type(v) is not int or v<=0 for v in values.values()) or
            values['end_wall_us']<values['start_wall_us'] or
            values['end_monotonic_us']<values['start_monotonic_us']):
        raise ValueError('Native execution interval unavailable or changed')
    epoch=datetime.datetime(1970,1,1,tzinfo=datetime.timezone.utc)
    return {name:(epoch+datetime.timedelta(microseconds=values[key])).isoformat()
            for name,key in [('startedAt','start_wall_us'),('finishedAt','end_wall_us')]}


class NativeResult:
    def __init__(self,store,journal,backend,gate):
        self.store,self.journal,self.backend,self.gate=store,journal,backend,gate
        self.key=journal.contract_digest

    def seal(self,prefix):
        """Caller holds credential lock; retain fence for future receipt publication."""
        require_active(self.store,self.key)
        if remaining(self.store,self.key)<=0:raise ValueError('Immutable result-sealing window expired')
        intent=self.store.read(prefix+'.intent.json');plan=intent['plan'];owned=intent['owned_plan']
        stream={'contract_digest':self.key,'prefix':prefix,'plan_digest':digest(plan)}
        if (plan['contract_digest']!=self.key or self.store.read('active-verifier.json')!=stream or
                intent['plan_digest']!=digest(plan) or
                prefix!=plan['source_owner']['unit']+'.verifier-'+str(plan['index']) or
                self.gate.store is not self.store or self.gate.contract_digest!=self.key or
                self.backend.store is not self.store or self.backend.key!=self.key):
            raise ValueError('Native result ownership changed')
        try:self.store.read('active-owner.json')
        except FileNotFoundError:pass
        else:raise ValueError('Model ownership conflicts with result sealing')
        for suffix in ('.cleanup-intent.json','.cleanup-complete.json'):
            try:self.store.read(prefix+suffix)
            except FileNotFoundError:pass
            else:raise ValueError('Cleaned verifier cannot publish result evidence')
        before=self.journal.read()
        if before[0]!=owned['journal_revision']:raise ValueError('Native result journal changed')
        if self.gate.verification_plan(owned['plan']['selection'])!=owned['plan']:
            raise ValueError('Native result bound inputs changed')
        observation=self.backend.adopt(plan)
        invocation=self.store.read(prefix+'.invocation.json')
        if invocation!={'plan_digest':digest(plan),'invocation_id':observation['invocation_id']}:
            raise ValueError('Native result invocation changed')
        native=observation['native']
        if (observation['plan_digest']!=digest(plan) or observation['exit_code']!=0 or observation['unit_result']!='success' or
                native['ownership_verified'] is not True or native['execution_finished'] is not True or
                native['cgroup_empty'] is not True):raise ValueError('Successful ended empty native result required')
        times=interval(observation)
        import pwd
        from private_launch import ACCOUNT
        account=pwd.getpwnam(ACCOUNT)
        if account.pw_uid==0:raise ValueError('Nonroot native result account required')
        def account_empty():
            process=subprocess.run(['/usr/bin/pgrep','-u',str(account.pw_uid)],capture_output=True,text=True,timeout=5)
            if process.returncode!=1 or process.stdout:raise ValueError('Native result account stream occupied')
        account_empty()
        artifacts=[]
        proof=plan['definition']['verifier']['proof'];base=Path(plan['definition']['base'])
        if not isinstance(proof['artifacts'],list) or not 1<=len(proof['artifacts'])<=128:
            raise ValueError('Bounded native result artifacts required')
        for artifact in proof['artifacts']:
            path=base/artifact['path']
            if not any(path.parent==Path(p) for p in plan['read_write_paths']):
                raise ValueError('Artifact outside declared writable output')
            data=read_regular(path,{0,account.pw_uid})
            artifacts.append({'path':str(path),'sha256':hashlib.sha256(data).hexdigest()})
        captures={}
        for name in ('stdout','stderr'):
            data=read_regular(self.store.root/(prefix+'.'+name),{self.store.owner_uid},mode=0o600)
            captures[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                            'text':data[:65536].decode('utf-8',errors='replace'),'truncated':len(data)>65536}
        if self.gate.verification_plan(owned['plan']['selection'])!=owned['plan'] or self.journal.read()!=before:
            raise ValueError('Native result inputs changed during sealing')
        fresh=self.backend.adopt(plan)
        if (fresh['invocation_id']!=observation['invocation_id'] or fresh['exit_code']!=0 or fresh['unit_result']!='success' or
                fresh['execution_interval']!=observation['execution_interval'] or
                not all(fresh['native'][k] is True for k in ('ownership_verified','execution_finished','cgroup_empty'))):
            raise ValueError('Native result ownership changed during sealing')
        account_empty()
        require_active(self.store,self.key)
        if remaining(self.store,self.key)<=0:raise ValueError('Immutable result-sealing window expired')
        result={'plan_digest':digest(plan),'owned_plan_digest':digest(owned),
                'invocation_id':observation['invocation_id'],'unit':plan['unit'],
                'execution_interval':observation['execution_interval'],**times,
                'argv':plan['argv'],'cwd':plan['cwd'],'verifier_id':plan['definition']['verifier']['id'],
                'identity':plan['definition']['identity'],'artifacts':artifacts,'captures':captures,
                'runtime':{'executable':str(Path(sys.executable).resolve()),'python':sys.version,
                           'platform':platform.platform(),'scope':'protected result observer'},
                'exitCode':0,'unit_result':'success','native_result_sealed':True,'checkpoint_published':False,'parent_accepted':False}
        try:self.store.create(prefix+'.result.json',result)
        except FileExistsError:
            if self.store.read(prefix+'.result.json')!=result:raise ValueError('Protected native result changed')
        if self.store.read(prefix+'.result.json')!=result:raise ValueError('Native result readback differs')
        return result

    def receipt_row(self,prefix):
        """Reauthenticate native evidence and prepare a row; no publication authority.

        Runtime describes the protected observer, as in the existing bound
        runner. Actual verifier invocation is retained separately as argv/cwd.
        """
        result=self.seal(prefix)
        binding,state,_=self.gate._read()
        owned=self.store.read(prefix+'.intent.json')['owned_plan']
        if (digest(owned)!=result['owned_plan_digest'] or
                self.gate.verification_plan(owned['plan']['selection'])!=owned['plan'] or
                digest(state)!=owned['plan']['checkpoint_sha256']):
            raise ValueError('Native receipt checkpoint changed after sealing')
        contract=self.gate.helper.contract_data(state['verificationContract']['path'])
        semantics=self.gate.helper.contract_semantics_sha256(contract)
        if state['verificationContract'].get('semanticsSha256')!=semantics:
            raise ValueError('Bound receipt contract semantics changed')
        if (not isinstance(semantics,str) or len(semantics)!=64 or
                any(c not in '0123456789abcdef' for c in semantics) or
                not isinstance(state.get('sessionId'),str) or not state['sessionId']):
            raise ValueError('Bound receipt contract/session required')
        row={key:result[key] for key in ('verifier_id','argv','cwd','identity','artifacts',
                                        'exitCode','startedAt','finishedAt','runtime')}
        row.update(proof_mode='bound',goal_id=state['sessionId'],contract_semantics=semantics,
                   status='passed',native_provenance={key:result[key] for key in
                   ('unit','invocation_id','plan_digest','owned_plan_digest','execution_interval','unit_result')},
                   sealed_result_sha256=digest(result),captures=result['captures'])
        if (self.gate._read()[:2]!=(binding,state) or
                self.gate.verification_plan(owned['plan']['selection'])!=owned['plan']):
            raise ValueError('Receipt binding changed during preparation')
        return row
