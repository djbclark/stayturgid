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

sys.path.insert(0, os.path.join(STG, "lib"))
try:
    import termux_api as tapi
except ImportError:
    tapi = None
# Deployed beside this script by the same copy loop. Importing it pins the
# no-emulator-scan setting for every adb server this loop or its children start.
try:
    import stayturgid_shell as _sh
except ImportError:
    _sh = None


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


def _rotate_logs() -> None:
    """Keep ~/.stayturgid/logs (and the /sdcard mirror) from growing forever.

    Nothing on the device rotated these. By 2026-10-02 repair-cfengine.log was
    29 MB on p7a and 16 MB on s24 (mostly CFEngine's ps-parse error spam, fixed
    separately), and every other log here grows without bound too.

    Rename-to-.1 rather than truncate-in-place, because otelcol-contrib tails
    repair.jsonl: a rename leaves its open fd valid so it drains the rotated
    file, and the fresh empty file is picked up as a new one. Truncating under
    it would make the fileconsumer re-read from the start and re-ship every
    line. Every writer here opens in append mode per line, so none of them hold
    a stale fd across the rename.
    """
    try:
        limit = int(os.environ.get("STAYTURGID_LOG_MAX_BYTES", str(2 * 1024 * 1024)))
    except ValueError:
        limit = 2 * 1024 * 1024
    if limit <= 0:
        return
    for d in (os.path.join(STG, "logs"), os.path.join(SD, "logs")):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            if name.endswith(".1"):
                continue
            path = os.path.join(d, name)
            try:
                if not os.path.isfile(path) or os.path.getsize(path) <= limit:
                    continue
                os.replace(path, path + ".1")
            except OSError:
                # /sdcard is FUSE-backed and can refuse a rename; never let log
                # housekeeping break the only on-device supervisor.
                pass


