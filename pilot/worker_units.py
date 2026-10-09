"""Generate a pinned private supervisor service/timer; installs/enables nothing."""
from pathlib import Path
from admission import initialize
from private_launch import ROOT


def units(bundle_digest):
    initialize(bundle_digest)
    bundle = Path(ROOT)/'control'/('bundle-'+bundle_digest)
    service = f'''[Unit]
Description=Deep Loop private bounded worker
ConditionPathExists={ROOT}/control/enabled-outcome.json
[Service]
Type=exec
User=root
WorkingDirectory={ROOT}/control
ExecStart=/usr/bin/python3 -Es {bundle}/private_worker.py
RuntimeMaxSec=45
TimeoutStartSec=5
TimeoutStopSec=5
KillMode=control-group
Restart=no
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths={ROOT}/control {ROOT}/home
UnsetEnvironment=OPENAI_API_KEY CODEX_API_KEY CODEX_HOME OPENAI_BASE_URL PYTHONPATH PYTHONHOME
'''
    timer = '''[Unit]
Description=Wake the explicitly enrolled Deep Loop private worker
[Timer]
OnBootSec=30
OnUnitInactiveSec=30
Unit=deep-loop-private-worker.service
[Install]
WantedBy=timers.target
'''
    return {'deep-loop-private-worker.service':service,'deep-loop-private-worker.timer':timer}
