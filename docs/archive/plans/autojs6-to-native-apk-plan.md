# AutoJs6 → native Kotlin APK migration plan

**Created:** 2026-07-22

**Status:** **Phases 1–3b implemented; dual-run rollout in progress** (2026-07-22).
Live status + remaining steps:
[native-agent-status-2026-07-22.md](native-agent-status-2026-07-22.md).
Checkpoint: [session-2026-07-22-native-agent.md](../../operations/sessions/session-2026-07-22-native-agent.md).

**Audience:** Maintainers and implementation agents. Advisory prompt material
(UserService + AIDL + `InputManager.injectInputEvent`) is incorporated as the
privileged payload design; refinements below supersede the raw prompt where they
conflict.

**Related:** [AutoJs6 component](../../architecture/components/autojs6.md),
[ADR 003 Shizuku catastrophic recovery](../../architecture/adr/003-shizuku-catastrophic-recovery.md),
[OPTIONS](../../options.md) item **K1**.

---

## Search result (2026-07-22)

No existing plan for “replace AutoJs6 with our own APK” was found in this repo
or in today’s commits. What _does_ exist and must not be confused with this work:

| Existing artifact                                                 | What it is                                             | Not this plan                      |
| ----------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------- |
| `device/autojs6/`                                                 | Rhino/JS watchdog project                              | Target of migration                |
| AutoJs6 fleet **debug** APK (sticky a11y rebind, OPTIONS H14/A11) | Fork of **AutoJs6 itself**                             | Still AutoJs6 runtime              |
| `device/termux/py/stayturgid_screen_awake_guard.py`               | Detects forced-awake / long timeout and offers restore | Opposite of keep-awake injection   |
| Obtainium / `android_apk` / bootstrap APKs                        | Install **third-party** APKs                           | Distribution, not a stayturgid app |
| Local forks `~/src/Shizuku`, `~/src/AutoJs6`                      | Upstream-ish forks we already maintain                 | Build inputs                       |

Today’s git history is AutoJs6 TypeScript tooling / Rhino gotchas
(`vendor/autojs6-typescript`), not a native app scaffold.

---

## Problem statement

AutoJs6 is the on-device **secondary** automation layer: co-monitor, catastrophic
Shizuku repair (shell then accessibility), Termux bridge kick, Tailscale probe,
notifications. It runs an interpreted Rhino engine (`isInterpretedMode = true`),
depends on accessibility for UI fallbacks, and has recurring engine/deploy
gotchas (locale path mirrors, `jvm-npm` redeclaration, Java/JS string coercion).

A purpose-built Kotlin APK that binds a **Shizuku UserService** (UID 2000) can:

- Run privileged work with **no shell process spawn** on the hot path
- Avoid Accessibility for anything that is pure settings/`InputManager`/binder
- Drop the Rhino footprint and AutoJs6 package entirely once feature parity is met
- Fix Shizuku API bugs in `~/src/Shizuku` rather than papering over them in app code

### Critical scope clarification

An external advisory framed the replacement as:

> fire a background UI event every 5 minutes—ONLY while the screen is on—to
> prevent an idle timeout.

That is a **valid privileged payload primitive** (and a good first vertical slice),
but it is **not** what `device/autojs6/` does today. AutoJs6 does **not** inject
keep-alive input events. Routine repair is Termux-primary; AutoJs6 is watchdog /
co-monitor / catastrophic recovery.

Before coding past a scaffold, Phase 0 must record which of these is true:

| ID      | Goal                                                                                                    | Use input injection?                                                                                                 |
| ------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **G-A** | App-level inactivity detectors that only reset on real `InputEvent`s (kiosk / media / adult apps, etc.) | **Yes** — `injectInputEvent` is correct                                                                              |
| **G-B** | System screen-off timer only                                                                            | Prefer `SCREEN_OFF_TIMEOUT`, `stay_on_while_plugged_in`, dim WakeLock, or `FLAG_KEEP_SCREEN_ON` — **not** fake input |
| **G-C** | Full AutoJs6 replacement (co-monitor + catastrophic + bridge + notifications)                           | Input injection is optional/subordinate; shell-as-UID-2000 APIs and later a11y policy dominate                       |

**Default assumption for this plan:** **G-C** is the migration end-state; **G-A**
(or a no-op inject smoke test) is Phase 1’s proof that UserService + reflection works.
If the operator only wants G-A/G-B, stop after Phase 1–1b and do **not** remove AutoJs6.

