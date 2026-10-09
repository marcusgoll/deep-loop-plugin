"""Build no-model qualification commands from the exact reserved native plan.

This module neither produces qualification receipts nor starts any process.
"""
from admission import digest,initialize
from native_backend import permission_digest
from private_launch import DISABLED_FEATURES, ROOT


def qualification_plan(plan, contract, probe_script):
    key=digest(contract)
    if plan['contract_digest']!=key or plan['candidate']!=ROOT+'/candidate/'+key:
        raise ValueError('Exact candidate and contract required')
    executor=contract['executor']
    if set(executor)!={'path','sha256'} or not executor['path'].startswith('/'):
        raise ValueError('Pinned executor required')
    initialize(executor['sha256'])
    if probe_script!=plan['candidate']+'/.deep-loop-qualification.py':
        raise ValueError('Fixed disposable probe path required')
    command=plan['command']; overrides=[]; disabled=[]
    for index,value in enumerate(command[:-1]):
        if value=='-c':overrides += ['-c',command[index+1]]
        if value=='--disable':disabled.append(command[index+1])
    if tuple(disabled)!=DISABLED_FEATURES or '--ignore-user-config' not in command or '--ignore-rules' not in command or '--strict-config' not in command:
        raise ValueError('Native policy differs from fixed private lane')
    flags=[item for feature in disabled for item in ('--disable',feature)]
    return {'contract_digest':key,'candidate':plan['candidate'],'executor':executor,
            'permission_digest':permission_digest(plan),
            # sandbox/features rejects strict and lacks exec's ignore flags. The
            # producer must prove these conditions; argv alone is insufficient.
            'configuration_preconditions':['no_user_config','no_project_config',
                                          'no_managed_config','no_rules',
                                          'effective_configuration_validated'],
            'sandbox_command':[executor['path'],'--no-daemon','sandbox','-C',plan['candidate'],
                               '-P','deep_loop_private',*flags,*overrides,'--',
                               '/usr/bin/python3','-I',probe_script],
            'features_command':[executor['path'],'--no-daemon','features','list',*flags,*overrides],
            'strict_command':[executor['path'],'--no-daemon','app-server','--strict-config',
                              '--listen','stdio://',*flags,*overrides],
            'model_calls':0}
