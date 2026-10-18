#!/data/data/com.termux/files/usr/bin/python
"""Record this fleet's own battery use, so a later change can be compared.

The boot loop already logs whole-device percent (stayturgid_battery_alarm.py).
Percent mixes the screen, the radios, and every other app, so it cannot say
whether a change to our code helped. This sampler records the counters that
can: per-package CPU, wake locks, radio bytes, jobs, and estimated mAh, plus
the fuel-gauge charge counter as the device-wide ground truth.

What it deliberately does not do, from Android's own batterystats guidance
(developer.android.com/topic/performance/power/setup-battery-historian,
source.android.com/docs/core/power/batterystats, BatteryManager):

- It never passes ``--reset``. That flag is for a lab capture. On a phone
  someone is using, it wipes the since-charge window and the Settings
  battery history.
- It does not read ``BATTERY_PROPERTY_CURRENT_NOW`` itself, and it does not
  flip the sign. The AOSP contract is positive = current into the battery,
  negative = discharging, but some devices invert it (issuetracker 37131318)
  and Termux:API correctly refuses to "fix" that. ``charge_counter`` (remaining
  µAh) over a window is the ground truth; current is only a hint on the gauge.
- It does not dump batterystats on the 5-minute pass. A dump takes seconds
  and is itself a load. ``start_adb.py`` forks this process at
  ``PROC_INTERVAL_SEC``; a dump runs at ``UID_INTERVAL_SEC``.
- It does not take its own wake lock. The boot loop is already awake.

``--charged --checkin`` is the machine-readable since-last-charge report.
Its ``pwi`` lines are estimated mAh from the device power profile, which is
poorly calibrated on many non-Pixel phones, so the CPU, wake lock, and byte
counters are the numbers to trust when the mAh looks wrong. Counters are
cumulative inside one charge session and drop back when the device is
plugged in; a backwards step is recorded as ``window_reset`` rather than a
negative delta.

Tracked packages are the ones this fleet exempts from battery optimization
(control/lib/fleet_app_profiles.json), minus retired AutoJs6, plus the debug
agent application id. A test locks that set to the profile file.

One JSON object per line in ``~/.stayturgid/logs/battery-use.jsonl`` (the
boot loop rotates it). ``v`` is 1. Times in the checkin rows are milliseconds
and byte counts are bytes, as batterystats publishes them. ``d_*`` is the
increase since the previous sample of that counter; it is omitted when the
since-charge window restarted. ``d_charge_uah`` is the change in remaining
capacity (negative while the battery is being used). ``procs`` is the busiest
processes of this UID, plus any CFEngine daemon (`cf-agent`, `cf-execd`,
`cf-serverd`, `cf-monitord`, `cf-promises`, `cf-hub`) even when it is idle.
The native agent is a different UID, so it is a batterystats package row
(`org.stayturgid.agent`), not a ``procs`` row. ``d_cpu_ticks`` sums every
process that stayed alive.
"""

import json
import os
import re
import subprocess
import sys
import time

PROC_INTERVAL_SEC = 1800
UID_INTERVAL_SEC = 6 * 3600
UID_RETRY_SEC = 1800
DUMP_TIMEOUT_SEC = 15
MAX_DUMP_BYTES = 8 * 1024 * 1024
PROC_TOP_N = 30
CHILD_TOP_N = 8
# CFEngine shares the Termux UID. Keep its daemons in the sample when they
# are not already among the busiest processes.
CFENGINE_CMDS = frozenset({"cf-agent", "cf-execd", "cf-serverd", "cf-monitord", "cf-promises", "cf-hub"})
ENV_PROC_SEC = "STAYTURGID_BATTERY_USE_PROC_SEC"
ENV_UID_SEC = "STAYTURGID_BATTERY_USE_UID_SEC"
ENV_DUMP_TIMEOUT = "STAYTURGID_BATTERY_USE_DUMP_TIMEOUT_SEC"
SCHEMA_VERSION = 1

