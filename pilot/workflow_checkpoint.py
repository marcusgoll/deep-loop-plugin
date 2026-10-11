"""Protected exact draft-delivery checkpoint publication and recovery.

No enrollment, dispatch, refunds or merge. Historical parent acceptance
remains immutable; only independently derived delivery and terminal images
can be recognized by the existing gate and checkpoint writer.
"""
from pathlib import Path
from admission import digest
from workflow_delivery import WAIT

FIELDS={'contract_digest','binding_sha256','parent_receipt_sha256','plan_sha256',
        'receipt_sha256','before','after','observation'}


def delivery_intent_records(store,key,binding,*,with_receipt=False):
    intent=store.read(key+'.workflow-delivery-checkpoint-intent.json')
    parent=store.read(key+'.parent-acceptance.json')
    plan=store.read(key+'.workflow-delivery-plan.json')
    receipt=store.read(key+'.workflow-delivery-complete.json')
    cap=binding['workflow_delivery']
    expected_fields={'contract_digest','plan_sha256','parent_receipt_sha256','export_sha256',
                     'candidate_snapshot_sha256','journal_revision','head_sha','base_sha',
                     'pull_request','checks','reviews','delivery_verified','complete'}
    if (set(intent)!=FIELDS or intent['contract_digest']!=key or binding.get('schema')!=4 or
            intent['binding_sha256']!=digest(binding) or intent['parent_receipt_sha256']!=digest(parent) or
            intent['plan_sha256']!=digest(plan) or intent['receipt_sha256']!=digest(receipt) or
            plan['capability']!=cap or plan['cut']['binding_sha256']!=digest(binding) or
            plan['cut']['parent_receipt']!=parent or plan['cut']['parent_receipt_sha256']!=digest(parent) or
            set(receipt)!=expected_fields or receipt['contract_digest']!=key or
            receipt['plan_sha256']!=digest(plan) or receipt['parent_receipt_sha256']!=digest(parent) or
            receipt['head_sha']!=plan['commit']['sha'] or receipt['base_sha']!=cap['base_sha'] or
            receipt['export_sha256']!=plan['export']['manifest_sha256'] or
            receipt['candidate_snapshot_sha256']!=plan['export']['candidate_snapshot_sha256'] or
            receipt['journal_revision']!=plan['cut']['outcome']['journal_revision'] or
            receipt['delivery_verified'] is not True or receipt['complete'] is not False or
            not isinstance(receipt['checks'],list) or not isinstance(receipt['reviews'],list) or
            [row['required'] for row in receipt['checks']]!=cap['required_checks'] or
            [row['required'] for row in receipt['reviews']]!=cap['required_reviews'] or
            digest(intent['before'])!=parent['checkpoint_sha256'] or
            intent['observation']!=parent['postimage_review_proof']):
        raise ValueError('Protected workflow delivery checkpoint intent identity drift')
    import re
    if re.fullmatch(r'https://github\.com/'+re.escape(cap['repository'])+r'/pull/[1-9][0-9]*',receipt['pull_request']) is None:
        raise ValueError('Workflow delivery intent endpoint drift')
    return (intent,receipt) if with_receipt else intent


def checked_delivery_intent(store,key,binding,helper):
    intent,receipt=delivery_intent_records(store,key,binding,with_receipt=True)
    archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in intent['before'] else None
    after=helper.verified_delivery_state(intent['before'],receipt['head_sha'],receipt['pull_request'],archive)
    if intent['after']!=after:raise ValueError('Substituted workflow delivery checkpoint postimage')
    if delivery_intent_records(store,key,binding,with_receipt=True)!=(intent,receipt):
        raise ValueError('Workflow delivery records changed during derivation')
    return intent


