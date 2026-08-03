"""Guards the heartbeat-freshness threshold that must agree across three
independent runtimes: Python (Mac-side health check), CFEngine (on-device
liveness check), and Kotlin (native-agent's own invariant test).

All three currently carry a literal 420 (seconds) with a comment saying
"MUST match" the others (#86, unify rule) -- there is no single file they
can all import from, since they run in different languages/processes on
different machines. This test is the enforcement the comments alone can't
provide: it fails CI the moment any one of the three literals is changed
without the others.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FLEET_HEALTH_PY = REPO_ROOT / "control" / "lib" / "fleet_health.py"
STAYTURGID_CF = REPO_ROOT / "device" / "termux" / "cfengine" / "policy" / "stayturgid.cf"
HEARTBEAT_WRITER_TEST_KT = (
    REPO_ROOT
    / "device"
    / "native-agent"
    / "app"
    / "src"
    / "test"
    / "kotlin"
    / "org"
    / "stayturgid"
    / "agent"
    / "HeartbeatWriterTest.kt"
)


def _extract(path: Path, pattern: str) -> int:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    assert match, f"{path}: pattern not found: {pattern!r}"
    return int(match.group(1))


def test_heartbeat_freshness_threshold_matches_across_python_cfengine_kotlin() -> None:
    python_value = _extract(FLEET_HEALTH_PY, r"AGENT_HEARTBEAT_FRESH_SEC\s*=\s*(\d+)")
    cfengine_value = _extract(STAYTURGID_CF, r'"freshness_sec"\s*string\s*=>\s*"(\d+)"')
    kotlin_value = _extract(HEARTBEAT_WRITER_TEST_KT, r"freshnessSec\s*=\s*(\d+)L")

    assert python_value == cfengine_value == kotlin_value, (
        f"Heartbeat freshness threshold has drifted out of sync (unify rule, #86): "
        f"fleet_health.py AGENT_HEARTBEAT_FRESH_SEC={python_value}, "
        f"stayturgid.cf freshness_sec={cfengine_value}, "
        f"HeartbeatWriterTest.kt freshnessSec={kotlin_value}. "
        "The on-device (CFEngine) and Mac-side (Python) liveness checks read "
        "the same heartbeat file with this same threshold and must agree, or "
        "one side will flag an agent stale/missing while the other doesn't. "
        "Update all three together."
    )
