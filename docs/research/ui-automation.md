# Research — Android UI automation options (2026-07-09)

Live comparison on **s24** (Samsung One UI / Android 16) and **hd8** (Fire OS 11).
p7a not touched. Stay-awake held during tests.

## Current fleet path (baseline)

Mac/on-device scripts: `uiautomator dump` → regex parse (`shared/ui_parse.py`) →
`adb shell input tap`. Wrapped in `ScreenControlSession` (consent + inversion).

| Metric | s24 | hd8 |
|--------|-----|-----|
| Raw dump+cat (n=5) | **~2500 ms** avg | similar order |
| Hardcoded coords | Obtainium gear/bulk update | — |
| Fragility | empty dumps, drawer toggle, dialogs, Fire `termux-dialog` | same + no Termux 5555 |

Docs already call **uiautomator2** the preferred *dev* tool and raw dump the
*fallback* (`HANDOFF.md`, `HACKING.md`) — but **fleet Python never imports u2**.

## Tools tested

### 1. uiautomator2 3.7.0 (already on Mac via pipx)

- Init OK on s24 + hd8 (`u2.jar` + server).
- Clean smoke (before Handsets): dump **~250–350 ms**, `d(text=…).click()` OK
  on Settings for both devices.
- **Conflicts:** shares Android’s exclusive `UiAutomation` slot with Handsets;
  default port **9008** collides with Handsets. After Handsets ran, u2 failed
  with `AccessibilityServiceAlreadyRegisteredError` / binary-protocol
  `BadStatusLine` until daemons were killed.
- Fits existing Python Mac scripts; needs `sys.path` to pipx venv (already
  documented).

### 2. Handsets 0.1.26 (installed `~/.handsets`, invoke as `~/.handsets/hs`)

- One jar via `app_process`; no Play app. Text/CSS-like selectors; agent-friendly
  `hs ui` table.
- **Works with AutoJs6 accessibility ON** (critical for fleet).
- Bench (hd8 warm socket): ping ~2–4 ms; full dump p50 **~16 ms**; `hs ui` loop
  avg **~90–126 ms** on both hosts when daemon up.
- Tap-by-label: `hs tap "Display"` OK on Fire Settings; AutoJs6 drawer
  `Foreground service` found in **~539 ms** on hd8 after open.
- **Multi-device sharp edge:** `hs use SERIAL` rejects `ip:5555` and mDNS ids
  (`unknown connect arg`). With many `adb devices` entries it demands
  `--device` but `use` still won’t take the serial as an arg. **Workaround that
  worked:** push `hs.jar`, start
  `CLASSPATH=… app_process … Main --port=N`, `adb forward tcp:N tcp:N`, then
  `hs --host 127.0.0.1 --port N …` (s24:9009, hd8:9008).
- Pre-1.0; PATH `hs` conflicts with shell alias `herdr status` — use full path
  or `handsets` symlink (do not overwrite herdr).

### 3. Maestro (already at `~/.maestro`)

- s24: trivial Settings flow **COMPLETED** (~30 s wall including JVM startup).
- hd8: failed once with “Device … is not connected” after adb disconnect churn.
- YAML flows are great for human-authored regression, awkward for dynamic
  fleet scripts + `ScreenControlSession`. Heavy. **Not a primary fleet driver.**

### 4. Appium / ShadowDroid

- Appium: not installed; latency and Node server overhead worse than u2/Handsets
  for our tap-heavy post-UI.
- ShadowDroid: similar “agent CLI + warm service” niche as Handsets; not
  installed this round — Handsets already covers the need.

## Recommendation

| Priority | Choice | Why |
|----------|--------|-----|
| **1 — Adopt** | **Handsets** behind a thin Mac helper | 20–30× faster hierarchy than raw dump; selectors kill most hardcoded coords; coexists with AutoJs6 a11y; CLI fits agent loops |
| **2 — Keep** | Raw dump+tap | Fallback when daemon down; no UiAutomation lock; already wired to presence/inversion |
| **3 — Optional** | uiautomator2 for one-off Mac debugging | Already installed; **do not** run alongside Handsets |
| **Avoid as fleet core** | Maestro / Appium | Wrong abstraction / weight for post-UI |

### Suggested implementation (next agent turn, Medium risk)

1. `shared/mac/ui_driver.py` — `HandsetsSession(serial, port)` start/stop +
   `tap_text` / `find` / `ui`; fall back to current dump-parse-tap.
2. Multi-device port map in inventory (e.g. s24:9009, p7a:9010, hd8:9008).
3. Pilot one script (`enable_autojs6_shizuku.py` drawer) on s24+hd8 before
   converting Obtainium/Aurora.
4. Document: never run u2 + Handsets concurrently; invoke `~/.handsets/hs`.

### Non-goals

- Replacing AutoJs6 accessibility watchdog (different problem: no-shell recovery).
- Relying on keep-awake apps (Mac `svc power stayon` during sessions).
