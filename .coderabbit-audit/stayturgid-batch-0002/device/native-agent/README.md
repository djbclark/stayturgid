# stayturgid-agent (native Kotlin)

OPTIONS **K1** replaces AutoJs6 with a purpose-built APK
that binds a **Shizuku UserService** (UID 2000) and injects silent input via
`InputManager.injectInputEvent` — **no** shell spawn, **no** Accessibility.

The agent also writes a 20-minute co-monitor heartbeat, repairs the Shizuku
shell path, and requests a Tailscale reconnect when either the tunnel or
remote Tailscale control-plane reachability is down. A repair is reported
successful only after both are re-probed as healthy. It also restores the configured
non-lockdown always-on VPN policy. Termux remains the primary sshd and routine
repair owner.

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

## Architecture

- `HostService` — FGS (`specialUse`), `SCREEN_ON`/`OFF`, coroutine timer
- `ShizukuUserService` — AIDL stub for keep-awake, co-monitor, shell repair,
  and Tailscale relaunch
- `ComonitorProbes` — STATUS for port 5555, Shizuku, sshd, a11y, Wi-Fi, and
  Tailscale; port probing falls back to `ss -ltn` on Fire OS when `/proc`
  hides adbd
- `CatastrophicRepair` — requests Tailscale reconnect through the app's
  exported receiver, falls back to its activity, and fails honestly when an
  app/runtime incompatibility still requires operator input
- Composite build: `dev.rikka.shizuku:api` / `:provider` from local fork
- `HandsetsStarter`/`HandsetsStartCommands` — peer-start the Handsets UI
  daemon on a Fire-OS device over external ADB (issue #121), the same
  no-Mac-dependency shape as `PeerStarter`'s Shizuku peer-start (issue #61)

The Termux twin in `device/termux/py/stayturgid_repair.py` runs every five
minutes and enforces the same runtime and always-on policy checks.

`app/src/main/assets/hs.jar` bundles the Handsets daemon (MIT-licensed,
Elliot Gao) so the agent can push it without the Mac having a copy; the
required license/copyright notice ships alongside it as the companion asset
`app/src/main/assets/hs.jar.LICENSE.txt`.

The launcher UI shows the version name/code, UTC build time, source revision,
application ID, build type, Android/device identity, and live Shizuku state.
The full diagnostic block is selectable and can be copied with one button.

## Retired AutoJs6 code

AutoJs6 was retired fleet-wide in the K1 cutover (2026-07-22) and its code
(`device/autojs6/`, `control/tools/autojs6/`) was deleted entirely in #162
(2026-07-31) — see
[docs/architecture/components/autojs6.md](../../docs/architecture/components/autojs6.md)
for historical reference only.

## Non-goals

The agent does not replace the Termux primary repair loop, restart Termux
sshd, or enable Accessibility. AutoJs6 package removal and signed-release
verification remain tracked operational work.
