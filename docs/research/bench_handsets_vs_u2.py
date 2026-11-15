# historical: production hostnames/IPs in this file are session records;
# see docs/architecture/multi-site-topology.md §4.1 for current example names
#!/usr/bin/env python3
"""Real-use-case bench: Handsets vs uiautomator2 vs raw dump (s24 / hd8).

Scenarios mirror fleet post-UI work:
  1. Warm hierarchy read (n=8)
  2. Settings: find + tap a label (n=5)

Drivers share UiAutomation — kill the other before each block.
Usage: PYTHONUNBUFFERED=1 python3 docs/research/bench_handsets_vs_u2.py
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "control" / "lib")]
import stayturgid_device as dev
import ui_driver as uid

U2_SITE = Path.home() / ".local/pipx/venvs/uiautomator2/lib/python3.14/site-packages"
sys.path.insert(0, str(U2_SITE))

HOSTS = ("s24", "hd8")
SETTINGS_LABEL = {
    "s24": "Display",
    "hd8": "Display",
}


def run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def kill_ui_daemons(serial: str) -> None:
    run(
        [
            "adb",
            "-s",
            serial,
            "shell",
            "pkill -f 'dev.handsets.daemon' 2>/dev/null; "
            "pkill -f hsd900 2>/dev/null; "
            "pkill -f hsd901 2>/dev/null; "
            "pkill -f 'com.wetest.uia2' 2>/dev/null; "
            "pkill -f atxagent 2>/dev/null; "
            "pkill -f 'uiautomator' 2>/dev/null; "
            "am force-stop com.github.uiautomator 2>/dev/null; "
            "am force-stop com.github.uiautomator.test 2>/dev/null; "
            "true",
        ],
        timeout=20,
    )
    time.sleep(0.8)


def stay_awake(serial: str) -> None:
    run(["adb", "-s", serial, "shell", "svc", "power", "stayon", "true"])
    run(
        [
            "adb",
            "-s",
            serial,
            "shell",
            "settings",
            "put",
            "global",
            "stay_on_while_plugged_in",
            "7",
        ]
    )


def open_settings(serial: str) -> None:
    run(["adb", "-s", serial, "shell", "am", "start", "-a", "android.settings.SETTINGS"])
    time.sleep(1.5)


def ms(samples: list[float]) -> str:
    if not samples:
        return "n/a"
    return "p50=%.0f avg=%.0f max=%.0f" % (
        statistics.median(samples),
        statistics.mean(samples),
        max(samples),
    )


def bench_raw_hierarchy(serial: str, n: int = 8) -> list[float]:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        run(
            ["adb", "-s", serial, "shell", "uiautomator", "dump", "/sdcard/bench.xml"],
            timeout=30,
        )
        run(["adb", "-s", serial, "shell", "cat", "/sdcard/bench.xml"], timeout=15)
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_handsets_hierarchy(hs: uid.HandsetsSession, n: int = 8) -> list[float]:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        hs.ui()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_u2_hierarchy(d, n: int = 8) -> list[float]:
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        d.dump_hierarchy()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def bench_handsets_settings_tap(hs: uid.HandsetsSession, label: str, n: int = 5):
    times, ok = [], 0
    for _ in range(n):
        open_settings(hs.serial)
        t0 = time.perf_counter()
        found = hs.find_text(label, timeout_ms=4000)
        tapped = hs.tap_text(label, timeout_ms=4000) if found else False
        times.append((time.perf_counter() - t0) * 1000)
        if found and tapped:
            ok += 1
        run(["adb", "-s", hs.serial, "shell", "input", "keyevent", "KEYCODE_BACK"])
        time.sleep(0.4)
    return times, ok, n


def bench_u2_settings_tap(d, serial: str, label: str, n: int = 5):
    times, ok = [], 0
    for _ in range(n):
        open_settings(serial)
        t0 = time.perf_counter()
        el = d(text=label)
        found = el.exists(timeout=4.0)
        tapped = False
        if found:
            el.click()
            tapped = True
        times.append((time.perf_counter() - t0) * 1000)
        if found and tapped:
            ok += 1
        d.press("back")
        time.sleep(0.4)
    return times, ok, n


def bench_raw_settings_tap(serial: str, label: str, n: int = 5):
    times, ok = [], 0
    for _ in range(n):
        open_settings(serial)
        t0 = time.perf_counter()
        run(
            ["adb", "-s", serial, "shell", "uiautomator", "dump", "/sdcard/bench.xml"],
            timeout=30,
        )
        r = run(["adb", "-s", serial, "shell", "cat", "/sdcard/bench.xml"], timeout=15)
        xml = r.stdout or ""
        found = label in xml
        tapped = False
        if found:
            # crude: tap via content if parse fails — use ui_parse if available
            try:
                import ui_parse as up  # type: ignore

                pt = up.parse_text_center(xml, label) if hasattr(up, "parse_text_center") else None
            except Exception:
                pt = None
            if pt is None:
                # fallback regex
                import re

                m = re.search(
                    r'text="%s"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' % re.escape(label),
                    xml,
                )
                if not m:
                    m = re.search(
                        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="%s"' % re.escape(label),
                        xml,
                    )
                if m:
                    pt = (
                        (int(m.group(1)) + int(m.group(3))) // 2,
                        (int(m.group(2)) + int(m.group(4))) // 2,
                    )
            if pt:
                run(
                    [
                        "adb",
                        "-s",
                        serial,
                        "shell",
                        "input",
                        "tap",
                        str(pt[0]),
                        str(pt[1]),
                    ]
                )
                tapped = True
        times.append((time.perf_counter() - t0) * 1000)
        if found and tapped:
            ok += 1
        run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_BACK"])
        time.sleep(0.4)
    return times, ok, n


def connect_u2(serial: str):
    import uiautomator2 as u2

    # Use non-default port to avoid Handsets 9012 on hd8 after restart
    d = u2.connect(serial)
    d.implicitly_wait(2.0)
    # force a hierarchy read to confirm
    d.dump_hierarchy()
    return d


def run_host(alias: str) -> dict:
    serial = dev.resolve_adb(alias)
    stay_awake(serial)
    label = SETTINGS_LABEL[alias]
    out: dict = {"alias": alias, "serial": serial}
    print("\n======== %s (%s) ========" % (alias, serial))

    # --- RAW ---
    kill_ui_daemons(serial)
    open_settings(serial)
    print("RAW hierarchy…")
    out["raw_hier"] = bench_raw_hierarchy(serial)
    print("  hierarchy ms:", ms(out["raw_hier"]))
    print("RAW settings tap…")
    t, ok, n = bench_raw_settings_tap(serial, label)
    out["raw_tap"] = (t, ok, n)
    print("  find+tap %s: %s ok=%d/%d" % (label, ms(t), ok, n))

    # --- HANDSETS ---
    kill_ui_daemons(serial)
    print("HANDSETS start…")
    t_start = time.perf_counter()
    hs = uid.HandsetsSession(serial, alias=alias)
    hs.start()
    out["hs_start_ms"] = (time.perf_counter() - t_start) * 1000
    print("  start: %.0f ms" % out["hs_start_ms"])
    open_settings(serial)
    print("HANDSETS hierarchy…")
    out["hs_hier"] = bench_handsets_hierarchy(hs)
    print("  hierarchy ms:", ms(out["hs_hier"]))
    print("HANDSETS settings tap…")
    t, ok, n = bench_handsets_settings_tap(hs, label)
    out["hs_tap"] = (t, ok, n)
    print("  find+tap %s: %s ok=%d/%d" % (label, ms(t), ok, n))
    hs.stop()
    kill_ui_daemons(serial)

    # --- U2 ---
    print("U2 connect…")
    t_start = time.perf_counter()
    u2_err = None
    d = None
    try:
        d = connect_u2(serial)
        out["u2_start_ms"] = (time.perf_counter() - t_start) * 1000
        print("  start: %.0f ms" % out["u2_start_ms"])
    except Exception as e:
        u2_err = str(e)
        out["u2_start_ms"] = None
        out["u2_error"] = u2_err
        print("  FAIL connect: %s" % u2_err)

    if d is not None:
        open_settings(serial)
        print("U2 hierarchy…")
        try:
            out["u2_hier"] = bench_u2_hierarchy(d)
            print("  hierarchy ms:", ms(out["u2_hier"]))
        except Exception as e:
            out["u2_hier"] = []
            out["u2_error"] = str(e)
            print("  FAIL hierarchy: %s" % e)

        print("U2 settings tap…")
        try:
            t, ok, n = bench_u2_settings_tap(d, serial, label)
            out["u2_tap"] = (t, ok, n)
            print("  find+tap %s: %s ok=%d/%d" % (label, ms(t), ok, n))
        except Exception as e:
            out["u2_tap"] = ([], 0, 0)
            out["u2_error"] = str(e)
            print("  FAIL tap: %s" % e)

        try:
            d.app_stop("com.github.uiautomator")
        except Exception:
            pass

    kill_ui_daemons(serial)
    run(["adb", "-s", serial, "shell", "input", "keyevent", "KEYCODE_HOME"])
    return out


def ratio(a: float, b: float) -> str:
    if b <= 0:
        return "n/a"
    return "%.1fx" % (a / b)


def summarize(results: list[dict]) -> str:
    lines = [
        "# Handsets vs uiautomator2 vs raw dump — live bench",
        "",
        "Date: 2026-07-09. Hosts: s24 + hd8. Stay-awake held. Drivers run",
        "serially (UiAutomation exclusive).",
        "",
        "## Results",
        "",
    ]
    for r in results:
        lines.append("### %s (`%s`)" % (r["alias"], r["serial"]))
        lines.append("")
        lines.append("| Scenario | Raw dump | Handsets | uiautomator2 |")
        lines.append("|----------|----------|----------|--------------|")
        lines.append(
            "| Hierarchy (ms) | %s | %s | %s |"
            % (ms(r.get("raw_hier") or []), ms(r.get("hs_hier") or []), ms(r.get("u2_hier") or []))
        )
        for key, name in (
            ("raw_tap", "Settings find+tap"),
            ("hs_tap", None),
            ("u2_tap", None),
        ):
            pass
        rt, rok, rn = r.get("raw_tap") or ([], 0, 0)
        ht, hok, hn = r.get("hs_tap") or ([], 0, 0)
        ut, uok, un = r.get("u2_tap") or ([], 0, 0)
        lines.append(
            "| Settings find+tap | %s (%d/%d) | %s (%d/%d) | %s (%d/%d) |"
            % (ms(rt), rok, rn, ms(ht), hok, hn, ms(ut), uok, un)
        )
        lines.append(
            "| Driver start (ms) | 0 | %.0f | %s |"
            % (
                r.get("hs_start_ms") or 0,
                ("%.0f" % r["u2_start_ms"]) if r.get("u2_start_ms") else (r.get("u2_error") or "fail")[:40],
            )
        )
        if r.get("u2_error"):
            lines.append("")
            lines.append("u2 error: `%s`" % r["u2_error"][:200])
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    hs_ok = all((r.get("hs_tap") or (None, 0, 1))[1] == (r.get("hs_tap") or (None, 0, 1))[2] for r in results)
    u2_ok = all(
        r.get("u2_hier") and (r.get("u2_tap") or (None, 0, 1))[1] == (r.get("u2_tap") or (None, 0, 1))[2]
        for r in results
    )
    # speed: compare median hierarchy
    speed_notes = []
    for r in results:
        rh = statistics.median(r["raw_hier"]) if r.get("raw_hier") else None
        hh = statistics.median(r["hs_hier"]) if r.get("hs_hier") else None
        uh = statistics.median(r["u2_hier"]) if r.get("u2_hier") else None
        if rh and hh:
            speed_notes.append(
                "%s hierarchy: Handsets %s faster than raw; vs u2 %s"
                % (
                    r["alias"],
                    ratio(rh, hh),
                    ratio(uh, hh) if uh else "u2 n/a",
                )
            )
    for s in speed_notes:
        lines.append("- %s" % s)
    lines.append("- Handsets Settings reliability: %s" % ("PASS" if hs_ok else "PARTIAL"))
    lines.append("- u2 Settings reliability: %s" % ("PASS" if u2_ok else "FAIL/PARTIAL"))
    adopt = hs_ok and (
        not u2_ok
        or all(
            statistics.median(r["hs_hier"]) < 0.5 * statistics.median(r["u2_hier"])
            for r in results
            if r.get("hs_hier") and r.get("u2_hier")
        )
        or all(
            statistics.median(r["hs_hier"]) < 0.2 * statistics.median(r["raw_hier"])
            for r in results
            if r.get("hs_hier") and r.get("raw_hier")
        )
    )
    lines.append("")
    if adopt:
        lines.append(
            "**Decision: adopt Handsets as primary fleet UI driver.** "
            "Keep raw dump as fallback when Handsets unavailable. "
            "uiautomator2 remains optional Mac debug only (never concurrent)."
        )
    else:
        lines.append(
            "**Decision: do not fully migrate yet** — Handsets not clearly better "
            "on reliability+speed for these scenarios."
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    results = []
    for alias in HOSTS:
        results.append(run_host(alias))
    report = summarize(results)
    out_path = REPO / "docs" / "research" / "handsets-vs-u2-bench.md"
    out_path.write_text(report)
    print("\n" + report)
    print("Wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
