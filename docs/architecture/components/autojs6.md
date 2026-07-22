# stayturgid AutoJs6 watchdog

Secondary layer: notifications, Tailscale probe, catastrophic Shizuku repair,
and a **JS co-monitor** that re-probes the same health surface as Termux repair
on **every host every cycle** (fleet parity — not Fire-only).

**Routine repair is Termux-primary** (`stayturgid-repair` every 5 min) — AutoJs6
defers `RUN_COMMAND` invoke unless the repair log is stale.

## What it does

| Interval         | Action                                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| 20 min + boot    | `main.js` cycle when engine alive                                                                          |
| On catastrophic  | Shizuku `shizuku()` shell repair, then a11y Shizuku Start tap                                              |
| Real-time repair | Only when Termux boot loop stale (>15 min)                                                                 |
| Co-monitor       | `lib/comonitor.js` — sshd / shizuku / a11y / shell5555 / wifi via `shizuku()` **every cycle on all hosts** |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb_reconnect.py`, Obtainium APK updates.

## Co-monitor (redundancy)

AutoJs6 has Shizuku API shell even when Termux hangs (battery API, Fire
`NO_LOCAL_ADB`, dead boot loop). Each cycle on **oneui-device / stock-android-device / fireos-device**:

1. Termux `[repair]` fresh → still run co-monitor (verify, don't skip)
2. Fire split-storage / Termux stale / bridge-fail → same co-monitor path
3. Co-monitor writes `[comonitor] STATUS port=… shizuku=… sshd=… a11y=…` to
   `/sdcard/stayturgid/logs/watchdog.log`
4. Termux repair dual-writes its STATUS to the same `/sdcard` path so AutoJs6
   can see freshness on Fire

Mac soft-health (`fleet_health_monitor.py`) restarts `main.js` if
`watchdog_stale`/`watchdog_missing` persists (~10 min), so a dead AutoJs6
engine self-heals without a manual `start_watchdog.py`.

## Project path (ASCII only)

Canonical install path (all hosts):

```text
/sdcard/stayturgid/autojs6/main.js
```

Do **not** run or leave a stayturgid project under AutoJs6’s locale sample
directories (`Scripts/` or Chinese **脚本/**). A stale tree at
`/sdcard/脚本/stayturgid` on p7a produced `SyntaxError: Invalid quantifier` when
opening that copy (2026-07-19). Deploy retires those mirrors
(`STALE_PROJECT_MIRRORS` in `autojs6_deploy_util.py`). Policy:
[coding-rules.md — Path and character set](../../coding-rules.md).

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup_autojs6.py` or Obtainium; fleet harden grants storage, `RUN_COMMAND`, notifications, battery unrestricted, unused-app off
2. Termux repair scripts deployed (`deploy_termux.py` / fleet)
3. Shizuku (thedjchi fork), TCP mode
4. **AutoJs6 fleet profile** — `device/autojs6/fleet_profile.json` applied via `FleetProfileActivity` intent by `enable_autojs6_shizuku.py` (no UI automation; uses [operator/AutoJs6 fleet-profile-553](https://github.com/djbclark/AutoJs6) build with [upstream API request](https://github.com/SuperMonster003/AutoJs6/issues/553)).

## Shizuku API (built-in, not a separate plugin)

AutoJs6 ships a global `shizuku(cmd)` function ([docs](https://docs.autojs6.com/#/shizuku)).
`lib/shizuku_shell.js` uses it for privileged shell before falling back to `shell()`.
Catastrophic repair tries `shizuku()` wireless-debug settings before the accessibility
Start-button tap. See [ADR 003](../adr/003-shizuku-catastrophic-recovery.md) for rationale
on why the UI fallback is retained.

Requires: Shizuku running, AutoJs6 authorized in Shizuku, **drawer toggle enabled**.

## Termux bridge

Grant `com.termux.permission.RUN_COMMAND` to AutoJs6 (setup script). Fallback: `bridges.py --mode repair` on a 2s poll (`touch run/repair_now`).

## Cycle behavior

1. If repair log fresh → skip routine `invokeRepair` (Termux boot loop owns it); **still** run co-monitor
2. If `CLOSED_NO_SHELL` → `shizuku()` shell attempt, then Shizuku UI tap
3. Always → `comonitor.run()` (sshd, a11y, shizuku, shell) on every host
4. Tailscale tun0 + coord ping; relaunch on failure
5. Notifications (stable IDs, coalesced)

## Boot / start paths

- **Boot (once):** Termux:Boot → `start-autojs6-watchdog.sh` → `boot-launcher.js` (may use `RunIntentActivity` — acceptable right after unlock)
- **5-min loop:** `stayturgid_autojs6_guard.py` — logs stale watchdog; arms `run/start_autojs6_now` for **autojs6-bridge** (rate-limited); **no** `am start` from the repair loop
- **bridges.py --mode autojs6:** 2s poll of `start_autojs6_now` → `boot-launcher.js` via `am start` (30 min cooldown)
- **Mac deploy / heal:** `./start_watchdog.py <host>` or `fleet_health_monitor` when `watchdog_stale`

## Layout

On device the project lives at `/sdcard/stayturgid/autojs6/` (or `$STAYTURGID_SD/autojs6/` on Fire OS).

```
device/autojs6/
  main.js, lib/ (watchdog, termux, shizuku, shizuku_shell, tailscale, …)
  scripts/boot-launcher.js
control/tools/autojs6/  — deploy.py, setup_autojs6.py, set_automation_mode.py, enable_autojs6_shizuku.py, start_watchdog.py, grant_shizuku.py, run_test.py
```

## Rhino JS-engine gotchas — read before touching `device/autojs6/**/*.ts`

`device/autojs6` compiles TypeScript to JavaScript that runs on AutoJs6's
bundled Rhino engine (`RhinoJavaScriptEngine`, `isInterpretedMode = true`),
**not** on Node/V8/QuickJS. tsc and the Node-based unit tests in `tests/js/`
both happily accept code that Rhino cannot actually run — these bugs are
invisible until the compiled output executes on a real device. All four were
discovered the same day (2026-07-22) debugging stayturgid#34: a fix deployed
cleanly, passed every test, and then p7a's AutoJs6 watchdog crashed on every
single launch attempt with no working engine until all four were found and
fixed. `tests/js/rhino-syntax-guard.test.ts` catches the two that are
mechanically detectable (see below); the other two require code review.

**1. Two files independently `require()`-ing the same module under the same
local name crash the whole script, anywhere in the require graph.**
`jvm-npm.js` (Rhino's CommonJS `require()` shim, `file:///android_asset/modules/jvm-npm.js`)
does not give each required file its own isolated top-level scope the way
Node's module system does. If two files — anywhere in the transitive
require graph reachable from `main.js`, not just direct siblings — each
declare `const log = require("./log.js")`, the _second_ one to load crashes
with `TypeError: redeclaration of var log.` This reproduces with a minimal
2-file repro independent of stayturgid's code, is independent of
`const`/`let`/`var`, and is independent of which file is the entry script.
Because nearly every module in this codebase logs (`const log = require("./log.js")`)
and shares config/notify/termux/comonitor/repair, this hit **every** shared
module, not just `log` — the fix was giving every file's local binding a
globally-unique name (`guardLog`, `watchdogConfig`, `comonitorNotify`, …).
`tests/js/rhino-syntax-guard.test.ts` asserts every top-level
`require()` local binding name across `main.js` + `lib/*.js` is globally
unique — a repeat of this bug fails the build.

**2. `main.js` — the raw entry script AutoJs6 executes directly — cannot use
tsc's CommonJS `exports` stamp.** Any `.ts` file containing `import`/`export`
syntax (including TS's own `import x = require(...)`) makes tsc emit
`Object.defineProperty(exports, "__esModule", { value: true })` as the first
statement, unconditionally, regardless of whether the file has real exports.
That's fine for `lib/*.ts` — those are only ever loaded _via_ `require()`,
which gives them a real `module.exports` object. `main.js` is different: it's
executed directly by the engine (`script.exec(context, scriptable, scriptable)`,
never `require()`'d by anything), so it has no `exports` object in scope —
`ReferenceError: "exports" is not defined.` on line 1 of its own body. Fix:
`main.ts` uses plain `const x: typeof import("./lib/foo.js") = require("./lib/foo.js")`
calls instead of `import x = require(...)` — a file with zero `import`/`export`
syntax anywhere is compiled by tsc as a plain script, not a module, and never
gets the stamp. If you add real `import`/`export` syntax back to `main.ts`,
you will reintroduce this — there is no automated check for it.

**3. `for...of` throws `EvaluatorException: syntax error` at runtime — not a
compile error.** This Rhino build's interpreted mode doesn't implement the
`for...of` iterator protocol despite `languageVersion = Context.VERSION_ES6`
being set; tsc's `ES2015` target (the floor — this tsc version has removed
the `ES5`/`ES3` targets that used to downlevel `for...of` to a plain indexed
loop automatically) emits `for...of` as-is, so nothing catches this before
deploy. Use a plain indexed `for (let i = 0; i < arr.length; i++)` loop
instead. `tests/js/rhino-syntax-guard.test.ts` greps every compiled
`device/autojs6/**/*.js` file (including `scripts/`) for `for...of` syntax
and fails the build if found. Likely-related-but-unconfirmed: anything else
that depends on the iterator protocol (array/object destructuring from an
iterable, spread into an array, generators, `Map`/`Set` iteration) — none of
these are currently used in this codebase, but treat them as suspect and
test on-device before relying on them.

**4. Java-interop return values don't have JS `String.prototype` methods
until explicitly coerced.** AutoJs6 API calls that return a Java
`java.lang.String` under the hood (confirmed: `Engine.getSource()`) come
back as a Rhino `NativeJavaObject` wrapper, not a native JS string primitive
— calling `.indexOf(...)`, `.trim()`, etc. directly on it throws
`TypeError: Cannot find function indexOf.` even though TypeScript's type
declarations say it's a plain `string`. Fix: wrap with `String(...)` before
using any `String.prototype` method — `String(engine.getSource() || "")`.
No compiler or test can catch this generically; if you add a new AutoJs6 API
call whose TS type is `string` but which is Java-backed at runtime, verify
on-device (or check what the underlying AutoJs6 API actually returns) before
assuming string methods work on it.
