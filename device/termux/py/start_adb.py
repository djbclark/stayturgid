#!/data/data/com.termux/files/usr/bin/python3
"""Stayturgid device boot supervisor (replaces start-adb.sh).

Runs at Termux:Boot — sets up environment, starts core services (sshd,
cf-serverd, FIRERPA), holds a wakelock, then backgrounds a daemon loop
that runs self-healing checks each cycle. The bootloop PID is written
immediately so the Ansible handler can verify it without waiting.

Deploy to: ~/.termux/boot/start-adb.sh (compat shim) or call directly.
"""

import os
import shlex
import signal
import subprocess
import sys
import time
from typing import IO, Any

PREFIX = "/data/data/com.termux/files/usr"
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
TMPDIR = os.path.join(PREFIX, "tmp")

os.environ["HOME"] = HOME
os.environ["PREFIX"] = PREFIX
os.environ["TMPDIR"] = TMPDIR
os.environ["LD_LIBRARY_PATH"] = os.path.join(PREFIX, "lib")

_paths = [
    os.path.join(PREFIX, "bin"),
    os.path.join(PREFIX, "sbin"),
]
os.environ["PATH"] = ":".join(p for p in _paths if os.path.isdir(p)) + ":" + os.environ.get("PATH", "")

STG = os.path.join(HOME, ".stayturgid")
BIN = os.path.join(STG, "bin")
BOOTLOG = os.path.join(STG, "logs", "boot.log")
BOOTLOOP_PID_FILE = os.path.join(STG, "run", "bootloop.pid")
CFENGINE_CF = os.path.join(STG, "cfengine", "stayturgid.cf")
CF_SERVERD_CF = os.path.join(STG, "cfengine", "cf-serverd.cf")
CF_SERVERD_PID = os.path.join(STG, "run", "cf-serverd.pid")


def _cfserverd_argv() -> list[str]:
    """cf-serverd argv, with optional verbosity for investigation.

    cf-serverd only survives on Termux as a child of this persistent boot loop;
    an SSH-launched instance dies on session close, so verbose logging cannot be
    obtained ad hoc. Set STAYTURGID_CFSERVERD_VERBOSE to make the boot-loop
    instance log the reason for e.g. cf-runagent "Unspecified server refusal"
    (stayturgid#84): "1" -> -v, "2"/"debug" -> -d, or an explicit "-<flag>".
    Unset/"0" keeps the quiet default.
    """
    argv = [os.path.join(PREFIX, "bin", "cf-serverd"), "-Ff", CF_SERVERD_CF]
    v = os.environ.get("STAYTURGID_CFSERVERD_VERBOSE", "").strip()
    if v in ("1", "v"):
        argv.append("-v")
    elif v in ("2", "d", "debug"):
        argv.append("-d")
    elif v.startswith("-"):
        argv.append(v)
    return argv


VERSION_CHECK_STAMP = os.path.join(STG, "state", "last_version_check")
OTELCOL_START = os.path.join(HOME, ".termux", "boot", "start-otelcol.sh")

_ENV_FILE = os.path.join(STG, "env")
try:
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("export "):
                continue
            parts = line[len("export ") :].split("=", 1)
            if len(parts) == 2:
                os.environ[parts[0]] = parts[1].strip().strip('"')
except OSError:
    pass

SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
FIRERPA_DIR = os.environ.get("STAYTURGID_FIRERPA_DIR", "/data/local/tmp/firerpa/server")
try:
    FIRERPA_PORT = int(os.environ.get("STAYTURGID_FIRERPA_PORT", "65000"))
except ValueError:
    FIRERPA_PORT = 65000
FIRERPA_CERTIFICATE = os.environ.get("STAYTURGID_FIRERPA_CERTIFICATE", os.path.join(FIRERPA_DIR, "lamda.pem"))
FIRERPA_ROOT = os.path.dirname(FIRERPA_DIR)
FIRERPA_LIFECYCLE = os.environ.get(
    "STAYTURGID_FIRERPA_LIFECYCLE",
    os.path.join(FIRERPA_ROOT, "firerpa_lifecycle.py"),
)
RISH = os.path.join(BIN, "rish")


