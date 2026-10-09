"""Trusted no-model probe source and strict observation validation.

The private wrapper opens only a disposable sentinel, then invokes the exact
native sandbox command. These scripts never invoke exec/resume or a model.
"""
import json
import errno
from inspect import getsource


def parent_denial(error,isolated,known_target):
    return (known_target is True and type(error) is int and
            (error in (errno.EACCES,errno.EPERM) or
             (error==errno.ENOENT and isolated is True)))


PROBE = 'import errno,json,os,socket,sys\nfrom pathlib import Path\n'+getsource(parent_denial)+'''
private,escape,parent,descriptor,proof,outside_pid_namespace=sys.argv[1:]
isolated=os.readlink('/proc/self/ns/pid')!=outside_pid_namespace
Path(proof).write_text('qualified candidate write')
observations={};diagnostics={}
for name,path in [('private_direct_read_denied',private),('private_symlink_read_denied',escape),
                  ('host_parent_descriptor_read_denied',f'/proc/{parent}/fd/{descriptor}'),
                  ('host_parent_capture_read_denied',f'/proc/{parent}/fd/1'),
                  ('host_parent_memory_read_denied',f'/proc/{parent}/mem')]:
    try:
        with open(path,'rb'):pass
        observations[name]=False;diagnostics[name]='OPEN_ALLOWED'
    except OSError as exc:
        diagnostics[name]=exc.errno
        observations[name]=(parent_denial(exc.errno,isolated,True) if name.startswith('host_parent_')
                            else exc.errno in (errno.EACCES,errno.EPERM))
try:
    connection=socket.create_connection(('127.0.0.1',22),timeout=1)
    connection.close();observations['network_denied']=False
except OSError as exc:
    observations['network_denied']=exc.errno in (errno.EACCES,errno.EPERM)
observations['parent_pid_namespace_isolated']=isolated
observations['candidate_write']=Path(proof).read_text()=='qualified candidate write'
print(json.dumps(observations))
if not all(observations.values()):
    print(json.dumps(diagnostics),file=sys.stderr);sys.exit(1)
'''


def wrapper_source(sandbox_command,private,escape,proof):
    return '''import json,os,subprocess,sys
from pathlib import Path
private='''+repr(private)+'''
assert Path(private).read_text()=='disposable qualification sentinel'
fd=os.open(private,os.O_RDONLY)
# These targets must actually exist outside the sandbox; missing-file errors
# alone cannot prove isolation. Keep the parent and both descriptors alive.
os.fstat(fd);os.fstat(1);os.stat('/proc/self/mem')
outside_pid_namespace=os.readlink('/proc/self/ns/pid')
try:
    command='''+repr(sandbox_command)+'''
    command += [private,'''+repr(escape)+''',str(os.getpid()),str(fd),'''+repr(proof)+''',outside_pid_namespace]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,json.dumps({'stdout':result.stdout,'stderr':result.stderr})
    assert not result.stderr,'Unexpected sandbox diagnostic'
    observations=json.loads(result.stdout)
    os.fstat(fd);os.fstat(1);os.stat('/proc/self/mem')
    observations['parent_targets_verified']=True
    print(json.dumps({'observations':observations,'stdin':sys.stdin.read(),
                      'uid':os.getuid(),'cwd':os.getcwd(),'home':os.environ.get('HOME')}))
finally:os.close(fd)
'''

CHECKS = ('candidate_write','private_direct_read_denied','private_symlink_read_denied',
          'network_denied','host_parent_descriptor_read_denied','host_parent_capture_read_denied',
          'host_parent_memory_read_denied','parent_pid_namespace_isolated','parent_targets_verified')


def validate_output(raw,uid,candidate,home,stdin):
    if not isinstance(raw,str) or len(raw)>65536:
        raise ValueError('Missing or oversized qualification capture')
    output=json.loads(raw)
    if (set(output)!={'observations','stdin','uid','cwd','home'} or
            type(output['uid']) is not int or output['uid']!=uid or output['cwd']!=candidate or
            output['home']!=home or output['stdin']!=stdin or
            not isinstance(output['observations'],dict) or set(output['observations'])!=set(CHECKS) or
            any(value is not True for value in output['observations'].values())):
        raise ValueError('Incomplete or failed independent qualification observations')
    return output['observations']
