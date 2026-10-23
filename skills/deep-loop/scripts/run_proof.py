"""Run reviewed exact-argv checks; no sandbox or provenance attestation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"cwd", "allowlist", "checks"}:
        raise ValueError("plan requires cwd, allowlist and checks")
    if not isinstance(plan["cwd"], str) or not Path(plan["cwd"]).is_absolute() or not Path(plan["cwd"]).is_dir():
        raise ValueError("cwd must name an existing absolute directory")
    def argv_ok(argv):
        return isinstance(argv, list) and bool(argv) and all(isinstance(x, str) and x and "\x00" not in x for x in argv)
    if not isinstance(plan["allowlist"], list) or not plan["allowlist"] or not all(argv_ok(x) for x in plan["allowlist"]):
        raise ValueError("allowlist requires exact nonempty argv arrays")
    if not isinstance(plan["checks"], list) or not plan["checks"]:
        raise ValueError("checks must be nonempty")
    ids = set()
    for c in plan["checks"]:
        if not isinstance(c, dict) or set(c) != {"id", "argv", "timeout"}:
            raise ValueError("check requires id, argv and timeout")
        if not isinstance(c["id"], str) or not c["id"].strip() or c["id"] in ids:
            raise ValueError("check IDs must be nonempty and unique")
        ids.add(c["id"])
        if not argv_ok(c["argv"]) or c["argv"] not in plan["allowlist"]:
            raise ValueError("unapproved command")
        if type(c["timeout"]) not in (int, float) or not 0 < c["timeout"] <= 300 or not math.isfinite(c["timeout"]):
            raise ValueError("timeout must be finite and within 0..300 seconds")
    return Path(plan["cwd"]).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        raw = args.plan.read_bytes()
        plan = json.loads(raw)
        cwd = validate_plan(plan)
        output = args.output.resolve()
        if not output.is_relative_to(cwd) or output == cwd or args.output.exists() or args.output.is_symlink():
            raise ValueError("output must be new and within cwd")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive reservation precedes execution; never overwrite another writer's proof.
        with output.open("x", encoding="utf-8") as stream:
            results = []
            for c in plan["checks"]:
                started = time.monotonic()
                try:
                    run = subprocess.run(c["argv"], cwd=cwd, capture_output=True, timeout=c["timeout"], shell=False)
                    status, code, out, err = ("passed" if run.returncode == 0 else "failed"), run.returncode, run.stdout, run.stderr
                except subprocess.TimeoutExpired as exc:
                    status, code, out, err = "timeout", None, exc.stdout or b"", exc.stderr or b""
                except OSError as exc:
                    status, code, out, err = "error", None, b"", str(exc).encode("utf-8")
                results.append({"id": c["id"], "argv": c["argv"], "outcome": status, "exit_code": code,
                                "seconds": round(time.monotonic() - started, 3),
                                "stdout": out[:65536].decode("utf-8", errors="replace"), "stderr": err[:65536].decode("utf-8", errors="replace")})
                if status != "passed":
                    break
            json.dump({"format": "deep-loop-proof-v1", "plan_sha256": hashlib.sha256(raw).hexdigest(), "checks": results}, stream, indent=2)
            stream.write("\n")
        print(f"Recorded {len(results)} checks: {output}")
        return 0 if len(results) == len(plan["checks"]) and all(x["outcome"] == "passed" for x in results) else 1
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