---

## Architecture (target)

```text
                    ┌─────────────────────────────────────┐
  host process      │  stayturgid.agent (Kotlin APK)      │
  (app UID)         │  ForegroundService + SCREEN_ON/OFF  │
                    │  Coroutine scheduler (screen-on)    │
                    │  Shizuku permission + bindUserService│
                    └───────────────┬─────────────────────┘
                                    │ AIDL binder (kept open while needed)
                                    v
                    ┌─────────────────────────────────────┐
  UserService       │  ShizukuUserService (UID 2000)      │
  (shell identity)  │  IStayTurgidService.aidl            │
                    │  • pingAwake() → InputManager       │
                    │  • later: probe/repair methods      │
                    │  • destroy() = 16777114 → exit(0)   │
                    └─────────────────────────────────────┘
                                    │
                    uses local fork  │  composite build
                                    v
                    ~/src/Shizuku/api  (dev.rikka.shizuku:api|provider)
```

### Design decisions (accepted)

1. **UserService + AIDL** — correct Shizuku primitive; forces real bound-service
   IPC. Do not invent sockets or `newProcess` bridges for in-process work.
2. **`InputManager.injectInputEvent` via reflection** — zero process spawn.
   **Never** `Runtime.exec("input …")` or `Shizuku.newProcess` on the 5‑minute path.
3. **Modern packages only** — `dev.rikka.shizuku:api` / `:provider`. Never
   `moe.shizuku.api` client namespaces.
4. **Fix the fork, not the app** — Shizuku API bugs land in `~/src/Shizuku`
   (prefer the `api/` tree), rebuild, rebind. No permanent app-side workarounds.
5. **Termux remains primary for routine repair** until an explicit later phase
   moves specific repairs into the APK. Do not re-centralize the 5‑min repair
   hot path into the Kotlin host without an ADR.

### Refinements over the raw advisory prompt

| Topic           | Advisory said                    | Plan says                                                                                                                                                                                                                       |
| --------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gradle path     | `includeBuild("~/src/Shizuku")`  | **No tilde.** Prefer property + env; path is the **API** project `~/src/Shizuku/api` (publishes `dev.rikka.shizuku:*`), not only the monorepo root. See scaffold below.                                                         |
| `daemon(false)` | Forced false                     | Prefer **`daemon(true)`** (API default) + **explicit unbind** on screen-off / host stop. With `false`, process death of the host kills the UserService; true + unbind is more robust across FGS restarts and Shizuku reconnect. |
| AIDL            | Only `pingAwake()`               | **Must** include `void destroy() = 16777114` and call `System.exit(0)` (Shizuku convention; see demo `IUserService.aidl`).                                                                                                      |
| Key / motion    | `KEYCODE_UNKNOWN` / `SHIFT_LEFT` | Acceptable. Also allow a tiny no-op `MotionEvent` if IME paths ignore pure keys. Measure both on oneui-device before locking.                                                                                                   |
| FGS             | “lightweight”                    | Android 14+ **foregroundServiceType** required; persistent notification is expected. Choose `specialUse` / documented type early; no silent system-exempt fantasy.                                                              |
| Idle goal       | Assumed app inactivity           | **Phase 0 must confirm G-A vs G-B vs G-C.**                                                                                                                                                                                     |

Source of truth for destroy transaction codes and daemon semantics:
`~/src/Shizuku/api/api/src/main/java/rikka/shizuku/Shizuku.java` (UserService
docs around the `UserServiceArgs` / `bindUserService` block) and
`~/src/Shizuku/api/demo/.../IUserService.aidl`.

---

## What AutoJs6 actually owns (migration inventory)

Map each duty before deleting anything.

