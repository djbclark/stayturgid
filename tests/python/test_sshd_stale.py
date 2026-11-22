"""The stale-sshd-listener check (module_utils/sshd_stale.py) run for real under bash.

p7a, 2026-11-21: an openssh upgrade replaced sshd under its running listener, which then reset
every login (`kex_exchange_identification`). The check reads /proc, so these tests run the actual
script against a fake /proc tree (STAYTURGID_PROC), a fake `stat` (STAYTURGID_STAT) and a fake `sv`
under the fake PREFIX. "Started" is the pidfile's mtime: a phone's app shell cannot read /proc/uptime
(`no-uptime` on t2e, p7a and m11).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_UTILS = Path(__file__).resolve().parents[2] / "ansible_collections/stayturgid/termux/plugins/module_utils"
sys.path.insert(0, str(_UTILS))

import sshd_stale as ss  # noqa: E402

NOW = 1_000_000


class Phone:
    """A fake Termux prefix plus /proc, with one sshd listener unless told otherwise."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.prefix = tmp_path / "usr"
        self.proc = tmp_path / "proc"
        (self.prefix / "var/run").mkdir(parents=True)
        (self.prefix / "bin").mkdir()
        self.proc.mkdir()
        self.sv_log = tmp_path / "sv.log"
        self.binary_ctime = NOW - 100
        self.stat_fails = ""  # "", "pidfile" or "binary": which `stat` the stub refuses
        self.pid_mtime = None
        self.supervised = True
        self.sv_pid = 4242  # the pid runsv reports for its sshd
        self.sv_restart_rc = 0

    def listener(self, pid=4242, *, started_s_ago, exe=None, argv0="sshd", pidfile=True, comm="sshd"):
        d = self.proc / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(("%s\0-D\0-e\0" % argv0).encode())
        (d / "exe").symlink_to(exe or str(self.prefix / "bin/sshd"))
        self.pid_mtime = NOW - started_s_ago
        if pidfile:
            (self.prefix / "var/run/sshd.pid").write_text("%d\n" % pid)

    def _stubs(self):
        stat = self.root / "fakestat"
        # `stat -c %Y .../sshd.pid` is the listener's start; `stat -c %Z bin/sshd libexec/sshd-session` the install.
        pidfile_line = "exit 1" if self.stat_fails == "pidfile" else "echo %d" % (self.pid_mtime or NOW)
        binary_lines = (
            "exit 1" if self.stat_fails == "binary" else "echo %d; echo %d" % (self.binary_ctime, self.binary_ctime - 7)
        )
        body = 'case "$*" in *sshd.pid*) %s;; *) %s;; esac\n' % (pidfile_line, binary_lines)
        stat.write_text("#!/bin/sh\n" + body)
        stat.chmod(0o755)
        sv = self.prefix / "bin/sv"
        sv.write_text(
            "#!/bin/sh\n"
            'echo "$SVDIR $*" >> %s\n'
            'case "$1" in status) echo "run: sshd: (pid %d) 5s; run: log: (pid 9) 5s"; exit %d;; restart) exit %d;; esac\n'
            % (self.sv_log, self.sv_pid, 0 if self.supervised else 1, self.sv_restart_rc)
        )
        sv.chmod(0o755)
        return stat

    def env(self):
        stat = self._stubs()
        return {
            "PATH": os.environ["PATH"],
            "STAYTURGID_PROC": str(self.proc),
            "STAYTURGID_STAT": str(stat),
        }

    def run(self, script):
        proc = subprocess.run(["bash", "-c", script], env=self.env(), text=True, capture_output=True, check=False)
        return proc

    def verdict(self):
        proc = self.run(ss.stale_check_script(str(self.prefix)))
        assert proc.returncode == 0, proc.stderr
        return ss.parse_verdict(proc.stdout)


@pytest.fixture
def phone(tmp_path):
    return Phone(tmp_path)


def test_listener_started_after_the_binary_changed_is_fresh(phone):
    phone.listener(started_s_ago=50)  # binary changed 100 s ago
    v = phone.verdict()
    assert v.fresh and v.supervised
    assert not v.stale


def test_listener_started_before_the_binary_changed_is_stale(phone):
    phone.listener(started_s_ago=900)
    v = phone.verdict()
    assert v.stale and v.reason == "older-than-binary"
    assert v.supervised


def test_newest_of_sshd_and_sshd_session_decides(phone):
    # sshd-session replaced later than sshd: the listener predates it.
    phone.binary_ctime = NOW - 40
    phone.listener(started_s_ago=60)
    assert phone.verdict().stale


@pytest.mark.parametrize(("extra", "stale"), [(ss.STALE_MARGIN_S, False), (ss.STALE_MARGIN_S + 1, True)])
def test_the_margin_is_five_seconds(phone, extra, stale):
    phone.listener(started_s_ago=100 + extra)  # binary changed 100 s ago
    assert phone.verdict().stale is stale


def test_a_missing_pidfile_mtime_is_unknown(phone):
    phone.listener(started_s_ago=900)
    phone.stat_fails = "pidfile"
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "no-pidfile-mtime" and not v.stale


def test_a_deleted_exe_is_stale_even_though_the_start_time_looks_fine(phone):
    # p7a: /proc/PID/exe was `.../bin/sshd.dpkg-tmp (deleted)`.
    phone.listener(started_s_ago=10, exe="%s/bin/sshd.dpkg-tmp (deleted)" % phone.prefix)
    v = phone.verdict()
    assert v.stale and v.reason == "deleted-exe"


def test_a_listener_that_reexeced_under_its_full_path_is_still_recognised(phone):
    phone.listener(started_s_ago=10, argv0=str(phone.prefix / "bin/sshd"))
    assert phone.verdict().fresh


