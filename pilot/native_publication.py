"""Protected receipt publication preparation; caller owns credential lock."""
import hashlib
from admission import digest
from native_result import NativeResult,read_regular


class NativePublication:
    def __init__(self,store,journal,backend,gate):
        self.store,self.journal,self.backend,self.gate=store,journal,backend,gate
        self.results=NativeResult(store,journal,backend,gate)

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
        self._save(prefix+'.publication-intent.json',intent)
        return intent