# Retired with the AutoJs6 cutover; still listed in the profile file.
RETIRED_PACKAGES = frozenset({"org.autojs.autojs6"})
# Installed only for debug builds, so it is not in the fleet profile.
EXTRA_PACKAGES = frozenset({"org.stayturgid.agent.debug"})
TRACKED_PACKAGES = frozenset(
    {
        "com.tailscale.ipn",
        "com.termux",
        "com.termux.api",
        "com.termux.boot",
        "com.termux.styling",
        "com.termux.widget",
        "com.termux.window",
        "dev.imranr.obtainium",
        "moe.shizuku.privileged.api",
        "net.dinglisch.android.taskerm",
        "org.stayturgid.agent",
        "org.stayturgid.agent.debug",
    }
)

_GAUGE_KEYS = (
    "charge_counter",
    "current",
    "current_average",
    "energy",
    "temperature",
    "voltage",
)
_UID_LINE = re.compile(r"^Uid (u\d+a\d+):\s*([0-9.]+)(?:\s+\(([^)]+)\))?\s*$")
_CAPACITY = re.compile(r"Capacity:\s*([0-9.]+)")
_COMPUTED = re.compile(r"Computed drain:\s*([0-9.]+)")
_ACTUAL = re.compile(r"actual drain:\s*([^,\n]+)")
_NAMED_POWER = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*([0-9.]+)\s*$")


def default_root():
    return os.path.join(os.environ.get("HOME", ""), ".stayturgid")


