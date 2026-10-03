"""Behavioural tests for the FIRERPA probe's running-stale half.

The probe answers two different questions: is the pinned build on disk
(`disk_ok`), and is anything still *executing* the build we replaced
(`running_stale`). The second exists because a disk-only gate reports false
success -- Unix keeps a replaced file alive for whoever holds it open, so the
post-install verify reads the new file while the service runs the old one.

These tests run the shell logic **extracted from install.yml**, not a copy of it,
against a synthetic /proc tree. A copy would only test the copy.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / "ansible_collections/stayturgid/firerpa/roles/firerpa/tasks/install.yml"
STAMP = "10.9 88957c04f6cae2e2cc56aaece92cec4074ad72092bc05f1e26e4095de7dedeca"


def _probe_body() -> str:
    """Pull the probe's device-side shell out of the real task."""
    tasks = yaml.safe_load(INSTALL.read_text(encoding="utf-8"))
    task = next(t for t in tasks if t["name"].startswith("Detect whether the device already"))
    raw = task["ansible.builtin.shell"]
    # strip the adb wrapper: everything between the first and last single quote
    inner = raw[raw.index("'") + 1 : raw.rindex("'")]
    return inner


def _run(tmp_path: Path, *, stamp: str, deleted_under_install: bool, pids=(101,)) -> str:
    """Run the probe body with a fake install dir, fake pidof and fake /proc."""
    d = tmp_path / "firerpa"
    (d / "server/bin").mkdir(parents=True)
    (d / "overrides").mkdir(parents=True)
    (d / "server/bin/python3.12").write_text("#!/bin/sh\n")
    (d / "server/bin/python3.12").chmod(0o755)
    (d / "overrides/aab.zip.signed").write_text("signed")
    (d / "overrides/aab.zip.patched").write_text("patched")
    if stamp is not None:
        (d / ".stayturgid-firerpa-version").write_text(stamp + "\n")

    proc = tmp_path / "proc"
    for pid in pids:
        pd = proc / str(pid)
        pd.mkdir(parents=True)
        lines = [f"7f0000000000-7f0000001000 r-xp 00000000 fd:03 1 {d}/server/bin/python3.12\n"]
        # a healthy device really does carry unrelated deleted mappings; include
        # them in every case so an unscoped "(deleted)" test would fail these tests
        lines.append("7f0000002000-7f0000003000 rw-s 00000000 00:10 2 /dev/ashmem/bitmap (deleted)\n")
        lines.append("7f0000004000-7f0000005000 rw-p 00000000 00:11 3 /memfd:jit-cache (deleted)\n")
        if deleted_under_install:
            lines.append(
                f"7f0000006000-7f0000007000 r--s 00000000 fd:03 4 "
                f"{d}/server/lib/python3.12/site-packages/lamda/aab.zip (deleted)\n"
            )
        (pd / "maps").write_text("".join(lines))
        (pd / "exe").symlink_to(d / "server/bin/python3.12")

    body = _probe_body()
    body = body.replace("{{ firerpa_install_dir }}", str(d))
    body = body.replace("{{ firerpa_version_stamp }}", STAMP)
    # fake pidof and redirect /proc at our tree
    body = body.replace("/proc/$pid/", f"{proc}/$pid/")
    script = f"pidof() {{ echo '{' '.join(str(p) for p in pids)}'; }}\n" + body

    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_converged_when_disk_matches_and_nothing_runs_the_old_build(tmp_path):
    assert _run(tmp_path, stamp=STAMP, deleted_under_install=False) == "CONVERGED"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_stale_when_a_process_still_holds_the_replaced_driver(tmp_path):
    """The whole point: disk is perfect, but a process runs the deleted build."""
    out = _run(tmp_path, stamp=STAMP, deleted_under_install=True)
    assert out.startswith("STALE")
    assert "disk_ok=1" in out, "disk really is converged in this case"
    assert "running_stale=1" in out


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_unrelated_deleted_mappings_do_not_force_a_reinstall(tmp_path):
    """Measured on a live device: a healthy s24 had 4 lamda processes with
    deleted mappings (/dev/ashmem/bitmap, /memfd:jit-cache). An unscoped
    "(deleted)" test would force a ~204 MiB reinstall on every deploy."""
    # the fixture always injects those two; converged means they were ignored
    assert _run(tmp_path, stamp=STAMP, deleted_under_install=False) == "CONVERGED"


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_stale_stamp_still_forces_install(tmp_path):
    out = _run(tmp_path, stamp="10.4 deadbeef", deleted_under_install=False)
    assert out.startswith("STALE") and "disk_ok=0" in out


# --- structural guards, so the scoping cannot be dropped later ---------------


def test_the_deleted_check_is_scoped_to_the_install_dir():
    body = _probe_body()
    assert 'grep -F "$D" /proc/$pid/maps' in body, "an unscoped (deleted) test is a false positive"
    assert 'grep -c "(deleted)"' in body


def test_the_probe_reports_which_half_failed():
    body = _probe_body()
    assert "disk_ok=" in body and "running_stale=" in body
    assert re.search(r"echo\s+\"STALE disk_ok=", body), "STALE should say which half failed"


def test_the_probe_still_fails_open():
    body = _probe_body()
    # CONVERGED must be the narrow branch; anything else falls through to STALE
    assert body.index("echo CONVERGED") < body.index("STALE disk_ok=")
