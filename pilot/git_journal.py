"""Append-only Git journal adapter; no model, task state or workflow dispatch.

Use only in a trusted host workspace with a dedicated remote. Repository access
and protected journal refs are caller obligations. Never expose this adapter or
its credentials to the candidate/model. Network uncertainty raises; no retry.
"""

import copy
import hashlib
import json
import os
import selectors
import subprocess
import time
import uuid

from admission import LIMITS, _validate, credit_task, finish, initialize, reserve


class GitJournal:
    def __init__(self, workspace, remote, contract_digest):
        initialize(contract_digest)
        self.workspace = str(workspace)
        self.remote = remote
        self.contract_digest = contract_digest
        self.ref = "refs/heads/deep-loop-journal/" + contract_digest

    def _git(self, *args, data=None):
        environment = dict(os.environ, GIT_AUTHOR_NAME="Deep Loop pilot",
                           GIT_AUTHOR_EMAIL="pilot@localhost",
                           GIT_COMMITTER_NAME="Deep Loop pilot",
                           GIT_COMMITTER_EMAIL="pilot@localhost")
        return subprocess.run(["git", "-C", self.workspace, *args], input=data,
                              capture_output=True, text=True, check=True,
                              env=environment, timeout=30).stdout.strip()

    def read(self):
        """Missing journal or failed fetch blocks; never initialize on read."""
        self._git("fetch", "--no-tags", "--", self.remote, self.ref)
        revision = self._git("rev-parse", "FETCH_HEAD")
        state = json.loads(self._git("show", revision + ":journal.json"))
        _validate(state, self.contract_digest)
        return revision, state

    def _git_bytes(self, *args, data):
        """Bound binary batch output while draining both pipes and reaping Git."""
        command = ['git', '-C', self.workspace, *args]
        limit = (LIMITS['attempts']+1)*(1048576+100)
        output, error = bytearray(), bytearray()
        deadline = time.monotonic()+30
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as process:
            try:
                process.stdin.write(data)
                process.stdin.close()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, (output, limit))
                    selector.register(process.stderr, selectors.EVENT_READ, (error, 65536))
                    while selector.get_map():
                        remaining = deadline-time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(command, 30)
                        for key, _ in selector.select(remaining):
                            target, maximum = key.data
                            chunk = os.read(key.fileobj.fileno(), min(65536, maximum-len(target)+1))
                            if not chunk:
                                selector.unregister(key.fileobj)
                            else:
                                target.extend(chunk)
                                if len(target) > maximum:
                                    raise ValueError('Journal batch transport output exceeds bound')
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 30)
                process.wait(timeout=remaining)
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command,
                                                        bytes(output), bytes(error))
                return bytes(output)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()

    @staticmethod
    def _decode_blobs(raw, count, *, object_width=None):
        """Decode exact ordered Git blob frames without stripping payload bytes."""
        if type(count) is not int or not 1 <= count <= LIMITS['attempts']+1:
            raise ValueError('Bounded journal blob group required')
        if not isinstance(raw, bytes) or len(raw) > count*(1048576+100):
            raise ValueError('Journal blob bytes exceed bound')
        if object_width not in (None, 40, 64):
            raise ValueError('Canonical journal object format required')
        offset, blobs, width = 0, [], object_width
        for _ in range(count):
            end = raw.find(b'\n', offset, offset+101)
            if end < 0:
                raise ValueError('Journal blob header missing')
            fields = raw[offset:end].split(b' ')
            if (len(fields) != 3 or len(fields[0]) not in (40, 64) or
                    any(c not in b'0123456789abcdef' for c in fields[0]) or
                    fields[1] != b'blob' or not fields[2].isdigit() or
                    fields[2].startswith(b'0')):
                raise ValueError('Canonical journal blob header required')
            if width is not None and width != len(fields[0]):
                raise ValueError('Journal blob object formats differ')
            width = len(fields[0])
            size = int(fields[2])
            if not 1 <= size <= 1048576:
                raise ValueError('Journal blob size exceeds bound')
            start = end+1
            body = raw[start:start+size]
            if len(body) != size or raw[start+size:start+size+1] != b'\n':
                raise ValueError('Journal blob frame truncated')
            algorithm = 'sha1' if width == 40 else 'sha256'
            actual = hashlib.new(algorithm, b'blob '+fields[2]+b'\0'+body).hexdigest().encode()
            if actual != fields[0]:
                raise ValueError('Journal blob digest differs')
            blobs.append(body)
            offset = start+size+1
        if offset != len(raw):
            raise ValueError('Journal blob trailing data')
        return blobs

    def verify_history(self, revision, expected):
        """Authenticate a saved revision and its retained append-only history."""
        if (not isinstance(revision,str) or len(revision) not in (40,64) or
                any(c not in '0123456789abcdef' for c in revision)):
            raise ValueError('Canonical journal commit revision required')
        current, state = self.read()
        saved = json.loads(self._git('show', revision + ':journal.json'))
        _validate(saved, self.contract_digest)
        if saved != expected:
            raise ValueError('Journal historical revision differs')
        self._git('merge-base', '--is-ancestor', revision, current)
        if (state['schema'] != saved['schema'] or
                state['attempts'][:len(saved['attempts'])] != saved['attempts'] or
                state.get('task_credits', [])[:len(saved.get('task_credits', []))] != saved.get('task_credits', [])):
            raise ValueError('Journal credited history missing or rewritten')
        return current, state

    def verify_histories(self, histories):
        """Authenticate this guard's credits between two fresh remote reads.

        No cut survives this call. Every saved state and ancestor is checked;
        remote advancement during the inspection rejects the entire group.
        """
        if (not isinstance(histories, (list, tuple)) or
                not 1 <= len(histories) <= LIMITS['attempts']):
            raise ValueError('Bounded journal history group required')
        selected = copy.deepcopy(histories)
        for row in selected:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise ValueError('Journal revision and exact state required')
            revision, expected = row
            if (not isinstance(revision, str) or len(revision) not in (40, 64) or
                    any(c not in '0123456789abcdef' for c in revision)):
                raise ValueError('Canonical journal commit revision required')
            _validate(expected, self.contract_digest)
        self._git('fetch', '--no-tags', '--', self.remote, self.ref)
        current = self._git('rev-parse', 'FETCH_HEAD')
        if (len(current) not in (40, 64) or
                any(c not in '0123456789abcdef' for c in current)):
            raise ValueError('Canonical current journal revision required')
        expressions = [current+':journal.json']+[r+':journal.json' for r, _ in selected]
        blobs = self._decode_blobs(self._git_bytes('cat-file', '--batch',
            data=('\n'.join(expressions)+'\n').encode()), len(expressions),
            object_width=len(current))
        state = json.loads(blobs[0].decode('utf-8'))
        _validate(state, self.contract_digest)
        for (revision, expected), blob in zip(selected, blobs[1:]):
            saved = json.loads(blob.decode('utf-8'))
            _validate(saved, self.contract_digest)
            if saved != expected:
                raise ValueError('Journal historical revision differs')
            self._git('merge-base', '--is-ancestor', revision, current)
            if (state['schema'] != saved['schema'] or
                    state['attempts'][:len(saved['attempts'])] != saved['attempts'] or
                    state.get('task_credits', [])[:len(saved.get('task_credits', []))] != saved.get('task_credits', [])):
                raise ValueError('Journal credited history missing or rewritten')
        if self.read() != (current, state):
            raise ValueError('Journal changed during batch history inspection')
        return current, state

    def publish(self, expected_revision, state, *, before_publish=None):
        """Append after exact revision, then verify provider-visible readback.

        A competing sibling commit cannot fast-forward the remote. A failed push
        or uncertain readback blocks launch even if the journal changed remotely.
        Passing None is explicit first enrollment, never a recovery operation.
        """
        _validate(state, self.contract_digest)
        if expected_revision is None:
            # An orphan commit cannot fast-forward an existing journal ref.
            if state != initialize(self.contract_digest, workflow=state["schema"] == 2):
                raise ValueError("Enrollment requires an empty journal")
            parents = []
        else:
            current, previous = self.read()
            if current != expected_revision:
                raise ValueError("Journal changed")
            old = previous["attempts"]
            new = state["attempts"]
            # Only append one reservation or finish the last reservation.
            appended = (len(new) == len(old)+1 and new[:-1] == old
                        and new[-1]["status"] == "reserved")
            finished = (bool(old) and len(new) == len(old)
                        and new[:-1] == old[:-1]
                        and old[-1]["status"] == "reserved"
                        and new[-1]["status"] == "finished"
                        and all(new[-1][k] == old[-1][k] for k in (
                            "run_id", "run_attempt", "model_seconds", "active_seconds")))
            credited = (previous["schema"] == state["schema"] == 2 and new == old and
                        len(state["task_credits"]) == len(previous["task_credits"])+1 and
                        state["task_credits"][:-1] == previous["task_credits"])
            if not (appended or finished or credited):
                raise ValueError("Journal history rewrite")
            last = new[-1]
            if credited:
                allowed = credit_task(previous, self.contract_digest, **state["task_credits"][-1])
            elif appended:
                allowed = reserve(previous, self.contract_digest, **{
                    key: last[key] for key in (
                        "run_id", "run_attempt", "model_seconds", "active_seconds")})
            else:
                allowed = finish(previous, self.contract_digest, **{
                    key: last[key] for key in ("run_id", "run_attempt", "progress_receipt")})
            if allowed != state:
                raise ValueError("Invalid journal transition")
            parents = ["-p", expected_revision]
        blob = self._git("hash-object", "-w", "--stdin",
                         data=json.dumps(state, sort_keys=True)+"\n")
        tree = self._git("mktree", data=f"100644 blob {blob}\tjournal.json\n")
        commit = self._git("commit-tree", tree, *parents,
                           data=f"Persist pilot admission {uuid.uuid4()} before execution\n")
        if before_publish is not None:before_publish()
        self._git("push", "--", self.remote, commit+":"+self.ref)
        observed, saved = self.read()
        if observed != commit or saved != state:
            raise ValueError("Uncertain journal publication; reconcile before launch")
        return commit
