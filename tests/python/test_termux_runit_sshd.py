"""Guards for the fresh-Termux runit/sshd fixup (tasks/runit_sshd.yml, 2026-10-17).

On a fresh Termux, bootstrap-ssh leaves a bare sshd and no runit; the role's
`reload sshd` handler (`sv hup`) then fails. The fixup starts one runsvdir, retires
only the bare listener (detached), reconnects and verifies. A healthy device
(runit already supervising sshd) must skip it and report no change.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "ansible_collections/stayturgid/termux/roles/termux_userland"


def _tasks(name: str) -> list[dict]:
    return yaml.safe_load((ROLE / "tasks" / name).read_text())


def _by_name(tasks: list[dict], name: str) -> dict:
    return next(t for t in tasks if t.get("name") == name)


def _script(task: dict) -> str:
    return task["ansible.builtin.shell"]


def _rendered(script: str) -> str:
    return script.replace("{{ termux_prefix | quote }}", "/data/data/com.termux/files/usr")


FIX = "Start runit and hand port 8022 from the bare sshd to runit's sshd"
PROBE = "Probe whether runit supervises sshd"


def test_fixup_is_included_after_boot_scripts_and_before_any_handler_runs():
    tasks = _tasks("main.yml")
    names = [t.get("name") for t in tasks]
    inc = _by_name(tasks, "Ensure runit supervises sshd (fresh-Termux fixup)")
    assert inc["ansible.builtin.include_tasks"] == "runit_sshd.yml"
    # It runs 00-start-services.sh, which must already be on the device.
    assert names.index(inc["name"]) > names.index("Deploy boot scripts")
    assert "'00-start-services.sh' in (stayturgid_boot_scripts | default([]))" in inc["when"]
    # Handlers run at the end of the play (the one earlier flush, in otelcol.yml, comes
    # before anything notifies `reload sshd`), so no flush may sit between the two.
    between = names[names.index("Deploy boot scripts") : names.index(inc["name"])]
    assert not any("flush" in (n or "") for n in between)
    handlers = yaml.safe_load((ROLE / "handlers/main.yml").read_text())
    assert any(h["name"] == "reload sshd" for h in handlers)


def test_healthy_device_skips_the_fix_and_reports_no_change():
    tasks = _tasks("runit_sshd.yml")
    probe = _by_name(tasks, PROBE)
    assert probe["changed_when"] is False
    assert probe["check_mode"] is False
    assert 'sv" status sshd' in _script(probe)
    fix = _by_name(tasks, FIX)
    assert fix["when"] == "_stayturgid_runit_sshd_probe.stdout | trim == 'unsupervised'"
    # Everything after the fix keys off the fix having changed something.
    for name in (
        "Wait for the control node to reach sshd on the new listener",
        "Wait for SSH on the runit-supervised sshd",
        "Verify sshd is supervised by runit (one runsvdir, listener under runsv)",
    ):
        assert _by_name(tasks, name)["when"] == "_stayturgid_runit_sshd_fix is changed"
    # sv needs SVDIR in a non-login SSH shell.
    assert "SVDIR=" in _script(probe)


def test_at_most_one_runsvdir_is_ever_started():
    script = _script(_by_name(_tasks("runit_sshd.yml"), FIX))
    guard = script.index('pgrep -f "[r]unsvdir $SVDIR"')
    assert guard < script.index('"$boot" </dev/null')
    assert script.count('"$boot"') == 2  # the -x check and the one call
    assert "$HOME/.termux/boot/00-start-services.sh" in script


def test_only_the_bare_listener_is_killed_and_detached():
    script = _script(_by_name(_tasks("runit_sshd.yml"), FIX))
    # Listeners only: argv[0] exactly sshd (not "sshd-session: ..." or "sshd: user"),
    # and never one whose parent is runsv.
    assert '[ "${argv0##*/}" = sshd ] || continue' in script
    assert '[ "$(cat "/proc/$ppid/comm" 2>/dev/null)" = runsv ] && continue' in script
    # Detached and delayed, with the pids collected beforehand: never pkill by name.
    assert 'setsid nohup bash -c "sleep 3; kill $bare"' in script
    assert "< /dev/null &" in script
    assert "pkill" not in script
    assert "killall" not in script


def test_play_waits_for_a_new_connection_then_verifies_one_runsvdir_and_runsv_parent():
    tasks = _tasks("runit_sshd.yml")
    names = [t["name"] for t in tasks]
    # meta: reset_connection ignores `when`, so it must not be used here.
    assert not [t for t in tasks if "ansible.builtin.meta" in t]
    reach = "Wait for the control node to reach sshd on the new listener"
    assert names.index(FIX) < names.index(reach) < names.index("Wait for SSH on the runit-supervised sshd")
    wait = _by_name(tasks, reach)
    assert wait["delegate_to"] == "localhost"
    assert wait["ansible.builtin.wait_for"]["delay"] >= 4  # past the detached kill's 3 s delay
    verify = _by_name(tasks, "Verify sshd is supervised by runit (one runsvdir, listener under runsv)")
    script = _script(verify)
    assert "grep -q '^run:'" in script
    assert '[ "$dirs" = 1 ]' in script
    assert '= runsv ] || { echo "sshd' in script
    assert verify["until"] == "_stayturgid_runit_sshd_verify.rc == 0"
    assert verify["changed_when"] is False


def test_shell_blocks_parse_as_bash():
    for task in _tasks("runit_sshd.yml"):
        if "ansible.builtin.shell" not in task:
            continue
        proc = subprocess.run(
            ["bash", "-n"], input=_rendered(_script(task)), text=True, capture_output=True, check=False
        )
        assert proc.returncode == 0, (task["name"], proc.stderr)


# termux-services' profile.d/start-services.sh trusts only service-daemon.pid, which
# our runsvdir starters never write: every login shell added a runsvdir (t2e had 8).
PIDFIX = REPO / "device/termux/profile.d/runsvdir-pidfile.sh"


def test_pidfile_fix_is_deployed_into_profile_d_and_sorts_before_start_services():
    assert PIDFIX.name < "start-services.sh"
    task = _by_name(_tasks("main.yml"), "Deploy the runsvdir pidfile fix for termux-services")
    copy = task["ansible.builtin.copy"]
    assert copy["src"].endswith("/device/termux/profile.d/runsvdir-pidfile.sh")
    assert copy["dest"] == "{{ termux_prefix }}/etc/profile.d/runsvdir-pidfile.sh"
    assert copy["mode"] == "0644"


def _source_pidfix(tmp_path: Path, shell: str, pgrep_body: str) -> tuple[Path, str]:
    stubs = tmp_path / "bin"
    stubs.mkdir()
    pgrep = stubs / "pgrep"
    pgrep.write_text(f'#!/bin/sh\necho "$*" >"{tmp_path}/pgrep.args"\n{pgrep_body}\n')
    pgrep.chmod(0o755)
    prefix = tmp_path / "usr"
    prefix.mkdir()
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "PREFIX": str(prefix)}
    proc = subprocess.run(
        [shell, "-c", f'. "{PIDFIX}"; echo "leak=${{_stayturgid_rsv-unset}}"'],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return prefix / "var/run/service-daemon.pid", proc.stdout


@pytest.mark.parametrize("shell", ["sh", "bash", "dash"])
def test_pidfile_fix_points_service_daemon_at_the_running_runsvdir(tmp_path, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    pidfile, out = _source_pidfix(tmp_path, shell, "echo 7750")
    assert pidfile.read_text() == "7750\n"
    assert "leak=unset" in out
    args = (tmp_path / "pgrep.args").read_text()
    assert args.startswith("-o -f [r]unsvdir ") and args.rstrip().endswith("/usr/var/service$")


@pytest.mark.parametrize("shell", ["sh", "bash", "dash"])
def test_pidfile_fix_leaves_the_pidfile_alone_when_no_runsvdir_runs(tmp_path, shell):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    pidfile, out = _source_pidfix(tmp_path, shell, "exit 1")
    assert not pidfile.exists()
    assert "leak=unset" in out


def test_no_runsvdir_guard_uses_pgrep_x():
    # `pgrep -x runsvdir` misses a runsvdir started by absolute path (t2e,
    # 2026-10-17): the CFEngine sshd bundle used it and started a second one on
    # every brief sshd gap. Every starter must use -f on the service dir.
    tracked = subprocess.run(
        ["git", "ls-files", "device"], cwd=REPO, text=True, capture_output=True, check=True
    ).stdout.split()
    offenders = [f for f in tracked if "pgrep -x runsvdir" in (REPO / f).read_text(errors="ignore")]
    assert offenders == []