| Duty                                                       | Today                                      | Native path                                                                                               | Phase |
| ---------------------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ----- |
| Co-monitor (sshd / shizuku / a11y list / shell5555 / wifi) | `lib/comonitor.js` via `shizuku()` shell   | UserService methods using Settings / ServiceManager / binder — **prefer no shell**; shell only if API gap | 2     |
| Catastrophic wireless ADB / Shizuku revive                 | `lib/shizuku.js` shell then a11y Start tap | Shell-equivalent as UID 2000 first; **UI tap still needs a11y or a Shizuku fork intent** (ADR 003)        | 3     |
| Kick Termux repair when log stale                          | `lib/termux.js` `RUN_COMMAND`              | `Context` / pending intent / `am` from host or UserService                                                | 2–3   |
| Tailscale tun0 + coord ping                                | `lib/tailscale.js`                         | Same probes from UserService or host + `rish`-class shell once                                            | 2     |
| Notifications                                              | `lib/notify.js`                            | Host `NotificationManager` (normal app UID)                                                               | 2     |
| Sticky a11y detect / rebind                                | AutoJs6 fork APK + stayturgid#29           | Either keep a tiny a11y companion **or** accept detect-only until fork intent path                        | 3–4   |
| Engine / project deploy                                    | `control/tools/autojs6/*`, Ansible role    | Obtainium + APK build CI; retire project deploy                                                           | 4     |
| Keep-alive input (if G-A)                                  | **Not present**                            | `pingAwake()`                                                                                             | 1     |

**Hard boundary (project policy):** Accessibility remains **detection-only** unless
the operator explicitly authorizes a new a11y service for the stayturgid APK.
Catastrophic UI taps currently violate that for AutoJs6 by deliberate exception
(ADR 003). The native migration should **shrink** that exception (fork intents),
not expand it.

---

## Proposed repo layout

```text
device/native-agent/                 # or device/stayturgid-agent/
  settings.gradle.kts
  build.gradle.kts
  gradle.properties                 # shizuku.api.dir=...
  app/
    build.gradle.kts
    src/main/
      AndroidManifest.xml
      aidl/.../IStayTurgidService.aidl
      java|kotlin/.../
        HostService.kt              # FGS + screen on/off + timer + bind
        ShizukuUserService.kt       # AIDL stub + inject / probes
        MainActivity.kt             # permission UI only
  README.md
```

Optional later: split `:agent` (host) and `:userservice` if ProGuard/process
isolation needs it; start as one module matching the Shizuku demo shape.

**Do not** put the APK sources under `device/autojs6/`.

---

## Build system (composite + local fork)

### Why `~/src/Shizuku/api`

Published coordinates `dev.rikka.shizuku:api` and `dev.rikka.shizuku:provider`
are produced by the **API** Gradle project (`groupIdBase = "dev.rikka.shizuku"`),
not by the manager/server monorepo root alone. Composite-include that tree:

Relative from `~/ops/stayturgid` → `../../src/Shizuku/api`.

### `settings.gradle.kts` (sketch)

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

// Prefer property override for CI/worktrees; never rely on shell ~ expansion.
val shizukuApiDir: File =
    providers.gradleProperty("shizuku.api.dir")
        .map { file(it) }
        .orElse(
            providers.environmentVariable("SHIZUKU_API_DIR")
                .map { file(it) }
        )
        .orElse(
            // Default: sibling of ops/ under $HOME/src
            file("${System.getenv("HOME")}/src/Shizuku/api")
        )
        .get()

if (!shizukuApiDir.isDirectory) {
    throw GradleException(
        "Shizuku API dir missing: $shizukuApiDir " +
            "(set -Pshizuku.api.dir= or SHIZUKU_API_DIR)"
    )
}

includeBuild(shizukuApiDir) {
    dependencySubstitution {
        substitute(module("dev.rikka.shizuku:api")).using(project(":api"))
        substitute(module("dev.rikka.shizuku:provider")).using(project(":provider"))
    }
}

