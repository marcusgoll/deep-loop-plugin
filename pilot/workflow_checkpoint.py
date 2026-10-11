"""Protected exact draft-delivery checkpoint publication and recovery.

No enrollment, dispatch, refunds, merge or terminal completion. Historical
parent acceptance remains immutable; only an independently derived delivery
postimage can be recognized by the existing gate and checkpoint writer.
"""
from pathlib import Path
from admission import digest

FIELDS={'contract_digest','binding_sha256','parent_receipt_sha256','plan_sha256',
        'receipt_sha256','before','after','observation'}


def checked_delivery_intent(store,key,binding,helper):
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
    archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in intent['before'] else None
    after=helper.verified_delivery_state(intent['before'],receipt['head_sha'],receipt['pull_request'],archive)
    if intent['after']!=after:raise ValueError('Substituted workflow delivery checkpoint postimage')
    return intent


class WorkflowCheckpoint:
    def __init__(self,controller,adapter):
        self.controller,self.adapter=controller,adapter
        self.store,self.key=controller.store,controller.contract_digest
        if adapter.controller is not controller or adapter.store is not self.store:
            raise ValueError('Trusted shared workflow delivery controller required')

    def _provider_guard(self,receipt):
        current=self.adapter.authenticate_delivery(locked=True)
        if current!=receipt:raise ValueError('Current provider acceptance changed before checkpoint publication')
        self.adapter._locked_guard()

    def step(self):
        name=self.key+'.workflow-delivery-checkpoint-intent.json'
        try:self.store.read(name)
        except FileNotFoundError:
            result=self.adapter.step()
            if result!='workflow_delivery_verified':return result
            receipt=self.adapter._read('complete')
            current=self.adapter.authenticate_delivery()
            if current!=receipt:raise ValueError('Provider acceptance changed before delivery intent')
            with self.store.lock():
                self._provider_guard(receipt)
                binding,state,_=self.controller.workflow_gate._read()
                proof=self.controller.workflow_gate.final_review_proof()
                archive=Path(binding['checkpoint_path']).parent.parent if 'proofResolution' in state else None
                after=self.controller.workflow_gate.helper.verified_delivery_state(state,receipt['head_sha'],receipt['pull_request'],archive)
                intent={'contract_digest':self.key,'binding_sha256':digest(binding),
                        'parent_receipt_sha256':self.adapter.cut['parent_receipt_sha256'],
                        'plan_sha256':digest(self.adapter.plan),'receipt_sha256':digest(receipt),
                        'before':state,'after':after,'observation':proof}
                self.adapter._locked_guard();self.store.create(name,intent)
                if checked_delivery_intent(self.store,self.key,binding,self.controller.workflow_gate.helper)!=intent:
                    raise ValueError('Workflow delivery checkpoint intent readback differs')
            return 'prepared_workflow_delivery_checkpoint'
        receipt=self.adapter._read('complete')
        if self.adapter.authenticate_delivery()!=receipt:
            raise ValueError('Current provider acceptance changed during delivery recovery')
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
            saved=gate._publish_checkpoint(intent,checked,postcheck,before_write=lambda:self._provider_guard(receipt))
            self._provider_guard(receipt)
            if saved!=intent['after'] or gate._read()[1]!=saved:
                raise ValueError('Workflow delivery checkpoint changed before completion receipt')
            self.controller._workflow_source_guard(intent['observation'],parent_recovery=True)
            if gate._read()[1]!=saved:raise ValueError('Workflow delivery checkpoint changed at final source guard')
            self.controller._workflow_mutation_authority(parent_recovery=True)
            self.store.create(result_name,completion)
            if self.store.read(result_name)!=completion:raise ValueError('Workflow delivery checkpoint completion readback differs')
            return 'recovered_workflow_delivery_checkpoint'
