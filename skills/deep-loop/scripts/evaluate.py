#!/usr/bin/env python3
"""Evaluate deterministic fixture outcomes; missing evidence is never success."""
import argparse
import json
from pathlib import Path


def evaluate(data):
    if not isinstance(data, dict) or not isinstance(data.get('scenarios'), list) or not data['scenarios']:
        raise ValueError('nonempty scenarios required')
    ids = set()
    results = []
    for s in data['scenarios']:
        if not isinstance(s, dict) or not isinstance(s.get('id'), str) or not s['id'].strip() or s['id'] in ids:
            raise ValueError('invalid or duplicate scenario id')
        ids.add(s['id'])
        required = s.get('required_checks')
        evidence = s.get('evidence')
        if not isinstance(required, list) or not required or not all(isinstance(x, str) and x.strip() for x in required) or len(required) != len(set(required)):
            raise ValueError('invalid required checks')
        malformed = 'evidence' in s and not isinstance(evidence,dict)
        if not isinstance(evidence, dict):
            evidence = {}
        missing = [] if malformed else [x for x in required if x not in evidence]
        failed = list(required) if malformed else [x for x in required if x in evidence and not (isinstance(evidence[x], dict) and evidence[x].get('passed') is True and isinstance(evidence[x].get('artifact_sha256'), str) and len(evidence[x]['artifact_sha256']) == 64 and all(c in '0123456789abcdef' for c in evidence[x]['artifact_sha256']))]
        status = 'failed' if failed else 'incomplete' if missing else 'passed'
        results.append({'id': s['id'], 'status': status, 'missing': missing, 'failed': failed})
    passed = sum(x['status'] == 'passed' for x in results)
    return {'format': 'deep-loop-evaluation-v1', 'total': len(results), 'passed': passed, 'pass_rate': passed / len(results), 'overall': 'passed' if passed == len(results) else 'not_proven', 'scenarios': results, 'warning': 'Self-reported fixture evidence is not execution attestation.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    try:
        result = evaluate(json.loads(a.input.read_bytes()))
        with a.output.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
    except (OSError,ValueError,TypeError) as exc:
        p.error(str(exc))
    print(result['overall'])
    return 0 if result['overall']=='passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
