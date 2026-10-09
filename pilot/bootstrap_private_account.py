"""Create the fixed private qualification account. Does not log in or launch work.

Print the plan by default. Explicit --apply needs root, a missing account/group,
and an unused state path. Existing resources always block rather than being
changed or reused. The shared orchestrator/Codex configuration is untouched.
"""

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys


ACCOUNT = "deep-loop-pilot"
ROOT = Path("/var/lib/deep-loop-private-pilot")
HOME_PATH = ROOT / "home"
CANDIDATE = ROOT / "candidate"


def plan():
    return {"account": ACCOUNT, "home": str(HOME_PATH),
            "candidate": str(CANDIDATE), "shell": "/usr/sbin/nologin",
            "supplementary_groups": [], "authentication": "not provisioned",
            "model_calls": 0, "scheduler_installed": False}


def apply():
    if sys.platform != "linux":
        raise ValueError("Private account bootstrap requires Linux")
    if os.geteuid() != 0:
        raise ValueError("Account bootstrap requires root")
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try:
            lookup(ACCOUNT)
        except KeyError:
            pass
        else:
            raise ValueError("Existing account/group requires independent inspection")
    # Exclusive creation blocks symlinks and any pre-existing state.
    def trusted_directory(path):
        state = path.stat()
        if (path.resolve() != path or state.st_uid != 0
                or state.st_mode & 0o022 or not path.is_dir()
                or any(name.startswith("system.posix_acl_")
                       for name in os.listxattr(path, follow_symlinks=False))):
            raise ValueError("Untrusted state directory")
    trusted_directory(ROOT.parent)
    ROOT.mkdir(mode=0o755)
    trusted_directory(ROOT)
    subprocess.run(["/usr/sbin/useradd", "--system", "--user-group",
                    "--home-dir", str(HOME_PATH), "--no-create-home",
                    "--shell", "/usr/sbin/nologin", ACCOUNT], check=True)
    account = pwd.getpwnam(ACCOUNT)
    if (account.pw_dir != str(HOME_PATH)
            or account.pw_shell != "/usr/sbin/nologin"
            or os.getgrouplist(ACCOUNT, account.pw_gid) != [account.pw_gid]):
        raise ValueError("Unexpected account identity; preserve for inspection")
    for path in (HOME_PATH, CANDIDATE):
        path.mkdir(mode=0o700)
        os.chown(path, account.pw_uid, account.pw_gid)
    return {**plan(), "created": True, "uid": account.pw_uid,
            "gid": account.pw_gid, "state_owner": ROOT.stat().st_uid,
            "home_mode": oct(HOME_PATH.stat().st_mode & 0o777),
            "candidate_mode": oct(CANDIDATE.stat().st_mode & 0o777)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(apply() if arguments.apply else plan(), indent=2))
