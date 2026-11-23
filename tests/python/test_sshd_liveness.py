"""Unit tests for sshd listener liveness checks (#341).

After `sv hup` re-execs Termux's sshd, the listener's cmdline becomes
`<PREFIX>/bin/sshd -D -e` and Termux's `pgrep -x sshd` returns 1 even though
the listener is up (s24, 2026-11-23). Bare `pgrep sshd` finds it, but also
false-positives on `sshd-session` children.

These tests exercise the actual shell commands from `termux_run_as.py` and
`device/termux/cfengine/policy/stayturgid.cf` under sh/bash with stubbed `sv`
and a POSIX-ERE `pgrep` backed by `grep -Eq`, plus the Python helpers in
`start_adb.py`, `stayturgid_repair.py`, and `stayturgid_verify.py`.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ansible_collections/stayturgid/termux/plugins/module_utils"))
sys.path.insert(0, str(REPO / "device/termux/py"))

import start_adb  # noqa: E402
import stayturgid_repair as repair  # noqa: E402
import stayturgid_shell  # noqa: E402
import termux_run_as as tr  # noqa: E402

_VERIFY_SPEC = importlib.util.spec_from_file_location(
    "stayturgid_verify_liveness",
    REPO / "ansible_collections/stayturgid/fleet/plugins/modules/stayturgid_verify.py",
)
assert _VERIFY_SPEC is not None and _VERIFY_SPEC.loader is not None
_VERIFY_MOD = importlib.util.module_from_spec(_VERIFY_SPEC)
_VERIFY_SPEC.loader.exec_module(_VERIFY_MOD)

CF_POLICY = REPO / "device/termux/cfengine/policy/stayturgid.cf"


class FakeTermuxHost:
    """Fake Termux prefix with stubbed `sv`, POSIX-ERE `pgrep`, and `sshd`."""

    def __init__(self, tmp_path: Path, prefix_name: str = "usr"):
        self.root = tmp_path
        self.prefix = tmp_path / prefix_name
        self.bin = self.prefix / "bin"
        self.bin.mkdir(parents=True)
        (self.prefix / "var/service/sshd").mkdir(parents=True)
        self.cmdlines = tmp_path / "cmdlines.txt"
        self.cmdlines.write_text("", encoding="utf-8")
        self.sv_log = tmp_path / "sv.log"
        self.pgrep_log = tmp_path / "pgrep.log"
        self.sshd_log = tmp_path / "sshd.log"

        # Real POSIX ERE `pgrep -f` stand-in using the system `grep -Eq`.
        pgrep = self.bin / "pgrep"
        pgrep.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{self.pgrep_log}"\n'
            '[ "$1" = "-f" ] || exit 2\n'
            f'grep -Eq -- "$2" "{self.cmdlines}"\n',
            encoding="utf-8",
        )
        pgrep.chmod(0o755)

        # Symlink real `grep` into prefix/bin so CFEngine's $(p)/bin/grep works.
        real_grep = shutil.which("grep")
        assert real_grep is not None
        (self.bin / "grep").symlink_to(real_grep)

        self.sshd_starts_listener = True
        self._write_sshd_stub()

    def _write_sshd_stub(self) -> None:
        sshd = self.bin / "sshd"
        add = f'printf "%s\\n" "sshd -D -e" >> "{self.cmdlines}"\n' if self.sshd_starts_listener else ""
        sshd.write_text(
            f'#!/bin/sh\necho started >> "{self.sshd_log}"\n{add}exit 0\n',
            encoding="utf-8",
        )
        sshd.chmod(0o755)

    def set_sv(self, output: str | None, rc: int = 0) -> None:
        sv = self.bin / "sv"
        if output is None:
            if sv.exists():
                sv.unlink()
            return
        sv.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.sv_log}"\nprintf \'%s\\n\' {shlex.quote(output)}\nexit {rc}\n',
            encoding="utf-8",
        )
        sv.chmod(0o755)

    def set_processes(self, lines: list[str]) -> None:
        self.cmdlines.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "PREFIX": str(self.prefix),
        }

    def run(self, script: str, shell: str = "bash") -> subprocess.CompletedProcess[str]:
        return subprocess.run([shell, "-c", script], env=self.env(), text=True, capture_output=True, check=False)


def _extract_cf_sshd_up_cmd() -> str:
    text = CF_POLICY.read_text(encoding="utf-8")
    m = re.search(
        r'bundle agent check_sshd\(p\)\s*\{.*?"sshd_up"\s+expression\s*=>\s*returnszero\(\s*"([^"]+)",\s*"useshell"\s*\)',
        text,
        re.DOTALL,
    )
    assert m is not None, "could not locate check_sshd sshd_up returnszero() in stayturgid.cf"
    return m.group(1)


@pytest.mark.parametrize("shell", ["sh", "bash"])
@pytest.mark.parametrize(
    ("sv_out", "sv_rc", "procs", "want_up"),
    [
        # Runit reporting run: wins even with no fallback processes.
        ("run: /usr/var/service/sshd: (pid 29807) 42s; run: log: (pid 9) 42s", 0, [], True),
        # Runit reporting down (even with `; run: log:` on the same line) must NOT count as up.
        ("down: /usr/var/service/sshd: 5s, normally up; run: log: (pid 9) 42s", 0, [], False),
        # Runit down/absent + re-exec'd listener -> up.
        ("down: /usr/var/service/sshd: 5s; run: log: (pid 9) 42s", 0, ["{prefix}/bin/sshd -D -e"], True),
        (None, 0, ["{prefix}/bin/sshd -D -e"], True),
        (None, 0, ["{prefix}/bin/sshd"], True),
        # Plain sshd -D / bare sshd -> up.
        (None, 0, ["sshd -D"], True),
        (None, 0, ["sshd -D -e"], True),
        (None, 0, ["sshd"], True),
        # sshd-session / sshd-auth / pre-9.8 session children -> NOT up.
        (None, 0, ["sshd-session: u0_a601 [priv]", "sshd-session: u0_a601@pts/0"], False),
        (None, 0, ["{prefix}/libexec/sshd-session -R"], False),
        (None, 0, ["sshd-auth: u0_a601 [net]"], False),
        (None, 0, ["sshd: u0_a601@pts/0"], False),
        # Unrelated processes mentioning sshd -> NOT up.
        (None, 0, ["runsv sshd", "svlogd -tt {prefix}/var/log/sv/sshd", "bash -c pgrep sshd"], False),
        # Nothing running -> NOT up.
        (None, 0, [], False),
        ("fail: /usr/var/service/sshd: runsv not running", 1, [], False),
    ],
)
def test_termux_run_as_liveness_matcher(tmp_path, shell, sv_out, sv_rc, procs, want_up):
    host = FakeTermuxHost(tmp_path)
    host.set_sv(sv_out, rc=sv_rc)
    host.set_processes([p.format(prefix=host.prefix) for p in procs])

    res = host.run(tr.sshd_liveness_cmd(str(host.prefix)), shell=shell)
    assert (res.returncode == 0) is want_up, (res.returncode, res.stderr)


def test_runit_state_short_circuits_before_pgrep(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.set_sv("run: sshd: (pid 29807) 10s", rc=0)
    host.set_processes([])

    res = host.run(tr.sshd_liveness_cmd(str(host.prefix)))
    assert res.returncode == 0
    assert host.sv_log.exists()
    assert not host.pgrep_log.exists()


def test_start_sshd_shell_skips_start_when_reexecd_listener_is_up(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.set_sv(None)
    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])

    res = host.run(tr.start_sshd_shell(str(host.prefix)))
    assert res.returncode == 0, res.stderr
    assert not host.sshd_log.exists()


def test_start_sshd_shell_skips_start_when_sv_reports_run(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.set_sv("run: sshd: (pid 123) 9s", rc=0)
    host.set_processes([])

    res = host.run(tr.start_sshd_shell(str(host.prefix)))
    assert res.returncode == 0, res.stderr
    assert not host.sshd_log.exists()


def test_start_sshd_shell_starts_sshd_when_only_session_children_exist(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.set_sv(None)
    host.set_processes(["sshd-session: u0_a601@pts/0"])

    res = host.run(tr.start_sshd_shell(str(host.prefix)))
    assert res.returncode == 0, res.stderr
    assert host.sshd_log.read_text(encoding="utf-8").strip() == "started"


def test_start_sshd_shell_fails_if_sshd_does_not_come_up(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.sshd_starts_listener = False
    host._write_sshd_stub()
    host.set_sv(None)
    host.set_processes([])

    res = host.run(tr.start_sshd_shell(str(host.prefix)))
    assert res.returncode != 0
    assert host.sshd_log.read_text(encoding="utf-8").strip() == "started"


def test_liveness_cmd_quotes_prefix_with_spaces_and_regex_metachars(tmp_path):
    host = FakeTermuxHost(tmp_path, prefix_name="odd.dir+1 with space")
    host.set_sv(None)
    # Metacharacter '.' must not match 'X' in the prefix path.
    wrong_prefix = str(host.prefix).replace("odd.dir", "oddXdir")
    host.set_processes([f"{wrong_prefix}/bin/sshd -D -e"])
    assert host.run(tr.sshd_liveness_cmd(str(host.prefix))).returncode != 0

    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])
    assert host.run(tr.sshd_liveness_cmd(str(host.prefix))).returncode == 0

    for script in (tr.start_sshd_shell(str(host.prefix)), tr.sshd_running_shell(str(host.prefix))):
        chk = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True, check=False)
        assert chk.returncode == 0, chk.stderr


def test_cfengine_check_sshd_has_no_shell_interpolation_and_matches_live_cases(tmp_path):
    raw_cmd = _extract_cf_sshd_up_cmd()
    # CFEngine's scanner eats shell $(...)/${...} inside returnszero() (stayturgid.cf:186).
    without_cf_vars = raw_cmd.replace("$(p)", "")
    assert "$(" not in without_cf_vars, raw_cmd
    assert "${" not in without_cf_vars, raw_cmd

    host = FakeTermuxHost(tmp_path)
    cmd = raw_cmd.replace("$(p)", str(host.prefix))

    cases = [
        ("run: sshd: (pid 29807) 10s; run: log: (pid 9) 10s", 0, [], True),
        ("down: sshd: 5s; run: log: (pid 9) 10s", 0, [], False),
        ("fail: sshd: unable to change to service directory", 1, [], False),
        ("fail: sshd: runsv not running", 1, [f"{host.prefix}/bin/sshd -D -e"], True),
        (None, 0, [f"{host.prefix}/bin/sshd -D -e"], True),
        (None, 0, ["sshd -D"], True),
        (None, 0, ["sshd"], True),
        (None, 0, ["sshd-session: u0_a601@pts/0", f"{host.prefix}/libexec/sshd-session -R"], False),
        # Self-match guard: the shell running the returnszero() command itself must not match.
        (None, 0, [f"/bin/sh -c {cmd}", f"{host.prefix}/bin/pgrep -f ^({host.prefix}/bin/)?sshd( |$)"], False),
        (None, 0, [], False),
    ]
    for sv_out, sv_rc, procs, want_up in cases:
        host.set_sv(sv_out, rc=sv_rc)
        host.set_processes(procs)
        res = host.run(cmd, shell="sh")
        assert (res.returncode == 0) is want_up, (sv_out, procs, res.returncode, res.stderr)


def test_liveness_matcher_never_self_matches_actual_shell_commands(tmp_path):
    host = FakeTermuxHost(tmp_path)
    host.set_sv(None)
    cmd = tr.sshd_liveness_cmd(str(host.prefix))
    pat = tr.sshd_liveness_pattern(str(host.prefix))
    host.set_processes(
        [
            f"/bin/sh -c {cmd}",
            f"bash -c {tr.start_sshd_shell(str(host.prefix))}",
            f"pgrep -f {pat}",
        ]
    )
    assert host.run(cmd, shell="sh").returncode != 0
    assert host.run(cmd, shell="bash").returncode != 0


def test_run_as_termux_two_layer_quoting(tmp_path):
    """Verify start_sshd_shell / sshd_running_shell survive adb shell's extra sh -c parse layer."""
    host = FakeTermuxHost(tmp_path, prefix_name="odd.dir+1 with space")
    host.set_sv(None)
    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])

    for script in (tr.sshd_running_shell(str(host.prefix)), tr.start_sshd_shell(str(host.prefix))):
        outer = "bash -c " + shlex.quote(script)
        res = host.run(outer, shell="sh")
        assert res.returncode == 0, res.stderr
    assert not host.sshd_log.exists()

    # With only sshd-session running, sshd_running_shell exits non-zero through the two-layer parse.
    host.set_processes(["sshd-session: u0_a601@pts/0"])
    outer = "bash -c " + shlex.quote(tr.sshd_running_shell(str(host.prefix)))
    assert host.run(outer, shell="sh").returncode != 0