def _boot_log(msg: str) -> None:
    try:
        # Created here, not only by the loop's _ensure_dirs(): a second start that
        # finds the loop already running logs that and returns before the loop's own
        # child has made logs/, and the line was then dropped (test-unit 115 flake).
        os.makedirs(os.path.dirname(BOOTLOG), exist_ok=True)
        with open(BOOTLOG, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _running_bootloop_pid() -> int:
    """PID of a live start_adb.py loop recorded in the pidfile, else 0."""
    try:
        with open(BOOTLOOP_PID_FILE) as f:
            pid = int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0
    if pid <= 0:
        return 0
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            cmdline = f.read().decode(errors="replace")
    except OSError:
        # No /proc (unit tests on macOS) or the pid is gone.
        try:
            r = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
            cmdline = r.stdout
        except (OSError, subprocess.TimeoutExpired):
            return 0
    return pid if "start_adb" in cmdline else 0


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


def try_sv_up_sshd() -> bool:
    """Bring sshd up under runit supervision (sv up sshd).

    Preferred over a bare `sshd`: runsv then restarts sshd if it ever dies
    on its own, and the same `sv up` path is what every other recovery
    trigger (Tasker RUN_COMMAND, login-shell start-services, cf-agent) uses,
    so there is exactly one supervised instance instead of a bare listener
    racing runsv for port 8022. Returns False when there is no usable sv
    path — caller falls back to the historical bare start.
    """
    sv = os.path.join(PREFIX, "bin", "sv")
    svdir = os.path.join(PREFIX, "var", "service")
    if not (os.access(sv, os.X_OK) and os.path.isdir(os.path.join(svdir, "sshd"))):
        return False
    env = dict(os.environ, SVDIR=svdir)
    try:
        # -f with the service dir, not -x: see stayturgid_repair.try_sv_up_sshd.
        if subprocess.run(["pgrep", "-f", "[r]unsvdir " + svdir], capture_output=True, timeout=5).returncode != 0:
            # The services' svlogd needs LOGDIR (see boot/00-start-services.sh).
            os.environ.setdefault("LOGDIR", os.path.join(PREFIX, "var", "log"))
            _run_bg(["runsvdir", svdir], log_path=None)
            time.sleep(2)
        r = subprocess.run([sv, "up", "sshd"], capture_output=True, timeout=10, env=env)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


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
            if try_sv_up_sshd():
                _boot_log("sshd started under runit (sv up sshd)")
            else:
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


ADB_UNAUTHORISED = "adb-unauthorised"


def _adb_connect() -> str:
    """Gated localhost:5555 connect: "device", "waiting" or "down".

    Shared with repair, the guards and the Mac's ssh health gather
    (stayturgid_shell.adb_connect), so an unauthorised Termux key gets one
    "Allow USB debugging?" dialog rather than one per caller per cycle.
    """
    if _sh is None:
        return "down"
    return _sh.adb_connect(timeout=5)


def _localhost_adb_state() -> str:
    """ "ok" (uid-2000 shell), "waiting" (Termux's key unauthorised) or "down"."""
    state = _adb_connect()
    if state != "device":
        return state
    rc, output = _capture(["adb", "-s", "localhost:5555", "shell", "id -u"], timeout=5)
    return "ok" if rc == 0 and output.strip() == "2000" else "down"


# @heals: FIRERPA-SECURE-RUNNING
def _localhost_adb_available() -> bool:
    return _localhost_adb_state() == "ok"


def _shell_transport() -> tuple[list[str] | None, str]:
    """Return persistent shell-UID ADB, recovering adbd through rish if needed."""
    state = _localhost_adb_state()
    if state == "ok":
        return ["adb", "-s", "localhost:5555", "shell"], "localhost-adb"
    if state == "waiting":
        # adbd is up and showing the dialog for Termux's key. A rish restart
        # drops that connection, and adb's automatic re-dial raises another.
        return None, ADB_UNAUTHORISED

    # A FIRERPA child launched directly inside a Shizuku rish session is killed
    # when that binder shell closes, even with nohup/setsid. Use rish only to
    # recover persistent TCP adbd, then launch through Termux localhost ADB.
    if os.access(RISH, os.X_OK):
        rc, output = _capture([RISH, "-c", "id -u"], timeout=8)
        if rc == 0 and output.strip().endswith("2000"):
            restart = "setprop service.adb.tcp.port 5555; setprop ctl.restart adbd"
            if _run([RISH, "-c", restart], timeout=10) == 0:
                for _ in range(8):
                    state = _localhost_adb_state()
                    if state == "ok":
                        return (
                            ["adb", "-s", "localhost:5555", "shell"],
                            "localhost-adb-rish-recovered",
                        )
                    if state == "waiting":
                        return None, ADB_UNAUTHORISED
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
        f"test -x {shlex.quote(os.path.join(FIRERPA_DIR, 'bin', 'python3.12'))} "
        f"&& test -r {shlex.quote(FIRERPA_CERTIFICATE)} "
        f"&& test -r {shlex.quote(FIRERPA_LIFECYCLE)}"
    )
    rc, transport = _shell_run(test_cmd, timeout=8)
    if transport == "unavailable":
        _boot_log(f"FIRERPA {reason}: privileged shell unavailable")
        return False
    if transport == ADB_UNAUTHORISED:
        _boot_log(f"FIRERPA {reason}: adb unauthorised, waiting for the user")
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

    # One serial only: adb treats 127.0.0.1:5555 and localhost:5555 as two
    # transports, and re-dials each on its own when adbd drops them, so a
    # revoke raised a dialog per alias. localhost:5555 reaches the same adbd.
    if _adb_connect() != "waiting":
        # Shizuku's TCP mode normally opens 5555 at boot. This still covers a
        # Termux adb server whose one transport is a Wireless-debugging one.
        # Not while a dialog is pending: restarting adbd under it raises another.
        _run(["adb", "tcpip", "5555"])

    while True:
        try:
            _ensure_dirs()
            _rotate_logs()

            if _run_repair_pass() is None and _run(["pgrep", "sshd"], capture_output=True) != 0:
                if not try_sv_up_sshd():
                    _run_bg(["sshd"])

            if _cmd_exists("termux-battery-status") and tapi is not None:
                # tapi.run() never signals a hung termux-api client on timeout
                # (orphans it instead) — a plain `timeout 8 ...` wrapper here
                # previously SIGTERM'd it mid-socket-write, producing a loud
                # "Error in ResultReturner" toast when com.termux.api was slow
                # to cold-start at boot (#38).
                r = tapi.run(["termux-battery-status"], timeout=8)
                if r is None or r.returncode != 0:
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
                    tapi.run_ff(["termux-api-start"])
                    time.sleep(2)
                else:
                    tapi.run_ff(["termux-api-start"])

            _run_guard("stayturgid_battery_alarm.py")
            _run_guard("stayturgid_screen_awake_guard.py", extra_args=["check"])
            _run_guard("stayturgid_agent_presence.py", extra_args=["guard"])

            _version_check()

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

        _sleep_watching_adb_auth(interval)