def _interval(environ, name, default, floor):
    try:
        value = int(environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if value < floor:
        return default
    return value


def proc_interval_sec(environ=None):
    return _interval(os.environ if environ is None else environ, ENV_PROC_SEC, PROC_INTERVAL_SEC, 60)


def uid_interval_sec(environ=None):
    return _interval(os.environ if environ is None else environ, ENV_UID_SEC, UID_INTERVAL_SEC, 300)


def dump_timeout_sec(environ=None):
    # Under the boot loop's 60s guard, with room for process scanning.
    value = _interval(os.environ if environ is None else environ, ENV_DUMP_TIMEOUT, DUMP_TIMEOUT_SEC, 5)
    if value > 40:
        return DUMP_TIMEOUT_SEC
    return value


def _state_path(root):
    return os.path.join(root, "state", "battery-use.json")


def _log_path(root):
    return os.path.join(root, "logs", "battery-use.jsonl")


def _status_path(root):
    return os.path.join(root, "state", "batt_status.json")


def load_state(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def append_log(path, sample):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        json.dump(sample, f, sort_keys=True, separators=(",", ":"))
        f.write("\n")


def _omit(row):
    return {k: v for k, v in row.items() if v is not None and v != [] and v != {}}


def fork_due(root=None, now=None, environ=None):
    """True when the already-running boot loop should fork this process.

    Uses the later of a completed sample and an attempt. ``start_adb.py``
    records the attempt before the fork, so a dump killed by the guard
    timeout does not retry on the next 5-minute pass.
    """
    root = default_root() if root is None else root
    now = time.time() if now is None else now
    state = load_state(_state_path(root))
    last = 0.0
    for key in ("proc_ts", "attempt_ts"):
        try:
            last = max(last, float(state.get(key) or 0))
        except (TypeError, ValueError):
            pass
    if last <= 0:
        return True
    return now - last >= proc_interval_sec(environ)


def mark_attempt(root=None, now=None):
    root = default_root() if root is None else root
    now = time.time() if now is None else now
    path = _state_path(root)
    state = load_state(path)
    state["attempt_ts"] = int(now)
    save_state(path, state)


def no_local_adb(root, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("STAYTURGID_NO_LOCAL_ADB") == "1":
        return True
    path = os.path.join(root, "env")
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return False
    for line in lines:
        line = line.strip()
        if line.startswith("export STAYTURGID_NO_LOCAL_ADB="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") == "1"
    return False


def dumpsys_command(timeout_sec):
    """Since-last-charge checkin. Never ``--reset``; see the module docstring."""
    return [
        "timeout",
        str(int(timeout_sec)),
        "adb",
        "-s",
        "localhost:5555",
        "shell",
        "dumpsys",
        "batterystats",
        "--charged",
        "--checkin",
    ]


def default_runner(cmd, timeout):
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        return {"rc": None, "text": "", "err": "timeout", "truncated": False}
    except OSError as exc:
        return {"rc": None, "text": "", "err": str(exc)[:200], "truncated": False}
    raw = completed.stdout or b""
    truncated = len(raw) > MAX_DUMP_BYTES
    err = (completed.stderr or b"")[:400].decode("utf-8", "replace").strip()
    return {
        "rc": completed.returncode,
        "text": raw[:MAX_DUMP_BYTES].decode("utf-8", "replace"),
        "err": err,
        "truncated": truncated,
    }


def _ints(fields):
    out = []
    for field in fields:
        try:
            out.append(int(field))
        except ValueError:
            return None
    return out


def _parse_wl(rest):
    # name, full ms, f, full n, partial ms, p, partial n, window ms, w, window n.
    # The name is everything before those nine tail fields, so a comma in it survives.
    if len(rest) < 10 or rest[-8] != "f" or rest[-5] != "p" or rest[-2] != "w":
        return None
    try:
        return {
            "name": ",".join(rest[:-9]),
            "full_ms": int(rest[-9]),
            "full_n": int(rest[-7]),
            "partial_ms": int(rest[-6]),
            "partial_n": int(rest[-4]),
            "window_ms": int(rest[-3]),
            "window_n": int(rest[-1]),
        }
    except ValueError:
        return None


def _parse_job(rest):
    if len(rest) < 3:
        return None
    try:
        return {"name": ",".join(rest[:-2]), "time_ms": int(rest[-2]), "count": int(rest[-1])}
    except ValueError:
        return None


def _blank_uid():
    return {
        "pkgs": [],
        "mah": None,
        "mah_parts": {},
        "wakelocks": [],
        "cpu_user_ms": 0,
        "cpu_system_ms": 0,
        "procs": [],
        "net": None,
        "jobs": [],
    }


def parse_checkin(text):
    """Parse ``dumpsys batterystats --checkin``. Unknown sections are ignored."""
    uid_map = {}
    uids = {}
    device_power = {}
    version = None
    capacity = None
    computed = None
    discharge = None

    def uid_row(uid):
        row = uids.get(uid)
        if row is None:
            row = _blank_uid()
            uids[uid] = row
        return row

    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            line_uid = int(parts[1])
        except ValueError:
            continue
        mode, section = parts[2], parts[3]
        rest = parts[4:]
        if section == "vers" and line_uid == 0:
            version = ",".join(rest[:6])
            continue
        if section == "uid" and len(rest) >= 2:
            try:
                mapped = int(rest[0])
            except ValueError:
                continue
            uid_map.setdefault(mapped, [])
            if rest[1] not in uid_map[mapped]:
                uid_map[mapped].append(rest[1])
            continue
        if mode != "l":
            continue
        if section == "pws" and line_uid == 0 and rest:
            try:
                capacity = float(rest[0])
                computed = float(rest[1]) if len(rest) > 1 else None
            except ValueError:
                pass
            continue
        if section == "dc" and line_uid == 0:
            discharge = _ints(rest)
            continue
        if section == "pwi" and len(rest) >= 2:
            try:
                mah = float(rest[1])
            except ValueError:
                continue
            if line_uid == 0:
                device_power[rest[0]] = mah
            else:
                uid_row(line_uid)["mah_parts"][rest[0]] = mah
            continue
        if section == "wl":
            parsed = _parse_wl(rest)
            if parsed:
                uid_row(line_uid)["wakelocks"].append(parsed)
            continue
        if section == "nt":
            nums = _ints(rest[:10])
            if nums and len(nums) >= 4:
                net = {
                    "mobile_rx": nums[0],
                    "mobile_tx": nums[1],
                    "wifi_rx": nums[2],
                    "wifi_tx": nums[3],
                }
                if len(nums) >= 9:
                    net["mobile_active_ms"] = nums[8]
                uid_row(line_uid)["net"] = net
            continue
        if section == "pr" and rest:
            nums = _ints(rest[1:])
            if not nums:
                continue
            row = uid_row(line_uid)
            row["cpu_user_ms"] += nums[0]
            if len(nums) > 1:
                row["cpu_system_ms"] += nums[1]
            row["procs"].append({"name": rest[0], "user_ms": nums[0], "system_ms": nums[1] if len(nums) > 1 else 0})
            continue
        if section == "jb":
            parsed = _parse_job(rest)
            if parsed:
                uid_row(line_uid)["jobs"].append(parsed)

    for uid, pkgs in uid_map.items():
        uid_row(uid)["pkgs"] = pkgs
    for row in uids.values():
        parts = row["mah_parts"]
        if "uid" in parts:
            row["mah"] = parts.pop("uid")
        elif parts:
            row["mah"] = sum(parts.values())
            row["mah_is_sum"] = True
        row["wakelocks"].sort(key=lambda w: w["partial_ms"] + w["full_ms"], reverse=True)
        row["procs"].sort(key=lambda p: p["user_ms"] + p["system_ms"], reverse=True)
        row["jobs"].sort(key=lambda j: j["time_ms"], reverse=True)
    return {
        "kind": "checkin",
        "checkin_version": version,
        "capacity_mah": capacity,
        "computed_drain_mah": computed,
        "discharge": discharge,
        "device_power_mah": device_power,
        "uids": uids,
        "parsed": version is not None or bool(uids) or bool(device_power),
    }


def parse_human(text):
    """Fallback when a device prints the prose report instead of checkin.

    Uid rows are kept only when they name a package. The prose sections do
    not reliably put the package on the ``Uid u0aN`` line; checkin does.
    """
    device_power = {}
    uids = {}
    capacity = None
    computed = None
    actual = None
    in_power = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Estimated power use"):
            in_power = True
            continue
        if not in_power:
            continue
        if not line:
            in_power = False
            continue
        cap = _CAPACITY.search(line)
        if cap:
            capacity = float(cap.group(1))
            comp = _COMPUTED.search(line)
            if comp:
                computed = float(comp.group(1))
            act = _ACTUAL.search(line)
            if act:
                actual = act.group(1).strip()
            continue
        uid_match = _UID_LINE.match(line)
        if uid_match:
            pkg = uid_match.group(3)
            if not pkg:
                continue
            uids[pkg] = float(uid_match.group(2))
            continue
        named = _NAMED_POWER.match(line)
        if named and named.group(1) not in ("Capacity", "Uid"):
            device_power[named.group(1)] = float(named.group(2))
    return {
        "kind": "human",
        "checkin_version": None,
        "capacity_mah": capacity,
        "computed_drain_mah": computed,
        "actual_drain": actual,
        "discharge": None,
        "device_power_mah": device_power,
        "pkg_mah": uids,
        "parsed": capacity is not None or bool(uids) or bool(device_power),
    }


def parse_batterystats(text):
    if ",pwi," in text or ",vers," in text:
        return parse_checkin(text)
    human = parse_human(text)
    if human["parsed"]:
        return human
    return parse_checkin(text)


def _counter_delta(old, new):
    if old is None or new is None:
        return None, False
    try:
        old_n = float(old)
        new_n = float(new)
    except (TypeError, ValueError):
        return None, False
    if new_n + 1e-6 < old_n:
        return None, True
    return new_n - old_n, False


def parse_proc_stat(text):
    """utime, stime, starttime from a ``/proc/<pid>/stat`` line. Ticks, not ms."""
    close = text.rfind(")")
    if close < 0:
        return None
    fields = text[close + 1 :].split()
    if len(fields) < 20:
        return None
    try:
        return int(fields[11]), int(fields[12]), int(fields[19])
    except ValueError:
        return None


def scan_procs(proc_root):
    found = []
    try:
        names = os.listdir(proc_root)
    except OSError:
        return found
    for name in names:
        if not name.isdigit():
            continue
        base = os.path.join(proc_root, name)
        try:
            with open(os.path.join(base, "stat")) as f:
                parsed = parse_proc_stat(f.read())
        except OSError:
            continue
        if parsed is None:
            continue
        utime, stime, starttime = parsed
        try:
            with open(os.path.join(base, "cmdline"), "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except OSError:
            cmd = ""
        if not cmd:
            cmd = text_comm(os.path.join(base, "stat"))
        found.append(
            {
                "pid": int(name),
                "start": starttime,
                "cpu_ticks": utime + stime,
                "cmd": cmd[:180],
            }
        )
    return found


def proc_cmd_name(cmd):
    first = (cmd or "").split(" ", 1)[0]
    return first.rsplit("/", 1)[-1]


def select_procs(procs):
    """Busiest processes, then any CFEngine daemon the top list missed."""
    ranked = sorted(procs, key=lambda p: p["cpu_ticks"], reverse=True)
    top = ranked[:PROC_TOP_N]
    seen = {p["pid"] for p in top}
    extra = [p for p in ranked if p["pid"] not in seen and proc_cmd_name(p["cmd"]) in CFENGINE_CMDS]
    return top + extra


def text_comm(stat_path):
    try:
        with open(stat_path) as f:
            text = f.read()
    except OSError:
        return ""
    open_at = text.find("(")
    close = text.rfind(")")
    if open_at < 0 or close < open_at:
        return ""
    return text[open_at + 1 : close][:180]


def proc_delta(previous, procs):
    """Sum of tick increases for pid+starttime pairs that are still running."""
    total = 0
    used = False
    prev = previous if isinstance(previous, dict) else {}
    for proc in procs:
        key = "%s:%s" % (proc["pid"], proc["start"])
        old = prev.get(key)
        if old is None:
            continue
        try:
            old_n = int(old)
        except (TypeError, ValueError):
            continue
        if proc["cpu_ticks"] >= old_n:
            total += proc["cpu_ticks"] - old_n
            used = True
    return total if used else None


def _read_gauge(root, now):
    try:
        with open(_status_path(root)) as f:
            status = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(status, dict):
        return {}
    gauge = {}
    for key in ("pct", "status", "plugged"):
        if key in status:
            gauge[key] = status[key]
    for key in _GAUGE_KEYS:
        if status.get(key) is not None:
            gauge[key] = status[key]
    try:
        ts = int(status.get("ts"))
    except (TypeError, ValueError):
        ts = None
    if ts is not None:
        gauge["status_ts"] = ts
        if now - ts > 1200:
            gauge["stale"] = True
    return gauge


def _boot_id(path):
    try:
        with open(path) as f:
            return f.read().strip()[:80]
    except OSError:
        return ""


def _tracked_rows(parsed, previous_uids):
    rows = []
    seen = set()
    if parsed.get("kind") == "human":
        for pkg, mah in sorted(parsed.get("pkg_mah", {}).items()):
            if pkg not in TRACKED_PACKAGES:
                continue
            rows.append(_omit({"pkg": pkg, "mah": mah}))
        return rows, {}
    baselines = {}
    for uid, src in parsed.get("uids", {}).items():
        pkgs = [pkg for pkg in src.get("pkgs", []) if pkg in TRACKED_PACKAGES]
        if not pkgs:
            continue
        shared = len(pkgs) > 1
        partial_ms = sum(w["partial_ms"] for w in src["wakelocks"])
        full_ms = sum(w["full_ms"] for w in src["wakelocks"])
        net = src.get("net") or {}
        base = {
            "mah": src.get("mah"),
            "cpu_user_ms": src.get("cpu_user_ms") or 0,
            "cpu_system_ms": src.get("cpu_system_ms") or 0,
            "wakelock_partial_ms": partial_ms,
            "wifi_rx": net.get("wifi_rx"),
            "wifi_tx": net.get("wifi_tx"),
            "mobile_rx": net.get("mobile_rx"),
            "mobile_tx": net.get("mobile_tx"),
        }
        if uid not in seen:
            seen.add(uid)
            baselines[str(uid)] = base
        prev = {}
        if isinstance(previous_uids, dict):
            prev = previous_uids.get(str(uid)) or {}
        reset = False
        deltas = {}
        for key, value in base.items():
            delta, went_back = _counter_delta(prev.get(key), value)
            if went_back:
                reset = True
            elif delta is not None and key in prev:
                deltas["d_" + key] = delta
        if reset:
            deltas = {"window_reset": True}
        omitted_wl = max(0, len(src["wakelocks"]) - CHILD_TOP_N)
        wakelocks = [
            _omit(
                {
                    "name": w["name"],
                    "partial_ms": w["partial_ms"],
                    "partial_n": w["partial_n"],
                    "full_ms": w["full_ms"],
                    "full_n": w["full_n"],
                }
            )
            for w in src["wakelocks"][:CHILD_TOP_N]
            if w["partial_ms"] or w["full_ms"]
        ]
        for pkg in pkgs:
            row = {
                "pkg": pkg,
                "uid": uid,
                "mah": src.get("mah"),
                "mah_is_sum": True if src.get("mah_is_sum") else None,
                "mah_parts": src.get("mah_parts") or None,
                "cpu_user_ms": src.get("cpu_user_ms") or 0,
                "cpu_system_ms": src.get("cpu_system_ms") or 0,
                "wakelock_partial_ms": partial_ms,
                "wakelock_full_ms": full_ms,
                "wakelocks": wakelocks,
                "wakelocks_omitted": omitted_wl or None,
                "net": net or None,
                "jobs": src["jobs"][:CHILD_TOP_N],
                "procs": src["procs"][:CHILD_TOP_N],
                "shared_uid": True if shared else None,
            }
            row.update(deltas)
            rows.append(_omit(row))
    rows.sort(key=lambda r: (r.get("pkg", ""), r.get("uid", 0)))
    return rows, baselines


def _tracked_mah(rows):
    seen = set()
    total = 0.0
    any_mah = False
    for row in rows:
        uid = row.get("uid")
        mah = row.get("mah")
        if mah is None or uid in seen:
            continue
        if uid is None:
            # Human fallback has no uid; each package row is its own total.
            seen.add(row.get("pkg"))
        else:
            seen.add(uid)
        total += float(mah)
        any_mah = True
    return total if any_mah else None


def _uid_due(state, now, force, interval):
    if force:
        return True
    try:
        last = float(state.get("uid_ts") or 0)
    except (TypeError, ValueError):
        last = 0.0
    return last <= 0 or now - last >= interval


def record(
    root, now, force=False, runner=None, proc_root="/proc", boot_id_path="/proc/sys/kernel/random/boot_id", environ=None
):
    """Take one sample. Returns the object written, or None when nothing was due.

    The boot loop only calls this when ``fork_due`` is true, so a normal call
    always writes a process sample. ``force`` also takes the batterystats dump.
    """
    environ = os.environ if environ is None else environ
    now_i = int(now)
    state = load_state(_state_path(root))
    boot = _boot_id(boot_id_path)
    procs = scan_procs(proc_root)
    # pid+starttime is only meaningful inside one boot. A missing boot id
    # (or a new one) drops the previous process table instead of inventing a delta.
    if not boot or (state.get("boot_id") and boot != state.get("boot_id")):
        previous_procs = {}
    else:
        previous_procs = state.get("procs")
    delta_ticks = proc_delta(previous_procs, procs)
    top = select_procs(procs)
    gauge = _read_gauge(root, now_i)
    sample = {
        "v": SCHEMA_VERSION,
        "kind": "proc",
        "ts": now_i,
        "boot_id": boot or None,
        "gauge": gauge or None,
        "n_procs": len(procs),
        "d_cpu_ticks": delta_ticks,
        "procs": [{"pid": p["pid"], "cpu_ticks": p["cpu_ticks"], "cmd": p["cmd"]} for p in top],
    }
    prev_charge = state.get("charge_counter")
    charge = gauge.get("charge_counter") if gauge else None
    if prev_charge is not None and charge is not None:
        try:
            sample["d_charge_uah"] = int(charge) - int(prev_charge)
        except (TypeError, ValueError):
            pass

    want_uid = _uid_due(state, now_i, force, uid_interval_sec(environ))
    baselines = state.get("uids") if isinstance(state.get("uids"), dict) else {}
    if want_uid and no_local_adb(root, environ):
        sample["uid_skipped"] = "no_local_adb"
        # Remember the skip so a Fire OS device (no loopback adb) does not
        # keep looking due on every fork. A manual ``now`` still reports it.
        if not force:
            state["uid_ts"] = now_i
    elif want_uid:
        timeout = dump_timeout_sec(environ)
        cmd = dumpsys_command(timeout)
        ran = (runner or default_runner)(cmd, timeout + 5)
        text = ran.get("text") or ""
        if ran.get("rc") != 0 or not text.strip():
            err = ran.get("err") or ("rc %s" % ran.get("rc"))
            sample["uid_error"] = str(err)[:200]
            state["uid_ts"] = now_i + UID_RETRY_SEC - uid_interval_sec(environ)
        else:
            parsed = parse_batterystats(text)
            if not parsed.get("parsed"):
                sample["uid_error"] = "unparsed"
                state["uid_ts"] = now_i + UID_RETRY_SEC - uid_interval_sec(environ)
            else:
                rows, new_bases = _tracked_rows(parsed, baselines)
                sample["kind"] = "uid"
                sample["uid_source"] = parsed.get("kind")
                sample["since"] = "charged"
                sample["checkin_version"] = parsed.get("checkin_version")
                sample["capacity_mah"] = parsed.get("capacity_mah")
                sample["computed_drain_mah"] = parsed.get("computed_drain_mah")
                sample["actual_drain"] = parsed.get("actual_drain")
                sample["discharge"] = parsed.get("discharge")
                sample["device_power_mah"] = parsed.get("device_power_mah") or None
                sample["packages"] = rows
                sample["tracked_mah"] = _tracked_mah(rows)
                # A truncated dump omits later UIDs, so it must not become the
                # baseline, but it also must not be retried every proc interval.
                state["uid_ts"] = now_i
                if ran.get("truncated"):
                    sample["uid_partial"] = True
                elif new_bases:
                    state["uids"] = new_bases
                elif parsed.get("kind") == "checkin":
                    state["uids"] = {}

    sample = _omit(sample)
    append_log(_log_path(root), sample)
    state["proc_ts"] = now_i
    state["attempt_ts"] = now_i
    state["boot_id"] = boot
    state["procs"] = {"%s:%s" % (p["pid"], p["start"]): p["cpu_ticks"] for p in procs}
    if charge is not None:
        try:
            state["charge_counter"] = int(charge)
        except (TypeError, ValueError):
            pass
    save_state(_state_path(root), state)
    return sample


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["record"], ["now"]):
        sys.stderr.write("usage: stayturgid_battery_use.py [now]\n")
        return 2
    root = default_root()
    try:
        record(root, time.time(), force=(argv == ["now"]))
    except Exception as exc:
        try:
            append_log(
                _log_path(root),
                _omit(
                    {
                        "v": SCHEMA_VERSION,
                        "kind": "error",
                        "ts": int(time.time()),
                        "error": ("%s: %s" % (type(exc).__name__, exc))[:200],
                    }
                ),
            )
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
