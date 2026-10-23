#!/usr/bin/env python3
"""Read-only GitHub snapshot normalizer. Input is untrusted API-exported JSON.

No network access, GitHub mutation, or authorization inference is performed.
"""
import argparse
import json
import re
from pathlib import Path


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError('snapshot must be an object')
    repo = raw.get('repository', {})
    pr = raw.get('pull_request', {})
    if not isinstance(repo, dict) or not isinstance(pr, dict):
        raise ValueError('repository and pull_request must be objects')
    head = pr.get('head_sha')
    checked = raw.get('checked_head_sha')
    if not isinstance(checked,str) or not re.fullmatch('[a-f0-9]{40}',checked):checked=None
    if not isinstance(head, str) or len(head) != 40 or any(c not in '0123456789abcdef' for c in head):
        raise ValueError('invalid head sha')
    checks = raw.get('checks', [])
    if not isinstance(checks, list):
        raise ValueError('checks must be a list')
    required = repo.get('required_checks')
    governance = repo.get('governance')
    unknown = []
    blocked = []
    identity=repo.get('full_name')
    number=pr.get('number')
    if not isinstance(identity,str) or not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',identity):
        unknown.append('repository identity unavailable');identity=None
    if type(number) is not int or number<1:
        unknown.append('PR number unavailable');number=None
    if not isinstance(governance, dict) or governance.get('inspected') is not True:
        unknown.append('repository governance not inspected')
    if not isinstance(required, list) or not all(isinstance(x, str) and x.strip() for x in required) or len(required) != len(set(required)):
        unknown.append('required check policy unavailable')
        required = []
    by_name = {}
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get('name'), str) or not check['name'].strip():
            raise ValueError('invalid check')
        by_name.setdefault(check['name'], []).append(check)
    for name in required:
        found = by_name.get(name, [])
        if len(found) != 1:
            unknown.append(f'{name}: missing or ambiguous check')
        elif found[0].get('head_sha') != head:
            unknown.append(f'{name}: check belongs to another head')
        elif found[0].get('conclusion') != 'success':
            blocked.append(f'{name}: not successful')
    if checked != head:
        unknown.append('checked head is stale or unavailable')
    review = pr.get('review_decision')
    if review == 'CHANGES_REQUESTED':
        blocked.append('blocking review')
    elif review != 'APPROVED':
        unknown.append('approval not established')
    if pr.get('mergeable') is False:
        blocked.append('merge conflicts')
    elif pr.get('mergeable') is not True:
        unknown.append('mergeability unknown')
    if pr.get('state') != 'open':
        blocked.append('PR is not open')
    return {
        'format': 'deep-loop-github-snapshot-v1',
        'repository': identity,
        'pr_number': number,
        'head_sha': head,
        'checked_head_sha': checked,
        'required_checks': required,
        'unknown': sorted(set(unknown)),
        'blocked': sorted(set(blocked)),
        'readiness': 'blocked' if blocked else 'unknown' if unknown else 'eligible_for_further_review',
        'authorization': 'not_established',
        'note': 'Readiness is not merge authorization; live revalidation is required.'
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    try:
        normalized = normalize(json.loads(a.input.read_bytes()))
        with a.output.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(normalized,indent=2,sort_keys=True)+'\n')
    except (OSError,ValueError,TypeError) as exc:
        p.error(str(exc))
    print(normalized['readiness'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
