"""Explicit protected graph binding; no model, timer or live enrollment.

The trusted operator authenticates human authority outside this API. It binds
only an already-approved, empty schema-2 outcome and never upgrades a pilot.
"""
from pathlib import Path
import os
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


class WorkflowHelperEnrollment:
    """Bind an already-protected pinned snapshot without activating execution.

    Snapshot installation is separate. The operator authenticates the exact
    record digest and existing graph approval; this API grants no model/window.
    Exact retries recover publication faults while journal and binding stay put.
    """
    def __init__(self,store,journal):
        self.store,self.journal=store,journal

    def apply(self,record,*,expected_helper_digest,approval_ref):
        from pinned_helper import PinnedHelper
        key=self.journal.contract_digest
        initialize(expected_helper_digest)
        if (not isinstance(record,dict) or
                set(record)!={'contract_digest','binding_digest','approval_ref','helper'} or
                digest(record)!=expected_helper_digest or record['contract_digest']!=key or
                not isinstance(approval_ref,str) or not approval_ref.strip() or len(approval_ref)>4096 or
                record['approval_ref']!=approval_ref):
            raise ValueError('Exact authenticated helper enrollment required')
        with self.store.lock():
            type(self.store)(self.store.root,owner_uid=self.store.owner_uid)
            require_active(self.store,key)
            for name in ('active-owner.json','enabled-outcome.json'):
                try:self.store.read(name)
                except FileNotFoundError:pass
                else:raise ValueError('Helper enrollment requires inactive unowned workflow')
            revision,state=self.journal.read()
            if state!=initialize(key,workflow=True):
                raise ValueError('Empty explicitly enrolled workflow journal required')
            binding=self.store.read(key+'.workflow.json')
            binding_intent=self.store.read(key+'.workflow-binding-intent.json')
            binding_complete=self.store.read(key+'.workflow-binding-complete.json')
            if (record['binding_digest']!=digest(binding) or binding.get('approval_ref')!=approval_ref or
                    set(binding_intent)!={'contract_digest','binding_digest','approval_ref','journal_revision','checkpoint_sha256'} or
                    binding_complete!={**binding_intent,'activated':False} or
                    binding_intent['contract_digest']!=key or binding_intent['binding_digest']!=digest(binding) or
                    binding_intent['approval_ref']!=approval_ref or binding_intent['journal_revision']!=revision):
                raise ValueError('Completed workflow binding required for helper enrollment')
            helper=PinnedHelper(record['helper'],owner_uid=self.store.owner_uid)
            def protected_checkpoint():
                path=Path(binding['checkpoint_path'])
                if path.parent!=self.store.root or path.resolve()!=path:
                    raise ValueError('Checkpoint must reside in protected controller store')
                fd=self.store._open(path.name,os.O_RDONLY);os.close(fd)
                return WorkflowGate(self.store,key,helper).validate_binding(binding)[1]
            checkpoint=protected_checkpoint()
            if digest(checkpoint)!=binding_intent['checkpoint_sha256']:
                raise ValueError('Enrollment checkpoint changed')
            intent={'contract_digest':key,'helper_digest':expected_helper_digest,
                    'binding_digest':digest(binding),'approval_ref':approval_ref,'journal_revision':revision}
            def publish_exact(name,value):
                try:self.store.create(name,value)
                except FileExistsError:
                    if self.store.read(name)!=value:raise ValueError('Partial helper enrollment identity changed')
                if self.store.read(name)!=value:raise ValueError('Helper enrollment readback differs')
            publish_exact(key+'.workflow-helper-intent.json',intent)
            publish_exact(key+'.workflow-helper.json',record)
            require_active(self.store,key)
            helper._verify()
            if (self.journal.read()!=(revision,state) or self.store.read(key+'.workflow.json')!=binding or
                    protected_checkpoint()!=checkpoint):
                raise ValueError('Helper enrollment source or journal changed')
            completed={**intent,'activated':False}
            publish_exact(key+'.workflow-helper-complete.json',completed)
            return completed
