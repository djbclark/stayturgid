#!/usr/bin/env python3
"""Smoke-test local UI-TARS and/or cloud VLM backends for stayturgid."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "control" / "lib"))

import vlm_cloud as cloud  # noqa: E402
import vlm_gate as vlm  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cloud-only",
        action="store_true",
        help="Skip local UI-TARS; only ping Gemini/Claude keys",
    )
    ap.add_argument(
        "--local-only",
        action="store_true",
        help="Skip cloud ping",
    )
    args = ap.parse_args(argv)
    rc = 0

    if not args.cloud_only:
        if vlm.ensure_server(start=True):
            print("UI-TARS local: OK on %s" % vlm._base_url())
            print(
                "Expect ~10-20s per gate on Apple Silicon Metal; "
                "CPU-only: much slower."
            )
        else:
            print(
                "UI-TARS local: NOT healthy (optional if cloud keys work)\n"
                "  curl -sf http://127.0.0.1:8081/health\n"
                "  just vlm-service-status",
                file=sys.stderr,
            )
            if args.local_only:
                return 1
            rc = 1

    if not args.local_only:
        result = cloud.ping_backends()
        # Never print full keys
        print(
            "Cloud keys: gemini=%s claude=%s"
            % (
                "present" if result.get("gemini_key") else "missing",
                "present" if result.get("claude_key") else "missing",
            )
        )
        print(
            "Models: gemini=%s claude=%s"
            % (result.get("gemini_model"), result.get("claude_model"))
        )
        g = result.get("gemini") or {}
        c = result.get("claude") or {}
        if g.get("ok"):
            print("Gemini ping: OK")
        else:
            print("Gemini ping: FAIL — %s" % g.get("error"), file=sys.stderr)
            rc = 1
        if c.get("ok"):
            print("Claude ping: OK")
        else:
            print("Claude ping: FAIL — %s" % c.get("error"), file=sys.stderr)
            rc = 1
        if os_environ_debug():
            print(json.dumps(result, indent=2)[:800])

    return rc


def os_environ_debug() -> bool:
    import os

    return os.environ.get("STAYTURGID_VLM_CHECK_DEBUG") == "1"


if __name__ == "__main__":
    raise SystemExit(main())
