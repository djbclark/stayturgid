#!/data/data/com.termux/files/usr/bin/python3
"""Fast repair bridge daemon.

Polls a trigger file every 2s; when found, deletes it and runs
stayturgid_repair.py.

Deploy to ~/.stayturgid/bin/bridges.py. Started at boot by:
  ~/.termux/boot/start-repair-bridge.sh.
  Shell script is a minimal one-liner (pidfile guard lives here).
"""

import argparse
import os
import subprocess
import sys
import time

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")

STG = os.path.join(HOME, ".stayturgid")
_ENV_FILE = os.path.join(STG, "env")
if os.path.isfile(_ENV_FILE):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("export STAYTURGID_SD="):
                os.environ["STAYTURGID_SD"] = line.split("=", 1)[1].strip().strip('"')

SD = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")

POLL_SEC = 2


def ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass


def _log(stg: str, name: str, msg: str) -> None:
    log_path = os.path.join(stg, "logs", f"{name}-bridge.log")
    _ensure_dir(os.path.dirname(log_path))
    try:
        with open(log_path, "a") as f:
            f.write(f"{ts()} [{name}-bridge] {msg}\n")
    except OSError:
        pass


def _pidfile_alive(pidfile_path: str) -> bool:
    try:
        with open(pidfile_path) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline") as f:
            raw = f.read()
        return "bridges" in raw or "stayturgid_bridges" in raw
    except (OSError, ValueError):
        return False


def _write_pidfile(stg: str, pidfile_name: str) -> None:
    pidfile = os.path.join(stg, "run", pidfile_name)
    _ensure_dir(os.path.dirname(pidfile))
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))


def _is_file(p: str) -> bool:
    return os.path.isfile(p)


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def run_repair_mode() -> None:
    name = "repair"
    _write_pidfile(STG, "bridge.pid")

    trigger1 = os.path.join(SD, "run", "repair_now")
    trigger2 = os.path.join("/sdcard/stayturgid/run", "repair_now")
    repair_script = os.path.join(STG, "bin", "stayturgid_repair.py")

    while True:
        if _is_file(trigger1) or _is_file(trigger2):
            _rm(trigger1)
            _rm(trigger2)
            _log(STG, name, "trigger seen")

            if os.access(repair_script, os.X_OK):
                try:
                    subprocess.run(
                        [repair_script],
                        capture_output=True,
                        timeout=120,
                    )
                    _log(STG, name, "repair complete")
                except Exception as e:
                    _log(STG, name, f"repair error: {e}")
            else:
                _log(STG, name, f"missing {repair_script}")

        time.sleep(POLL_SEC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stayturgid bridge daemon")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["repair"],
        help="Bridge mode: repair (stayturgid_repair.py)",
    )
    _ = parser.parse_args()

    pidfile = os.path.join(STG, "run", "bridges.pid")
    if _pidfile_alive(pidfile):
        return 0

    run_repair_mode()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
