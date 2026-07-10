#!/usr/bin/env python3
"""Periodically compare RevengeQuickSwitcher VLM.md for useful best-practice deltas.

Upstream (sibling project, not vendored)::

  ~/src/RevengeQuickSwitcher/VLM.md

State + reports (operator-local)::

  ~/.config/stayturgid/state/vlm-upstream/
  ~/.config/stayturgid/logs/vlm-upstream-check.log

Exit codes:
  0 — no change (or first snapshot only)
  1 — upstream changed (report written)
  2 — upstream missing / error

Usage:
  python3 control/bin/vlm_upstream_check.py
  python3 control/bin/vlm_upstream_check.py --notify   # macOS notification on change
  python3 control/bin/vlm_upstream_check.py --force    # rewrite report even if hash same
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_UPSTREAM = Path.home() / "src" / "RevengeQuickSwitcher" / "VLM.md"
STATE_DIR = Path.home() / ".config" / "stayturgid" / "state" / "vlm-upstream"
LOG = Path.home() / ".config" / "stayturgid" / "logs" / "vlm-upstream-check.log"
HASH_FILE = STATE_DIR / "last.sha256"
SNAPSHOT = STATE_DIR / "last.VLM.md"
REPORT = STATE_DIR / "last_report.md"
STAY_VLM_DOC = Path(__file__).resolve().parents[2] / "docs" / "vlm.md"

# Sections / patterns worth flagging for stayturgid agents.
WATCH_PATTERNS = [
    (r"(?im)^## Hybrid local \+ cloud.*", "Hybrid local + cloud section"),
    (r"(?im)^### Verified model IDs.*", "Verified model IDs"),
    (r"(?im)^### Best practices for Android screenshots.*", "Android screenshot best practices"),
    (r"(?im)^### Device state before blaming VLM.*", "Device state before blaming VLM"),
    (r"(?im)^### Local-first with cloud retry.*", "Local-first cloud retry"),
    (r"(?im)^### Screen-control lease.*", "Screen-control lease (DSCL)"),
    (r"(?im)gemini-[a-z0-9.\-]+", "Gemini model id mentions"),
    (r"(?im)claude-[a-z0-9.\-]+", "Claude model id mentions"),
    (r"(?im)gpt-4o[a-z0-9.\-]*", "OpenAI model id mentions"),
    (r"(?im)QSS_VLM_[A-Z0-9_]+", "QSS_VLM_* env vars"),
    (r"(?im)temperature|max_tokens|maxOutputTokens|sips -Z", "Inference/image knobs"),
]


def ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = "%s  %s\n" % (ts(), msg)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    print(line, end="")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_hits(text: str) -> list[tuple[str, list[str]]]:
    hits: list[tuple[str, list[str]]] = []
    for pattern, label in WATCH_PATTERNS:
        found = re.findall(pattern, text)
        if not found:
            continue
        # For full-section regexes, keep first match snippet only.
        snippets: list[str] = []
        for m in found[:8]:
            s = m if isinstance(m, str) else str(m)
            s = s.strip()
            if len(s) > 240:
                s = s[:237] + "..."
            if s and s not in snippets:
                snippets.append(s)
        if snippets:
            hits.append((label, snippets))
    return hits


def new_model_ids(prev: str, cur: str) -> list[str]:
    def ids(t: str) -> set[str]:
        out = set()
        out |= set(re.findall(r"gemini-[a-z0-9.\-]+", t, re.I))
        out |= set(re.findall(r"claude-[a-z0-9.\-]+", t, re.I))
        out |= set(re.findall(r"gpt-4o[a-z0-9.\-]*", t, re.I))
        return {x.lower() for x in out}

    return sorted(ids(cur) - ids(prev))


def write_report(
    *,
    upstream: Path,
    digest: str,
    changed: bool,
    hits: list[tuple[str, list[str]]],
    new_ids: list[str],
    prev_digest: str | None,
) -> str:
    lines = [
        "# VLM upstream check report",
        "",
        "- Checked at: `%s`" % ts(),
        "- Upstream: `%s`" % upstream,
        "- SHA-256: `%s`" % digest,
        "- Previous: `%s`" % (prev_digest or "(none)"),
        "- Changed: **%s**" % ("yes" if changed else "no"),
        "- stayturgid doc: `%s`" % STAY_VLM_DOC,
        "",
    ]
    if new_ids:
        lines.append("## New model id strings vs previous snapshot")
        lines.append("")
        for mid in new_ids:
            lines.append("- `%s`" % mid)
        lines.append("")
    if hits:
        lines.append("## Watched topics present in upstream")
        lines.append("")
        for label, snippets in hits:
            lines.append("### %s" % label)
            for s in snippets:
                lines.append("- %s" % s.replace("\n", " ")[:200])
            lines.append("")
    lines.append("## Agent action checklist")
    lines.append("")
    lines.append("1. Read upstream `Hybrid local + cloud` + `Verified model IDs`.")
    lines.append("2. Compare defaults in `control/lib/vlm_cloud.py` / `docs/vlm.md`.")
    lines.append("3. Prefer `-latest` Gemini aliases when they return usable JSON;")
    lines.append("   keep a known-good pinned fallback (currently `gemini-3.1-flash-lite`).")
    lines.append("4. Port capture/prompt best practices into stayturgid docs if missing.")
    lines.append("5. Do **not** copy Discord-specific checks; adapt principles only.")
    lines.append("")
    return "\n".join(lines)


def notify(title: str, message: str) -> None:
    try:
        message = message.replace("\\", "\\\\").replace('"', '\\"')
        title = title.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            [
                "osascript",
                "-e",
                'display notification "%s" with title "%s"' % (message, title),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--upstream",
        default=os.environ.get("STAYTURGID_VLM_UPSTREAM", str(DEFAULT_UPSTREAM)),
        help="Path to RevengeQuickSwitcher VLM.md",
    )
    ap.add_argument("--notify", action="store_true", help="macOS notify on change")
    ap.add_argument("--force", action="store_true", help="Rewrite report even if unchanged")
    args = ap.parse_args(argv)

    upstream = Path(args.upstream).expanduser()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not upstream.is_file():
        log("ERROR: upstream missing: %s" % upstream)
        return 2

    try:
        text = upstream.read_text(encoding="utf-8")
    except OSError as e:
        log("ERROR: read failed: %s" % e)
        return 2

    digest = sha256_text(text)
    prev = HASH_FILE.read_text(encoding="utf-8").strip() if HASH_FILE.is_file() else None
    prev_text = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.is_file() else ""
    changed = prev != digest

    hits = extract_hits(text)
    new_ids = new_model_ids(prev_text, text) if prev_text else sorted(
        set(re.findall(r"(?:gemini|claude|gpt-4o)[a-z0-9.\-]*", text, re.I))
    )[:20]

    report = write_report(
        upstream=upstream,
        digest=digest,
        changed=changed,
        hits=hits,
        new_ids=new_ids if changed or args.force else [],
        prev_digest=prev,
    )

    if changed or args.force or not REPORT.is_file():
        REPORT.write_text(report, encoding="utf-8")
        SNAPSHOT.write_text(text, encoding="utf-8")
        HASH_FILE.write_text(digest + "\n", encoding="utf-8")

    if not changed and not args.force:
        log("ok unchanged sha=%s… hits=%d" % (digest[:12], len(hits)))
        print("No change in %s" % upstream)
        print("Report: %s" % REPORT)
        return 0

    log(
        "CHANGED sha=%s… → %s… new_model_ids=%d watch_hits=%d"
        % ((prev or "none")[:12], digest[:12], len(new_ids), len(hits))
    )
    print(report)
    print("Wrote %s" % REPORT)
    if args.notify:
        notify(
            "stayturgid VLM upstream",
            "RevengeQuickSwitcher/VLM.md changed — review %s" % REPORT.name,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
