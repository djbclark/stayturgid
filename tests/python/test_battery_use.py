"""Unit tests for the on-device battery-use sampler. No device and no dumpsys."""

import json
import os
import sys
from pathlib import Path

import stayturgid_battery_use as bu

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))

CHECKIN = """\
9,0,i,vers,36,117,P,P
9,0,i,uid,10123,com.termux
9,0,i,uid,10123,com.termux.api
9,0,i,uid,10200,org.stayturgid.agent
9,0,i,uid,10300,com.termux.boot
9,0,i,uid,10999,com.other
9,0,l,pws,4500,120.5,100,140
9,0,l,dc,8,5,3
9,0,l,pwi,screen,40
9,0,l,pwi,cell,10
9,10123,l,pwi,uid,15.5
9,10123,l,pwi,cpu,12
9,10123,l,wl,*alarm*,0,f,0,3600000,p,4,0,w,0
9,10123,l,wl,a,b,1,f,2,3,p,4,5,w,6
9,10123,l,nt,0,0,100,200,0,0,1,2,5000,3
9,10123,l,pr,python3,8000,2000,0,1
9,10123,l,jb,com.termux/.app.TermuxService,1500,2
9,10200,l,pwi,uid,1.25
9,10200,l,wl,stayturgid:locate,100,f,1,0,p,0,0,w,0
9,10300,l,pwi,cpu,1.5
9,10300,l,pwi,wifi,0.5
9,10999,l,pwi,uid,99
"""

HUMAN = """\
Estimated power use (mAh):
  Capacity: 2390, Computed drain: 93.8, actual drain: 80-100
  Screen: 52.5
  Uid u0a96: 6.26 (com.termux)
  Uid u0a1: 50 (com.other)
  Uid u0a2: 3.5

Some other section:
  Uid u0a96: 1 (com.termux)
"""


def _write_proc(proc_root, pid, utime, stime, start, cmd):
    base = proc_root / str(pid)
    base.mkdir(parents=True, exist_ok=True)
    # Field 14/15 are utime/stime and field 22 is starttime. See proc(5).
    tail = [
        "R",
        "1",
        "1",
        "1",
        "0",
        "-1",
        "0",
        "0",
        "0",
        "0",
        "0",
        str(utime),
        str(stime),
        "0",
        "0",
        "20",
        "0",
        "1",
        "0",
        str(start),
    ]
    (base / "stat").write_text("42 (python) " + " ".join(tail) + "\n")
    (base / "cmdline").write_bytes(cmd)


def _status(root, now, charge, pct=70):
    path = root / "state" / "batt_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ts": int(now),
                "pct": pct,
                "status": "DISCHARGING",
                "plugged": "UNPLUGGED",
                "current": -180000,
                "charge_counter": charge,
            }
        )
    )


def _runner(text, rc=0, truncated=False):
    calls = []

    def run(cmd, timeout):
        calls.append((cmd, timeout))
        return {"rc": rc, "text": text, "err": "", "truncated": truncated}

    return calls, run


def test_tracked_packages_match_the_fleet_profile():
    profiles = json.loads((REPO / "control/lib/fleet_app_profiles.json").read_text())
    unrestricted = {entry["package"] for entry in profiles if entry.get("battery_unrestricted")}
    expect = (unrestricted - set(bu.RETIRED_PACKAGES)) | set(bu.EXTRA_PACKAGES)
    assert set(bu.TRACKED_PACKAGES) == expect
    assert "org.autojs.autojs6" not in bu.TRACKED_PACKAGES


def test_dumpsys_command_never_resets():
    cmd = bu.dumpsys_command(15)
    assert "--reset" not in cmd
    assert cmd[0] == "timeout"
    assert "--charged" in cmd and "--checkin" in cmd
    assert "batterystats" in cmd


def test_checkin_attributes_tracked_packages_and_ignores_the_rest():
    parsed = bu.parse_checkin(CHECKIN)
    rows, bases = bu._tracked_rows(parsed, {})
    by_pkg = {}
    for row in rows:
        by_pkg.setdefault(row["pkg"], []).append(row)
    assert set(by_pkg) == {"com.termux", "com.termux.api", "com.termux.boot", "org.stayturgid.agent"}
    termux = by_pkg["com.termux"][0]
    assert termux["mah"] == 15.5
    assert termux["mah_parts"] == {"cpu": 12}
    assert termux["shared_uid"] is True
    assert termux["cpu_user_ms"] == 8000
    assert termux["cpu_system_ms"] == 2000
    assert termux["wakelock_partial_ms"] == 3600003
    names = {w["name"]: w for w in termux["wakelocks"]}
    assert names["*alarm*"]["partial_ms"] == 3600000
    assert names["*alarm*"]["partial_n"] == 4
    assert names["a,b"]["partial_ms"] == 3
    assert termux["net"]["wifi_rx"] == 100
    assert termux["net"]["wifi_tx"] == 200
    assert termux["net"]["mobile_active_ms"] == 5000
    assert termux["jobs"] == [{"name": "com.termux/.app.TermuxService", "time_ms": 1500, "count": 2}]
    assert termux["procs"][0]["name"] == "python3"
    assert by_pkg["com.termux.boot"][0]["mah"] == 2.0
    assert by_pkg["com.termux.boot"][0]["mah_is_sum"] is True
    assert by_pkg["org.stayturgid.agent"][0]["mah"] == 1.25
    assert by_pkg["org.stayturgid.agent"][0]["wakelock_full_ms"] == 100
    assert bu._tracked_mah(rows) == 18.75
    assert parsed["capacity_mah"] == 4500
    assert parsed["computed_drain_mah"] == 120.5
    assert parsed["discharge"] == [8, 5, 3]
    assert parsed["device_power_mah"]["screen"] == 40
    assert "10999" not in bases
    assert bases["10123"]["mah"] == 15.5


