#!/usr/bin/env python3
"""Validate the stayturgid site identity and check for configuration drift.

Operators: run after editing ``ansible/inventory/hosts.yml`` or before
any fleet deploy to catch divergence between declared and hard-coded
identity.

    python3 control/bin/validate_site_identity.py
    python3 control/bin/validate_site_identity.py --check-drift
    python3 control/bin/validate_site_identity.py --check-secrets
    python3 control/bin/validate_site_identity.py --host s24
    python3 control/bin/validate_site_identity.py --json

Exit codes:
    0   All checks passed.
    1   One or more violations found.
    2   Configuration / environment error (missing inventory, binary, etc.).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root discovery (same logic as site_identity.py — no shared import needed)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent


def _find_repo_root() -> Path:
    p = _HERE
    while p != p.parent:
        if (p / "device" / "termux").is_dir() and (p / "control" / "lib").is_dir():
            return p
        p = p.parent
    raise RuntimeError(f"Cannot find repo root (walked up from {_HERE})")


# ---------------------------------------------------------------------------
# Load site_identity from sibling lib/
# ---------------------------------------------------------------------------


def _load_si():
    root = _find_repo_root()
    lib = root / "control" / "lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    import site_identity as _si  # noqa: PLC0415

    return _si


# ---------------------------------------------------------------------------
# Drift scanner
# ---------------------------------------------------------------------------

# File extensions to scan for hardcoded literals
_SCAN_EXTS = {".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".j2", ".conf", ".cfg"}

# Paths to skip entirely (relative to repo root); exact prefix match
_SKIP_PREFIXES = (
    "ansible/inventory/",  # SSOT — literals here are correct
    "tests/",  # test fixtures intentionally use literals
    "docs/",  # documentation
    "examples/",  # example configs
    ".ansible/",  # downloaded collections
    "node_modules/",
    ".venv",
    "__pycache__",
    ".git/",
)

# Also skip files whose name matches these patterns
_SKIP_FILENAME_RE = re.compile(r"(session-.*\.md|devices\.conf\.example|hosts\.yml\.example)$")


def _should_skip(rel: str) -> bool:
    if any(rel.startswith(p) for p in _SKIP_PREFIXES):
        return True
    return bool(_SKIP_FILENAME_RE.search(rel))


def _build_drift_patterns(site) -> list[tuple[str, str]]:
    """Return (pattern, description) pairs for every production literal."""
    patterns: list[tuple[str, str]] = []

    for alias, dev in site.devices.items():
        # Device alias as a standalone word (not part of e.g. "s24ultra")
        patterns.append((rf"\b{re.escape(alias)}\b", f"device alias '{alias}'"))

        # Tailscale / management IP
        if dev.ansible_host and dev.ansible_host != "-":
            ip_esc = re.escape(dev.ansible_host)
            patterns.append((ip_esc, f"ansible_host IP '{dev.ansible_host}' ({alias})"))

        # USB serial
        if dev.device_usb_serial and dev.device_usb_serial != "-":
            patterns.append(
                (
                    re.escape(dev.device_usb_serial),
                    f"USB serial '{dev.device_usb_serial}' ({alias})",
                )
            )

        # LAN IP
        if dev.device_lan_ip and dev.device_lan_ip != "-":
            ip_esc = re.escape(dev.device_lan_ip)
            patterns.append((ip_esc, f"LAN IP '{dev.device_lan_ip}' ({alias})"))

    # Control node
    cn = site.control_node
    if cn.lan_ip:
        patterns.append((re.escape(cn.lan_ip), f"control node LAN IP '{cn.lan_ip}'"))
    if cn.tailscale_ip:
        patterns.append((re.escape(cn.tailscale_ip), f"control node Tailscale IP '{cn.tailscale_ip}'"))

    return patterns


def check_drift(site, root: Path) -> list[dict]:
    """Scan tracked source files for hardcoded production literals.

    Returns a list of violation dicts:
        {file, line, pattern_desc, excerpt}
    """
    compiled = [(re.compile(pat), desc) for pat, desc in _build_drift_patterns(site)]
    violations: list[dict] = []

    # Use git ls-files for tracked files only (fast, honours .gitignore)
    import subprocess

    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        # Fallback: walk the tree
        tracked = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.suffix in _SCAN_EXTS]
    else:
        tracked = [
            f.strip() for f in result.stdout.splitlines() if f.strip() and Path(root / f.strip()).suffix in _SCAN_EXTS
        ]

    for rel in tracked:
        if _should_skip(rel):
            continue
        fpath = root / rel
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rx, desc in compiled:
                if rx.search(line):
                    violations.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "pattern": desc,
                            "excerpt": line.strip()[:120],
                        }
                    )
                    break  # one violation per line is enough

    return violations


# ---------------------------------------------------------------------------
# Secrets scanner
# ---------------------------------------------------------------------------

# Patterns that suggest a secret leaked into the inventory
_SECRET_RE = re.compile(
    r"""
    # Telegram bot token
    \d{8,10}:[A-Za-z0-9_-]{35,}
    |
    # Generic long base64/hex blob (40+ chars)
    (?<![/\w])[A-Za-z0-9+/]{40,}={0,2}(?![/\w])
    |
    # SSH private key header
    -----BEGIN\s+(?:RSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----
    """,
    re.VERBOSE,
)

# Lines in the inventory that are expected to contain long-ish strings
_ALLOW_LINE_RE = re.compile(
    r"""
    ansible_ssh_public_key      # public key — OK
    | device_label              # human label
    | device_usb_serial         # serial numbers, not secrets
    | stayturgid_automation_mode
    """,
    re.VERBOSE,
)


def check_secrets(inventory_path: Path) -> list[dict]:
    """Scan the inventory YAML for secret-shaped strings.

    Returns a list of finding dicts: {file, line, excerpt}
    """
    findings: list[dict] = []
    try:
        text = inventory_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"file": str(inventory_path), "line": 0, "excerpt": str(exc)}]

    for lineno, line in enumerate(text.splitlines(), start=1):
        if _ALLOW_LINE_RE.search(line):
            continue
        if _SECRET_RE.search(line):
            findings.append(
                {
                    "file": str(inventory_path),
                    "line": lineno,
                    "excerpt": line.strip()[:120],
                }
            )
    return findings


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _print_site_summary(site, host_filter: str | None) -> None:
    devices = {host_filter: site.devices[host_filter]} if host_filter else site.devices
    print(f"Site identity — {len(site.devices)} device(s) declared\n")
    for alias, dev in sorted(devices.items()):
        print(f"  {alias}")
        print(f"    ansible_host          : {dev.ansible_host}")
        print(f"    ansible_port          : {dev.ansible_port}")
        print(f"    ansible_user          : {dev.ansible_user}")
        print(f"    device_label          : {dev.device_label}")
        print(f"    device_usb_serial     : {dev.device_usb_serial}")
        print(f"    device_lan_ip         : {dev.device_lan_ip}")
        print(f"    automation_mode       : {dev.stayturgid_automation_mode}")
    cn = site.control_node
    print("\n  control_node")
    print(f"    ssh_user              : {cn.ssh_user}")
    print(f"    lan_ip                : {cn.lan_ip}")
    print(f"    tailscale_ip          : {cn.tailscale_ip}")
    print()


def _print_drift(violations: list[dict], json_out: bool) -> None:
    if json_out:
        return  # handled by caller
    if not violations:
        print("drift: OK — no hardcoded production literals found in source")
        return
    print(f"drift: FAIL — {len(violations)} violation(s) found\n")
    for v in violations:
        print(f"  {v['file']}:{v['line']}  [{v['pattern']}]")
        print(f"    {v['excerpt']}")
    print()


def _print_secrets(findings: list[dict], json_out: bool) -> None:
    if json_out:
        return
    if not findings:
        print("secrets: OK — no secret-shaped strings in inventory")
        return
    print(f"secrets: FAIL — {len(findings)} potential secret(s) in inventory\n")
    for f in findings:
        print(f"  {f['file']}:{f['line']}")
        print(f"    {f['excerpt']}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        metavar="ALIAS",
        help="Print identity for a single host alias and exit 0.",
    )
    parser.add_argument(
        "--check-drift",
        action="store_true",
        help="Scan tracked source files for hardcoded production literals.",
    )
    parser.add_argument(
        "--check-secrets",
        action="store_true",
        help="Scan hosts.yml for secret-shaped strings.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass the identity cache and re-run ansible-inventory.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print violations but always exit 0 (advisory / pre-Phase-2 mode).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Emit all output as a JSON object.",
    )
    args = parser.parse_args()

    try:
        root = _find_repo_root()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    si = _load_si()

    inventory_path = root / "ansible" / "inventory" / "hosts.yml"

    # ---- Load site identity ----
    try:
        site = si.load_site_identity(
            force_refresh=args.force_refresh,
            inventory_path=inventory_path,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if args.warn_only:
            print("identity: WARN — inventory is unavailable (warn-only mode)")
            return 0
        return 2
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if args.warn_only:
            print("identity: WARN — inventory could not be loaded (warn-only mode)")
            return 0
        return 2
    except ValueError as exc:
        print(f"INVALID inventory: {exc}", file=sys.stderr)
        if args.warn_only:
            print("identity: WARN — inventory is incomplete (warn-only mode)")
            return 0
        return 1

    # ---- Single host mode ----
    if args.host:
        if args.host not in site.devices:
            known = ", ".join(sorted(site.devices.keys()))
            print(
                f"ERROR: unknown host '{args.host}'. Known: {known}",
                file=sys.stderr,
            )
            return 2
        if args.json_out:
            from dataclasses import asdict

            print(json.dumps(asdict(site.devices[args.host]), indent=2))
        else:
            _print_site_summary(site, args.host)
        return 0

    # ---- Default: print validated site summary ----
    exit_code = 0
    drift_violations: list[dict] = []
    secret_findings: list[dict] = []

    if args.check_drift:
        drift_violations = check_drift(site, root)
        if drift_violations:
            exit_code = 1

    if args.check_secrets:
        secret_findings = check_secrets(inventory_path)
        if secret_findings:
            exit_code = 1

    if args.json_out:
        from dataclasses import asdict

        output = {
            "valid": exit_code == 0,
            "warn_only": args.warn_only,
            "site": {
                "devices": {a: asdict(d) for a, d in site.devices.items()},
                "control_node": asdict(site.control_node),
                "telegram_allowed_users": list(site.telegram_allowed_users),
                "telegram_home_channel": site.telegram_home_channel,
            },
        }
        if args.check_drift:
            output["drift_violations"] = drift_violations
        if args.check_secrets:
            output["secret_findings"] = secret_findings
        print(json.dumps(output, indent=2))
        return 0 if args.warn_only else exit_code

    # Human-readable output
    _print_site_summary(site, None)
    if args.check_drift:
        _print_drift(drift_violations, args.json_out)
    if args.check_secrets:
        _print_secrets(secret_findings, args.json_out)

    if exit_code == 0 and not args.check_drift and not args.check_secrets:
        print("identity: OK — inventory is valid and complete")

    if exit_code != 0 and args.warn_only:
        n = len(drift_violations) + len(secret_findings)
        print(
            f"identity: WARN — {n} violation(s) found (warn-only mode; "
            "run without --warn-only for hard exit — Phase 2 will fix these)"
        )
        return 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
