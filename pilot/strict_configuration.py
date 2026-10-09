"""No-client strict native configuration validation with a negative control."""
import os
import re
import subprocess
import time
from native_session import MAX_CAPTURE_BYTES
from systemd_observer import observe_unit

UNKNOWN='deep_loop_deliberately_unknown_config_field'


def validate_strict(store,plan,commands,unit_prefix,raw):
    records=[]
    for number,phase in enumerate(('positive','unknown_override'),1):
        unit=unit_prefix+'-'+str(number)
        prompt=raw(store,unit+'.prompt',b'')
        output=raw(store,unit+'.jsonl',b'')
        errors=raw(store,unit+'.stderr',b'')
        properties=dict(plan['properties'],RuntimeMaxSec=5,TimeoutStartSec=5,TimeoutStopSec=2,
                        Slice='system.slice',LimitCORE=0,LimitFSIZE=MAX_CAPTURE_BYTES,
                        PrivateNetwork='yes',IPAddressDeny='any',RestrictAddressFamilies='AF_UNIX',
                        StandardInput='file:'+str(prompt),StandardOutput='append:'+str(output),
                        StandardError='append:'+str(errors))
        command=list(commands['strict_command'])
        if phase=='unknown_override':command+=['-c',UNKNOWN+'=true']
        args=['/usr/bin/systemd-run','--unit='+unit,'--service-type=exec']
        args+=['--property='+name+'='+str(value) for name,value in properties.items()]
        subprocess.run(args+command,capture_output=True,text=True,check=True,timeout=5)
        invocation=subprocess.run(['/usr/bin/systemctl','show',unit+'.service','--property=InvocationID','--value'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        deadline=time.monotonic()+12
        while True:
            try:observation=observe_unit(unit,invocation)
            except ValueError as exc:
                if str(exc)!='Missing kernel population evidence':raise
                observation=None
            if observation and observation['execution_finished']:break
            if time.monotonic()>=deadline:raise ValueError('Strict probe observation expired; inspect same unit')
            time.sleep(.1)
        values=subprocess.run(['/usr/bin/systemctl','show',unit+'.service','--property=InvocationID,ExecMainStatus,PrivateNetwork,RestrictAddressFamilies'],capture_output=True,text=True,check=True,timeout=5)
        native=dict(line.split('=',1) for line in values.stdout.splitlines())
        if (set(native)!={'InvocationID','ExecMainStatus','PrivateNetwork','RestrictAddressFamilies'} or
                native['InvocationID']!=invocation or native['PrivateNetwork']!='yes' or
                native['RestrictAddressFamilies'].split()!=['AF_UNIX']):
            raise ValueError('Strict probe native identity changed')
        captures={}
        for suffix in ('jsonl','stderr'):
            fd=store._open(unit+'.'+suffix,os.O_RDONLY)
            with os.fdopen(fd,'rb') as stream:data=stream.read(65537)
            if len(data)>65536:raise ValueError('Strict probe diagnostic exceeds bound')
            captures[suffix]=data.decode()
        diagnostic=validate_result(phase,native['ExecMainStatus'],captures['jsonl'],captures['stderr'])
        record={'phase':phase,'native':observation,'status':native['ExecMainStatus'],
                'stdin_bytes':0,'stdout_bytes':len(captures['jsonl'].encode()),
                'stderr_bytes':len(captures['stderr'].encode()),'network_denied_externally':True,
                'diagnostic_class':diagnostic}
        store.create(unit+'.strict-observation.json',record)
        subprocess.run(['/usr/bin/systemctl','stop',unit+'.service'],capture_output=True,text=True,check=True,timeout=5)
        records.append(record)
    return records


def catalog_refresh_cancelled(stderr):
    """Recognize only the pinned native startup cancellation seen on the host.

    No client messages or model turns are sent by this strict probe; network is
    separately denied. Preserve raw stderr and classify this one metadata-task
    cancellation. Additional lines or other errors remain qualification failures.
    """
    plain=re.sub(r'\x1b\[[0-9;]*m','',stderr)
    return re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z '
        r'ERROR codex_models_manager::manager: failed to refresh available models: '
        r'task [1-9][0-9]* was cancelled\n?',plain) is not None


def validate_result(phase,status,stdout,stderr):
    if stdout:raise ValueError('Unexpected strict parser output')
    if phase=='positive':
        if status!='0' or (stderr and not catalog_refresh_cancelled(stderr)):
            raise ValueError('Strict positive control failed')
        return 'catalog_refresh_cancelled' if stderr else 'clean'
    elif phase=='unknown_override':
        if status!='1' or UNKNOWN not in stderr or not re.search(r'\b(?:unknown|unrecognized)\b',stderr.lower()):
            raise ValueError('Strict negative control did not reject unknown field')
        return 'unknown_override_rejected'
    else:raise ValueError('Unknown strict parser phase')
