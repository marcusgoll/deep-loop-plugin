"""Protected receipt publication preparation; caller owns credential lock."""
import hashlib
from authority import require_active
from worker_window import remaining
from admission import digest
from native_result import NativeResult,read_regular


class NativePublication:
    def __init__(self,store,journal,backend,gate):
        self.store,self.journal,self.backend,self.gate=store,journal,backend,gate
        self.results=NativeResult(store,journal,backend,gate)

    def _authorized(self):
        require_active(self.store,self.journal.contract_digest)
        if remaining(self.store,self.journal.contract_digest)<=0:
            raise ValueError('Immutable native publication window expired')

    def _save(self,name,value):
        try:self.store.create(name,value)
        except FileExistsError:
            if self.store.read(name)!=value:raise ValueError('Native publication record changed')
        if self.store.read(name)!=value:raise ValueError('Native publication readback differs')

    def prepare(self,prefix):
        """Save exact receipt and transition before checkpoint mutation.

        Repeated preparation reauthenticates the same ended invocation and
        current artifacts. Receipt persistence alone grants no task acceptance.
        An interrupted preparation can adopt identical files, never rerun work.
        """
        row=self.results.receipt_row(prefix)
        result=self.store.read(prefix+'.result.json')
        if row['sealed_result_sha256']!=digest(result):raise ValueError('Native sealed result changed')
        name=prefix+'.receipt.json';rows=[row]
        self._save(name,rows)
        path=self.store.root/name
        payload=read_regular(path,{self.store.owner_uid},mode=0o600)
        receipt={'path':str(path),'sha256':hashlib.sha256(payload).hexdigest()}
        transition=self.gate.verified_state(row['verifier_id'],receipt,
            'Authenticated native invocation '+row['native_provenance']['invocation_id'])
        revision,journal=self.journal.read()
        owned=self.store.read(prefix+'.intent.json')['owned_plan']
        if (revision!=owned['journal_revision'] or digest(owned)!=result['owned_plan_digest'] or
                digest(transition['before'])!=owned['plan']['checkpoint_sha256']):
            raise ValueError('Native publication authority changed')
        intent={'contract_digest':self.journal.contract_digest,'prefix':prefix,
                'sealed_result_sha256':digest(result),'receipt':receipt,
                'journal_revision':revision,'journal_sha256':digest(journal),
                'transition':transition,'parent_accepted':False}
        # Reauthenticate immediately before durable publication authority.
        if self.results.receipt_row(prefix)!=row or self.journal.read()!=(revision,journal):
            raise ValueError('Native publication inputs changed during preparation')
        self._authorized()
        self._save(prefix+'.publication-intent.json',intent)
        return intent

    def publish(self,prefix):
        """Apply or adopt only the saved transition; retain the verifier fence."""
        intent=self.store.read(prefix+'.publication-intent.json')
        result=self.store.read(prefix+'.result.json')
        revision,journal=self.journal.read()
        if (intent['contract_digest']!=self.journal.contract_digest or intent['prefix']!=prefix or
                intent['parent_accepted'] is not False or
                intent['sealed_result_sha256']!=digest(result) or
                intent['journal_revision']!=revision or intent['journal_sha256']!=digest(journal)):
            raise ValueError('Native publication intent authority changed')
        receipt=intent['receipt'];path=self.store.root/(prefix+'.receipt.json')
        payload=read_regular(path,{self.store.owner_uid},mode=0o600)
        if receipt!={'path':str(path),'sha256':hashlib.sha256(payload).hexdigest()}:
            raise ValueError('Native publication receipt changed')
        row=self.results.receipt_row(prefix)
        if self.store.read(prefix+'.receipt.json')!=[row]:raise ValueError('Native publication result row changed')
        transition=intent['transition']
        observation=transition['observation']
        if (observation['receipt']!=receipt or observation['verifier_id']!=row['verifier_id'] or
                observation['parent_accepted'] is not False):
            raise ValueError('Native publication transition identity changed')
        self._authorized()
        saved=self.gate.publish_verified_state(transition,before_write=self._authorized)
        # A crash here is recovered through the immutable before/after intent;
        # no execution or fresh transition is permitted.
        if self.results.receipt_row(prefix)!=row or self.journal.read()!=(revision,journal):
            raise ValueError('Native publication inputs changed after checkpoint write')
        complete={'contract_digest':intent['contract_digest'],'prefix':prefix,
                  'intent_sha256':digest(intent),'checkpoint_sha256':digest(saved),
                  'receipt':receipt,'parent_accepted':False,'checkpoint_published':True}
        self._authorized()
        self._save(prefix+'.publication-complete.json',complete)
        return complete
