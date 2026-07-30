from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PREFLIGHT = REPO / "ansible/playbooks/fleet/preflight.yml"


def test_ssh_bootstrap_wakes_termux_before_attempting_and_ignores_module_failure() -> None:
    """#103: a fully backgrounded Termux can leave `pkg`/run-as unusable until
    its activity has run since last killed (same technique as
    control/bin/firerpa_heal.py's restart_sshd()). The wake step must run
    before the bootstrap attempt, and a bootstrap module failure must not
    pre-empt the existing re-probe/assert (which has the clearer fail_msg)."""
    text = PREFLIGHT.read_text()
    assert text.index("Wake a possibly-backgrounded Termux before SSH bootstrap") < text.index(
        "Bootstrap Termux authorized_keys and sshd over adb"
    )
    assert "com.termux/.app.TermuxActivity" in text
    assert text.index("Bootstrap Termux authorized_keys and sshd over adb") < text.index(
        "Re-probe Termux SSH after bootstrap"
    )
    assert text.index("Re-probe Termux SSH after bootstrap") < text.index("Assert Termux SSH is reachable")
    # ignore_errors must apply to the bootstrap task specifically, not the
    # whole play — check it's the nearest ignore_errors after that task name.
    bootstrap_idx = text.index("Bootstrap Termux authorized_keys and sshd over adb")
    reprobe_idx = text.index("Re-probe Termux SSH after bootstrap")
    assert "ignore_errors: true" in text[bootstrap_idx:reprobe_idx]
