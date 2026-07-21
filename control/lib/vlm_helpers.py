"""Optional UI-TARS orchestration for stayturgid Mac scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import vlm_gate as vlm


def vlm_usable() -> bool:
    """True when local UI-TARS and/or cloud VLM backends are available."""
    try:
        import vlm_cloud as cloud
    except ImportError:
        cloud = None
    local = vlm.vlm_enabled() and vlm.server_healthy()
    remote = bool(cloud and cloud.cloud_enabled())
    return local or remote


def auto_verify_enabled() -> bool:
    """Run VLM gates when local server is up and/or cloud keys are configured."""
    try:
        import vlm_cloud as cloud
    except ImportError:
        cloud = None
    if vlm.server_healthy():
        return True
    if cloud and cloud.cloud_enabled():
        return True
    return False


def verify_shot(shot: Path, check: str) -> tuple[bool, dict[str, Any]]:
    """One gate; skipped when server down unless strict."""
    gate = vlm.VlmGate(autostart=True, allow_server_only=True)
    return gate.verify(shot, check)


def issue_tags_from_verify(shot: Path, check: str, fail_tag: str) -> list[str]:
    ok, detail = verify_shot(shot, check)
    if detail.get("skipped"):
        return []
    if not ok:
        return [fail_tag]
    return []
