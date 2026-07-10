#!/usr/bin/env python3
"""Smoke-test local UI-TARS vision gate for stayturgid."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "mac"))

import vlm_gate as vlm  # noqa: E402


def main() -> int:
    if not vlm.ensure_server(start=True):
        print(
            "UI-TARS server not healthy — run in a dedicated terminal:\n"
            "  make vlm-install && make vlm-server",
            file=sys.stderr,
        )
        return 1
    gate = vlm.VlmGate(autostart=False)
    if not gate.ready:
        print("VlmGate not ready", file=sys.stderr)
        return 1
    print("UI-TARS-1.5-7B ready on %s" % vlm._base_url())
    print("Expect ~10-20s per gate on Apple Silicon Metal; CPU-only: much slower.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
