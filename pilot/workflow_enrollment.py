"""Explicit protected graph binding; no model, timer or live enrollment.

The trusted operator authenticates human authority outside this API. It binds
only an already-approved, empty schema-2 outcome and never upgrades a pilot.
"""
from pathlib import Path
import stat

from admission import digest, initialize
from authority import require_active
from workflow_gate import WorkflowGate


class WorkflowBindingEnrollment:
    def __init__(self, store, journal, helper):
        self.store, self.journal, self.helper = store, journal, helper

    def apply(self, binding, *, expected_binding_digest, approval_ref):
        key = self.journal.contract_digest
        initialize(expected_binding_digest)
        if (digest(binding) != expected_binding_digest or
                not isinstance(approval_ref,str) or not approval_ref.strip() or
                len(approval_ref)>4096 or binding.get('approval_ref') != approval_ref):
            raise ValueError('Exact authenticated workflow binding approval required')
        with self.store.lock():
            require_active(self.store,key)
            for name in ('active-owner.json','enabled-outcome.json',key+'.workflow.json',
                         key+'.workflow-binding-intent.json',key+'.workflow-binding-complete.json'):
                try:self.store.read(name)
                except FileNotFoundError:pass
                else:raise ValueError('Existing or partial workflow binding requires inspection')
            revision,state = self.journal.read()
            if state != initialize(key,workflow=True):
                raise ValueError('Empty explicitly enrolled workflow journal required')
            type(self.store)(self.store.root,owner_uid=self.store.owner_uid)
            if Path(binding['checkpoint_path']).parent != self.store.root:
                raise ValueError('Checkpoint must reside in protected controller store')
            gate = WorkflowGate(self.store,key,self.helper)
            _,checkpoint,_ = gate.validate_binding(binding)
            path = Path(binding['checkpoint_path'])
            # Graph status is private host authority. The candidate must not be
            # able to replace this directory, checkpoint or its proof records.
            for target in (path.parent,path):
                info=target.lstat()
                if (target.resolve()!=target or info.st_uid!=self.store.owner_uid or
                        info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode) or
                        target==path and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1) or
                        target==path.parent and (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700)):
                    raise ValueError('Protected private checkpoint required')
            if self.journal.read() != (revision,state):
                raise ValueError('Workflow journal changed before binding')
            require_active(self.store,key)
            intent={'contract_digest':key,'binding_digest':expected_binding_digest,
                    'approval_ref':approval_ref,'journal_revision':revision,
                    'checkpoint_sha256':digest(checkpoint)}
            self.store.create(key+'.workflow-binding-intent.json',intent)
            self.store.create(key+'.workflow.json',binding)
            if (self.store.read(key+'.workflow.json') != binding or
                    gate.validate_binding(binding)[1] != checkpoint or self.journal.read() != (revision,state)):
                raise ValueError('Workflow binding independent readback differs')
            completed={**intent,'activated':False}
            self.store.create(key+'.workflow-binding-complete.json',completed)
            if self.store.read(key+'.workflow-binding-complete.json') != completed:
                raise ValueError('Workflow binding completion readback differs')
            return completed
