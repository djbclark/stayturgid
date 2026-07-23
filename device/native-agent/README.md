# stayturgid-agent (native Kotlin)

Phase 1 scaffold for OPTIONS **K1**: replace AutoJs6 with a purpose-built APK
that binds a **Shizuku UserService** (UID 2000) and injects silent input via
`InputManager.injectInputEvent` — **no** shell spawn, **no** Accessibility.

**End-state:** full AutoJs6 retirement (G-C). **Now:** dual-run; AutoJs6 stays.

Plan: [`docs/archive/plans/autojs6-to-native-apk-plan.md`](../../docs/archive/plans/autojs6-to-native-apk-plan.md)  
Checkpoint: [`docs/operations/sessions/session-2026-07-22-native-agent.md`](../../docs/operations/sessions/session-2026-07-22-native-agent.md)

## Package

| Item            | Value                  |
| --------------- | ---------------------- |
| applicationId   | `org.stayturgid.agent` |
| debug suffix    | `.debug`               |
| minSdk / target | 26 / 36                |

## Build

Requires Android SDK (`ANDROID_HOME` or `local.properties` `sdk.dir`) and
**JDK 17 or 21** (AGP 8.10 rejects JDK 25+). On this Mac:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
```

```bash
cd device/native-agent
# optional: point at local Shizuku API fork (default $HOME/src/Shizuku/api)
# export SHIZUKU_API_DIR=$HOME/src/Shizuku/api
./gradlew :app:assembleDebug
```

Default build uses a **Gradle composite** against `$HOME/src/Shizuku/api`.
Fork fixes applied for composite (outside this repo): demo `proguardFiles`
varargs, `demo-hidden-api-stub` `namespace`.

Disable composite and use Maven Central if the fork is unavailable:

```bash
./gradlew :app:assembleDebug -Pshizuku.composite=false
```

APK path:

```text
app/build/outputs/apk/debug/app-debug.apk
```

From repo root:

```bash
just agent-assemble
just agent-rollout              # reachable hosts from devices.conf
just agent-rollout p7a s24      # subset
just agent-install 100.x.x.x:5555
just agent-grant p7a
just agent-start p7a
```

Live fleet status: [docs/archive/plans/native-agent-status-2026-07-22.md](../../docs/archive/plans/native-agent-status-2026-07-22.md).

## Install / pilot

```bash
adb -s <serial> install -r app/build/outputs/apk/debug/app-debug.apk
adb -s <serial> shell am start -n org.stayturgid.agent.debug/.MainActivity
```

1. Ensure Shizuku is running (fleet fork).
2. Open app → **Request Shizuku permission** → grant in Shizuku.
3. **Start host service** (or reboot — `BootReceiver` starts FGS).
4. With screen on, logcat should show `StayTurgidUS: pingAwake ok` and
   `StayTurgidHost: pingAwake IPC ok` (immediate + every 5 min).

```bash
adb logcat -s StayTurgidHost:I StayTurgidUS:I StayTurgidMain:I StayTurgidApp:I StayTurgidBoot:I
```

## Architecture (Phase 1)

- `HostService` — FGS (`specialUse`), `SCREEN_ON`/`OFF`, coroutine timer
- `ShizukuUserService` — AIDL stub, `destroy()=16777114`, `pingAwake()`
- Composite build: `dev.rikka.shizuku:api` / `:provider` from local fork

## What AutoJs6 is still for (and do you need to rebuild it?)

| AutoJs6 duty today                     | Need AutoJs6 rebuild to continue agent work?  |
| -------------------------------------- | --------------------------------------------- |
| Co-monitor STATUS → `watchdog.log`     | **No** — agent writes `agent.log` in parallel |
| Catastrophic UI tap (a11y) last resort | **No** — agent does shell-first only          |
| Termux bridge when repair log stale    | **No** for agent Phase 1–3                    |
| Sticky a11y detect (fork APK)          | **No** unless you change AutoJs6 itself       |

**Do not** build/push AutoJs6 just to continue native-agent work. Only rebuild
AutoJs6 if you change `device/autojs6/**` or the AutoJs6 APK fork.

## Non-goals still on AutoJs6 / Termux

Termux primary repair loop, a11y UI catastrophic taps, Obtainium catalog for
agent, removing AutoJs6 (Phase 4).