def test_human_fallback_keeps_named_packages_only():
    parsed = bu.parse_batterystats(HUMAN)
    assert parsed["kind"] == "human"
    assert parsed["capacity_mah"] == 2390
    assert parsed["computed_drain_mah"] == 93.8
    assert parsed["actual_drain"] == "80-100"
    assert parsed["device_power_mah"]["Screen"] == 52.5
    rows, _ = bu._tracked_rows(parsed, {})
    assert rows == [{"mah": 6.26, "pkg": "com.termux"}]
    assert bu._tracked_mah(rows) == 6.26


def test_backwards_counter_is_a_window_reset_not_a_negative_delta():
    delta, reset = bu._counter_delta(15.5, 1.0)
    assert delta is None and reset is True
    delta, reset = bu._counter_delta(15.5, 16.0)
    assert delta == 0.5 and reset is False
    delta, reset = bu._counter_delta(None, 16.0)
    assert delta is None and reset is False


def test_cfengine_daemons_stay_when_busier_processes_fill_the_sample(tmp_path):
    root = str(tmp_path / "stg")
    proc = tmp_path / "proc"
    for pid in range(1, bu.PROC_TOP_N + 1):
        _write_proc(proc, pid, 1000 + pid, 0, 1, b"busy\0")
    _write_proc(proc, 900, 1, 0, 1, b"/data/data/com.termux/files/usr/sbin/cf-agent\0")
    _write_proc(proc, 901, 0, 0, 1, b"cf-execd\0")
    sample = bu.record(
        root,
        1_000,
        runner=_runner("", rc=1)[1],
        proc_root=str(proc),
        boot_id_path=str(tmp_path / "noboot"),
        environ={},
    )
    names = [bu.proc_cmd_name(row["cmd"]) for row in sample["procs"]]
    assert names.count("cf-agent") == 1
    assert names.count("cf-execd") == 1
    assert len(sample["procs"]) == bu.PROC_TOP_N + 2


def test_proc_stat_fields_match_proc_5():
    stat = "42 (py thon) R 1 1 1 0 -1 0 0 0 0 0 100 50 0 0 20 0 1 0 999\n"
    assert bu.parse_proc_stat(stat) == (100, 50, 999)


def test_fork_backs_off_after_an_attempt(tmp_path):
    root = str(tmp_path)
    assert bu.fork_due(root, now=1_000_000, environ={}) is True
    bu.mark_attempt(root, now=1_000_000)
    assert bu.fork_due(root, now=1_000_000 + 60, environ={}) is False
    assert bu.fork_due(root, now=1_000_000 + bu.PROC_INTERVAL_SEC, environ={}) is True
    assert bu.proc_interval_sec({"STAYTURGID_BATTERY_USE_PROC_SEC": "1"}) == bu.PROC_INTERVAL_SEC


def test_record_dumps_on_the_uid_interval_and_diffs_the_next_one(tmp_path):
    root = tmp_path / "stg"
    proc = tmp_path / "procroot"
    boot = tmp_path / "boot_id"
    boot.write_text("boot-a\n")
    _write_proc(proc, 42, 100, 50, 999, b"python\0stayturgid_repair.py\0")
    now = 1_700_000_000
    _status(root, now, 3_000_000)
    calls, run = _runner(CHECKIN)
    first = bu.record(str(root), now, runner=run, proc_root=str(proc), boot_id_path=str(boot), environ={})
    assert len(calls) == 1
    assert "--reset" not in calls[0][0]
    assert first["kind"] == "uid"
    assert first["tracked_mah"] == 18.75
    assert first["gauge"]["charge_counter"] == 3_000_000
    assert first["gauge"]["current"] == -180000
    assert "d_charge_uah" not in first
    assert "d_cpu_ticks" not in first
    assert first["procs"][0]["cmd"] == "python stayturgid_repair.py"
    assert first["procs"][0]["cpu_ticks"] == 150

    _write_proc(proc, 42, 110, 55, 999, b"python\0stayturgid_repair.py\0")
    _status(root, now + 100, 2_990_000)
    later = CHECKIN.replace("9,10123,l,pwi,uid,15.5", "9,10123,l,pwi,uid,16.0")
    later = later.replace("3600000,p,4", "3601000,p,5")
    calls2, run2 = _runner(later)
    second = bu.record(
        str(root),
        now + 100,
        force=True,
        runner=run2,
        proc_root=str(proc),
        boot_id_path=str(boot),
        environ={},
    )
    assert len(calls2) == 1
    assert second["d_charge_uah"] == -10000
    assert second["d_cpu_ticks"] == 15
    termux = next(row for row in second["packages"] if row["pkg"] == "com.termux")
    assert termux["d_mah"] == 0.5
    assert termux["d_wakelock_partial_ms"] == 1000
    assert "window_reset" not in termux