class WorkflowCheckpoint:
    def __init__(self,controller,adapter):
        self.controller,self.adapter=controller,adapter
        self.store,self.key=controller.store,controller.contract_digest
        if adapter.controller is not controller or adapter.store is not self.store:
            raise ValueError('Trusted shared workflow delivery controller required')

    def _provider_readback_guard(self,receipt):
        """Fresh provider acceptance; never sufficient for a protected write."""
        current=self.adapter.authenticate_delivery(locked=True)
        if current!=receipt:raise ValueError('Current provider acceptance changed before checkpoint publication')

    def _provider_guard(self,receipt):
        self._provider_readback_guard(receipt)
        self.adapter._locked_history_guard()

    def _post_publication_guard(self,binding,expected):
        # Provider acceptance is freshly reinspected by the later completion
        # wake. This publication remains an incomplete recovery stage.
        self.adapter._locked_history_guard()
        if self.controller.workflow_gate._read()[:2]!=(binding,expected):
            raise ValueError('Workflow published checkpoint changed at history guard')
        self.controller._workflow_mutation_authority(parent_recovery=True)

    def step(self):
        name=self.key+'.workflow-delivery-checkpoint-intent.json'
        try:self.store.read(name)
        except FileNotFoundError:
            receipt=self.adapter._read('complete')
            if receipt is None:
                # The protected delivery receipt ends this wake. It is a
                # recovery locator, never authority for the next publication.
                result=self.adapter.step()
                return WAIT if result=='workflow_delivery_verified' else result
            self.adapter._initialize()
            with self.store.lock():
                binding,state,_=self.controller.workflow_gate._read()
                proof=self.controller.workflow_gate.final_review_proof()
                archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in state else None
                after=self.controller.workflow_gate.helper.verified_delivery_state(state,receipt['head_sha'],receipt['pull_request'],archive)
                intent={'contract_digest':self.key,'binding_sha256':digest(binding),
                        'parent_receipt_sha256':self.adapter.cut['parent_receipt_sha256'],
                        'plan_sha256':digest(self.adapter.plan),'receipt_sha256':digest(receipt),
                        'before':state,'after':after,'observation':proof}
                # Derive first, then freshly authenticate provider acceptance
                # and retained history together at the protected write cut.
                self._provider_guard(receipt)
                if self.controller.workflow_gate._read()[:2]!=(binding,state):
                    raise ValueError('Delivery intent checkpoint changed during history guard')
                self.controller._workflow_mutation_authority(parent_recovery=True)
                self.store.create(name,intent)
                if checked_delivery_intent(self.store,self.key,binding,self.controller.workflow_gate.helper)!=intent:
                    raise ValueError('Workflow delivery checkpoint intent readback differs')
            return 'prepared_workflow_delivery_checkpoint'
        receipt=self.adapter._read('complete')
        self.adapter._initialize()
        with self.store.lock():
            gate=self.controller.workflow_gate;binding,state,_=gate._read()
            intent=checked_delivery_intent(self.store,self.key,binding,gate.helper)
            if state not in (intent['before'],intent['after']):raise ValueError('Workflow delivery checkpoint recovery drift')
            completion={'contract_digest':self.key,'intent_sha256':digest(intent),
                        'checkpoint_sha256':digest(intent['after']),'receipt_sha256':digest(receipt),
                        'delivery_verified':True,'complete':False}
            result_name=self.key+'.workflow-delivery-checkpoint.json'
            try:saved_completion=self.store.read(result_name)
            except FileNotFoundError:saved_completion=None
            if saved_completion is not None:
                if saved_completion!=completion or state!=intent['after']:
                    raise ValueError('Workflow delivery checkpoint completion drift')
                self._provider_guard(receipt)
                return 'workflow_delivery_checkpoint_verified'
            def checked(saved):
                if checked_delivery_intent(self.store,self.key,binding,gate.helper)!=saved:
                    raise ValueError('Workflow delivery checkpoint transition changed')
                actual_binding,current,_=gate._read()
                if actual_binding!=binding or current not in (saved['before'],saved['after']):
                    raise ValueError('Workflow delivery checkpoint exact preimage changed')
                return {**saved,'before':current}
            def postcheck():
                actual=gate._read()[1]
                archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in actual else None
                return gate.helper.validation_issues(actual,'delivery',archive)
            if state==intent['before']:
                saved=gate._publish_checkpoint(intent,checked,postcheck,
                    before_write=lambda:self._provider_guard(receipt),
                    after_write=lambda:self._post_publication_guard(binding,intent['after']))
                if saved!=intent['after']:raise ValueError('Delivery checkpoint publication differs')
                return WAIT
            saved=state
            # No write occurs until the final full retained-history closure.
            self._provider_readback_guard(receipt)
            if saved!=intent['after'] or gate._read()[1]!=saved:
                raise ValueError('Workflow delivery checkpoint changed before completion receipt')
            self.controller._workflow_source_guard(intent['observation'],parent_recovery=True)
            if gate._read()[1]!=saved:raise ValueError('Workflow delivery checkpoint changed at final source guard')
            self.controller._workflow_mutation_authority(parent_recovery=True)
            self.adapter._locked_history_guard()
            if gate._read()[:2]!=(binding,saved) or saved!=intent['after']:
                raise ValueError('Workflow completion checkpoint changed during history guard')
            self.controller._workflow_mutation_authority(parent_recovery=True)
            self.store.create(result_name,completion)
            if self.store.read(result_name)!=completion:raise ValueError('Workflow delivery checkpoint completion readback differs')
            return 'recovered_workflow_delivery_checkpoint'


