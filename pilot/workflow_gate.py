"""Protected graph/proof selection for a future enrolled workflow coordinator.

The caller supplies the trusted, pinned helper and holds the credential lock.
This module selects tasks; it neither enrolls a live outcome nor dispatches one.
Mutable task state stays in the existing checkpoint.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

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
