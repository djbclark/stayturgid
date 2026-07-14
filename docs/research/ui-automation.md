# Research — Android UI automation options (2026-07-09)

Live comparison on **s24** (Samsung One UI / Android 16) and **hd8** (Fire OS 11).
p7a not touched. Stay-awake held during tests.

## Current fleet path (baseline)

Mac/on-device scripts: `uiautomator dump` → regex parse (`control/lib/ui_parse.py`) →
`adb shell input tap`. Wrapped in `ScreenControlSession` (consent + inversion).

| Metric             | s24                                                       | hd8                   |
| ------------------ | --------------------------------------------------------- | --------------------- |
| Raw dump+cat (n=5) | **~2500 ms** avg                                          | similar order         |
| Hardcoded coords   | Obtainium gear/bulk update                                | —                     |
| Fragility          | empty dumps, drawer toggle, dialogs, Fire `termux-dialog` | same + no Termux 5555 |

Docs already call **uiautomator2** the preferred _dev_ tool and raw dump the
_fallback_ (`docs/handoff.md`, `docs/hacking.md`) — but **fleet Python never imports u2**.

## Tools tested

### 1. uiautomator2 3.7.0 (already on Mac via uv tool)

- Init OK on s24 + hd8 (`u2.jar` + server).
- Clean smoke (before Handsets): dump **~250–350 ms**, `d(text=…).click()` OK
  on Settings for both devices.
- **Conflicts:** shares Android’s exclusive `UiAutomation` slot with Handsets;
  default port **9008** collides with Handsets. After Handsets ran, u2 failed
  with `AccessibilityServiceAlreadyRegisteredError` / binary-protocol
  `BadStatusLine` until daemons were killed.
- Fits existing Python Mac scripts; needs `sys.path` to uv tool venv (already
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
  `hs --host 127.0.0.1 --port N …` (s24:9013, hd8:9012).

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

| Priority                | Choice                                      | Why                                                                                          |
| ----------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **1 — Primary (Mac)**   | **Handsets** via `control/lib/ui_driver.py` | 17–42× faster hierarchy than raw; ~4× vs u2; works with AutoJs6 a11y; Fire Settings reliable |
| **2 — Fallback**        | Raw dump+tap                                | When Handsets missing; Termux on-device scripts; no UiAutomation lock                        |
| **3 — Optional debug**  | uiautomator2                                | One-off Mac debugging only; **never** alongside Handsets                                     |
| **Avoid as fleet core** | Maestro / Appium                            | Wrong abstraction / weight for post-UI                                                       |

Live numbers: [handsets-vs-u2-bench.md](handsets-vs-u2-bench.md).

**Agent playbook (Mac → Android UI):** [mac-android-ui-automation.md](mac-android-ui-automation.md)
(best practices, quiet audits, sample code).

### Implementation — **DONE** (2026-07-09)

1. `control/lib/ui_driver.py` — `HandsetsSession`, `try_handsets()`, switch
   table parse, `tap_id` / `tap_any_text` / `wait_text`.
2. Ports: s24 **9013**, hd8 **9012**, p7a **9014**.
3. Mac scripts Handsets-primary: `enable_autojs6_shizuku.py`,
   `configure_aurora.py`, `import_catalog.py`, `enable_shizuku_installer.py`.
4. Termux Handsets wire client **shipped** (`stayturgid_handsets.py`):
   s24 bench ~12× vs dump; AutoJs6 / Aurora / Obtainium Termux twins
   Handsets-primary (`try_session` + dump fallback). Details:
   [handsets-under-termux.md](handsets-under-termux.md). hd8 Handsets via
   peer bootstrap (or Mac adb).
5. Do not run u2 + Handsets concurrently; invoke `~/.handsets/hs` (Mac)
   or the Termux wire client (no host binary).

### Non-goals

- Replacing AutoJs6 accessibility watchdog (different problem: no-shell recovery).
- Relying on keep-awake apps (Mac `svc power stayon` during sessions).
- Shipping Android builds of the host `hs` CLI (wait for upstream or use wire client).
