"""Append-only Git journal adapter; no model, task state or workflow dispatch.

Use only in a trusted host workspace with a dedicated remote. Repository access
and protected journal refs are caller obligations. Never expose this adapter or
its credentials to the candidate/model. Network uncertainty raises; no retry.
"""

import json
import os
import subprocess
import uuid

from admission import _validate, finish, initialize, reserve


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

    def publish(self, expected_revision, state):
        """Append after exact revision, then verify provider-visible readback.

        A competing sibling commit cannot fast-forward the remote. A failed push
        or uncertain readback blocks launch even if the journal changed remotely.
        Passing None is explicit first enrollment, never a recovery operation.
        """
        _validate(state, self.contract_digest)
        if expected_revision is None:
            # An orphan commit cannot fast-forward an existing journal ref.
            if state != initialize(self.contract_digest):
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
            if not (appended or finished):
                raise ValueError("Journal history rewrite")
            last = new[-1]
            if appended:
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
        self._git("push", "--", self.remote, commit+":"+self.ref)
        observed, saved = self.read()
        if observed != commit or saved != state:
            raise ValueError("Uncertain journal publication; reconcile before launch")
        return commit
