#!/usr/bin/env python3
"""Network landing page — single page with links to all web services.

Serves on port 8088 (must not collide with Caddy health on 8080). Reads static
definitions from services.json and generated state from the user-local landing
state file. Supports HTMX-based hide/show for unreachable services and
on-demand rescan.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_TEMPLATES = _HERE / "templates"

sys.path.insert(0, str(_REPO))
from flask import Flask, render_template_string, request

from control.landing import state  # noqa: E402

PORT = 8088  # Phase D4: was 8080 (collided with caddy-health); plists pass --port 8088
app = Flask(__name__, template_folder=str(_TEMPLATES))


def _load_services() -> list[dict]:
    return state.load_state().get("services", [])


def _load_hidden() -> list[str]:
    return state.load_state().get("hidden", [])


def _load_last_scan() -> str:
    return state.load_state().get("last_scan", "")


def _save_hidden(hidden: list[str]) -> None:
    data = state.load_state()
    data["hidden"] = sorted(set(hidden))
    try:
        state.write_state(data)
    except OSError:
        pass


def _render(name: str, **ctx) -> str:
    f = _TEMPLATES / name
    if f.is_file():
        return render_template_string(f.read_text(), **ctx)
    return f"<!-- {name} not found -->"


@app.route("/")
def index():
    services = _load_services()
    _load_hidden()
    last_scan = _load_last_scan()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    mac_services = [s for s in services if s.get("group") == "mac"]
    device_services = [s for s in services if s.get("group") == "devices"]
    other_services = [s for s in services if s.get("group") not in ("mac", "devices")]

    return _render(
        "index.html",
        mac_services=mac_services,
        device_services=device_services,
        other_services=other_services,
        last_scan=last_scan,
        now=now,
    )


@app.route("/hide", methods=["POST"])
def hide():
    url = request.form.get("url", "")
    if url:
        hidden = _load_hidden()
        if url not in hidden:
            hidden.append(url)
        _save_hidden(hidden)
    return "", 204


@app.route("/rescan", methods=["POST"])
def rescan():
    script = _HERE / "discover.py"
    try:
        subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "", 204


@app.route("/health")
def health():
    return "ok", 200, {"Content-Type": "text/plain"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Network landing page")
    ap.add_argument("--port", type=int, default=PORT, help=f"Listen port (default: {PORT})")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    app.run(host="127.0.0.1", port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
