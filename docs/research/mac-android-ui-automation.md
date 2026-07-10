# Mac → Android UI automation — best practices

Guide for agents debugging or configuring an Android app from a Mac over
wireless ADB (+ optional SSH). Tuned for unrooted consumer devices; patterns
match stayturgid’s fleet stack but apply to any single-app debug session.

Companion research: [ui-automation.md](ui-automation.md) (tool bake-off),
[handsets-vs-u2-bench.md](handsets-vs-u2-bench.md).

---

## Goals

1. Drive the app UI from the Mac (tap, swipe, type, assert).
2. Leave a clear visual signal that an agent owns the glass (display inversion).
3. Prefer hierarchy selectors over hardcoded coordinates.
4. Optional **UI-TARS vision gates** on high-stakes screenshots (`STAYTURGID_VLM=1`, see [docs/vlm.md](../../docs/vlm.md)).
5. Survive flaky wireless ADB, dialogs, and multi-device `adb devices` lists.
6. Fail closed on input when the session is not properly armed.

---

## Stack (recommended order)

| Priority | Tool | When |
|----------|------|------|
| **1** | **Handsets** (`hs` + on-device jar) | Primary Mac driver — fast hierarchy, works with AutoJs6 a11y |
| **2** | Raw `uiautomator dump` + regex + `adb shell input` | Fallback when Handsets missing; on-device Termux scripts |
| **3** | uiautomator2 | One-off debug only — **never** alongside Handsets (exclusive UiAutomation) |
| Avoid as core | Maestro / Appium | Fine for human YAML flows; heavy for dynamic agent scripts |

Multi-device sharp edge: stock `hs use SERIAL` often rejects `ip:5555`. Push
`hs.jar`, start `app_process … Main --port=N`, `adb forward`, then
`hs --host 127.0.0.1 --port N …`. Stayturgid wraps this in
`control/lib/ui_driver.py` (`HandsetsSession` / `try_handsets`).

---

## Session discipline (non-negotiable)

### Hold one session across the whole flow

Do **not** open/close screen-control between every tap. Short gaps (dialogs,
activity transitions) look like “session ended” if you tear down early — then
the next tap races inversion off or steals focus.

```python
with ScreenControlSession(host, label=host) as session:
    with try_handsets(serial, host) as hs:
        open_app(...)
        navigate_settings(...)
        assert_toggles(...)
        # HOME only at the very end
```

### Always invert while controlling

Display inversion is the “agent has the glass” signal. Keep it on for the
entire live UI window. Input must refuse to run when inversion is off
(fail closed).

### Quiet overnight / unattended audits

`STAYTURGID_PRESENCE_QUIET=1`:

- No flashlight / torch pulses
- No vibrate
- No consent dialog (auto-allow)
- No presence notification / toast / release dialog

Still enables inversion + lease. Use for scheduled screenshot jobs — **not**
as a substitute for a real session when a human is watching the phone.

`STAYTURGID_SKIP_PRESENCE=1` is debug-only (skips consent/torch entirely). Do
not use it to hide live UI work.

### Clear overlays first

PiP, floating bubbles, and system dialogs steal taps. Clear them at session
start (`ui_clearance` / dumpsys dismiss) before the first meaningful tap.

---

## Connectivity tips

```bash
adb connect <tailscale-or-lan>:5555
adb -s <serial> wait-for-device
adb -s <serial> shell echo ok
```

- Prefer a stable serial alias (`devices.conf` / inventory) over raw IPs in scripts.
- Reconnect before long flows; wireless ADB drops under sleep / Wi‑Fi roam.
- If SSH is available (Termux), use it for presence / file deploy; keep ADB for
  input and screencap.
- Expect some hosts offline: skip and log `unreachable`, do not abort the whole
  fleet run.

Wake / stay-on during a session (Mac):

```bash
adb -s "$SERIAL" shell svc power stayon true   # session start
adb -s "$SERIAL" shell svc power stayon false  # session end
```

Do not leave stay-on forever on a pocket phone.

---

## Finding and tapping UI

### Prefer text / resource-id / content-desc

```python
# Handsets (preferred)
hs.tap_text("Settings", timeout_ms=2500)
hs.tap_id("com.example.app:id/menu_more", timeout_ms=2000)
hs.tap_desc("More options", timeout_ms=1500)

# Preference Switch next to a title row
checked, ok = hs.switch_near_label("Filter apps from other sources")
if ok and not checked:
    hs.tap_switch_for_label("Filter apps from other sources")
```

### Raw dump fallback

```python
adb -s "$SERIAL" shell uiautomator dump /sdcard/ui.xml
adb -s "$SERIAL" shell cat /sdcard/ui.xml
# parse bounds="[x1,y1][x2,y2]" → tap center
adb -s "$SERIAL" shell input tap "$X" "$Y"
```

### Screenshots for humans / agents

```bash
adb -s "$SERIAL" exec-out screencap -p > /tmp/screen.png
```

