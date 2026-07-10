"""Optional UI-TARS orchestration for stayturgid Mac scripts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import vlm_gate as vlm


def vlm_usable() -> bool:
    """True when vision gates are enabled and llama-server responds."""
    return vlm.vlm_enabled() and vlm.server_healthy()


def auto_verify_enabled() -> bool:
    """Run VLM gates when server is up even if STAYTURGID_VLM is unset."""
    if vlm.vlm_enabled():
        return vlm.server_healthy()
    return vlm.server_healthy()


def verify_shot(shot: Path, check: str) -> tuple[bool, dict[str, Any]]:
    """One gate; skipped when server down unless strict."""
    gate = vlm.VlmGate(autostart=True, allow_server_only=True)
    return gate.verify(shot, check)


def issue_tags_from_verify(
    shot: Path, check: str, fail_tag: str
) -> list[str]:
    ok, detail = verify_shot(shot, check)
    if detail.get("skipped"):
        return []
    if not ok:
        return [fail_tag]
    return []