rootProject.name = "stayturgid-agent"
include(":app")
```

### App dependencies

```kotlin
dependencies {
    implementation("dev.rikka.shizuku:api:13.1.5")      // version ignored when substituted
    implementation("dev.rikka.shizuku:provider:13.1.5")
    // kotlinx-coroutines-android, androidx lifecycle, etc.
}
```

If composite resolution fails, fall back to `mavenLocal()` after
`./gradlew publishToMavenLocal` in the fork — still **no** permanent reliance on
Maven Central for the fork you are actively patching.

---

## Phase plan

### Phase 0 — Scope gate (docs only, ~1 hour operator)

**Done when:**

- [ ] Operator records G-A / G-B / G-C (or combination) in OPTIONS **K1**
- [ ] Package name chosen (suggestion: `org.stayturgid.agent`)
- [ ] Min/target SDK aligned with fleet (S24 Android 16, P7A, Fire HD 8)
- [ ] Decision: FGS notification copy + `foregroundServiceType`
- [ ] Decision: keep AutoJs6 dual-running during soak (recommended **yes**)

**Exit:** no code if only G-B and settings already suffice.

### Phase 1 — Scaffold + `pingAwake` proof (no fleet cutover)

**Deliverables:**

1. Gradle project under `device/native-agent/` (name final in Phase 0)
2. `IStayTurgidService.aidl` with `destroy() = 16777114` and `pingAwake()`
3. `ShizukuUserService` implementing inject via `InputManager` reflection
4. `HostService` FGS: dynamic `ACTION_SCREEN_ON` / `OFF`, coroutine interval
   (default 5 min, configurable), bind while interactive, unbind on off/stop
5. Shizuku permission request UX + provider in manifest
6. Manual install path: `./gradlew :app:assembleDebug` + `adb install -r`
7. Unit/instrumentation: reflection failure logs cleanly; destroy exits process

**Acceptance (oneui-device first):**

- [ ] With screen on, log shows binder `pingAwake` every N minutes **without**
      new `app_process` / `sh` children for input
- [ ] `dumpsys activity services` shows FGS; notification acceptable
- [ ] Screen off cancels timer and unbinds (or leaves daemon idle per choice)
- [ ] Killing host with `daemon(true)` does not leave a zombie without destroy;
      unbind + destroy path verified
- [ ] AutoJs6 **untouched** and still healthy

**Explicit non-goals:** co-monitor, repair, Obtainium catalog, removing AutoJs6.

### Phase 1b — Optional keep-alive productization (only if G-A)

- Config interval / event type (key vs motion)
- Disable path that does not require uninstall
- Document interaction with `stayturgid_screen_awake_guard.py` (guard should
  **not** fight intentional keep-awake; may need allowlist of our package’s
  wakelock if any)

### Phase 2 — Co-monitor parity (first real AutoJs6 bite)

Port `lib/comonitor.js` probes into UserService or host+UserService:

- sshd listening / echo
- Shizuku binder alive
- a11y **read-only** list (no `settings put`)
- `service.adb.tcp.port` / shell on 5555 where Fire allows
- wifi / tun0 as today

Write the same STATUS line shape to
`/sdcard/stayturgid/logs/watchdog.log` (or a sibling `agent.log` dual-written)
so Mac `fleet_health_monitor` can grow a new stale signal without a flag day.

**Acceptance:** co-monitor STATUS freshness with AutoJs6 co-monitor **disabled**
on one pilot host for ≥24h soak; Termux repair still primary.

### Phase 3 — Catastrophic path without AutoJs6 a11y (hard)

1. Reimplement shell wireless repair as UID 2000 direct API / `cmd` / settings
   (same sequence as ADR 003 shell path)
2. Prefer **Shizuku fork start/stop intents** (thedjchi / evaluated forks) over
   UI tap
3. Only if still blocked: operator-approved a11y in _this_ APK with
   detect-first policy — requires explicit OPTIONS + coding-rules amendment

**Acceptance:** simulated `CLOSED_NO_SHELL` recovery on oneui-device without
AutoJs6 running; Fire OS path documented (may remain peer-ADB dependent).

### Phase 4 — Cutover and retire AutoJs6

1. Obtainium catalog entry + signing (fleet debug key or release key policy)
2. Ansible: install agent APK, grant Shizuku, battery unrestricted, unused-app off
   (mirror AutoJs6 harden)
3. Boot: Termux:Boot or package `BOOT_COMPLETED` → start FGS (measure OEM kills)
4. Dual-run soak on all hosts
5. Remove: `device/autojs6` deploy from default playbooks, Mac autojs6 heal,
   `autojs6_watchdog` role, RUN_COMMAND grants for AutoJs6
6. Healing registry: replace AutoJs6 `must_cover` IDs with agent IDs
7. Docs: component page, handoff, hacking, OPTIONS close K1

**Rollback:** re-enable AutoJs6 project + Obtainium AutoJs6 package; agent can
remain installed disabled.

---

## Implementation prompt (for a future coding agent)

Use this **after** Phase 0. It incorporates destroy(), path safety, daemon
policy, and forbids shell-spawn input.

```text
# StayTurgid native agent — Phase 1 scaffold

You are a senior Android systems engineer. Scaffold a Kotlin Android app under
device/native-agent/ that will eventually replace AutoJs6. Phase 1 is ONLY:
Shizuku UserService + screen-on timer + InputManager.injectInputEvent. Do not
port co-monitor or remove AutoJs6.

