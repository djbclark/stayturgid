"""Unit tests for the Python battery-alarm twin (stayturgid_battery_alarm.py).

These test the pure decision logic directly (tiers, wallpaper-backup
validation, quiet detection) — the end-to-end behavior + shell/Python parity
is covered by tests/test-unit.sh (battery_suite run against both twins).
"""

import importlib

import pytest

alarm = importlib.import_module("stayturgid_battery_alarm")


@pytest.mark.parametrize(
    "tier,color,blinks",
    [
        (30, "purple", 1),
        (25, "blue", 2),
        (20, "green", 3),
        (15, "yellow", 4),
        (10, "orange", 5),
        (5, "red", 10),
        (0, "red", 10),
    ],
)
def test_tier_color_and_blinks(tier, color, blinks):
    assert alarm.TIER_COLOR.get(tier, "red") == color
    assert alarm.TIER_BLINKS.get(tier, 10 if tier <= 5 else 1) == blinks


def test_only_lowest_tier_selected():
    # At 12% the applicable tiers are 30/25/20/15; only 15 should fire.
    applicable = [t for t in alarm.TIERS if 12 <= t]
    assert applicable == [30, 25, 20, 15]
    assert applicable[-1] == 15


def test_wallpaper_backup_valid(tmp_path, monkeypatch):
    good = tmp_path / "wp.png"
    good.write_bytes(b"\x89PNG\r\n\x1a\nrest")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(good))
    assert alarm.wallpaper_backup_valid() is True
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(bad))
    assert alarm.wallpaper_backup_valid() is False
    monkeypatch.setattr(alarm, "WALLPAPER_BACKUP", str(tmp_path / "missing.png"))
    assert alarm.wallpaper_backup_valid() is False


def test_dnd_detection(monkeypatch):
    calls = {"zen": "0", "filter": "mInterruptionFilter=ALL", "ringer": "2"}

    def fake_adb_shell(*cmd):
        c = " ".join(cmd)
        if "zen_mode" in c:
            return calls["zen"]
        if "dumpsys notification" in c:
            return calls["filter"]
        if "get-ringer-mode" in c:
            return calls["ringer"]
        return ""

    monkeypatch.setattr(alarm, "adb_shell", fake_adb_shell)

    assert alarm.dnd_or_sleep_quiet() is False
    calls["zen"] = "1"
    assert alarm.dnd_or_sleep_quiet() is True
    calls["zen"] = "0"
    calls["filter"] = "mInterruptionFilter=PRIORITY"
    assert alarm.dnd_or_sleep_quiet() is True
    calls["filter"] = "mInterruptionFilter=ALL"
    calls["ringer"] = "0"
    assert alarm.dnd_or_sleep_quiet() is True


def test_malformed_battery_json_exits_zero(monkeypatch):
    monkeypatch.setattr(alarm, "out_of", lambda args: '{"status": "DISCHARGING"}')
    # no percentage => clean exit 0, no crash
    assert alarm.main() == 0


# --- locate sound / evening warnings / Mac-hub status (2026-10-05) ----------------------

D = alarm.datetime.datetime


@pytest.fixture
def state(tmp_path, monkeypatch):
    for name in ("STATUS_JSON", "SOUND_PID", "SOUND_STOP", "CONT_DISMISSED", "SKIP_NIGHT", "EVENING_DONE", "BATT_LOG"):
        monkeypatch.setattr(alarm, name, str(tmp_path / name.lower()))
    sounds, runs, delays = [], [], []
    monkeypatch.setattr(
        alarm, "start_sound", lambda secs, why, delay=0: sounds.append(secs) or delays.append(delay) or True
    )
    monkeypatch.setattr(alarm, "run", lambda args, **kw: runs.append(args))
    monkeypatch.setattr(alarm, "_test_delays", delays, raising=False)
    return tmp_path, sounds, runs


def _log_lines(path, rows):
    with open(path, "w") as f:
        for ts, pct, status in rows:
            f.write("%s [batt] pct=%d%% status=%s plugged=UNPLUGGED\n" % (ts, pct, status))


@pytest.mark.parametrize("hour,quiet", [(8, True), (9, False), (20, False), (21, True), (0, True)])
def test_quiet_hours(hour, quiet):
    assert alarm.quiet_hours(D(2026, 10, 5, hour, 30)) is quiet


def test_drain_rate_uses_current_discharge_only(state):
    _log_lines(
        alarm.BATT_LOG,
        [
            ("2026-10-05 10:00:00", 60, "DISCHARGING"),
            ("2026-10-05 10:30:00", 50, "CHARGING"),
            ("2026-10-05 11:00:00", 40, "DISCHARGING"),
            ("2026-10-05 12:00:00", 36, "DISCHARGING"),
        ],
    )
    assert alarm.drain_per_hour(D(2026, 10, 5, 12, 0)) == pytest.approx(4.0)


def test_drain_rate_none_without_enough_history(state):
    _log_lines(alarm.BATT_LOG, [("2026-10-05 11:50:00", 40, "DISCHARGING"), ("2026-10-05 12:00:00", 39, "DISCHARGING")])
    assert alarm.drain_per_hour(D(2026, 10, 5, 12, 0)) is None


