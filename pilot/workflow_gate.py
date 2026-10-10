"""Protected graph/proof selection for a future enrolled workflow coordinator.

The caller supplies the trusted, pinned helper and holds the credential lock.
This module selects tasks; it neither enrolls a live outcome nor dispatches one.
Mutable task state stays in the existing checkpoint.
"""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import stat
import uuid

from admission import digest
from authority import require_active

STATIC_FIELDS = ('id', 'title', 'acceptance', 'kind', 'stage', 'dependsOn')


def graph_identity(tasks):
    return [{field: task.get(field, [] if field == 'dependsOn' else
             'review' if field == 'stage' else None) for field in STATIC_FIELDS}
            for task in tasks]


def checkpoint_bytes(path):
    """Walk from the filesystem root without following mutable links."""
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Regular checkpoint file required')
            payload = stream.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError('Checkpoint exceeds bounded reader limit')
        return payload
    finally:
        os.close(directory)


class WorkflowGate:
    def __init__(self, store, contract_digest, helper):
        self.store, self.contract_digest, self.helper = store, contract_digest, helper

    def _read(self):
        require_active(self.store, self.contract_digest)
        binding = self.store.read(self.contract_digest + '.workflow.json')
        try:
            intent = self.store.read(self.contract_digest + '.workflow-binding-intent.json')
        except FileNotFoundError:
            intent = None
        if intent is not None:
            completed = self.store.read(self.contract_digest + '.workflow-binding-complete.json')
            if (completed != {**intent, 'activated':False} or
                    intent.get('contract_digest') != self.contract_digest or
                    intent.get('binding_digest') != digest(binding) or
                    intent.get('approval_ref') != binding.get('approval_ref')):
                raise ValueError('Workflow binding completion identity drift')
        return self.validate_binding(binding)

    def validate_binding(self, binding):
        """Inspect a proposed binding before its protected publication."""
        if (not isinstance(binding, dict) or set(binding) != {
                'contract_digest', 'approval_ref', 'checkpoint_path', 'session_id',
                'verification_contract', 'graph', 'task_verifiers', 'task_prompts', 'boundary'} or
                binding['contract_digest'] != self.contract_digest or
                not isinstance(binding['session_id'], str) or not binding['session_id'].strip() or
                not isinstance(binding['approval_ref'], str) or not binding['approval_ref'].strip() or
                binding['boundary'] != 'integrated_candidate'):
            raise ValueError('Unsupported protected workflow binding')
        approval = self.store.read(self.contract_digest + '.approval.json')
        if (set(approval) != {'contract', 'approval_ref'} or
                not isinstance(approval['approval_ref'], str) or not approval['approval_ref'].strip() or
                digest(approval['contract']) != self.contract_digest):
            raise ValueError('Parent approval drift')
        path = Path(binding['checkpoint_path'])
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError('Canonical checkpoint path required')
        payload = checkpoint_bytes(path)
        state = json.loads(payload)
        if (state.get('sessionId') != binding['session_id'] or
                state.get('verificationContract') != binding['verification_contract']):
            raise ValueError('Checkpoint parent identity drift')
        tasks, by_id = self.helper.task_records(state)
        if not tasks or graph_identity(tasks) != binding['graph']:
            raise ValueError('Approved task graph drift')
        mapping = binding['task_verifiers']
        if (not isinstance(mapping, dict) or set(mapping) != set(by_id) or
                any(not isinstance(ids, list) or not ids or
                    any(not isinstance(i, str) or not i for i in ids) or
                    len(ids) != len(set(ids)) for ids in mapping.values())):
            raise ValueError('Complete approved task verifier mapping required')
        prompts = binding['task_prompts']
        if (not isinstance(prompts, dict) or set(prompts) != set(by_id) or
                any(not isinstance(prompt, str) or not prompt.strip() or
                    len(prompt.encode('utf-8')) > 65536 for prompt in prompts.values())):
            raise ValueError('Complete bounded approved task prompts required')
        failures = self.helper.contract_definition_issues(state)
        if failures:
            raise ValueError('Parent contract definitions blocked: ' + '; '.join(failures))
        contract = self.helper.contract_data(Path(binding['verification_contract']['path']), verify_files=False)
        blocking = {v['id'] for v in contract['verifiers'] if v['gate'] == 'blocking'}
        mapped = {i for ids in mapping.values() for i in ids}
        if mapped != blocking:
            raise ValueError('Task mapping must cover every parent blocking verifier exactly by ID')
        return binding, state, by_id

    def verification_plan(self,selection):
        """Read selected bound inputs; no command execution or acceptance.

        The controller authenticates the stopped owned attempt before use. An
        executor must run the returned argv without root candidate privileges.
        """
        binding,state,_=self._read()
        current=self.selection()
        if (not isinstance(selection,dict) or set(selection)!={
                'task_id','binding_digest','session_id','prompt_sha256'} or
                selection['task_id'] not in current['ready'] or
                selection['binding_digest']!=current['binding_digest'] or
                selection['session_id']!=current['session_id'] or
                selection['prompt_sha256']!=current['prompt_sha256'][selection['task_id']]):
            raise ValueError('Verification task selection changed')
        ids=sorted(binding['task_verifiers'][selection['task_id']])
        definitions=self.helper.verification_definitions(state,ids)
        if self._read()[:2]!=(binding,state):
            raise ValueError('Verification checkpoint changed during inspection')
        return {'contract_digest':self.contract_digest,'selection':dict(selection),
                'checkpoint_sha256':digest(state),'verifier_ids':ids,'definitions':definitions,
                'execution_authorized':False,'parent_accepted':False}

    def outcome_proof(self):
        """Inspect all current integrated proof; never accept or deliver a parent.

        Task status/evidence here is input for the controller's historical
        ownership and credit authentication, not proof of durable acceptance.
        """
        binding,state,by_id=self._read()
        if any(task['status']!='done' for task in by_id.values()):
            raise ValueError('Workflow outcome has unfinished tasks')
        ids=sorted({identifier for mapped in binding['task_verifiers'].values()
                    for identifier in mapped})
        failures=self.helper.prerequisite_issues(state,ids)
        if failures:raise ValueError('Workflow outcome proof blocked: '+'; '.join(failures))
        tasks={}
        for task_id in sorted(by_id):
            selection={'task_id':task_id,'binding_digest':digest(binding),
                       'session_id':state['sessionId'],
                       'prompt_sha256':hashlib.sha256(binding['task_prompts'][task_id].encode()).hexdigest()}
            observation=self.task_acceptance(selection)
            if observation['checkpoint_sha256']!=digest(state):
                raise ValueError('Workflow outcome changed during task inspection')
            tasks[task_id]={'evidence':by_id[task_id].get('evidence'),
                            'observation':observation}
        if self._read()[:2]!=(binding,state):
            raise ValueError('Workflow outcome checkpoint changed during inspection')
        checks={c.get('verifierId'):c for c in state.get('checks',[])}
        return {'kind':'workflow_outcome_proof','contract_digest':self.contract_digest,
                'binding_digest':digest(binding),'session_id':state['sessionId'],
                'checkpoint_sha256':digest(state),'verifier_ids':ids,
                'proof_receipts':{i:checks[i]['receipt'] for i in ids},'tasks':tasks,
                'parent_accepted':False,'delivery_verified':False}

    def task_acceptance(self, selection):
        """Inspect selected task proof; never mutate checkpoint or accept parent.

        The controller must retain this observation only for its authenticated,
        stopped owned attempt. A task status or successful model exit is not proof.
        Checkpoint identity is provenance, never semantic progress identity.
        """
        binding, state, by_id = self._read()
        if (not isinstance(selection, dict) or set(selection) != {
                'task_id', 'binding_digest', 'session_id', 'prompt_sha256'} or
                selection['binding_digest'] != digest(binding) or
                selection['session_id'] != state['sessionId'] or
                selection['task_id'] not in by_id):
            raise ValueError('Task acceptance selection identity drift')
        task_id = selection['task_id']
        if by_id[task_id]['status'] not in ('pending', 'running', 'done'):
            raise ValueError('Task acceptance cancelled or blocked')
        if selection['prompt_sha256'] != hashlib.sha256(
                binding['task_prompts'][task_id].encode()).hexdigest():
            raise ValueError('Task acceptance prompt identity drift')
        ancestors = set()
        def visit(identifier):
            for parent in by_id[identifier].get('dependsOn', []):
                if parent not in ancestors:
                    ancestors.add(parent)
                    visit(parent)
        visit(task_id)
        if any(by_id[i]['status'] != 'done' for i in ancestors):
            raise ValueError('Task acceptance has unfinished prerequisites')
        ids = sorted({v for i in ancestors | {task_id}
                      for v in binding['task_verifiers'][i]})
        failures = self.helper.prerequisite_issues(state, ids)
        if failures:
            raise ValueError('Task acceptance proof blocked: ' + '; '.join(failures))
        # Re-read through the same protected identities after proof inspection.
        # Concurrent checkpoint changes invalidate this observation.
        again = self._read()
        if again[0] != binding or again[1] != state:
            raise ValueError('Task acceptance checkpoint changed during inspection')
        checks = {c.get('verifierId'): c for c in state.get('checks', [])}
        return {'contract_digest': self.contract_digest, 'kind': 'workflow_task_proof',
                'selection': dict(selection), 'verifier_ids': ids,
                'proof_receipts': {i: checks[i]['receipt'] for i in ids},
                'checkpoint_sha256': digest(state), 'parent_accepted': False}

    def accepted_state(self, selection, evidence):
        """Prepare helper-owned transition after protected current proof checks.

        No filesystem write occurs. The coordinator must compare the exact
        preimage again under its publication lock and read back the saved state.
        """
        observation = self.task_acceptance(selection)
        _, state, _ = self._read()
        if digest(state) != observation['checkpoint_sha256']:
            raise ValueError('Task acceptance checkpoint changed before transition')
        result = self.helper.accepted_task_state(state, selection['task_id'],
                    observation['verifier_ids'], evidence, observation['checkpoint_sha256'])
        return {'before': state, 'after': result, 'observation': observation}

    def verified_state(self,verifier_id,receipt,evidence):
        binding,state,_=self._read()
        after=self.helper.verified_check_state(state,verifier_id,receipt,evidence,digest(state))
        if self._read()[:2]!=(binding,state):raise ValueError('Verification checkpoint changed before transition')
        return {'before':state,'after':after,'observation':{'kind':'native_verification_check',
                'binding_digest':digest(binding),'verifier_id':verifier_id,'receipt':receipt,
                'evidence':evidence,'parent_accepted':False}}

    def _checked_verification_transition(self,transition):
        observation=transition['observation']
        if observation.get('kind')!='native_verification_check' or observation.get('parent_accepted') is not False:
            raise ValueError('Verification check transition required')
        binding,_,_=self._read()
        if observation['binding_digest']!=digest(binding):raise ValueError('Verification binding changed')
        return self.verified_state(observation['verifier_id'],observation['receipt'],observation['evidence'])

    def _checked_acceptance_transition(self,transition):
        observation=transition['observation'];task_id=observation['selection']['task_id']
        evidence=next(t['evidence'] for t in transition['after']['tasks'] if t['id']==task_id)
        return self.accepted_state(observation['selection'],evidence)

    def publish_verified_state(self,transition,before_write=None):
        return self._publish_checkpoint(transition,self._checked_verification_transition,
            lambda:self.helper.prerequisite_issues(self._read()[1],[transition['observation']['verifier_id']]),before_write)

    def publish_accepted_state(self,transition,before_write=None):
        return self._publish_checkpoint(transition,self._checked_acceptance_transition,
            lambda:self.task_acceptance(transition['observation']['selection']),before_write)

    def _publish_checkpoint(self, transition,check_transition,postcheck,before_write=None):
        """Publish exactly a proof-checked transition in a protected checkpoint.

        Caller holds the credential lock and has persisted its owned-attempt
        acceptance intent. This local lock fences participating checkpoint
        writers; uncoordinated external edits remain a deployment restriction.
        """
        binding, _, _ = self._read()
        path = Path(binding['checkpoint_path'])
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        lock = '.deep-task-acceptance.lock'
        temporary = '.deep-task-acceptance-' + uuid.uuid4().hex + '.tmp'
        lock_fd = None
        try:
            for component in path.parts[1:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                os.close(directory); directory = child
            info = os.fstat(directory)
            if info.st_uid != self.store.owner_uid or info.st_mode & 0o022:
                raise ValueError('Protected checkpoint directory required')
            lock_fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                              0o600, dir_fd=directory)
            info = os.fstat(lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.store.owner_uid or
                    info.st_mode & 0o022 or info.st_nlink != 1):
                raise ValueError('Protected checkpoint lock required')
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.store.owner_uid or
                        info.st_mode & 0o022):
                    raise ValueError('Protected checkpoint file required')
                payload = stream.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError('Checkpoint exceeds bounded writer limit')
            current = json.loads(payload)
            if current not in (transition['before'], transition['after']):
                raise ValueError('Stale task acceptance checkpoint preimage')
            checked = check_transition(transition)
            if checked['before'] != current or checked['after'] != transition['after']:
                raise ValueError('Task acceptance transition or proof changed')
            if current != transition['after']:
                encoded = (json.dumps(transition['after'], indent=2) + '\n').encode()
                if len(encoded) > 1024 * 1024:
                    raise ValueError('Accepted checkpoint exceeds bounded writer limit')
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
                # Recheck immediately before replacement; participating writers
                # must use this same lock, and candidates cannot write this tree.
                if checkpoint_bytes(path) != payload:
                    raise ValueError('Checkpoint changed before acceptance publication')
                if before_write is not None:before_write()
                os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            if before_write is not None:before_write()
            os.fsync(directory)
            saved = json.loads(checkpoint_bytes(path))
            if saved != transition['after']:
                raise ValueError('Accepted checkpoint independent readback differs')
            proof=postcheck()
            if isinstance(proof,list) and proof:raise ValueError('Published checkpoint proof changed')
            return saved
        finally:
            try: os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError: pass
            if lock_fd is not None: os.close(lock_fd)
            os.close(directory)

    def selection(self):
        binding, state, by_id = self._read()
        queue = self.helper.task_queue(state)
        ready, blocked = [], {r['task']['id']: r['reasons'] for r in queue['waiting']}
        for task in queue['ready']:
            ancestors = set()
            def visit(identifier):
                for parent in by_id[identifier].get('dependsOn', []):
                    if parent not in ancestors:
                        ancestors.add(parent)
                        visit(parent)
            visit(task['id'])
            ids = sorted({v for ancestor in ancestors for v in binding['task_verifiers'][ancestor]})
            failures = self.helper.prerequisite_issues(state, ids) if ids else []
            if failures:
                blocked[task['id']] = failures
            else:
                ready.append(task['id'])
        return {'binding_digest': digest(binding), 'session_id': state['sessionId'],
                'ready': ready, 'blocked': blocked,
                'prompt_sha256': {i: hashlib.sha256(binding['task_prompts'][i].encode()).hexdigest() for i in ready}}


