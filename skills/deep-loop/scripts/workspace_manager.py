"""Exclusive directory reservation; no OS sandbox or permission separation."""
import argparse
import json
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("job")
    args=parser.parse_args()
    reserved={"CON","PRN","AUX","NUL",*[f"COM{i}" for i in range(1,10)],*[f"LPT{i}" for i in range(1,10)]}
    if not re.fullmatch("[a-zA-Z0-9_-]+",args.job) or args.job.upper() in reserved:
        parser.error("invalid/reserved job directory name")
    try:
        root=args.root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        path=root/args.job
        path.mkdir(mode=0o700)
    except OSError as exc:
        parser.error(f"reservation refused; preserve existing workspace: {exc}")
    print(json.dumps({"workspace":str(path),"job":args.job,"isolation":"exclusive-directory-only"}))
    return 0


if __name__=="__main__":raise SystemExit(main())
