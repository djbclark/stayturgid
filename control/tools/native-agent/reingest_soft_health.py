#!/usr/bin/env python3
"""Re-post soft_health.jsonl to OpenObserve (catch-up after outages / bad auth).

Vector is the live path; this is the manual / recovery path when:
  - OpenObserve was down for days and sink buffer was cleared
  - 401 Unauthorized dropped events (Vector treats auth as non-retriable)
  - operator wants to re-seed the ``soft_health`` stream from disk SSOT

Never deletes or truncates the JSONL. Skips corrupt lines. Batches POSTs with
retries on 5xx / connection errors (not on permanent 4xx except 429).

Usage:
  ./reingest_soft_health.py
  ./reingest_soft_health.py --since 2026-07-20T00:00:00Z
  ./reingest_soft_health.py --dry-run
  OPENOBSERVE_ROOT_EMAIL=… OPENOBSERVE_ROOT_PASSWORD=… ./reingest_soft_health.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "control" / "lib"))
import stats  # noqa: E402

DEFAULT_URI = "http://127.0.0.1:5080/oo/api/default/soft_health/_json"
BATCH = 50
MAX_ATTEMPTS = 12


def _post_batch(uri: str, user: str, password: str, rows: list[dict]) -> None:
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        uri,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    # basic auth
    import base64

    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # URI is default localhost OO or operator --uri; not untrusted web input.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urllib.request.urlopen(req, timeout=60) as resp:
                if 200 <= resp.status < 300:
                    return
                raise RuntimeError(f"HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            last_err = e
            # 401/403 — do not spin forever; operator must fix creds
            if e.code in (401, 403):
                raise SystemExit(
                    f"OpenObserve auth failed HTTP {e.code}. "
                    "Set OPENOBSERVE_ROOT_EMAIL / OPENOBSERVE_ROOT_PASSWORD "
                    "(and Vector launchd EnvironmentVariables)."
                ) from e
            if e.code == 429 or e.code >= 500:
                time.sleep(min(60, 2**attempt))
                continue
            raise SystemExit(f"OpenObserve rejected batch HTTP {e.code}: {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(min(60, 2**attempt))
    raise SystemExit(f"gave up after {MAX_ATTEMPTS} attempts: {last_err}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--uri", default=os.environ.get("SOFT_HEALTH_OO_URI", DEFAULT_URI))
    p.add_argument("--since", default=None, help="ISO ts inclusive, e.g. 2026-07-20T00:00:00Z")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--file", type=Path, default=None, help="override soft_health.jsonl path")
    args = p.parse_args(argv)

    path = args.file or stats.soft_health_path()
    if not path.is_file():
        print(f"no file: {path}")
        return 0

    user = os.environ.get("OPENOBSERVE_ROOT_EMAIL", "")
    password = os.environ.get("OPENOBSERVE_ROOT_PASSWORD", "")
    if not args.dry_run and not user:
        print("OPENOBSERVE_ROOT_EMAIL unset", file=sys.stderr)
        return 2

    batch: list[dict] = []
    ok = 0
    skipped = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(ev, dict):
                skipped += 1
                continue
            if args.since and str(ev.get("ts") or "") < args.since:
                continue
            batch.append(ev)
            if len(batch) >= BATCH:
                if args.dry_run:
                    ok += len(batch)
                else:
                    _post_batch(args.uri, user, password, batch)
                    ok += len(batch)
                batch = []
    if batch:
        if args.dry_run:
            ok += len(batch)
        else:
            _post_batch(args.uri, user, password, batch)
            ok += len(batch)

    print(f"{'dry-run ' if args.dry_run else ''}posted={ok} skipped_corrupt={skipped} file={path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