@pytest.mark.parametrize(
    ("ps_out", "want"),
    [
        ("u:r:untrusted_app:s0 u0_a601 4321 1 sshd\n", "u:r:untrusted_app:s0"),
        (
            "u:r:untrusted_app:s0 u0_a601 29807 1 /data/data/com.termux/files/usr/bin/sshd\n",
            "u:r:untrusted_app:s0",
        ),
        ("u:r:untrusted_app:s0 u0_a601 4322 4321 sshd-session\n", ""),
        ("u:r:untrusted_app:s0 u0_a601 4323 4322 sshd-auth\n", ""),
        ("", ""),
    ],
)
def test_sshd_domain_recognises_reexecd_listener_and_ignores_children(ps_out, want):
    assert tr.sshd_domain(lambda _cmd: (0, ps_out, ""), "dev") == want


def test_on_device_helpers_survive_missing_or_old_stayturgid_shell(monkeypatch, tmp_path):
    """Rolling rsync updates start_adb.py and stayturgid_repair.py before stayturgid_shell.py."""
    host = FakeTermuxHost(tmp_path)
    host.set_sv(None)
    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])
    monkeypatch.setenv("PATH", f"{host.bin}:/usr/bin:/bin")

    monkeypatch.setattr(start_adb, "PREFIX", str(host.prefix))
    for stale_sh in (None, object()):
        monkeypatch.setattr(start_adb, "_sh", stale_sh)
        assert start_adb.sshd_is_running() is True

    monkeypatch.setattr(repair, "PREFIX", str(host.prefix))
    monkeypatch.setattr(repair, "sshd_listening", lambda: False)
    monkeypatch.setattr(repair, "_shell_lib", lambda: object())
    assert repair.sshd_up() is True
    monkeypatch.setattr(repair, "_shell_lib", lambda: (_ for _ in ()).throw(ImportError("no stayturgid_shell")))
    assert repair.sshd_up() is True


