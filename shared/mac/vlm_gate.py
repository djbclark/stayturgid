#!/usr/bin/env python3
"""Local UI-TARS-1.5-7B vision gates for stayturgid Mac QA (llama.cpp server).

Optional screenshot verification before/after high-stakes UI steps. Not used on
self-heal hot paths. See VLM.md.

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

REPO = Path(__file__).resolve().parents[2]
SERVER_SH = REPO / "mac" / "ui_tars_server.sh"


def _env(name: str, default: str) -> str:
    stay = os.environ.get("STAYTURGID_" + name)
    if stay is not None and str(stay).strip() != "":
        return str(stay).strip()
    qss = os.environ.get("QSS_" + name)
    if qss is not None and str(qss).strip() != "":
        return str(qss).strip()
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
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def ensure_server(start: bool = True) -> bool:
    if server_healthy():
        return True
    if not start or not SERVER_SH.is_file():
        return False
    subprocess.run(["bash", str(SERVER_SH)], check=False, timeout=200)
    deadline = time.time() + 200
    while time.time() < deadline:
        if server_healthy():
            return True
        time.sleep(1)
    return False


def _model_id() -> str:
    try:
        req = urllib.request.Request(_base_url() + "/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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


class VlmGate:
    """Vision verification gate using local UI-TARS."""

    def __init__(self, *, autostart: bool = True) -> None:
        self.ready = False
        if not vlm_enabled():
            return
        self.ready = ensure_server(start=autostart)

    def verify(
        self,
        image_path: Path,
        check: str,
        *,
        min_confidence: float = 0.55,
        custom_prompt: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.ready:
            skipped: dict[str, Any] = {"skipped": True, "reason": "vlm_unavailable"}
            if vlm_strict() and vlm_enabled():
                skipped["ok"] = False
                return False, skipped
            return True, skipped
        prompt = custom_prompt or CHECK_PROMPTS.get(check)
        if not prompt:
            return True, {"skipped": True, "reason": "unknown_check"}
        t0 = time.time()
        raw, parsed = ask_image(image_path, prompt)
        elapsed = time.time() - t0
        detail: dict[str, Any] = {
            "check": check,
            "raw": raw,
            "parsed": parsed,
            "elapsed_s": round(elapsed, 1),
        }
        if not parsed:
            detail["ok"] = False
            detail["reason"] = "unparseable_response"
            return False, detail
        ok = bool(parsed.get("ok"))
        conf = float(parsed.get("confidence", 0.8 if ok else 0.2))
        detail["confidence"] = conf
        if check == "play_autoupdate_dont" and ok:
            setting = str(parsed.get("setting", "unknown")).lower()
            ok = setting in ("dont_auto_update", "don't_auto_update", "dont")
            detail["setting"] = setting
        if check == "no_gms_crash_dialog":
            ok = bool(parsed.get("ok")) and not bool(parsed.get("crash_visible", False))
        if ok and conf < min_confidence:
            ok = False
            detail["reason"] = "low_confidence"
        detail["ok"] = ok
        return ok, detail

    def require(self, image_path: Path, check: str, label: str = "") -> bool:
        ok, detail = self.verify(image_path, check)
        if not detail.get("skipped") and not ok:
            tag = label or check
            note = detail.get("parsed", {}) or {}
            notes = note.get("notes", detail.get("reason", ""))
            print(
                "VLM BLOCK %s: %s (%.1fs)"
                % (tag, notes, detail.get("elapsed_s", 0)),
                flush=True,
            )
        return ok
