"""Unit tests for control/bin/fire_peer_help.py ForceCommand parsing."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "bin"))

import fire_peer_help as fph  # noqa: E402


def test_ssh_original_parses_verb(monkeypatch):
    monkeypatch.setenv(
        "SSH_ORIGINAL_COMMAND",
        "handsets-start --target 192.168.1.157:5555 --port 9012",
    )
    seen = {}

    def fake(verb, target, port):
        seen["v"] = verb
        seen["t"] = target
        seen["p"] = port
        return 0

    monkeypatch.setattr(fph, "run_verb", fake)
    assert fph.main([]) == 0
    assert seen == {"v": "handsets-start", "t": "192.168.1.157:5555", "p": 9012}


def test_ssh_original_denies_empty(monkeypatch):
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "")
    # Empty falls through to argparse — need argv
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND", raising=False)
    # Without SSH_ORIGINAL and without argv, argparse fails
    try:
        fph.main([])
        assert False, "expected SystemExit"
    except SystemExit:
        pass
