# stayturgid-agent (native Kotlin)

Phase 1 scaffold for OPTIONS **K1**: replace AutoJs6 with a purpose-built APK
that binds a **Shizuku UserService** (UID 2000) and injects silent input via
`InputManager.injectInputEvent` — **no** shell spawn, **no** Accessibility.

**End-state:** full AutoJs6 retirement (G-C). **Now:** dual-run; AutoJs6 stays.

Plan: [`docs/operations/plans/autojs6-to-native-apk-plan.md`](../../docs/operations/plans/autojs6-to-native-apk-plan.md)  
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
just agent-install host=oneui-device   # when adb path known
```

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

## Non-goals (still AutoJs6 / Termux)

Co-monitor, catastrophic repair, Termux bridge, Obtainium catalog entry,
removing AutoJs6. See plan Phases 2–4.
