"""Private root supervisor entrypoint. Requires explicit protected enrollment.

An immutable boot-clock window bounds all wakeups. systemd independently bounds
this trusted process; native model units retain their own charged timeouts.
"""
import json
import os
from pathlib import Path
import pwd
import re
import subprocess

from admission import digest
from resume_verifier import ResumeVerifier
from git_journal import GitJournal
from native_backend import NativeBackend
from private_controller import PrivateController, TrustedStore
from private_launch import ACCOUNT, ROOT
from private_wakeup import tick
from worker_window import remaining
from trusted_delivery import TrustedDelivery
from github_transport import GitHubAPI, UncertainAPI
from delivery_artifact import DeliveryArtifact
from pinned_helper import BoundPinnedHelper
from workflow_gate import WorkflowGate
from native_verifier import NativeVerifier

TIMER = 'deep-loop-private-worker.timer'
WORKER_SECONDS = 60


def run(store, factory, *, window=remaining, delivery_factory=None):
    enabled = store.read('enabled-outcome.json')
    if set(enabled) != {'contract_digest'}:
        raise ValueError('Malformed approved worker selection')
    key = enabled['contract_digest']
    left = window(store,key)
    # A fixed 45-second native runtime plus startup/stop/inspection margins must
    # fit before even a reconciliation wakeup starts. No timer resets the window.
    if left <= WORKER_SECONDS:
        return 'stopped_execution_window'
    result=tick(store,factory,expected_contract_digest=key,active_window_remaining=left)
    if result=='ready_for_trusted_delivery' and delivery_factory is not None:
        try:return delivery_factory(key).step()
        except UncertainAPI:return 'wait_for_trusted_delivery'
    return result


def qualify_service():
    invocation = os.environ.get('INVOCATION_ID', '')
    if not re.fullmatch(r'[0-9a-f]{32}', invocation):
        raise ValueError('Worker must run in its trusted systemd service')
    actual = subprocess.run(['/usr/bin/systemctl','show','deep-loop-private-worker.service',
                             '--property=InvocationID','--value'],capture_output=True,text=True,
                            check=True,timeout=5).stdout.strip()
    if actual != invocation:
        raise ValueError('Worker native invocation mismatch')
    path='/org/freedesktop/systemd1/unit/deep_2dloop_2dprivate_2dworker_2eservice'
    for property_name,expected in [('RuntimeMaxUSec',45000000),('TimeoutStopUSec',5000000),
                                   ('TimeoutStartUSec',5000000)]:
        observed=subprocess.run(['/usr/bin/busctl','get-property','org.freedesktop.systemd1',path,
                                 'org.freedesktop.systemd1.Service',property_name],
                                capture_output=True,text=True,check=True,timeout=5).stdout.strip()
        if observed != 't '+str(expected):
            raise ValueError('Native worker timeout configuration drift')


def build_controller(store,key):
    """Production construction; helper authority is checked at proof use.

    Keep exact-owner reconciliation available when workflow helper files have
    become unavailable. The gate cannot select/accept work without those files.
    """
    approval=store.read(key+'.approval.json')
    if digest(approval['contract'])!=key:raise ValueError('Worker approval changed')
    control=store.root
    journal=GitJournal(control/'journal-work',str(control/'journal.git'),key)
    gate=WorkflowGate(store,key,BoundPinnedHelper(store,key))
    backend=NativeBackend(store,key,workflow_gate=gate)
    verifier=ResumeVerifier(Path(ROOT)/'candidate'/key,pwd.getpwnam(ACCOUNT).pw_uid,store,allow_runtime_guards=True)
    return PrivateController(store,journal,backend,verifier,workflow_gate=gate,native_verifier=NativeVerifier(store,key))


def main():
    if os.geteuid() != 0:
        raise ValueError('Private trusted root supervisor required')
    control = Path(ROOT)/'control'
    store = TrustedStore(control)
    def factory(key):
        return build_controller(store,key)
    def delivery_factory(key):
        journal=GitJournal(control/'journal-work',str(control/'journal.git'),key)
        reader=DeliveryArtifact(Path(ROOT)/'candidate'/key,pwd.getpwnam(ACCOUNT).pw_uid,store,allow_runtime_guards=True)
        return TrustedDelivery(store,journal,GitHubAPI(),reader)
    try:
        qualify_service()
        result = run(store,factory,delivery_factory=delivery_factory)
        print(json.dumps({'terminal':result}),flush=True)
    except Exception:
        # Faults require trusted inspection; recurring wakeups cannot conceal a
        # missing journal/ownership/window or keep retrying a failed adapter.
        subprocess.run(['/usr/bin/systemctl','stop',TIMER],check=True,timeout=5)
        raise
    if result not in {'submitted_once','wait_for_predecessor','finished_without_verified_progress',
                      'finished_with_verified_progress','wait_for_trusted_delivery',
                      'recovered_workflow_task_acceptance','recovered_workflow_task_credit',
                      'wait_for_native_verifier','prepared_native_verifier_publication',
                      'recovered_native_verifier_publication','recovered_native_verifier_cleanup'}:
        subprocess.run(['/usr/bin/systemctl','stop',TIMER],check=True,timeout=5)


if __name__ == '__main__':
    main()