def _run_repair_pass() -> int | None:
    """One ordinary stayturgid_repair.py run (rc), or None when it is not installed.

    The script's own non-blocking lock turns a run that lands on another pass
    (cf-agent's bootloop restart, the Mac's ssh heal) into its duplicate branch.
    """
    repair = os.path.join(BIN, "stayturgid_repair.py")
    if not os.access(repair, os.X_OK):
        return None
    return subprocess.run(["python3", repair], capture_output=True, timeout=300).returncode


# Revoking USB debugging authorisations kills everything under adbd's sessions:
# the Shizuku server and the uid-2000 watchdog loop that would restart it. The
# repair pass that finds Termux's key unauthorised can only stand down, and the
# next one is a full interval away (Shizuku down 15 min after the operator had
# already accepted the dialog, s24 2026-10-04). While the shared auth-wait marker
# exists, this loop's sleep reads `adb devices` (no connect, so no dialog) and
# runs one repair pass as soon as the row is "device" again.
ADB_REAUTH_POLL_SEC = 10.0
# With no marker the sleep only stats the file, so a wait that another caller
# (cf-agent, the Mac's ssh health gather) starts mid-sleep is still noticed.
ADB_REAUTH_IDLE_SEC = 60.0
# Rate cap on top of one-pass-per-marker, should the transport flap.
ADB_REAUTH_MIN_GAP_SEC = 60.0
ADB_REAUTH_STAMP = os.path.join(STG, "state", "adb-reauth-repair")


def _adb_auth_marker_text() -> str | None:
    """The shared auth-wait marker's content, or None when there is no marker."""
    if _sh is None:
        return None
    try:
        with open(_sh.adb_auth_marker()) as f:
            return f.read().strip()
    except OSError:
        return None


def _reauth_stamp() -> tuple[float, str]:
    """(when, marker text) of the last pass this loop triggered."""
    try:
        with open(ADB_REAUTH_STAMP) as f:
            when, _, marker = f.read().strip().partition(" ")
        return float(when), marker
    except (OSError, ValueError):
        return 0.0, ""


def _repair_on_reauth(marker: str, now: float) -> bool:
    """Run one repair pass if Termux's key was accepted while *marker* stood.

    The gate confirms "device" and clears the marker (an authorised row costs it
    one `adb devices`, no connect). The stamp is written before the pass, so a
    pass that fails or hangs is not retried here; the timer owns recovery.
    """
    last, consumed = _reauth_stamp()
    if marker == consumed or 0 <= now - last < ADB_REAUTH_MIN_GAP_SEC:
        return False
    if _sh.adb_devices_state(timeout=5) != "device":
        return False
    if _sh.adb_connect(timeout=5) != "device":
        return False
    try:
        os.makedirs(os.path.dirname(ADB_REAUTH_STAMP), exist_ok=True)
        with open(ADB_REAUTH_STAMP, "w") as f:
            f.write(f"{int(now)} {marker}\n")
    except OSError:
        # Without the stamp nothing bounds a retry of this event.
        return False
    _boot_log("adb authorised again: running the repair pass now, not at the next interval")
    try:
        outcome = f"rc={_run_repair_pass()}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        outcome = type(exc).__name__
    _boot_log(f"repair pass after adb re-authorisation finished: {outcome}")
    return True


def _sleep_watching_adb_auth(interval: float) -> None:
    """Sleep *interval*, cutting it short only for one repair pass on re-authorisation."""
    deadline = time.monotonic() + interval
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return
        step = ADB_REAUTH_IDLE_SEC
        marker = _adb_auth_marker_text()
        if marker is not None:
            step = ADB_REAUTH_POLL_SEC
            try:
                _repair_on_reauth(marker, time.time())
            except Exception as exc:
                _boot_log(f"adb re-authorisation check failed: {type(exc).__name__}: {exc}")
        time.sleep(min(left, step))


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
    # Hold wakelock for Doze resistance. tapi.run_ff also catches the
    # TimeoutExpired the bare subprocess.run below did not (only OSError was
    # handled), which would otherwise crash boot if termux-wake-lock hangs.
    if tapi is not None:
        tapi.run_ff(["termux-wake-lock"])
    else:
        try:
            subprocess.run(["termux-wake-lock"], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

    startup_sshd()
    startup_cfserverd()

    # One loop per device. Termux:Boot, the deploy handler (which kills the
    # recorded loop first), and the Mac fleet-health heal can all land here;
    # without this a second start ran two loops side by side (t2e 2026-09-29).
    running = _running_bootloop_pid()
    if running:
        _boot_log(f"bootloop already running (pid {running}); not starting another")
        return 0

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
