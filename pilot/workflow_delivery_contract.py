"""Explicit full-candidate draft delivery capability; no provider operation.

This capability must be part of an exact approved initial workflow binding.
It does not upgrade a retained binding, enroll an outcome or activate a worker.
"""
from datetime import datetime
import re

from git_candidate_export import RULES


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and '\0' not in value and len(value.encode('utf-8')) <= limit


def _positive(value):
    return type(value) is int and value > 0


def _ref(value):
    return (isinstance(value, str) and len(value) <= 200 and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', value) is not None and
            '..' not in value and not value.endswith(('/', '.')) and
            all(part and not part.startswith('.') and not part.endswith('.lock')
                for part in value.split('/')))


def validate_workflow_delivery(capability, contract_digest):
    if not isinstance(contract_digest,str) or re.fullmatch(r'[0-9a-f]{64}',contract_digest) is None:
        raise ValueError('Exact workflow contract identity required')
    fields = {'kind','approval_ref','repository','repository_id','publisher','publisher_id',
              'base_ref','base_sha','branch','title','body','commit','export_rules',
              'required_checks','required_reviews'}
    if (not isinstance(capability, dict) or set(capability) != fields or
            capability['kind'] != 'full_workflow_draft_v1' or
            not _text(capability['approval_ref'],4096) or
            not isinstance(capability['repository'],str) or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',capability['repository']) is None or
            not _positive(capability['repository_id']) or
            not isinstance(capability['publisher'],str) or
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',capability['publisher']) is None or
            not _positive(capability['publisher_id']) or
            not _ref(capability['base_ref']) or
            not isinstance(capability['base_sha'],str) or
            re.fullmatch(r'[0-9a-f]{40}',capability['base_sha']) is None or capability['base_sha'] == '0'*40 or
            capability['branch'] != 'deep-loop-workflow/'+contract_digest or
            not _text(capability['title'],256) or not _text(capability['body'],65536) or
            capability['export_rules'] != RULES):
        raise ValueError('Exact explicit full workflow draft delivery authority required')
    commit = capability['commit']
    if (not isinstance(commit,dict) or set(commit) != {'name','email','date','message'} or
            not _text(commit['name'],256) or any(c in commit['name'] for c in '\r\n<>') or
            not _text(commit['email'],256) or
            re.fullmatch(r'[^\s<>]+@[^\s<>]+',commit['email']) is None or
            not _text(commit['message'],4096) or not commit['message'].endswith('\n') or
            not isinstance(commit['date'],str) or
            re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',commit['date']) is None):
        raise ValueError('Exact frozen Git commit metadata required')
    try: datetime.strptime(commit['date'],'%Y-%m-%dT%H:%M:%SZ')
    except ValueError as exc: raise ValueError('Invalid frozen commit date') from exc
    checks = capability['required_checks']; reviews = capability['required_reviews']
    if not isinstance(checks,list) or not 1 <= len(checks) <= 32 or not isinstance(reviews,list) or len(reviews) > 32:
        raise ValueError('Complete bounded check and review obligations required')
    identities = set()
    for check in checks:
        if (not isinstance(check,dict) or set(check) != {'name','app_id','app_slug','workflow_path','event'} or
                not _text(check['name'],256) or not _positive(check['app_id']) or
                not isinstance(check['app_slug'],str) or re.fullmatch(r'[a-z0-9-]{1,100}',check['app_slug']) is None or
                not isinstance(check['workflow_path'],str) or
                re.fullmatch(r'\.github/workflows/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.ya?ml',check['workflow_path']) is None or
                check['event'] != 'pull_request' or (check['name'],check['app_id']) in identities):
            raise ValueError('Explicit unique hosted check provenance required')
        identities.add((check['name'],check['app_id']))
    identities = set()
    for review in reviews:
        if (not isinstance(review,dict) or set(review) != {'login','id'} or not _positive(review['id']) or
                not isinstance(review['login'],str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',review['login']) is None or
                review['id'] in identities):
            raise ValueError('Explicit unique reviewer identity required')
        identities.add(review['id'])
    return capability