@pytest.mark.parametrize(
    ("procs", "want"),
    [
        (["/data/data/com.termux/files/usr/bin/sshd -D -e"], True),
        (["sshd -D"], True),
        (["sshd"], True),
        (["sshd-session: u0_a601@pts/0"], False),
        (["sshd: u0_a601@pts/0"], False),
        ([], False),
    ],
)
def test_shared_python_liveness_pattern(procs, want):
    pat = stayturgid_shell.sshd_liveness_pattern("/data/data/com.termux/files/usr")
    assert pat == tr.sshd_liveness_pattern("/data/data/com.termux/files/usr")
    matched = any(re.search(pat, line) for line in procs)
    assert matched is want


def test_start_adb_sshd_is_running_prefers_sv_then_pgrep_f(monkeypatch, tmp_path):
    host = FakeTermuxHost(tmp_path)
    monkeypatch.setattr(start_adb, "PREFIX", str(host.prefix))
    monkeypatch.setenv("PATH", f"{host.bin}:/usr/bin:/bin")

    host.set_sv("run: sshd: (pid 42) 5s", rc=0)
    host.set_processes([])
    assert start_adb.sshd_is_running() is True

    host.set_sv("down: sshd: 5s; run: log: (pid 9) 5s", rc=0)
    host.set_processes([])
    assert start_adb.sshd_is_running() is False

    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])
    assert start_adb.sshd_is_running() is True

    host.set_processes(["sshd-session: u0_a601@pts/0"])
    assert start_adb.sshd_is_running() is False