TERMINAL_FIELDS=FIELDS|{'delivery_checkpoint_sha256','delivery_intent_sha256'}


def terminal_intent_records(store,key,binding,*,expected_delivery=None):
    """Authenticate a closed image against both independently derived transitions."""
    delivery=delivery_intent_records(store,key,binding)
    if expected_delivery is not None and delivery!=expected_delivery:
        raise ValueError('Workflow delivery records changed during terminal derivation')
    checkpoint=store.read(key+'.workflow-delivery-checkpoint.json')
    receipt=store.read(key+'.workflow-delivery-complete.json')
    expected={'contract_digest':key,'intent_sha256':digest(delivery),
              'checkpoint_sha256':digest(delivery['after']),'receipt_sha256':digest(receipt),
              'delivery_verified':True,'complete':False}
    intent=store.read(key+'.workflow-terminal-intent.json')
    if (checkpoint!=expected or set(intent)!=TERMINAL_FIELDS or
            any(intent[field]!=delivery[field] for field in
                ('contract_digest','binding_sha256','parent_receipt_sha256','plan_sha256','receipt_sha256')) or
            intent['delivery_checkpoint_sha256']!=digest(checkpoint) or
            intent['delivery_intent_sha256']!=digest(delivery) or intent['before']!=delivery['after']):
        raise ValueError('Protected workflow terminal intent identity drift')
    # The proof is the same historical cut at the delivered checkpoint hash.
    from private_controller import PrivateController
    proof=PrivateController._parent_proof_at_checkpoint(delivery['observation'],digest(intent['before']))
    if intent['observation']!=proof:raise ValueError('Workflow terminal observation drift')
    return intent


def checked_terminal_intent(store,key,binding,helper):
    delivery=checked_delivery_intent(store,key,binding,helper)
    intent=terminal_intent_records(store,key,binding,expected_delivery=delivery)
    archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in intent['before'] else None
    if intent['after']!=helper.completed_state(intent['before'],archive):
        raise ValueError('Substituted workflow terminal checkpoint postimage')
    if terminal_intent_records(store,key,binding,expected_delivery=delivery)!=intent:
        raise ValueError('Workflow terminal records changed during derivation')
    return intent