Name shots by step (`01_home.png`, `12_installer.png`). Keep them outside the
git tree (e.g. `~/.config/…/artifacts/`).

### Typing

Prefer an automation IME (e.g. AdbKeyboard) for `input text`, then **restore**
the user’s default IME on session exit.

---

## Sample: quiet Mac audit of one settings screen

```python
#!/usr/bin/env python3
"""Minimal quiet screenshot + assert pattern."""
import os
import subprocess
from pathlib import Path

os.environ["STAYTURGID_PRESENCE_QUIET"] = "1"  # no torch / sound / dialog

# project imports: screen_control, ui_driver, stayturgid_device …

def shot(serial: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["adb", "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=40,
    )
    path.write_bytes(r.stdout or b"")

def audit(host: str, out: Path) -> list[str]:
    issues: list[str] = []
    serial = resolve_adb(host)
    subprocess.run(["adb", "connect", serial], capture_output=True)
    with ScreenControlSession(host, label=host) as session:
        with try_handsets(serial, host) as hs:
            session.shell("am", "start", "-n", "com.example/.Settings")
            shot(serial, out / "settings.png")
            if hs is None:
                issues.append("handsets_unavailable")
            else:
                checked, ok = hs.switch_near_label("Enable feature")
                if not ok:
                    issues.append("toggle_missing")
                elif not checked:
                    issues.append("toggle_off")
            session.shell("input", "keyevent", "KEYCODE_HOME")
    return issues
```

Stayturgid’s fleet job: `control/bin/gui_audit.py` (3:14am launchd, quiet presence).

---

## Assertion patterns that age well

| Prefer | Avoid |
|--------|--------|
| Switch checked near a stable label | Absolute `(x,y)` from one phone skin |
| `resource-id` when the app owns it | Matching transient toast text |
| Soft-fail optional OEM labels (`Battery` / `App battery usage`) | Assuming Pixel strings on Samsung/Fire |
| Log `issues=tag1,tag2` for triage | Silent `print("maybe ok")` |
| Per-host skip on unreachable | Hard `sys.exit(1)` for one dead phone |

OEM label aliases (battery, overflow menus, “Don’t allow”) are normal — keep
tuples of synonyms and try in order.

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Taps do nothing | Inversion off / session not held | Hold `ScreenControlSession`; gate input |
| Wrong toggle flips | Nearest-Switch heuristic too wide | Prefer Switch *after* the title row |
| Empty hierarchy | App animating / wrong activity | `wait_text` / sleep / re-dump |
| Handsets `BadStatusLine` | u2 still holding UiAutomation | Kill u2 daemon; don’t run both |
| `hs use` rejects serial | Crowded `adb devices` / `ip:5555` | Fixed port + `--host 127.0.0.1` |
| Focus jumps to Discord/etc. | Overlay / notification | Clear obstructions; re-launch target |
| Fire `termux-dialog` hangs | Fire OS Termux API stalls | Short SSH timeouts; quiet mode for audits |
| Battery-unrestrict prompt | App wants unrestricted for auto-update | Deny; keep OS battery optimized if policy says so |

---

## Debugging an arbitrary app (checklist)

1. Install / grant debug: wireless debugging or USB once, then `adb tcpip 5555`.
2. Confirm `adb shell pm path <pkg>` and launch activity (`dumpsys package` /
   `cmd package resolve-activity`).
3. Open a Handsets (or dump) session; map Settings / the screen under test.
4. Script navigation with waits; screenshot each step.
5. Assert durable state (Switch checked, selected radio, permission granted via
   `dumpsys` / `appops` when possible — UI only when settings live only in UI).
6. Tear down: session exit restores the prior foreground activity (or HOME
   if it was the launcher), then inversion off, IME restored, stay-on false.
   Do not force `KEYCODE_HOME` at the batch endpoint unless you want launcher.
7. Re-run after reboot once — cold-start is where most automation lies.

Non-UI checks when available (faster, schedule-friendly):

```bash
adb shell dumpsys deviceidle | grep <pkg>     # Doze whitelist?
adb shell appops get <pkg> RUN_IN_BACKGROUND
adb shell settings get secure enabled_accessibility_services
```

---

## Stayturgid wiring (this repo)

| Piece | Role |
|-------|------|
| `control/lib/screen_control.py` | Consent + inversion + gated `input` |
| `control/lib/ui_driver.py` | Handsets primary |
| `control/bin/gui_audit.py` | Neo/Aurora GUI audit — **parked**; manual only |
| `control/bin/check_fleet_health.py` | Session triage (`make health`); fleet-health + access-monitor only |
| `com.stayturgid.gui-audit` | launchd **parked** (not installed while app stores disabled) |

Logs: `~/.config/stayturgid/logs/gui-audit.log`.
Screenshots: `~/.config/stayturgid/artifacts/gui-audit/<date>/<host>/`.