def test_stayturgid_repair_sshd_up_prefers_sv_then_pgrep_f(monkeypatch, tmp_path):
    host = FakeTermuxHost(tmp_path)
    monkeypatch.setattr(repair, "PREFIX", str(host.prefix))
    monkeypatch.setattr(repair, "sshd_listening", lambda: False)
    monkeypatch.setenv("PATH", f"{host.bin}:/usr/bin:/bin")

    host.set_sv("run: sshd: (pid 42) 5s", rc=0)
    host.set_processes([])
    assert repair.sshd_up() is True

    host.set_sv("down: sshd: 5s; run: log: (pid 9) 5s", rc=0)
    host.set_processes(["sshd-session: u0_a601@pts/0"])
    assert repair.sshd_up() is False

    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])
    assert repair.sshd_up() is True


def test_stayturgid_verify_check_sshd_prefers_sv_then_pgrep_f(monkeypatch, tmp_path):
    host = FakeTermuxHost(tmp_path)
    monkeypatch.setattr(_VERIFY_MOD, "TERMUX_PREFIX", str(host.prefix))
    monkeypatch.setattr(_VERIFY_MOD, "_shell", lambda *a, **k: (1, "", ""))
    monkeypatch.setenv("PATH", f"{host.bin}:/usr/bin:/bin")

    host.set_sv("run: sshd: (pid 42) 5s", rc=0)
    host.set_processes([])
    ok, msg = _VERIFY_MOD.check_sshd()
    assert ok is True and "sv status" in msg

    host.set_sv("down: sshd: 5s; run: log: (pid 9) 5s", rc=0)
    host.set_processes(["sshd-session: u0_a601@pts/0"])
    ok, _ = _VERIFY_MOD.check_sshd()
    assert ok is False

    host.set_processes([f"{host.prefix}/bin/sshd -D -e"])
    ok, msg = _VERIFY_MOD.check_sshd()
    assert ok is True and "pgrep -f" in msg


def test_no_production_code_uses_pgrep_x_sshd():
    """Guard against reintroducing `pgrep -x sshd`, which misses re-exec'd listeners (#341)."""
    tracked = subprocess.run(
        ["git", "ls-files", "device", "ansible_collections"],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    bad_re = re.compile(r"""pgrep\s+-x\s+sshd|['"]pgrep['"]\s*,\s*['"]-x['"]\s*,\s*['"]sshd['"]""")
    offenders = []
    for rel in tracked:
        for lineno, line in enumerate((REPO / rel).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if bad_re.search(line):
                offenders.append(f"{rel}:{lineno}")
    assert offenders == []