## Build
- Kotlin DSL only.
- Composite-include local Shizuku API at $HOME/src/Shizuku/api via
  includeBuild + dependencySubstitution for dev.rikka.shizuku:api and
  :provider. Property shizuku.api.dir / env SHIZUKU_API_DIR overrides path.
  NEVER use bare "~/..." in Gradle.
- Dependencies: dev.rikka.shizuku:api and :provider only (not moe.shizuku.*).
- If the Shizuku API is wrong or broken: fix ~/src/Shizuku (api tree), do not
  hack around it permanently in this app.

## AIDL IStayTurgidService
- void destroy() = 16777114;  // required; System.exit(0)
- void pingAwake();

## UserService
- Implement Stub; constructors () and (Context) with @Keep as in Shizuku demo.
- pingAwake: reflect InputManager.getInstance / injectInputEvent; silent
  KeyEvent or tiny MotionEvent; catch and log; NEVER Runtime.exec or
  Shizuku.newProcess for input.
- UserServiceArgs: daemon(true), processNameSuffix, version bumped when stub changes.
- Host unbinds on screen off / FGS stop and relies on destroy for process exit.

## Host
- ForegroundService with required Android 14+ service type + ongoing notification.
- Dynamic receivers ACTION_SCREEN_ON / ACTION_SCREEN_OFF.
- Screen on: ensure bound, start coroutine every 5 minutes calling pingAwake.
- Screen off: cancel job, unbindUserService.
- Shizuku.checkSelfPermission / requestPermission before bind.

## Output
settings.gradle.kts, app/build.gradle.kts, AIDL, ShizukuUserService.kt,
HostService.kt, Manifest, short device/native-agent/README.md with build/install.
Strict null-safety. No AutoJs6 deletions.
```

---

## Risks and non-goals

| Risk                                      | Mitigation                                                                           |
| ----------------------------------------- | ------------------------------------------------------------------------------------ |
| OEM kills FGS / ignores FGS type          | Pilot S24 + P7A; battery unrestricted; document manufacturer settings                |
| UserService dies with Shizuku restart     | Rebind on binder received / permission listener (Shizuku API)                        |
| Dual-running AutoJs6 + agent double-heals | Phase 2+ feature flags; only one catastrophic owner                                  |
| Fire OS no local adb                      | Keep Termux `STAYTURGID_NO_LOCAL_ADB` semantics; agent must not assume loopback 5555 |
| Expanding a11y surface                    | ADR + OPTIONS; prefer fork intents                                                   |
| Composite build friction                  | mavenLocal fallback; CI documents `SHIZUKU_API_DIR`                                  |
| Mis-scoping keep-awake as full migration  | Phase 0 gate                                                                         |

**Non-goals (unless operator expands K1):**

- Replacing Termux repair / boot loop
- Replacing FIRERPA, Obtainium, or Mac adb_reconnect
- Root / Magisk
- Play Store distribution
- Using Accessibility as the primary inject path

---

## Effort sketch

| Phase | Calendar (single agent + one pilot device) |
| ----- | ------------------------------------------ |
| 0     | Hours                                      |
| 1     | 1–3 days                                   |
| 1b    | +1 day if G-A productized                  |
| 2     | 3–7 days + soak                            |
| 3     | 1–2 weeks (fork/intent unknowns)           |
| 4     | 1 week + multi-host soak                   |

---

## Completion criteria (whole program)

- [ ] Pilot host healthy with AutoJs6 **uninstalled** for agreed soak window
- [ ] Fleet health / healing registry / deploy path know only the agent
- [ ] No Rhino project deploy in default `just deploy`
- [ ] Docs and OPTIONS K1 closed
- [ ] Rollback recipe tested once

---

## References (local)

- Shizuku UserService demo: `~/src/Shizuku/api/demo/`
- Shizuku bind/destroy docs: `~/src/Shizuku/api/api/src/main/java/rikka/shizuku/Shizuku.java`
- AutoJs6 duties: `docs/architecture/components/autojs6.md`
- Catastrophic policy: `docs/architecture/adr/003-shizuku-catastrophic-recovery.md`
- Screen-awake **restore** helper (not inject): `device/termux/py/stayturgid_screen_awake_guard.py`