def task_progress_identity(observation):
    """One progress credit per approved task, independent of receipt reruns.

    Only call after current proof and stopped-attempt ownership validation.
    Receipt/checkpoint/invocation changes are provenance, not new task progress.
    This identity neither accepts the checkpoint nor the parent.
    """
    if (not isinstance(observation, dict) or observation.get('kind') != 'workflow_task_proof' or
            observation.get('parent_accepted') is not False):
        raise ValueError('Task proof observation required')
    selection = observation.get('selection')
    if (not isinstance(selection, dict) or set(selection) != {
            'task_id', 'binding_digest', 'session_id', 'prompt_sha256'} or
            any(not isinstance(value, str) or not value for value in selection.values()) or
            not isinstance(observation.get('contract_digest'), str)):
        raise ValueError('Task progress identity required')
    return digest({'contract_digest': observation['contract_digest'],
                   'kind': 'approved_workflow_task', 'selection': selection})


def native_prompt(store, key, owner, contract):
    """Read exact approved task instructions from private authority, not argv."""
    try:
        binding = store.read(key + '.workflow.json')
    except FileNotFoundError:
        try:
            store.read(owner['unit'] + '.workflow-attempt.json')
        except FileNotFoundError:
            return contract['prompt']
        raise ValueError('Workflow native attempt lost its binding')
    receipt = store.read(owner['unit'] + '.workflow-attempt.json')
    selection = receipt['selection']
    if (set(receipt) != {'owner', 'selection'} or receipt['owner'] != owner or
            selection['binding_digest'] != digest(binding) or
            binding['contract_digest'] != key or selection['session_id'] != binding['session_id']):
        raise ValueError('Native workflow selection identity drift')
    prompt = binding['task_prompts'][selection['task_id']]
    if hashlib.sha256(prompt.encode()).hexdigest() != selection['prompt_sha256']:
        raise ValueError('Native task instructions changed')
    return contract['prompt'] + '\n\nApproved task instructions:\n' + prompt
