#!/usr/bin/env python3
"""Fire OS peer keepalive — Shizuku + Handsets via fleet peers (boot loop).

Only runs when ``STAYTURGID_NO_LOCAL_ADB=1``. Rate-limited so the 5-min boot
loop does not hammer SSH/ADB. Invoked from ``device/termux/py/start_adb.py``.

Usage:
  stayturgid_peer_keepalive.py          # shizuku then handsets
  stayturgid_peer_keepalive.py shizuku
  stayturgid_peer_keepalive.py handsets
"""

from __future__ import annotations

import os
import sys
import time

HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
STG = os.path.join(HOME, ".stayturgid")
STATE = os.path.join(STG, "state")
# Min seconds between peer attempts per verb (boot loop is 300s; allow each cycle
# but skip if a recent success/attempt stamp is too fresh for failures).
MIN_INTERVAL_SEC = int(os.environ.get("STAYTURGID_PEER_KEEPALIVE_SEC", "240"))


def _no_local_adb() -> bool:
    if os.environ.get("STAYTURGID_NO_LOCAL_ADB") == "1":
        return True
    env = os.path.join(STG, "env")
    if os.path.isfile(env):
        try:
            with open(env) as f:
                for line in f:
                    if "STAYTURGID_NO_LOCAL_ADB=1" in line:
                        return True
        except OSError:
            pass
    return False


def _stamp_path(verb: str) -> str:
    return os.path.join(STATE, "peer_keepalive_%s" % verb)


def _recent(verb: str) -> bool:
    path = _stamp_path(verb)
    try:
        age = time.time() - os.path.getmtime(path)
        return age < MIN_INTERVAL_SEC
    except OSError:
        return False


def _touch(verb: str) -> None:
    os.makedirs(STATE, exist_ok=True)
    path = _stamp_path(verb)
    try:
        with open(path, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def _log(msg: str) -> None:
    os.makedirs(os.path.join(STG, "logs"), exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " [peer-keepalive] " + msg + "\n"
    try:
        with open(os.path.join(STG, "logs", "peer-keepalive.log"), "a") as f:
            f.write(line)
    except OSError:
        pass
    # Also append to shared watchdog log when present.
    sd = os.environ.get("STAYTURGID_SD", "/sdcard/stayturgid")
    try:
        with open(os.path.join(sd, "logs", "watchdog.log"), "a") as f:
            f.write(line)
    except OSError:
        pass


def ensure_shizuku() -> bool:
    if _recent("shizuku"):
        return True
    try:
        import stayturgid_peer_bootstrap as peer
    except ImportError as e:
        _log("shizuku skip: %s" % e)
        return False
    # Cheap local check via pgrep if we somehow have shell — usually skip on Fire.
    ok, detail = peer.bootstrap_shizuku()
    _touch("shizuku")
    _log(("OK" if ok else "FAIL") + " shizuku: " + detail)
    return ok


def ensure_handsets() -> bool:
    if _recent("handsets"):
        return True
    try:
        import stayturgid_handsets as hs
    except ImportError as e:
        _log("handsets skip: %s" % e)
        return False
    if not hs.enabled() or not hs.available():
        _log("handsets unavailable")
        return False
    port = hs._default_port()
    if hs.ping(port):
        _touch("handsets")
        _log("handsets already up port=%d" % port)
        return True
    try:
        hs.start(port)
        ok = hs.ping(port)
        _touch("handsets")
        _log(("OK" if ok else "FAIL") + " handsets start port=%d" % port)
        return ok
    except Exception as e:  # noqa: BLE001
        _touch("handsets")
        _log("FAIL handsets: %s" % e)
        return False


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not _no_local_adb():
        return 0
    if os.environ.get("STAYTURGID_PEER_BOOTSTRAP", "1") == "0":
        return 0
    verbs = argv or ["shizuku", "handsets"]
    rc = 0
    for v in verbs:
        if v == "shizuku":
            if not ensure_shizuku():
                rc = 1
        elif v == "handsets":
            if not ensure_handsets():
                rc = 1
        else:
            sys.stderr.write("usage: stayturgid_peer_keepalive.py [shizuku|handsets]...\n")
            return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