def test_charge_window_restart_does_not_look_like_negative_use(tmp_path):
    root = str(tmp_path)
    calls, run = _runner(CHECKIN)
    bu.record(
        root, 2_000_000, runner=run, proc_root=str(tmp_path / "empty"), boot_id_path=str(tmp_path / "nope"), environ={}
    )
    restarted = CHECKIN.replace("9,10123,l,pwi,uid,15.5", "9,10123,l,pwi,uid,1.0")
    _, run2 = _runner(restarted)
    second = bu.record(
        root,
        2_000_100,
        force=True,
        runner=run2,
        proc_root=str(tmp_path / "empty"),
        boot_id_path=str(tmp_path / "nope"),
        environ={},
    )
    termux = next(row for row in second["packages"] if row["pkg"] == "com.termux")
    assert termux["window_reset"] is True
    assert "d_mah" not in termux
    assert termux["mah"] == 1.0


def test_failed_dump_retries_later_not_on_the_next_call(tmp_path):
    root = str(tmp_path)
    calls, run = _runner("", rc=1)
    now = 3_000_000
    sample = bu.record(
        root, now, runner=run, proc_root=str(tmp_path / "p"), boot_id_path=str(tmp_path / "b"), environ={}
    )
    assert sample["uid_error"]
    assert len(calls) == 1
    calls.clear()
    bu.record(root, now + 60, runner=run, proc_root=str(tmp_path / "p"), boot_id_path=str(tmp_path / "b"), environ={})
    assert calls == []
    bu.record(
        root,
        now + bu.UID_RETRY_SEC,
        runner=run,
        proc_root=str(tmp_path / "p"),
        boot_id_path=str(tmp_path / "b"),
        environ={},
    )
    assert len(calls) == 1


def test_truncated_dump_is_not_a_baseline_and_is_not_retried_immediately(tmp_path):
    root = str(tmp_path)
    _, run = _runner(CHECKIN, truncated=True)
    sample = bu.record(
        root, 4_000_000, runner=run, proc_root=str(tmp_path / "p"), boot_id_path=str(tmp_path / "b"), environ={}
    )
    assert sample["uid_partial"] is True
    state = json.loads((tmp_path / "state" / "battery-use.json").read_text())
    assert "uids" not in state
    calls, run2 = _runner(CHECKIN)
    bu.record(root, 4_000_060, runner=run2, proc_root=str(tmp_path / "p"), boot_id_path=str(tmp_path / "b"), environ={})
    assert calls == []


def test_no_local_adb_skips_the_dump(tmp_path):
    root = tmp_path
    (root / "env").write_text('export STAYTURGID_NO_LOCAL_ADB="1"\n')
    calls, run = _runner(CHECKIN)
    sample = bu.record(
        str(root),
        5_000_000,
        force=True,
        runner=run,
        proc_root=str(tmp_path / "p"),
        boot_id_path=str(tmp_path / "b"),
        environ={},
    )
    assert calls == []
    assert sample["uid_skipped"] == "no_local_adb"


def test_a_new_boot_does_not_diff_process_cpu(tmp_path):
    root = str(tmp_path / "stg")
    proc = tmp_path / "proc"
    boot = tmp_path / "boot"
    boot.write_text("one\n")
    _write_proc(proc, 7, 10, 0, 5, b"sshd\0")
    bu.record(root, 6_000_000, runner=_runner("", rc=1)[1], proc_root=str(proc), boot_id_path=str(boot), environ={})
    boot.write_text("two\n")
    _write_proc(proc, 7, 10, 0, 5, b"sshd\0")
    second = bu.record(
        root,
        6_001_000,
        runner=_runner("", rc=1)[1],
        proc_root=str(proc),
        boot_id_path=str(boot),
        environ={},
    )
    assert "d_cpu_ticks" not in second


def test_boot_loop_forks_the_sampler_instead_of_every_pass():
    text = (REPO / "device/termux/py/start_adb.py").read_text()
    assert "_run_battery_use()" in text
    assert "fork_due" in text
    assert "mark_attempt" in text


def test_device_tier_checks_the_deployed_sampler():
    import device_tier as dt

    assert "stayturgid_battery_use.py" in dt.TRACKED_SCRIPTS
    assert "stayturgid_battery_use.py" in dt.REMOTE_GATHER


def test_sampler_is_executable():
    mode = os.stat(REPO / "device/termux/py/stayturgid_battery_use.py").st_mode
    assert mode & 0o111


def test_usage_rejects_unknown_arguments(capsys):
    assert bu.main(["--reset"]) == 2
    assert "usage:" in capsys.readouterr().err
