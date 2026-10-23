#!/usr/bin/env python3
"""Compare two fixture evaluation sets; no empirical performance claims."""
import argparse,json
from pathlib import Path
from evaluate import evaluate

def compare(data):
    if not isinstance(data,dict) or set(data)!={'baseline','candidate'}:raise ValueError('baseline and candidate required')
    a=evaluate(data['baseline']);b=evaluate(data['candidate'])
    ai={s['id'] for s in a['scenarios']};bi={s['id'] for s in b['scenarios']}
    if ai!=bi:raise ValueError('scenario sets differ')
    checks_a={s['id']:set(s['required_checks']) for s in data['baseline']['scenarios']}
    checks_b={s['id']:set(s['required_checks']) for s in data['candidate']['scenarios']}
    if checks_a!=checks_b:raise ValueError('required check sets differ')
    return {'format':'deep-loop-comparison-v1','baseline':a,'candidate':b,'pass_rate_delta':b['pass_rate']-a['pass_rate'],'warning':'Fixture comparison only; not a measured improvement in autonomous engineering.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    try:
        result=compare(json.loads(a.input.read_bytes()))
        with a.output.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
    except (ValueError,TypeError,OSError) as exc:p.error(str(exc))
    print('fixture comparison recorded')
    return 0

if __name__=='__main__':raise SystemExit(main())