class WorkflowTerminal(WorkflowCheckpoint):
    """Separate helper-owned closeout, retaining exact delivery recovery semantics."""
    def step(self):
        name=self.key+'.workflow-terminal-intent.json'
        try:self.store.read(name)
        except FileNotFoundError:
            try:self.store.read(self.key+'.workflow-delivery-checkpoint.json')
            except FileNotFoundError:return super().step()
            self.adapter._initialize()
            receipt=self.adapter._read('complete')
            with self.store.lock():
                gate=self.controller.workflow_gate;binding,state,_=gate._read()
                delivery=checked_delivery_intent(self.store,self.key,binding,gate.helper)
                checkpoint=self.store.read(self.key+'.workflow-delivery-checkpoint.json')
                expected={'contract_digest':self.key,'intent_sha256':digest(delivery),
                          'checkpoint_sha256':digest(delivery['after']),'receipt_sha256':digest(receipt),
                          'delivery_verified':True,'complete':False}
                if checkpoint!=expected or state!=delivery['after']:
                    raise ValueError('Verified delivery checkpoint required before terminal intent')
                archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in state else None
                after=gate.helper.completed_state(state,archive)
                proof=gate.final_review_proof()
                intent={**delivery,'before':state,'after':after,'observation':proof,
                        'delivery_checkpoint_sha256':digest(checkpoint),'delivery_intent_sha256':digest(delivery)}
                self._provider_guard(receipt)
                if gate._read()[:2]!=(binding,state):raise ValueError('Terminal intent changed during history guard')
                self.controller._workflow_mutation_authority(parent_recovery=True)
                self.store.create(name,intent)
                if checked_terminal_intent(self.store,self.key,binding,gate.helper)!=intent:
                    raise ValueError('Workflow terminal intent readback differs')
            return 'prepared_workflow_terminal_checkpoint'
        receipt=self.adapter._read('complete')
        self.adapter._initialize()
        with self.store.lock():
            gate=self.controller.workflow_gate;binding,state,_=gate._read()
            intent=checked_terminal_intent(self.store,self.key,binding,gate.helper)
            if state not in (intent['before'],intent['after']):raise ValueError('Workflow terminal recovery drift')
            completion={'contract_digest':self.key,'intent_sha256':digest(intent),
                        'checkpoint_sha256':digest(intent['after']),'receipt_sha256':digest(receipt),
                        'delivery_verified':True,'complete':True}
            result_name=self.key+'.workflow-terminal-complete.json'
            try:existing=self.store.read(result_name)
            except FileNotFoundError:existing=None
            if existing is not None:
                if existing!=completion or state!=intent['after']:raise ValueError('Workflow terminal completion drift')
                self._provider_guard(receipt)
                return 'workflow_complete_verified'
            def checked(saved):
                if checked_terminal_intent(self.store,self.key,binding,gate.helper)!=saved:
                    raise ValueError('Workflow terminal transition changed')
                current_binding,current,_=gate._read()
                if current_binding!=binding or current not in (saved['before'],saved['after']):
                    raise ValueError('Workflow terminal exact preimage changed')
                return {**saved,'before':current}
            def postcheck():
                current=gate._read()[1]
                archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in current else None
                issues=gate.helper.validation_issues(current,'ship',archive)
                if issues:raise ValueError('Workflow terminal SHIP validation blocked: '+'; '.join(issues))
                return gate.final_review_proof()
            if state==intent['before']:
                saved=gate._publish_checkpoint(intent,checked,postcheck,
                    before_write=lambda:self._provider_guard(receipt),
                    after_write=lambda:self._post_publication_guard(binding,intent['after']))
                if saved!=intent['after']:raise ValueError('Terminal checkpoint publication differs')
                return WAIT
            saved=state
            # No write occurs until the final full retained-history closure.
            self._provider_readback_guard(receipt)
            self.controller._workflow_source_guard(intent['observation'],parent_recovery=True)
            if gate._read()[:2]!=(binding,saved) or saved!=intent['after']:
                raise ValueError('Workflow terminal checkpoint changed at final source guard')
            self.controller._workflow_mutation_authority(parent_recovery=True)
            self.adapter._locked_history_guard()
            if gate._read()[:2]!=(binding,saved) or saved!=intent['after']:
                raise ValueError('Workflow completion checkpoint changed during history guard')
            self.controller._workflow_mutation_authority(parent_recovery=True)
            self.store.create(result_name,completion)
            if self.store.read(result_name)!=completion:raise ValueError('Workflow terminal completion readback differs')
            return 'recovered_workflow_terminal_checkpoint'
