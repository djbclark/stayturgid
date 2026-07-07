"""Unit tests for the Python device tier's pure logic.

These cover the parsing/evaluation that was fragile in the old shell version
(heredoc paren miscounts, md5/md5sum split, sed key extraction). No device or
SSH — the I/O layer is separate.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tests"))
import device_tier as dt  # noqa: E402

HEALTHY = """\
ssh=ok
sshd=ok
bootloop=ok
bridge=ok
shell5555=ok
repairlog=fresh
battery=88
taskerlegacy=notif:0,files:0
mirror=pinned
penalties=off
writesettings=allow
md5 stayturgid-repair.sh aaa
md5 repair-bridge.sh bbb
"""


def kinds(results):
    return {r["desc"]: r["kind"] for r in results}


def test_parse_report_kv_and_md5():
    rep = dt.parse_report(HEALTHY)
    assert rep["ssh"] == "ok"
    assert rep["battery"] == "88"
    assert rep["taskerlegacy"] == "notif:0,files:0"
    assert rep["md5"] == {"stayturgid-repair.sh": "aaa", "repair-bridge.sh": "bbb"}


def test_parse_report_ignores_malformed_md5_lines():
    rep = dt.parse_report("md5 onlyname\nmd5 a b c d\nfoo=bar\n")
    assert rep["md5"] == {}
    assert rep["foo"] == "bar"


def test_parse_report_value_with_equals():
    rep = dt.parse_report("k=a=b=c\n")
    assert rep["k"] == "a=b=c"


def test_evaluate_all_green(monkeypatch):
    # pretend deployed md5s match the repo
    monkeypatch.setattr(dt, "TRACKED_SCRIPTS", {"stayturgid-repair.sh": "termux/stayturgid-repair.sh"})
    monkeypatch.setattr(dt, "file_md5", lambda p: "aaa")
    res = evaluate = dt.evaluate("s24", dt.parse_report(HEALTHY))
    k = kinds(res)
    assert k["s24: sshd running"] == "ok"
    assert k["s24: Termux mirror pinned (deterministic pkg update)"] == "ok"
    assert k["s24: sshd per-source penalties disabled"] == "ok"
    assert k["s24: Termux:API WRITE_SETTINGS granted (battery flash)"] == "ok"
    assert k["s24: deployed termux scripts match repo"] == "ok"
    assert all(v != "fail" for v in k.values())


def test_evaluate_flags_failures():
    rep = dt.parse_report(HEALTHY.replace("penalties=off", "penalties=ON")
                          .replace("writesettings=allow", "writesettings=MISSING")
                          .replace("mirror=pinned", "mirror=UNPINNED"))
    k = kinds(dt.evaluate("p7a", rep))
    assert k["p7a: sshd per-source penalties disabled"] == "fail"
    assert k["p7a: Termux:API WRITE_SETTINGS granted (battery flash)"] == "fail"
    assert k["p7a: Termux mirror pinned (deterministic pkg update)"] == "fail"


def test_evaluate_tasker_remnant_fails():
    rep = dt.parse_report(HEALTHY.replace("taskerlegacy=notif:0,files:0",
                                          "taskerlegacy=notif:0,files:1"))
    k = kinds(dt.evaluate("p7a", rep))
    assert k["p7a: no legacy Tasker stayturgid remnants"] == "fail"


def test_evaluate_bridge_and_drift_are_todo_not_fail(monkeypatch):
    monkeypatch.setattr(dt, "TRACKED_SCRIPTS", {"stayturgid-repair.sh": "termux/stayturgid-repair.sh"})
    monkeypatch.setattr(dt, "file_md5", lambda p: "DIFFERENT")
    rep = dt.parse_report(HEALTHY.replace("bridge=ok", "bridge=down"))
    k = kinds(dt.evaluate("p7a", rep))
    assert k["p7a: repair bridge alive (pidfile)"] == "todo"
    assert k["p7a: deployed termux scripts match repo"] == "todo"


def test_evaluate_battery_unknown_fails():
    rep = dt.parse_report(HEALTHY.replace("battery=88", "battery=unknown"))
    k = kinds(dt.evaluate("p7a", rep))
    assert k["p7a: termux-api battery readable"] == "fail"


def test_file_md5_matches_hashlib(tmp_path):
    import hashlib
    f = tmp_path / "x"
    f.write_bytes(b"hello")
    assert dt.file_md5(str(f)) == hashlib.md5(b"hello").hexdigest()
    assert dt.file_md5(str(tmp_path / "missing")) is None


def test_load_hosts_skips_comments(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("# header\ns24 RFCX 100.1 192.1\np7a 3526 100.2 192.2\n\n")
    assert dt.load_hosts(str(conf)) == ["s24", "p7a"]


def test_device_row(tmp_path):
    conf = tmp_path / "devices.conf"
    conf.write_text("s24 RFCX 100.1 192.1\n")
    assert dt.device_row("s24", str(conf)) == ("RFCX", "100.1", "192.1")
    assert dt.device_row("nope", str(conf)) is None


def test_parse_heal():
    assert dt.parse_heal("STATUS port=open shizuku=up sshd=up")["kind"] == "ok"
    assert dt.parse_heal("STATUS port=CLOSED_NO_SHELL")["kind"] == "fail"
    assert dt.parse_heal("")["kind"] == "fail"


def test_tap_counts_and_todo_not_failure(capsys):
    tap = dt.Tap()
    tap.emit({"kind": "ok", "desc": "a"})
    tap.emit({"kind": "todo", "desc": "b", "detail": "later"})
    tap.emit({"kind": "fail", "desc": "c", "detail": "boom"})
    passed = tap.done()
    out = capsys.readouterr().out
    assert "ok 1 - a" in out
    assert "not ok 2 - b # TODO later" in out
    assert "not ok 3 - c" in out
    assert "1..3" in out
    assert passed is False  # one real fail
    tap2 = dt.Tap()
    tap2.emit({"kind": "todo", "desc": "x"})
    assert tap2.done() is True  # TODO alone doesn't fail the run
