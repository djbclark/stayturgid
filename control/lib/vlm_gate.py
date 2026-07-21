#!/usr/bin/env python3
"""Local UI-TARS-1.5-7B vision gates for stayturgid Mac QA (llama.cpp server).

Optional screenshot verification before/after high-stakes UI steps. Not used on
self-heal hot paths. See docs/vlm.md.

Env (STAYTURGID_VLM_* preferred; QSS_VLM_* accepted for shared model dir):
  STAYTURGID_VLM=1|0           — enable gates (default 0)
  STAYTURGID_VLM_STRICT=1      — fail when server down or check fails
  STAYTURGID_VLM_PORT=8081     — llama-server port
  STAYTURGID_VLM_TIMEOUT=900   — seconds per inference
  STAYTURGID_VLM_MAX_WIDTH=720 — downscale width before encode
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import vlm_cloud as cloud
except ImportError:  # pragma: no cover
    cloud = None

REPO = Path(__file__).resolve().parents[2]
UI_TARS_DIR = REPO / "control" / "vlm" / "ui-tars"
SERVER_SH = UI_TARS_DIR / "ui_tars_server.sh"
MAC_SITE_PLAYBOOK = REPO / "ansible" / "playbooks" / "control_node" / "site.yml"
ANSIBLE_CFG = REPO / "ansible" / "ansible.cfg"
LAUNCHAGENT_PLIST = Path.home() / "Library/LaunchAgents/homebrew.mxcl.ui-tars.plist"
LAUNCHAGENT_LABEL = "homebrew.mxcl.ui-tars"


def _env(name: str, default: str) -> str:
    stay = os.environ.get("STAYTURGID_" + name)
    if stay is not None and str(stay).strip() != "":
        return str(stay).strip()
    qss = os.environ.get("QSS_" + name)
    if qss is not None and str(qss).strip() != "":
        return str(qss).strip()
    if name == "VLM_PORT":
        ui = os.environ.get("UI_TARS_PORT")
        if ui is not None and str(ui).strip() != "":
            return str(ui).strip()
    return default


DEFAULT_PORT = int(_env("VLM_PORT", "8081"))
DEFAULT_TIMEOUT = int(_env("VLM_TIMEOUT", "900"))
IMAGE_MAX_WIDTH = int(_env("VLM_MAX_WIDTH", "720"))

CHECK_PROMPTS: dict[str, str] = {
    "play_autoupdate_dont": (
        "You verify Android screenshots from a tablet running Google Play Store.\n"
        "Is this the 'Auto-update apps' preference screen with radio buttons?\n"
        "Options: 'Don't auto-update apps', 'Over any network', 'Over Wi-Fi only'.\n"
        'Reply JSON only: {"ok":true,"setting":"dont_auto_update|wifi_only|any_network|unknown",'
        '"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true ONLY if 'Don't auto-update apps' is clearly the selected option."
    ),
    "aurora_autoupdate_dont": (
        "You verify Android screenshots from Aurora Store (FOSS Play client) settings.\n"
        "Is this the Automatic updates preference screen or section?\n"
        "Desired selection: 'Do not auto-update', 'Don't auto-update', or 'Never'.\n"
        "NOT ok: 'Check & install available updates automatically' selected.\n"
        'Reply JSON only: {"ok":true,"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true only when do-not-auto-update is clearly selected."
    ),
    "no_gms_crash_dialog": (
        "You verify an Android device screenshot for error dialogs.\n"
        "Is there a crash/error dialog for Google Services Framework, Google Play "
        "services, or Play Store (e.g. 'has stopped', 'keeps stopping')?\n"
        'Reply JSON only: {"ok":true,"crash_visible":false,"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true only when NO such crash dialog is visible."
    ),
    "play_protect_clear": (
        "You verify an Android screenshot during an app install flow.\n"
        "Is Google Play Protect blocking the install (warning dialog, 'Install anyway', "
        "'Blocked', or similar Play Protect overlay)?\n"
        'Reply JSON only: {"ok":true,"play_protect_visible":false,"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true only when Play Protect is NOT blocking (installer may proceed)."
    ),
    "neo_shizuku_installer": (
        "You verify a Neo Store (F-Droid client) settings screenshot.\n"
        "Is Shizuku shown as the selected/active installer (radio, switch, or checkmark)?\n"
        'Reply JSON only: {"ok":true,"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true only when Shizuku installer is clearly selected."
    ),
    "aurora_shizuku_installer": (
        "You verify an Aurora Store settings screenshot (Installation method).\n"
        "Is Shizuku installer selected/enabled?\n"
        'Reply JSON only: {"ok":true,"confidence":0.0-1.0,"notes":"..."}\n'
        "Set ok:true only when Shizuku is the active installer choice."
    ),
}


def vlm_enabled() -> bool:
    return _env("VLM", "0").lower() not in ("0", "false", "no")


def vlm_strict() -> bool:
    return _env("VLM_STRICT", "0").lower() not in ("0", "false", "no")


def _base_url() -> str:
    return "http://127.0.0.1:%d" % DEFAULT_PORT


def server_healthy() -> bool:
    try:
        req = urllib.request.Request(_base_url() + "/health")
        with urllib.request.urlopen(req, timeout=3) as resp:  # nosemgrep
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _ansible_mac_vlm(*, tags: str, install: bool = False) -> None:
    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(ANSIBLE_CFG)
    cmd = [
        "ansible-playbook",
        str(MAC_SITE_PLAYBOOK),
        "--tags",
        tags,
    ]
    if install:
        cmd.extend(["-e", "stayturgid_vlm_enabled=true"])
    subprocess.run(
        cmd,
        check=False,
        timeout=600,
        cwd=str(REPO),
        env=env,
    )


def ensure_server(start: bool = True) -> bool:
    if server_healthy():
        return True
    if not start:
        return False
    if os.uname().sysname == "Darwin":
        if LAUNCHAGENT_PLIST.is_file():
            _ansible_mac_vlm(tags="agents-ensure")
        else:
            _ansible_mac_vlm(tags="vlm-service", install=True)
    elif SERVER_SH.is_file():
        # Non-macOS: no launchd — manual background server only.
        subprocess.run(["bash", str(SERVER_SH)], check=False, timeout=200)
    deadline = time.time() + 300
    while time.time() < deadline:
        if server_healthy():
            return True
        time.sleep(1)
    return False


def _model_id() -> str:
    try:
        req = urllib.request.Request(_base_url() + "/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosemgrep
            payload = json.loads(resp.read().decode("utf-8"))
        models = payload.get("data") or payload.get("models") or []
        if models:
            return str(models[0].get("id") or models[0].get("name") or "ui-tars")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, IndexError):
        pass
    return "ui-tars"


def prepare_image(path: Path, *, max_width: int | None = None) -> Path:
    max_width = max_width or IMAGE_MAX_WIDTH
    out = path.with_name(path.stem + ".vlm.png")
    if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    try:
        subprocess.run(
            ["sips", "-Z", str(max_width), str(path), "--out", str(out)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return out
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return path


def _encode_image(path: Path) -> str:
    return base64.b64encode(prepare_image(path).read_bytes()).decode("ascii")


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def ask_image(path: Path, prompt: str, *, timeout: int | None = None) -> tuple[str, dict[str, Any] | None]:
    timeout = timeout or DEFAULT_TIMEOUT
    body = {
        "model": _model_id(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + _encode_image(path)},
                    },
                ],
            }
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        _base_url() + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
        payload = json.loads(resp.read().decode("utf-8"))
    raw = ""
    try:
        raw = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raw = json.dumps(payload)
    return raw, _parse_json_blob(raw)


def adb_screencap(serial: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        subprocess.run(
            ["adb", "-s", serial, "exec-out", "screencap", "-p"],
            check=True,
            stdout=f,
            timeout=60,
        )
    return dest


def _score_check(
    check: str,
    parsed: dict[str, Any] | None,
    *,
    min_confidence: float,
) -> tuple[bool, dict[str, Any]]:
    """Apply check-specific ok rules. Returns (ok, detail_fields)."""
    detail: dict[str, Any] = {}
    if not parsed:
        return False, {"reason": "unparseable_response"}
    ok = bool(parsed.get("ok"))
    try:
        conf = float(parsed.get("confidence", 0.8 if ok else 0.2))
    except (TypeError, ValueError):
        conf = 0.8 if ok else 0.2
    detail["confidence"] = conf
    if check == "play_autoupdate_dont" and ok:
        setting = str(parsed.get("setting", "unknown")).lower()
        ok = setting in ("dont_auto_update", "don't_auto_update", "dont")
        detail["setting"] = setting
    if check == "no_gms_crash_dialog":
        ok = bool(parsed.get("ok")) and not bool(parsed.get("crash_visible", False))
    if check == "play_protect_clear":
        ok = bool(parsed.get("ok")) and not bool(parsed.get("play_protect_visible", False))
    if ok and conf < min_confidence:
        ok = False
        detail["reason"] = "low_confidence"
    detail["ok"] = ok
    return ok, detail


def _should_escalate_cloud(
    local_ready: bool,
    local_detail: dict[str, Any] | None,
    *,
    min_confidence: float,
) -> bool:
    if cloud is None or not cloud.cloud_enabled() or not cloud.escalate_enabled():
        return False
    if not local_ready:
        return True
    if not local_detail:
        return True
    if local_detail.get("skipped"):
        return True
    if not local_detail.get("ok"):
        return True
    conf = float(local_detail.get("confidence") or 0)
    if conf < min_confidence:
        return True
    return False


class VlmGate:
    """Vision verification gate: local UI-TARS + optional cloud escalate."""

    def __init__(self, *, autostart: bool = True, allow_server_only: bool = False) -> None:
        # Cloud keys make the gate usable even when local UI-TARS is off/down.
        self.cloud_ready = bool(cloud is not None and cloud.cloud_enabled())
        self.ready = False
        # Match historical local enablement: explicit STAYTURGID_VLM, or
        # allow_server_only when the server is already up (or we may start it).
        if vlm_enabled() or allow_server_only:
            if vlm_enabled() or server_healthy() or autostart:
                self.ready = ensure_server(start=autostart)
            elif server_healthy():
                self.ready = True

    @property
    def usable(self) -> bool:
        """True when local server and/or cloud backends can run a verify()."""
        return bool(self.ready or self.cloud_ready)

    def verify(
        self,
        image_path: Path,
        check: str,
        *,
        min_confidence: float = 0.55,
        custom_prompt: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        prompt = custom_prompt or CHECK_PROMPTS.get(check)
        if not prompt:
            return True, {"skipped": True, "reason": "unknown_check"}

        local_detail: dict[str, Any] | None = None
        local_ok = False

        if self.ready:
            t0 = time.time()
            try:
                raw, parsed = ask_image(image_path, prompt)
                local_ok, scored = _score_check(check, parsed, min_confidence=min_confidence)
                local_detail = {
                    "check": check,
                    "backend": "local-ui-tars",
                    "raw": raw,
                    "parsed": parsed,
                    "elapsed_s": round(time.time() - t0, 1),
                    **scored,
                }
            except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as e:
                local_detail = {
                    "check": check,
                    "backend": "local-ui-tars",
                    "ok": False,
                    "reason": "local_error",
                    "error": str(e)[:200],
                    "elapsed_s": round(time.time() - t0, 1),
                }
                local_ok = False

            if local_ok and not _should_escalate_cloud(True, local_detail, min_confidence=min_confidence):
                return True, local_detail or {"ok": True, "backend": "local-ui-tars"}

        # Local unavailable / failed / low confidence → cloud (if configured).
        if _should_escalate_cloud(self.ready, local_detail, min_confidence=min_confidence) or (
            not self.ready and self.cloud_ready
        ):
            t1 = time.time()
            try:
                raw, parsed, backend = cloud.ask_cloud(
                    image_path,
                    prompt,
                    prepare=prepare_image,
                    timeout=min(DEFAULT_TIMEOUT, 120),
                )
                ok, scored = _score_check(check, parsed, min_confidence=min_confidence)
                detail: dict[str, Any] = {
                    "check": check,
                    "backend": "cloud-%s" % (backend or "unknown"),
                    "raw": raw,
                    "parsed": parsed,
                    "elapsed_s": round(time.time() - t1, 1),
                    "escalated_from": (local_detail or {}).get("backend"),
                    "local": local_detail,
                    **scored,
                }
                # If local had a pass and cloud disagrees without parse, keep local.
                if not ok and local_ok and local_detail:
                    local_detail = dict(local_detail)
                    local_detail["cloud_attempt"] = detail
                    return True, local_detail
                return ok, detail
            except Exception as e:
                if local_detail is not None:
                    local_detail = dict(local_detail)
                    local_detail["cloud_error"] = str(e)[:200]
                    if local_ok:
                        return True, local_detail
                    return False, local_detail
                skipped: dict[str, Any] = {
                    "skipped": True,
                    "reason": "cloud_error",
                    "error": str(e)[:200],
                    "ok": False,
                }
                if vlm_strict() and (vlm_enabled() or self.cloud_ready):
                    return False, skipped
                return True, skipped

        if local_detail is not None:
            return local_ok, local_detail

        skipped = {"skipped": True, "reason": "vlm_unavailable"}
        if vlm_strict() and (vlm_enabled() or self.cloud_ready):
            skipped["ok"] = False
            return False, skipped
        return True, skipped

    def require(self, image_path: Path, check: str, label: str = "") -> bool:
        ok, detail = self.verify(image_path, check)
        if not detail.get("skipped") and not ok:
            tag = label or check
            note = detail.get("parsed", {}) or {}
            notes = note.get("notes", detail.get("reason", ""))
            print(
                "VLM BLOCK %s [%s]: %s (%.1fs)"
                % (
                    tag,
                    detail.get("backend", "?"),
                    notes,
                    detail.get("elapsed_s", 0),
                ),
                flush=True,
            )
        return ok