def _ensure_dirs() -> None:
    for d in [
        os.path.join(STG, "logs"),
        os.path.join(STG, "run"),
        os.path.join(STG, "state"),
    ]:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    for d in [
        os.path.join(SD, "logs"),
        os.path.join(SD, "run"),
        os.path.join(SD, "state"),
    ]:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass


def _boot_log(msg: str) -> None:
    try:
        with open(BOOTLOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _pid_alive(pidfile: str) -> bool:
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip() or 0)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _write_pid(pidfile: str, pid: int) -> None:
    try:
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        with open(pidfile, "w") as f:
            f.write(str(pid))
    except OSError:
        pass


def _run(cmd: list[str], **kwargs) -> int:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("timeout", 30)
    try:
        return subprocess.run(cmd, **kwargs).returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


def _capture(cmd: list[str], *, timeout: float = 30) -> tuple[int, str]:
    """Run a command and return a stable ``(rc, stdout)`` result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def _run_bg(cmd: list[str], log_path: str | None = None) -> int:
    try:
        stdout: IO[Any] | int | None = None
        stderr: int | None = None
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            stdout = open(log_path, "a")
            stderr = subprocess.STDOUT
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        return p.pid
    except OSError:
        return -1


# ── One-time startup ────────────────────────────────────────────────────────


def startup_sshd() -> None:
    """Start sshd, removing a stale runsv/down file that silently blocks it."""
    down = os.path.join(PREFIX, "var", "service", "sshd", "down")
    try:
        os.remove(down)
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["pgrep", "-x", "sshd"],
            capture_output=True,
            timeout=5,
        )
        if r.returncode != 0:
            _run_bg(["sshd"], log_path=None)
            _boot_log("sshd started")
    except (OSError, subprocess.TimeoutExpired):
        pass


def startup_cfserverd() -> None:
    if not os.access(os.path.join(PREFIX, "bin", "cf-serverd"), os.X_OK):
        return
    if not os.path.isfile(CF_SERVERD_CF):
        return
    if _pid_alive(CF_SERVERD_PID):
        return
    pid = _run_bg(
        _cfserverd_argv(),
        log_path=os.path.join(STG, "logs", "cf-serverd.log"),
    )
    if pid > 0:
        _write_pid(CF_SERVERD_PID, pid)
        _boot_log(f"cf-serverd started (pid {pid})")


# @heals: FIRERPA-SECURE-RUNNING
def _localhost_adb_available() -> bool:
    _run(["adb", "connect", "localhost:5555"], timeout=5)
    rc, output = _capture(["adb", "-s", "localhost:5555", "shell", "id -u"], timeout=5)
    return rc == 0 and output.strip() == "2000"


def _shell_transport() -> tuple[list[str] | None, str]:
    """Return persistent shell-UID ADB, recovering adbd through rish if needed."""
    if _localhost_adb_available():
        return ["adb", "-s", "localhost:5555", "shell"], "localhost-adb"

    # A FIRERPA child launched directly inside a Shizuku rish session is killed
    # when that binder shell closes, even with nohup/setsid. Use rish only to
    # recover persistent TCP adbd, then launch through Termux localhost ADB.
    if os.access(RISH, os.X_OK):
        rc, output = _capture([RISH, "-c", "id -u"], timeout=8)
        if rc == 0 and output.strip().endswith("2000"):
            restart = "setprop service.adb.tcp.port 5555; setprop ctl.restart adbd"
            if _run([RISH, "-c", restart], timeout=10) == 0:
                for _ in range(8):
                    if _localhost_adb_available():
                        return (
                            ["adb", "-s", "localhost:5555", "shell"],
                            "localhost-adb-rish-recovered",
                        )
                    time.sleep(1)

    return None, "unavailable"


def _shell_run(command: str, *, timeout: float = 12) -> tuple[int, str]:
    transport, name = _shell_transport()
    if transport is None:
        return -1, name
    return _run(transport + [command], timeout=timeout), name


def _firerpa_alive() -> bool:
    """Probe FIRERPA through the shell identity that owns the service."""
    cmd = f"ss -ltn 2>/dev/null | grep -q ':{FIRERPA_PORT} '"
    rc, _ = _shell_run(cmd, timeout=8)
    return rc == 0


def _launch_firerpa_via_shell(reason: str) -> bool:
    """Launch FIRERPA as Android uid 2000 through local ADB or rish."""
    test_cmd = (
        f"test -x {shlex.quote(os.path.join(FIRERPA_DIR, 'bin', 'python3.9'))} "
        f"&& test -r {shlex.quote(FIRERPA_CERTIFICATE)} "
        f"&& test -r {shlex.quote(FIRERPA_LIFECYCLE)}"
    )
    rc, transport = _shell_run(test_cmd, timeout=8)
    if transport == "unavailable":
        _boot_log(f"FIRERPA {reason}: privileged shell unavailable")
        return False
    if rc != 0:
        _boot_log(f"FIRERPA {reason}: runtime, lifecycle wrapper, or certificate missing via {transport}")
        return False

    lifecycle_cmd = [
        sys.executable,
        FIRERPA_LIFECYCLE,
        "start",
        f"--port={FIRERPA_PORT}",
        f"--certificate={FIRERPA_CERTIFICATE}",
    ]
    if transport.startswith("localhost-adb"):
        lifecycle_cmd.extend(["--adb-target", "localhost:5555"])
    else:
        lifecycle_cmd.extend(["--rish", RISH])
    rc = _run(lifecycle_cmd, timeout=75)
    if rc == 0:
        _boot_log(f"FIRERPA secure {reason} with accessibility coexistence activated via {transport}")
        return True
    # Some Android adb/rish versions keep the client pipe open after the
    # fully redirected background launch. A local client timeout is not a
    # launch failure if the listener subsequently appears.
    for _ in range(10):
        time.sleep(2)
        if _firerpa_alive():
            _boot_log(f"FIRERPA secure {reason} confirmed via {transport} after client rc={rc}")
            return True
    _boot_log(f"FIRERPA secure {reason} failed rc={rc} via {transport}")
    return False


def startup_firerpa() -> None:
    enabled = os.environ.get("STAYTURGID_FIRERPA_ENABLED", "1")
    if enabled != "1":
        return
    if _firerpa_alive():
        return
    _launch_firerpa_via_shell("startup")


# ── Daemon loop ─────────────────────────────────────────────────────────────


def daemon_loop() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        interval = float(os.environ.get("STAYTURGID_INTERVAL_SEC", "300"))
    except ValueError:
        interval = 300.0
    if interval < 1.0:
        interval = 300.0

    try:
        settle = float(os.environ.get("STAYTURGID_BOOT_SETTLE_SEC", "30"))
    except ValueError:
        settle = 30.0
    time.sleep(settle)

    _run(["adb", "connect", "127.0.0.1:5555"])
    _run(["adb", "tcpip", "5555"])

    while True:
        try:
            _ensure_dirs()

            repair = os.path.join(BIN, "stayturgid_repair.py")
            if os.access(repair, os.X_OK):
                subprocess.run(["python3", repair], capture_output=True, timeout=300)
            elif _run(["pgrep", "sshd"], capture_output=True) != 0:
                _run_bg(["sshd"])

            if _cmd_exists("termux-battery-status"):
                r = subprocess.run(
                    ["timeout", "8", "termux-battery-status"],
                    capture_output=True,
                    timeout=15,
                )
                if r.returncode != 0:
                    _run(
                        [
                            "adb",
                            "-s",
                            "localhost:5555",
                            "shell",
                            "am",
                            "force-stop",
                            "com.termux.api",
                        ]
                    )
                    time.sleep(2)
                    _run(["termux-api-start"])
                    time.sleep(2)
                else:
                    _run(["termux-api-start"])

            _run_guard("stayturgid_battery_alarm.py")
            _run_guard("stayturgid_screen_awake_guard.py", extra_args=["check"])
            _run_guard("stayturgid_agent_presence.py", extra_args=["guard"])

            _version_check()
            _run_guard("stayturgid_autojs6_guard.py", extra_args=["check"])

            if (
                os.environ.get("STAYTURGID_NO_LOCAL_ADB", "0") == "1"
                and os.environ.get("STAYTURGID_PEER_BOOTSTRAP", "1") != "0"
            ):
                _run_guard("stayturgid_peer_keepalive.py")

            _run_cfagent()
            _monitor_cfserverd()
            _monitor_firerpa()
            _monitor_otelcol()
        except Exception as exc:
            # A single slow Termux API or repair command must never terminate
            # the only on-device supervisor.
            _boot_log(f"bootloop iteration failed: {type(exc).__name__}: {exc}")

        time.sleep(interval)


def _cmd_exists(name: str) -> bool:
    import shutil

    return shutil.which(name) is not None


def _run_guard(script_name: str, extra_args: list[str] | None = None) -> None:
    path = os.path.join(BIN, script_name)
    if not os.access(path, os.X_OK):
        return
    cmd = ["python3", path]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _version_check() -> None:
    script = os.path.join(BIN, "stayturgid_check_repo_version.py")
    if not os.access(script, os.X_OK):
        return
    now = int(time.time())
    last = 0
    try:
        with open(VERSION_CHECK_STAMP) as f:
            last = int(f.read().strip() or 0)
    except (OSError, ValueError):
        pass
    if now - last >= 86400:
        try:
            subprocess.run(["python3", script], capture_output=True, timeout=60)
            _write_pid(VERSION_CHECK_STAMP, now)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_cfagent() -> None:
    cf_agent = os.path.join(PREFIX, "bin", "cf-agent")
    if not os.access(cf_agent, os.X_OK):
        return
    if not os.path.isfile(CFENGINE_CF):
        return
    log_path = os.path.join(STG, "logs", "repair-cfengine.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as lf:
            subprocess.run(
                [cf_agent, "-D", "android,linux", "-Kf", CFENGINE_CF],
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _monitor_cfserverd() -> None:
    if not os.path.isfile(CF_SERVERD_PID):
        return
    if _pid_alive(CF_SERVERD_PID):
        return
    cf_bin = os.path.join(PREFIX, "bin", "cf-serverd")
    if not os.access(cf_bin, os.X_OK) or not os.path.isfile(CF_SERVERD_CF):
        return
    pid = _run_bg(
        _cfserverd_argv(),
        log_path=os.path.join(STG, "logs", "cf-serverd.log"),
    )
    if pid > 0:
        _write_pid(CF_SERVERD_PID, pid)
        _boot_log(f"cf-serverd restarted (pid {pid})")


def _monitor_firerpa() -> None:
    enabled = os.environ.get("STAYTURGID_FIRERPA_ENABLED", "1")
    if enabled != "1":
        return
    if _firerpa_alive():
        return
    _launch_firerpa_via_shell("restart")


# @heals: OTELCOL-RUNNING
def _monitor_otelcol() -> None:
    """Re-run the pidfile-safe boot entrypoint if edge collection is enabled."""
    if not os.access(OTELCOL_START, os.X_OK):
        return
    rc = _run([OTELCOL_START], timeout=15)
    if rc != 0:
        _boot_log(f"otelcol restart failed rc={rc}")


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> int:
    # Hold wakelock for Doze resistance
    try:
        subprocess.run(["termux-wake-lock"], capture_output=True, timeout=5)
    except OSError:
        pass

    startup_sshd()
    startup_cfserverd()

    pid = os.fork()
    if pid == 0:
        # Child: detach from Termux:Boot's launch pipe, then run forever.
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        if devnull > 2:
            os.close(devnull)
        startup_firerpa()
        daemon_loop()
        sys.exit(0)
    else:
        # Parent: write pidfile immediately, then exit (Ansible handler checks this)
        _write_pid(BOOTLOOP_PID_FILE, pid)
        _boot_log(f"bootloop started (pid {pid})")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
