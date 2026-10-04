"""Device-free tests for the Termux recovery scripts.

sshd-recover-tasker.sh (the Tasker dispatcher), sshd-recover.sh and
boot/00-start-services.sh run against a temp HOME laid out like the phone's.
Each is sourced into bash after shell-function stubs for every Termux/Android
command: functions, not PATH shims, because a BASH_ENV that rebuilds PATH
would otherwise put real binaries first (BASH_ENV is dropped as well).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "device" / "termux" / "tasker"
BOOT_SCRIPT = REPO / "device" / "termux" / "boot" / "00-start-services.sh"

COMMON_STUBS = r"""
timeout() { echo "timeout $*" >>"$CALLS"; shift; "$@"; }
sleep() { :; }
tty() { echo "not a tty"; }
"""

DISPATCHER_STUBS = r"""
sv() { echo "sv $*" >>"$CALLS"; echo "${SV_STATUS:-run: sshd: (pid 42) 9s; run: log: (pid 41) 9s}"; }
"""

WAKE_STUB = 'termux-wake-lock() { echo "wake" >>"$CALLS"; }\n'

# runsvdir counts as running once setsid has "started" it; sshd once `sv up`
# succeeded (SV_UP_WORKS) or it was already up (SSHD_UP file).
SUPERVISOR_STUBS = r"""
pgrep() { echo "pgrep $*" >>"$CALLS"; [ -f "$HOME/runsvdir_up" ]; }
setsid() { echo "setsid $*" >>"$CALLS"; : >"$HOME/runsvdir_up"; }
sv() {
  echo "sv $*" >>"$CALLS"
  case "$1" in
    up) [ -n "${SV_UP_WORKS:-}" ] && : >"$HOME/sshd_up" ;;
    status)
      if [ -f "$HOME/sshd_up" ]; then echo "run: sshd: (pid 42) 3s; run: log: (pid 41) 3s"
      else echo "down: sshd: 9s, normally up"; fi ;;
  esac
}
"""


class Phone:
    def __init__(self, tmp_path: Path):
        self.home = tmp_path / "home"
        self.prefix = tmp_path / "prefix"
        self.tasker = self.home / ".termux" / "tasker"
        self.recover_d = self.tasker / "recover.d"
        self.state = self.home / ".stayturgid" / "state"
        self.run_dir = self.home / ".stayturgid" / "run"
        self.calls = tmp_path / "calls.log"
        self.order = self.home / "order"
        self.tasker.mkdir(parents=True)
        self.calls.write_text("")
        for name in ("sshd-recover-tasker.sh", "sshd-recover.sh", "recover-lock.sh"):
            shutil.copy2(SRC / name, self.tasker / name)

    def step(self, name: str, rc: int = 0, body: str = "") -> Path:
        self.recover_d.mkdir(exist_ok=True)
        p = self.recover_d / name
        p.write_text('#!/bin/sh\necho %s >>"$HOME/order"\n%sexit %d\n' % (name, body, rc))
        p.chmod(0o755)
        return p

    def source(self, script: Path, stubs: str, **env: str) -> subprocess.CompletedProcess:
        harness = COMMON_STUBS + stubs + '. "%s"\n' % script
        full = {k: v for k, v in os.environ.items() if k != "BASH_ENV"}
        full.update(HOME=str(self.home), PREFIX=str(self.prefix), CALLS=str(self.calls))
        full.update(env)
        return subprocess.run(["bash", "-c", harness], capture_output=True, text=True, env=full, timeout=60)

    def dispatch(self, *, wake: bool = True, **env: str) -> subprocess.CompletedProcess:
        stubs = DISPATCHER_STUBS + (WAKE_STUB if wake else "")
        return self.source(self.tasker / "sshd-recover-tasker.sh", stubs, **env)

    def recover(self, **env: str) -> subprocess.CompletedProcess:
        return self.source(self.tasker / "sshd-recover.sh", SUPERVISOR_STUBS, **env)

    def ran(self) -> list[str]:
        return self.order.read_text().split() if self.order.exists() else []

    def result(self) -> dict[str, str]:
        out = {}
        for line in (self.state / "tasker-sshd-recover.result").read_text().splitlines():
            k, _, v = line.partition("=")
            out[k] = v
        return out

    def hold_lock(self, name: str, pid: int, since: int) -> Path:
        lock = self.run_dir / name
        lock.mkdir(parents=True)
        (lock / "owner").write_text("%d %d\n" % (pid, since))
        return lock


@pytest.fixture
def phone(tmp_path):
    return Phone(tmp_path)


def _dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


# --- dispatcher -------------------------------------------------------------


def test_marker_line1_is_a_bare_epoch(phone):
    phone.step("10-a")
    before = int(time.time())
    phone.dispatch()
    line1 = (phone.state / "tasker-sshd-recover.ts").read_text().splitlines()[0]
    assert line1.isdigit() and int(line1) >= before


def test_steps_run_in_name_order_and_skip_non_executables(phone):
    phone.step("20-b")
    phone.step("05-c")
    phone.step("10-a")
    (phone.recover_d / "15-not-executable").write_text('#!/bin/sh\necho bad >>"$HOME/order"\n')
    (phone.recover_d / "12-a-directory").mkdir()
    r = phone.dispatch()
    assert r.returncode == 0, r.stderr
    assert phone.ran() == ["05-c", "10-a", "20-b"]


def test_failing_step_does_not_abort_the_rest(phone):
    phone.step("10-ok")
    phone.step("20-fail", rc=3)
    phone.step("30-ok")
    r = phone.dispatch()
    assert phone.ran() == ["10-ok", "20-fail", "30-ok"]
    assert r.returncode == 1
    res = phone.result()
    assert res["exit"] == "1"
    assert (res["step.10-ok"], res["step.20-fail"], res["step.30-ok"]) == ("0", "3", "0")


def test_result_file_content(phone):
    phone.step("10-a")
    before = int(time.time())
    r = phone.dispatch()
    assert r.returncode == 0, r.stderr
    res = phone.result()
    assert int(res["end"]) >= before
    assert res["exit"] == "0"
    assert res["step.10-a"] == "0"
    assert res["sv_sshd"].startswith("run: sshd:")
    assert res["tty"] == "not a tty"
    assert not (phone.state / "tasker-sshd-recover.result.tmp").exists()


def test_missing_recover_d_is_a_failure(phone):
    r = phone.dispatch()
    assert r.returncode == 1
    res = phone.result()
    assert res["exit"] == "1"
    assert not [k for k in res if k.startswith("step.")]


def test_each_step_gets_its_own_timeout(phone):
    step = phone.step("10-a")
    phone.dispatch(STAYTURGID_RECOVER_STEP_TIMEOUT_SEC="7")
    assert "timeout 7 %s" % step in phone.calls.read_text()


def test_takes_bounded_wake_lock(phone):
    phone.step("10-a")
    phone.dispatch()
    calls = phone.calls.read_text()
    assert "timeout 5 termux-wake-lock" in calls
    assert "wake" in calls.splitlines()


def test_runs_without_termux_wake_lock(phone):
    phone.step("10-a")
    r = phone.dispatch(wake=False)
    assert r.returncode == 0, r.stderr
    assert phone.ran() == ["10-a"]


def test_min_interval_skips_second_run_but_still_stamps_marker(phone):
    phone.step("10-a")
    phone.dispatch()
    first_result = (phone.state / "tasker-sshd-recover.result").read_text()
    marker = phone.state / "tasker-sshd-recover.ts"
    marker.write_text("1\n")
    r = phone.dispatch()
    assert r.returncode == 0
    assert phone.ran() == ["10-a"]
    assert marker.read_text().strip() != "1"
    assert (phone.state / "tasker-sshd-recover.result").read_text() == first_result


def test_min_interval_elapsed_runs_again(phone):
    phone.step("10-a")
    phone.dispatch()
    (phone.state / "tasker-sshd-recover.last-run").write_text(str(int(time.time()) - 31))
    phone.dispatch()
    assert phone.ran() == ["10-a", "10-a"]


def test_live_lock_holder_skips_run(phone):
    phone.step("10-a")
    owner = "%d %d\n" % (os.getpid(), int(time.time()))
    lock = phone.hold_lock("tasker-sshd-recover.lock", os.getpid(), int(time.time()))
    r = phone.dispatch()
    assert r.returncode == 0
    assert phone.ran() == []
    assert (lock / "owner").read_text() == owner
    assert (phone.state / "tasker-sshd-recover.ts").exists()


@pytest.mark.parametrize("holder", ["dead", "too_old", "no_owner"])
def test_stale_lock_is_broken_and_released(phone, holder):
    phone.step("10-a")
    if holder == "dead":
        lock = phone.hold_lock("tasker-sshd-recover.lock", _dead_pid(), int(time.time()))
    elif holder == "too_old":
        lock = phone.hold_lock("tasker-sshd-recover.lock", os.getpid(), int(time.time()) - 901)
    else:
        lock = phone.run_dir / "tasker-sshd-recover.lock"
        lock.mkdir(parents=True)
    r = phone.dispatch()
    assert r.returncode == 0, r.stderr
    assert phone.ran() == ["10-a"]
    assert not lock.exists()


def test_lock_released_after_normal_run(phone):
    phone.step("10-a")
    phone.dispatch()
    assert not (phone.run_dir / "tasker-sshd-recover.lock").exists()


def test_real_10_sshd_runs_sibling_sshd_recover(phone):
    phone.recover_d.mkdir()
    real = (SRC / "recover.d" / "10-sshd").read_text().splitlines()
    step = phone.recover_d / "10-sshd"
    # The Termux shebang does not exist on the Mac.
    step.write_text("\n".join(["#!/bin/sh"] + real[1:]) + "\n")
    step.chmod(0o755)
    fake = phone.tasker / "sshd-recover.sh"
    fake.write_text('#!/bin/sh\necho sshd-recover >>"$HOME/order"\nexit "${FAKE_RC:-0}"\n')
    fake.chmod(0o755)
    phone.dispatch()
    assert phone.ran() == ["sshd-recover"]
    assert phone.result()["step.10-sshd"] == "0"
    (phone.state / "tasker-sshd-recover.last-run").unlink()
    phone.dispatch(FAKE_RC="1")
    assert phone.result()["step.10-sshd"] == "1"
    assert phone.result()["exit"] == "1"


# --- sshd-recover.sh --------------------------------------------------------


def test_sshd_recover_already_up_exits_0_without_starting_anything(phone):
    (phone.home / "runsvdir_up").touch()
    (phone.home / "sshd_up").touch()
    r = phone.recover()
    assert r.returncode == 0, r.stderr
    calls = phone.calls.read_text()
    assert "setsid" not in calls
    assert "sv up" not in calls
    assert "pgrep -f [r]unsvdir %s/var/service" % phone.prefix in calls


def test_sshd_recover_starts_runsvdir_once_and_waits_for_run(phone):
    r = phone.recover(SV_UP_WORKS="1")
    assert r.returncode == 0, r.stderr
    calls = phone.calls.read_text().splitlines()
    assert calls.count("setsid runsvdir %s/var/service" % phone.prefix) == 1
    assert "sv up sshd" in calls
    assert not (phone.run_dir / "runsvdir-start.lock").exists()


def test_sshd_recover_exits_nonzero_when_sshd_never_runs(phone):
    (phone.home / "runsvdir_up").touch()
    r = phone.recover()
    assert r.returncode != 0
    assert phone.calls.read_text().splitlines().count("sv up sshd") == 10
    log = (phone.home / ".stayturgid" / "logs" / "sshd-selfheal.log").read_text()
    assert "still not running" in log


def test_sshd_recover_proceeds_past_a_wedged_live_lock_holder(phone):
    lock = phone.hold_lock("runsvdir-start.lock", os.getpid(), int(time.time()))
    r = phone.recover(SV_UP_WORKS="1")
    assert r.returncode == 0, r.stderr
    assert lock.exists(), "must not release a lock it does not own"
    log = (phone.home / ".stayturgid" / "logs" / "sshd-selfheal.log").read_text()
    assert "lock unavailable" in log


def test_sshd_recover_breaks_a_dead_holders_lock(phone):
    lock = phone.hold_lock("runsvdir-start.lock", _dead_pid(), int(time.time()))
    r = phone.recover(SV_UP_WORKS="1")
    assert r.returncode == 0, r.stderr
    assert not lock.exists()
    assert "lock unavailable" not in (phone.home / ".stayturgid" / "logs" / "sshd-selfheal.log").read_text()


def test_sshd_recover_works_without_lock_helper(phone):
    (phone.tasker / "recover-lock.sh").unlink()
    r = phone.recover(SV_UP_WORKS="1")
    assert r.returncode == 0, r.stderr


# --- boot/00-start-services.sh ----------------------------------------------


def test_boot_script_takes_and_releases_the_shared_runsvdir_lock(phone):
    r = phone.source(BOOT_SCRIPT, SUPERVISOR_STUBS)
    assert r.returncode == 0, r.stderr
    calls = phone.calls.read_text().splitlines()
    assert calls.count("setsid %s/bin/runsvdir %s/var/service" % (phone.prefix, phone.prefix)) == 1
    assert not (phone.run_dir / "runsvdir-start.lock").exists()


def test_boot_script_leaves_a_live_holders_lock_alone(phone):
    lock = phone.hold_lock("runsvdir-start.lock", os.getpid(), int(time.time()))
    phone.source(BOOT_SCRIPT, SUPERVISOR_STUBS)
    assert lock.exists()
