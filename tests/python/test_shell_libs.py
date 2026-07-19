"""Unit tests for control/lib CLI helpers (resolve_adb, stayturgid_root)."""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_stayturgid_root_finds_repo():
    sys.path.insert(0, str(REPO / "control" / "lib"))
    import stayturgid_root as root_mod  # noqa: E402

    assert root_mod.stayturgid_root(REPO / "control/bin/deploy_fleet.py") == REPO


def test_stayturgid_root_cli(tmp_path):
    script = REPO / "control/lib/stayturgid_root.py"
    orphan = tmp_path / "nowhere/caller.py"
    orphan.parent.mkdir(parents=True)
    orphan.touch()
    r = subprocess.run(
        [str(script), str(orphan)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "repo root not found" in r.stderr


def test_resolve_adb_cli_usb_tailscale_and_dash_ts(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("oneui-device RFCX 100.0.0.11 192.0.2.55\n")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    adb = stubs / "adb"
    adb.write_text('#!/usr/bin/env bash\nif [ "$1" = "devices" ]; then printf "RFCX\\tdevice\\n"; fi\nexit 0\n')
    adb.chmod(0o755)
    env = {
        "PATH": f"{stubs}:{os.environ.get('PATH', '')}",
        "STAYTURGID_DEVICES_CONF": str(conf),
    }
    cli = REPO / "control/lib/resolve_adb.py"

    r = subprocess.run([str(cli), "oneui-device"], capture_output=True, text=True, env=env, check=False)
    assert r.stdout.strip() == "RFCX"

    adb.write_text("#!/usr/bin/env bash\nexit 0\n")
    adb.chmod(0o755)
    r = subprocess.run([str(cli), "oneui-device"], capture_output=True, text=True, env=env, check=False)
    # When neither LAN nor Tailscale is TCP-open, static_fallback prefers Tailscale
    # (stable) over DHCP LAN — see adb_resolve.static_fallback.
    assert r.stdout.strip() == "100.0.0.11:5555"

    conf.write_text("oneui-device RFCX - -\n")
    r = subprocess.run([str(cli), "oneui-device"], capture_output=True, text=True, env=env, check=False)
    assert r.stdout.strip() == "oneui-device"

    conf.write_text("stock-android-device - - 192.0.2.9\n")
    r = subprocess.run([str(cli), "stock-android-device"], capture_output=True, text=True, env=env, check=False)
    assert r.stdout.strip() == "192.0.2.9:5555"

    r = subprocess.run(
        [str(cli), "--ssh-host", "stock-android-device"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert r.stdout.strip() == "stock-android-device"


def test_gplaycli_wrapper_sets_pythonpath(tmp_path):
    """Smoke: gplaycli launcher prepends pip vendor before exec (no real gplaycli needed)."""
    script = REPO / "control/tools/play/gplaycli.py"
    fake_py = tmp_path / "python3.14"
    fake_py.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in -c) echo "/fake/pip/_vendor"; exit 0 ;; -m) echo "MODULE:$PYTHONPATH"; exit 0 ;; esac\n'
        "exit 1\n"
    )
    fake_py.chmod(0o755)
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "GPLAYCLI_PYTHON": str(fake_py)},
        check=False,
    )
    assert r.returncode == 0
    assert "/fake/pip/_vendor" in r.stdout
