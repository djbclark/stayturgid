#!/data/data/com.termux/files/usr/bin/python3
"""Fast repair + AutoJs6 restart bridge daemon (consolidated).

Replaces repair-bridge.sh + autojs6-bridge.sh. Polls trigger files every 2s;
when a trigger is found, deletes it and runs the corresponding action.

Modes:
  --mode repair   Poll repair_now -> run stayturgid_repair.py (no cooldown)
  --mode autojs6  Poll start_autojs6_now -> am start boot-launcher.js
                  (30-min cooldown to prevent spam restarts)

Deploy to ~/.stayturgid/bin/bridges.py. Started at boot by:
  ~/.termux/boot/start-repair-bridge.sh or start-autojs6-bridge.sh.
  Shell scripts are now minimal one-liners (pidfile guard lives here).
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

AUTOJS_PKG = "org.autojs.autojs6"
AUTOJS_RUN = "org.autojs.autojs.external.open.RunIntentActivity"
COOLDOWN_SEC = 1800
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


def run_autojs6_mode() -> None:
    name = "autojs6"
    _write_pidfile(STG, "autojs6-bridge.pid")

    trigger1 = os.path.join(SD, "run", "start_autojs6_now")
    trigger2 = os.path.join("/sdcard/stayturgid/run", "start_autojs6_now")
    cooldown_stamp = os.path.join(STG, "state", "last_autojs6_bridge_start")
    _ensure_dir(os.path.dirname(cooldown_stamp))

    boot_script = os.path.join("/sdcard/stayturgid/autojs6/scripts/boot-launcher.js")
    if not os.path.isfile(boot_script):
        boot_script = os.path.join(SD, "autojs6", "scripts", "boot-launcher.js")

    def cooldown_ok() -> bool:
        if not os.path.isfile(cooldown_stamp):
            return True
        try:
            with open(cooldown_stamp) as f:
                last = int(f.read().strip() or 0)
        except (OSError, ValueError):
            return True
        return int(time.time()) - last >= COOLDOWN_SEC

    def start_launcher() -> bool:
        if not os.path.isfile(boot_script):
            _log(STG, name, f"missing {boot_script}")
            return False
        try:
            subprocess.run(
                [
                    "am", "start", "-a", "android.intent.action.VIEW",
                    "-d", f"file://{boot_script}",
                    "-t", "text/javascript",
                    "-n", f"{AUTOJS_PKG}/{AUTOJS_RUN}",
                ],
                capture_output=True,
                timeout=30,
            )
            with open(cooldown_stamp, "w") as f:
                f.write(str(int(time.time())))
            _log(STG, name, "am start boot-launcher.js")
            return True
        except Exception as e:
            _log(STG, name, f"am start error: {e}")
            return False

    while True:
        if _is_file(trigger1) or _is_file(trigger2):
            _rm(trigger1)
            _rm(trigger2)
            _log(STG, name, "trigger seen")

            if cooldown_ok():
                start_launcher()
            else:
                _log(STG, name, "skipped (cooldown)")

        time.sleep(POLL_SEC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stayturgid bridge daemon")
    parser.add_argument(
        "--mode", required=True, choices=["repair", "autojs6"],
        help="Bridge mode: repair (stayturgid_repair.py) or autojs6 (boot-launcher.js)",
    )
    args = parser.parse_args()

    pidfile = os.path.join(STG, "run", "bridges.pid" if args.mode == "repair" else "autojs6-bridge.pid")
    if _pidfile_alive(pidfile):
        return 0

    if args.mode == "repair":
        run_repair_mode()
    else:
        run_autojs6_mode()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
