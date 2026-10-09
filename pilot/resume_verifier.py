"""Protected two-invocation acceptance for the disposable resume pilot.

Intermediate checkpoint evidence is not progress: it cannot trigger delivery or
reset cumulative no-progress accounting. Call only after controller ownership
proves the native invocation ended with an empty cgroup, under its store lock.
"""
import uuid

from admission import digest, initialize
from artifact_verifier import ArtifactVerifier, _path


class ResumeVerifier:
    def __init__(self, candidate, owner_uid, store):
        self.artifact = ArtifactVerifier(candidate, owner_uid)
        self.store = store

    def _session(self, key, owner):
        session = self.store.read(owner['unit'] + '.session.json')
        invocation = self.store.read(owner['unit'] + '.invocation.json')
        if (set(session) != {'contract_digest', 'unit', 'invocation_id', 'session_id'} or
                session['contract_digest'] != key or session['unit'] != owner['unit'] or
                invocation['owner'] != owner or
                session['invocation_id'] != invocation['invocation_id']):
            raise ValueError('Resume verification lacks native session provenance')
        sid = session['session_id']
        if not isinstance(sid, str) or str(uuid.UUID(sid)) != sid:
            raise ValueError('Resume verification requires a canonical session UUID')
        return session

    def __call__(self, contract, owner):
        if 'resume_verification' not in contract:
            return self.artifact(contract, owner)
        key = digest(contract)
        if owner['contract_digest'] != key:
            raise ValueError('Resume verification contract drift')
        specification = contract['resume_verification']
        if set(specification) != {'checkpoint_path', 'checkpoint_sha256'}:
            raise ValueError('Unsupported resume verification contract')
        checkpoint = _path(specification['checkpoint_path'])
        initialize(specification['checkpoint_sha256'])
        if checkpoint in contract['verification']['baseline'] or checkpoint == contract['verification']['artifact_path']:
            raise ValueError('Checkpoint must be a separate temporary artifact')
        session = self._session(key, owner)
        name = key + '.checkpoint.json'
        try:
            first = self.store.read(name)
        except FileNotFoundError:
            checkpoint_contract = {**contract, 'verification': {
                'baseline': contract['verification']['baseline'],
                'artifact_path': checkpoint,
                'artifact_sha256': specification['checkpoint_sha256']}}
            observed = self.artifact(checkpoint_contract, {'contract_digest': digest(checkpoint_contract)})
            if observed is None:
                return None
            self.store.create(name, {'session': session, 'checkpoint_sha256': specification['checkpoint_sha256']})
            return None
        if (set(first) != {'session', 'checkpoint_sha256'} or
                first['checkpoint_sha256'] != specification['checkpoint_sha256'] or
                first['session']['contract_digest'] != key):
            raise ValueError('Protected checkpoint evidence changed')
        previous = first['session']
        # Reconciliation of the first invocation must never accept its own final
        # output. The second must explicitly request and report the same session.
        if (session['unit'] == previous['unit'] or
                session['invocation_id'] == previous['invocation_id']):
            return None
        if (owner['session_id'] != previous['session_id'] or
                session['session_id'] != previous['session_id']):
            raise ValueError('Final artifact lacks explicit same-session resume')
        evidence = self.artifact(contract, owner)
        if evidence is None:
            return None
        proof = {'checkpoint': first, 'resumed_session': session, 'evidence': evidence}
        final_name = key + '.resume-acceptance.json'
        try:
            self.store.create(final_name, proof)
        except FileExistsError:
            if self.store.read(final_name) != proof:
                raise ValueError('Conflicting protected resume acceptance')
        return evidence


def validate_resume_acceptance(contract, evidence, store):
    """Re-read protected native provenance before every delivery transition."""
    key = digest(contract)
    proof = store.read(key + '.resume-acceptance.json')
    first = store.read(key + '.checkpoint.json')
    if (set(proof) != {'checkpoint', 'resumed_session', 'evidence'} or
            proof['checkpoint'] != first or proof['evidence'] != evidence or
            set(first) != {'session', 'checkpoint_sha256'} or
            first['checkpoint_sha256'] != contract['resume_verification']['checkpoint_sha256']):
        raise ValueError('Protected resume acceptance drift')
    sessions = [first['session'], proof['resumed_session']]
    owners = []
    for session in sessions:
        if (set(session) != {'contract_digest', 'unit', 'invocation_id', 'session_id'} or
                session['contract_digest'] != key or
                not isinstance(session['session_id'], str) or
                str(uuid.UUID(session['session_id'])) != session['session_id'] or
                store.read(session['unit'] + '.session.json') != session):
            raise ValueError('Protected resume session drift')
        invocation = store.read(session['unit'] + '.invocation.json')
        owner = invocation['owner']
        if (invocation['invocation_id'] != session['invocation_id'] or
                owner['unit'] != session['unit'] or owner['contract_digest'] != key):
            raise ValueError('Protected resume invocation drift')
        owners.append(owner)
    previous, resumed = sessions
    if (previous['unit'] == resumed['unit'] or
            previous['invocation_id'] == resumed['invocation_id'] or
            previous['session_id'] != resumed['session_id'] or
            owners[1]['session_id'] != previous['session_id']):
        raise ValueError('Protected acceptance lacks distinct same-session resume')
    return digest(proof)