def test_evening_warns_only_when_predicted_dead_before_10am(state):
    _, sounds, runs = state
    # 30% at 2%/h lasts 15 h: 18:50 + 15 h = 09:50 tomorrow -> warn with 15 s
    alarm.evening_check(30, 2.0, D(2026, 10, 5, 18, 50))
    assert sounds == [15]
    assert alarm._test_delays == [300]  # scheduled for 18:55 exactly
    assert any("No nightly warnings today" in a for a in runs[-1])
    # same slot again: already done
    alarm.evening_check(30, 2.0, D(2026, 10, 5, 18, 58))
    assert sounds == [15]
    # 19:55 slot, healthy battery (90% at 2%/h) -> no sound
    alarm.evening_check(90, 2.0, D(2026, 10, 5, 19, 55))
    assert sounds == [15]
    # 20:55 slot, dying -> 60 s
    alarm.evening_check(10, 2.0, D(2026, 10, 5, 20, 52))
    assert sounds == [15, 60]


def test_evening_unknown_rate_assumes_idle_drain(state):
    _, sounds, _ = state
    alarm.evening_check(12, None, D(2026, 10, 5, 19, 50))  # 12 h at 1%/h -> 07:50
    assert sounds == [30]


def test_skip_tonight_suppresses_evening(state):
    _, sounds, _ = state
    alarm._write(alarm.SKIP_NIGHT, "2026-10-05")
    alarm.evening_check(5, 2.0, D(2026, 10, 5, 18, 55))
    assert sounds == []
    alarm.evening_check(5, 2.0, D(2026, 10, 6, 18, 55))  # next day it's back
    assert sounds == [15]


def test_outside_slots_nothing(state):
    _, sounds, _ = state
    alarm.evening_check(5, 2.0, D(2026, 10, 5, 18, 30))  # 25 min early: too soon
    alarm.evening_check(5, 2.0, D(2026, 10, 5, 21, 1))
    assert sounds == []


def test_status_json_tracks_last_charged(state):
    alarm.write_status({"plugged": "PLUGGED_AC"}, 80, "CHARGING", None)
    first = alarm.json.loads(open(alarm.STATUS_JSON).read())
    assert first["last_charged"] and first["eta_min"] is None
    alarm.write_status({"plugged": "UNPLUGGED"}, 50, "DISCHARGING", 5.0)
    st = alarm.json.loads(open(alarm.STATUS_JSON).read())
    assert st["last_charged"] == first["last_charged"]
    assert st["eta_min"] == 600


def test_tier_sound_seconds():
    assert alarm.TIER_SOUND_SEC == {30: 10, 25: 20, 20: 30, 15: 40, 10: 50, 5: 60}
    assert alarm.CONTINUOUS_PCT == 2


def test_stop_sound_dismisses_loop(state, monkeypatch):
    monkeypatch.setattr(alarm, "_sound_pid_mode", lambda: (123, "loop"))
    alarm.stop_sound()
    assert alarm.os.path.exists(alarm.CONT_DISMISSED)
    assert alarm.os.path.exists(alarm.SOUND_STOP)


# --- agent player: built-in speaker only, vibrating (2026-10-08) ---------------------------


@pytest.mark.parametrize(
    "out,expected",
    [
        ("package:org.stayturgid.agent versionCode:33\n", True),
        ("package:org.stayturgid.agent.debug versionCode:40\npackage:org.stayturgid.agent versionCode:32", False),
        ("package:org.stayturgid.agent versionCode:34\nError: Shell does not have permission", True),
        ("", False),  # no local adb: fall back to termux-media-player
    ],
)
def test_agent_plays_sound_needs_versioncode_33(monkeypatch, out, expected):
    monkeypatch.setattr(alarm, "adb_shell", lambda *cmd: out)
    assert alarm.agent_plays_sound() is expected


def _sound_loop_runs(state, monkeypatch, agent):
    _, _, runs = state
    monkeypatch.setattr(alarm, "agent_plays_sound", lambda: agent)
    monkeypatch.setattr(alarm, "_force_audible", lambda music=True: runs.append(["force", music]) or (lambda: None))
    monkeypatch.setattr(alarm.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 5))
    monkeypatch.setattr(alarm.time, "time", lambda: next(clock))
    alarm.sound_loop(10)
    return runs


def test_sound_loop_leases_the_agent_and_stops_it(state, monkeypatch):
    runs = _sound_loop_runs(state, monkeypatch, agent=True)
    assert ["force", False] in runs  # the agent sets the alarm volume; media volume untouched
    leases = [r[r.index("secs") + 1] for r in runs if r[:2] == ["am", "broadcast"]]
    assert leases and set(leases[:-1]) == {str(alarm.AGENT_LEASE_SEC)} and leases[-1] == "0"
    assert not any(r[0] == "termux-media-player" and r[1] == "play" for r in runs)


def test_sound_loop_falls_back_to_termux_player_and_vibrates(state, monkeypatch):
    runs = _sound_loop_runs(state, monkeypatch, agent=False)
    assert ["force", True] in runs
    assert ["termux-media-player", "play", alarm.SOUND_FILE] in runs
    assert any(r[0] == "termux-vibrate" for r in runs)
    assert not any(r[:2] == ["am", "broadcast"] for r in runs)


def test_stop_sound_timed_does_not_dismiss_loop(state, monkeypatch):
    monkeypatch.setattr(alarm, "_sound_pid_mode", lambda: (123, "timed"))
    alarm.stop_sound()
    assert not alarm.os.path.exists(alarm.CONT_DISMISSED)


def test_agent_ships_the_same_clip():
    root = alarm.os.path.join(alarm.os.path.dirname(__file__), "..", "..")
    termux = alarm.os.path.join(root, "device/termux/assets/battery-colors/locate.mp3")
    agent = alarm.os.path.join(root, "device/native-agent/app/src/main/res/raw/locate.mp3")
    with open(termux, "rb") as a, open(agent, "rb") as b:
        assert a.read() == b.read(), "rerun control/tools/gen_locate_sound.py"
