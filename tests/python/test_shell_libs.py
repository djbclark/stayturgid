"""Unit tests for legacy bash helpers in shared/mac/ (sourced libs, not twins)."""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _bash_eval(script: Path, body: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", f'source "{script}"\n{body}'],
        capture_output=True,
        text=True,
        env=merged,
        check=False,
    )


def test_stayturgid_root_finds_repo():
    script = REPO / "shared/mac/stayturgid-root.sh"
    nested = REPO / "mac/deploy_fleet.py"
    r = _bash_eval(script, f'ROOT="$(stayturgid_root "{nested}")" && echo "$ROOT"')
    assert r.returncode == 0
    assert r.stdout.strip() == str(REPO)


def test_stayturgid_root_errors_outside_repo(tmp_path):
    script = REPO / "shared/mac/stayturgid-root.sh"
    orphan = tmp_path / "nowhere/caller.sh"
    orphan.parent.mkdir(parents=True)
    orphan.touch()
    r = _bash_eval(script, f'stayturgid_root "{orphan}"', {"HOME": str(tmp_path)})
    assert r.returncode != 0
    assert "repo root not found" in r.stderr


def test_resolve_adb_usb_tailscale_and_dash_ts(tmp_path):
    script = REPO / "shared/mac/resolve-adb.sh"
    conf = tmp_path / "devices.conf"
    conf.write_text(
        "s24 RFCX 100.123 192.168.68.55\n"
        "hd8 - 100.200.1.2 -\n"
        "p7a - - 192.168.1.9\n"
    )

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    adb = stubs / "adb"
    adb.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "devices" ]; then printf "RFCX\\tdevice\\n"; fi\n'
        "exit 0\n"
    )
    adb.chmod(0o755)
    env = {
        "PATH": f"{stubs}:{os.environ.get('PATH', '')}",
        "STAYTURGID_DEVICES_CONF": str(conf),
    }

    # USB connected -> serial
    conf.write_text("s24 RFCX 100.123 192.168.68.55\n")
    r = _bash_eval(script, 'resolve_adb s24', env)
    assert r.stdout.strip() == "RFCX"

    # Not connected -> tailscale
    adb.write_text("#!/usr/bin/env bash\nexit 0\n")
    adb.chmod(0o755)
    r = _bash_eval(script, 'resolve_adb s24', env)
    assert r.stdout.strip() == "100.123:5555"

    # ts=- with no USB must not emit "-:5555" (quoting/field guard)
    conf.write_text("s24 RFCX - -\n")
    r = _bash_eval(script, 'resolve_adb s24', env)
    assert r.stdout.strip() == "s24"

    # lan fallback when tailscale missing
    conf.write_text("p7a - - 192.168.1.9\n")
    r = _bash_eval(script, 'resolve_adb p7a', env)
    assert r.stdout.strip() == "192.168.1.9:5555"

    # unknown alias passes through
    r = _bash_eval(script, 'resolve_adb raw:5555', env)
    assert r.stdout.strip() == "raw:5555"

    r = _bash_eval(script, 'resolve_ssh_host p7a', env)
    assert r.stdout.strip() == "p7a"
    r = _bash_eval(script, 'resolve_ssh_host raw:5555', env)
    assert r.stdout.strip() == ""


def test_gplaycli_wrapper_sets_pythonpath(tmp_path, monkeypatch):
    """Smoke: gplaycli.sh prepends pip vendor before exec (no real gplaycli needed)."""
    script = REPO / "play/mac/gplaycli.sh"
    fake_py = tmp_path / "python3.14"
    fake_py.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in -c) echo "/fake/pip"; exit 0 ;; -m) echo "MODULE:$PYTHONPATH"; exit 0 ;; esac\n'
        "exit 1\n"
    )
    fake_py.chmod(0o755)
    r = subprocess.run(
        [str(script), "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "GPLAYCLI_PYTHON": str(fake_py)},
        check=False,
    )
    assert r.returncode == 0
    assert "/fake/_vendor" in r.stdout
