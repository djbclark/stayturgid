"""Unit tests for the Mac-hub battery watch (control/lib/battery_watch.py)."""

import datetime

import battery_watch as bw

NOW = datetime.datetime(2026, 10, 5, 15, 0).timestamp()


def phone(**kw):
    st = {"ts": NOW, "pct": 60, "status": "DISCHARGING", "plugged": "UNPLUGGED", "eta_min": None, "last_charged": NOW}
    st.update(kw)
    return st


def test_parse_pmset_discharging():
    out = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t22%; discharging; 0:25 remaining present: true"
    st = bw.parse_pmset(out, NOW)
    assert st["pct"] == 22 and st["eta_min"] == 25 and not bw.on_charger(st)


def test_parse_pmset_charging_and_desktop():
    out = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t29%; charging; 2:17 remaining present: true"
    assert bw.on_charger(bw.parse_pmset(out, NOW))
    assert bw.parse_pmset("Now drawing from 'AC Power'", NOW) is None


def test_phone_low_by_eta_once_until_charged():
    mem = {}
    assert bw.evaluate("s24", phone(pct=40, eta_min=110), mem, NOW)
    assert bw.evaluate("s24", phone(pct=38, eta_min=100), mem, NOW) == []
    assert bw.evaluate("s24", phone(status="CHARGING", plugged="PLUGGED_AC"), mem, NOW) == []
    assert "s24" not in mem
    assert bw.evaluate("s24", phone(pct=40, eta_min=110), mem, NOW)


def test_phone_low_by_pct_without_eta():
    assert "15%" in bw.evaluate("p7a", phone(pct=15), {}, NOW)[0]
    assert bw.evaluate("p7a", phone(pct=16, eta_min=600), {}, NOW) == []


def test_eta_counts_down_from_status_time():
    # 150 min left as of 40 min ago -> 110 min now
    assert bw.evaluate("s24", phone(ts=NOW - 2400, eta_min=150), {}, NOW)


def test_stale_status_ignored():
    assert bw.evaluate("s24", phone(ts=NOW - 3 * 3600, pct=5), {}, NOW) == []


def test_mac_threshold_is_30_min():
    mac = {"ts": NOW, "pct": 30, "status": "discharging", "on_charger": False, "eta_min": 45}
    assert bw.evaluate("mac", mac, {}, NOW, computer=True) == []
    mac["eta_min"] = 25
    assert bw.evaluate("mac", mac, {}, NOW, computer=True)


def test_not_charged_in_24h():
    msgs = bw.evaluate("hd8", phone(last_charged=NOW - 30 * 3600), {}, NOW)
    assert any("30h" in m for m in msgs)


def test_rollcall_once_at_21():
    at21 = datetime.datetime(2026, 10, 5, 21, 10).timestamp()
    statuses = {
        "s24": phone(ts=at21, pct=40),
        "p7a": phone(ts=at21, pct=80),
        "t2e": phone(ts=at21, pct=20, status="CHARGING"),
        "hd8": None,
    }
    mem = {}
    call = bw.rollcall(statuses, mem, at21)
    assert "s24: 40%" in call and "hd8: unreachable" in call
    assert "p7a" not in call and "t2e" not in call
    assert bw.rollcall(statuses, mem, at21 + 600) is None
    assert bw.rollcall(statuses, {}, NOW) is None  # 15:00
