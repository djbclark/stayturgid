#!/usr/bin/env python3
"""Cloud VLM backends for stayturgid screenshot gates (Gemini + Claude).

API keys load from env, then (if unset) from operator-local files **outside git**::

  ~/.config/stayturgid/gemini.env      # GEMINI_API_KEY=...
  ~/.config/stayturgid/anthropic.env   # ANTHROPIC_API_KEY=...
  ~/.config/stayturgid/vlm-cloud.env   # optional combined file

Never commit those files. Prefer separate one-key-per-file layout.

Escalation policy (used by vlm_gate.VlmGate):
  local UI-TARS first (when available) → Gemini Flash on fail/low conf/unavailable
  → Claude Sonnet as second cloud opinion when Gemini fails or conf is low.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

CONFIG_DIR = Path.home() / ".config" / "stayturgid"
GEMINI_ENV = CONFIG_DIR / "gemini.env"
ANTHROPIC_ENV = CONFIG_DIR / "anthropic.env"
COMBINED_ENV = CONFIG_DIR / "vlm-cloud.env"

# Working defaults as of 2026-07 (probed against live keys).
# Prefer a known-good Flash Lite over -latest when the alias burns tokens on
# "thinking" and returns empty parts under low maxOutputTokens. Override with
# STAYTURGID_GEMINI_MODEL=gemini-flash-latest if desired (see RQS VLM.md).
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
# Escalation / second opinion — full Sonnet with vision (no temperature param).
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
# Cheaper Claude option documented for bulk gates (set STAYTURGID_CLAUDE_MODEL).
DEFAULT_CLAUDE_CHEAP_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_TIMEOUT = 90
DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 1024


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def load_cloud_keys() -> None:
    """Load operator key files into os.environ (setdefault — env wins)."""
    _load_env_file(COMBINED_ENV)
    _load_env_file(GEMINI_ENV)
    _load_env_file(ANTHROPIC_ENV)


def cloud_mode() -> str:
    """off | auto | gemini | claude | both."""
    raw = (
        (os.environ.get("STAYTURGID_VLM_CLOUD") or os.environ.get("STAYTURGID_VLM_CLOUD_BACKEND") or "auto")
        .strip()
        .lower()
    )
    if raw in ("0", "false", "no", "off", "none"):
        return "off"
    if raw in ("1", "true", "yes", "on"):
        return "auto"
    return raw


def cloud_enabled() -> bool:
    load_cloud_keys()
    if cloud_mode() == "off":
        return False
    return bool(gemini_key() or anthropic_key())


def escalate_enabled() -> bool:
    """When true, cloud runs if local fails / low conf / unavailable."""
    raw = os.environ.get("STAYTURGID_VLM_CLOUD_ESCALATE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def gemini_key() -> str:
    load_cloud_keys()
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_GENAI_API_KEY")
        or ""
    ).strip()


def anthropic_key() -> str:
    load_cloud_keys()
    return (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()


def gemini_model() -> str:
    return (
        os.environ.get("STAYTURGID_GEMINI_MODEL") or os.environ.get("GEMINI_VLM_MODEL") or DEFAULT_GEMINI_MODEL
    ).strip()


def claude_model() -> str:
    return (
        os.environ.get("STAYTURGID_CLAUDE_MODEL") or os.environ.get("ANTHROPIC_VLM_MODEL") or DEFAULT_CLAUDE_MODEL
    ).strip()


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    # Strip markdown fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _encode_png(path: Path, prepare: Callable[[Path], Path] | None = None) -> tuple[str, str]:
    """Return (mime, base64). Optionally prepare/downscale via *prepare*."""
    p = prepare(path) if prepare else path
    data = p.read_bytes()
    # sips/prepare may keep png; sniff jpeg
    mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
    return mime, base64.b64encode(data).decode("ascii")


def ask_gemini(
    path: Path,
    prompt: str,
    *,
    timeout: int | None = None,
    prepare: Callable[[Path], Path] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    key = gemini_key()
    if not key:
        return "", None
    timeout = timeout or DEFAULT_TIMEOUT
    mime, b64 = _encode_png(path, prepare)
    model = gemini_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            # Thinking models (e.g. gemini-3.5-flash via -latest) spend tokens on
            # internal thoughts; keep headroom so JSON answers still appear.
            "maxOutputTokens": int(
                os.environ.get(
                    "STAYTURGID_GEMINI_MAX_OUTPUT_TOKENS",
                    str(DEFAULT_GEMINI_MAX_OUTPUT_TOKENS),
                )
            ),
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
        payload = json.loads(resp.read().decode("utf-8"))
    raw = ""
    try:
        parts = payload["candidates"][0]["content"].get("parts") or []
        # Skip thought-only parts if present; keep text parts.
        texts = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            if p.get("thought"):
                continue
            if p.get("text"):
                texts.append(str(p["text"]))
        raw = "".join(texts)
    except (KeyError, IndexError, TypeError):
        raw = json.dumps(payload)
    return raw, _parse_json_blob(raw)


def ask_claude(
    path: Path,
    prompt: str,
    *,
    timeout: int | None = None,
    prepare: Callable[[Path], Path] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    key = anthropic_key()
    if not key:
        return "", None
    timeout = timeout or DEFAULT_TIMEOUT
    mime, b64 = _encode_png(path, prepare)
    media = "image/jpeg" if "jpeg" in mime else "image/png"
    body = {
        "model": claude_model(),
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep
        payload = json.loads(resp.read().decode("utf-8"))
    raw = ""
    try:
        blocks = payload.get("content") or []
        raw = "".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict))
    except (KeyError, TypeError):
        raw = json.dumps(payload)
    return raw, _parse_json_blob(raw)


def backends_available() -> list[str]:
    mode = cloud_mode()
    out: list[str] = []
    if mode in ("auto", "both", "gemini") and gemini_key():
        out.append("gemini")
    if mode in ("auto", "both", "claude") and anthropic_key():
        out.append("claude")
    if mode == "gemini" and "gemini" not in out and gemini_key():
        out.append("gemini")
    if mode == "claude" and "claude" not in out and anthropic_key():
        out.append("claude")
    return out


def ask_cloud(
    path: Path,
    prompt: str,
    *,
    prefer: str | None = None,
    timeout: int | None = None,
    prepare: Callable[[Path], Path] | None = None,
) -> tuple[str, dict[str, Any] | None, str]:
    """Try cloud backends in order. Returns (raw, parsed, backend_name)."""
    order = backends_available()
    if prefer == "claude" and "claude" in order:
        order = ["claude"] + [b for b in order if b != "claude"]
    elif prefer == "gemini" and "gemini" in order:
        order = ["gemini"] + [b for b in order if b != "gemini"]

    last_raw = ""
    last_parsed: dict[str, Any] | None = None
    last_name = ""
    for name in order:
        try:
            if name == "gemini":
                raw, parsed = ask_gemini(path, prompt, timeout=timeout, prepare=prepare)
            else:
                raw, parsed = ask_claude(path, prompt, timeout=timeout, prepare=prepare)
            last_raw, last_parsed, last_name = raw, parsed, name
            if parsed is not None:
                return raw, parsed, name
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, json.JSONDecodeError) as e:
            last_raw = f"{name}_error:{e}"
            last_name = name
            continue
    return last_raw, last_parsed, last_name


def ping_backends() -> dict[str, Any]:
    """Text-only health check for stored keys (no image)."""
    load_cloud_keys()
    out: dict[str, Any] = {
        "gemini_key": bool(gemini_key()),
        "claude_key": bool(anthropic_key()),
        "gemini_model": gemini_model(),
        "claude_model": claude_model(),
    }
    # Gemini text
    if gemini_key():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model()}:generateContent"
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": 'Reply exactly: {"ok":true,"ping":"gemini"}'}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 64},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": gemini_key(),
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosemgrep
                payload = json.loads(resp.read().decode())
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            out["gemini"] = {"ok": True, "text": text[:120]}
        except Exception as e:
            out["gemini"] = {"ok": False, "error": str(e)[:200]}
    else:
        out["gemini"] = {"ok": False, "error": "no_key"}

    if anthropic_key():
        body = {
            "model": claude_model(),
            "max_tokens": 64,
            "messages": [
                {
                    "role": "user",
                    "content": 'Reply exactly: {"ok":true,"ping":"claude"}',
                }
            ],
        }
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": anthropic_key(),
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosemgrep
                payload = json.loads(resp.read().decode())
            text = payload["content"][0]["text"]
            out["claude"] = {"ok": True, "text": text[:120]}
        except Exception as e:
            out["claude"] = {"ok": False, "error": str(e)[:200]}
    else:
        out["claude"] = {"ok": False, "error": "no_key"}
    return out