@pytest.mark.parametrize("supervised", [True, False])
def test_supervision_is_reported_either_way(phone, supervised):
    phone.supervised = supervised
    phone.listener(started_s_ago=900)
    v = phone.verdict()
    assert v.stale and v.supervised is supervised
    assert "%s/var/service status sshd" % phone.prefix in phone.sv_log.read_text()


def test_a_bare_stale_listener_beside_a_runsv_with_its_own_sshd_is_not_supervised(phone):
    # runsv runs, but its sshd (pid 7777) is not the pidfile's listener (4242): `sv restart`
    # would leave the stale bare one running.
    phone.sv_pid = 7777
    phone.listener(started_s_ago=900)
    v = phone.verdict()
    assert v.stale and v.supervised is False


def test_retire_script_kills_only_the_verified_pidfile_pid(phone):
    phone.listener(pid=os.getpid(), started_s_ago=900)
    # A process named sshd that is really us: replace cmdline so the argv0 check passes, then
    # use a stub `kill` to see what would be killed.
    stub = phone.root / "stubbin"
    stub.mkdir()
    (stub / "kill").write_text('#!/bin/sh\necho "$@" > %s/killed\n' % phone.root)
    (stub / "kill").chmod(0o755)
    script = 'kill() { echo "$@" > %s/killed; }\n' % phone.root + ss.retire_bare_listener_script(str(phone.prefix))
    script = script.replace('"/proc/$pid/cmdline"', '"%s/$pid/cmdline"' % phone.proc)
    proc = phone.run(script)
    assert proc.returncode == 0, proc.stderr
    assert (phone.root / "killed").read_text().strip() == str(os.getpid())


@pytest.mark.parametrize("pidfile_text", ["", "abc", "12 34"])
def test_retire_script_refuses_a_bad_pidfile(phone, pidfile_text):
    (phone.prefix / "var/run/sshd.pid").write_text(pidfile_text)
    proc = phone.run(ss.retire_bare_listener_script(str(phone.prefix)))
    assert proc.returncode == 3 and "not killing" in proc.stderr


def test_retire_script_refuses_a_pid_that_is_not_sshd(phone):
    (phone.prefix / "var/run/sshd.pid").write_text("%d\n" % os.getpid())  # a python/pytest process
    proc = phone.run(ss.retire_bare_listener_script(str(phone.prefix)))
    assert proc.returncode == 3 and "not sshd" in proc.stderr


def test_no_pidfile_is_unknown_never_stale(phone):
    phone.listener(started_s_ago=900, pidfile=False)
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "no-pidfile" and not v.stale


def test_pid_that_is_gone_is_unknown(phone):
    (phone.prefix / "var/run/sshd.pid").write_text("999\n")
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "pid-gone"


def test_a_reused_pid_that_is_not_sshd_is_unknown(phone):
    phone.listener(started_s_ago=900, argv0="logcat")
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "pid-not-sshd"


def test_unreadable_exe_is_unknown_not_stale(phone):
    phone.listener(started_s_ago=900)
    (phone.proc / "4242/exe").unlink()
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "exe-unreadable"


def test_missing_binary_ctime_is_unknown(phone):
    phone.listener(started_s_ago=900)
    phone.stat_fails = "binary"
    v = phone.verdict()
    assert v.state == "unknown" and v.reason == "no-binary-ctime"


def test_restart_script_restarts_through_sv_when_supervised(phone):
    phone.listener(started_s_ago=900)
    proc = phone.run(ss.restart_script(str(phone.prefix)))
    assert proc.returncode == 0, proc.stderr
    log = phone.sv_log.read_text().splitlines()
    assert "%s/var/service restart sshd" % phone.prefix in log


def test_restart_script_refuses_an_unsupervised_listener(phone):
    phone.supervised = False
    proc = phone.run(ss.restart_script(str(phone.prefix)))
    assert proc.returncode == 3
    assert "not supervised" in proc.stderr
    assert "restart sshd" not in phone.sv_log.read_text()


def test_restart_script_reports_sv_failure(phone):
    phone.sv_restart_rc = 1
    assert phone.run(ss.restart_script(str(phone.prefix))).returncode == 1


def test_prefix_is_quoted_into_the_scripts():
    script = ss.stale_check_script("/odd path/usr")
    assert script.startswith("PREFIX='/odd path/usr'\n")
    assert ss.restart_script("/odd path/usr").startswith("PREFIX='/odd path/usr'\n")


@pytest.mark.parametrize("script", [ss.stale_check_script(), ss.restart_script(), ss.retire_bare_listener_script()])
def test_scripts_parse_as_bash(script):
    proc = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_the_check_script_never_writes_or_kills():
    body = ss.stale_check_script()
    for word in ("kill", "rm ", "> /", ">>", "restart", "mv "):
        assert word not in body, word


@pytest.mark.parametrize(
    ("output", "state", "reason", "supervised"),
    [
        ("fresh\nsupervised=yes\n", "fresh", "", True),
        ("stale deleted-exe\nsupervised=no\n", "stale", "deleted-exe", False),
        ("unknown no-pidfile\r\nsupervised=yes\r\n", "unknown", "no-pidfile", True),
        ("", "unknown", "no-output", False),
        ("sshd: error: something odd\n", "unknown", "no-output", False),
        ("stale older-than-binary\n", "stale", "older-than-binary", False),
    ],
)
def test_parse_verdict(output, state, reason, supervised):
    v = ss.parse_verdict(output)
    assert (v.state, v.reason, v.supervised) == (state, reason, supervised)
