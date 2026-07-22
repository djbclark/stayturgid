# Session checkpoint — native-agent Phase 1 (2026-07-22)

**Purpose:** Recoverable handoff if the implementing agent runs out of context.  
**OPTIONS:** K1  
**Plan:** [autojs6-to-native-apk-plan.md](../plans/autojs6-to-native-apk-plan.md)

## Operator direction

- Work continuously on **implementation**; stop only for questions.
- End goal: **remove AutoJs6** (G-C). Phase 1 does **not** remove it (dual-run).

## Status: Phase 1 **device-proven** on stock Pixel 7a

| Step                                        | Status                      |
| ------------------------------------------- | --------------------------- |
| Scaffold `device/native-agent/`             | **done**                    |
| Composite build vs `~/src/Shizuku/api`      | **done**                    |
| `just agent-assemble`                       | **done**                    |
| Install on Pixel 7a (`100.65.230.108:5555`) | **done**                    |
| FGS HostService running                     | **done**                    |
| Shizuku UserService bind (`:userservice`)   | **done**                    |
| `pingAwake` inject via InputManager         | **done** (Context path)     |
| AutoJs6 removal                             | **not started** (Phase 2–4) |
| Co-monitor port                             | **not started**             |

### Live evidence (2026-07-22 ~10:32 device local)

```text
StayTurgidUS: constructor with Context: android.app.Application@...
StayTurgidUS: InputManager via Context
StayTurgidUS: pingAwake ok
StayTurgidHost: UserService connected
StayTurgidHost: pingAwake IPC ok
process: org.stayturgid.agent.debug:userservice
```

Package: `org.stayturgid.agent.debug` (debug build).  
Version: `0.1.1-phase1` (versionCode 2).

## Phase 0 defaults used

| Choice    | Value                                     |
| --------- | ----------------------------------------- |
| End-state | G-C (full AutoJs6 replacement later)      |
| Phase 1   | UserService + screen-on timer + pingAwake |
| FGS type  | `specialUse`                              |
| daemon    | `true` + unbind on screen-off             |
| AutoJs6   | left installed                            |

## Shizuku fork fixes (outside stayturgid)

`~/src/Shizuku/api` — re-apply if missing:

1. `demo/build.gradle` — `proguardFiles` varargs (not Groovy list)
2. `demo-hidden-api-stub/build.gradle` — `namespace = "rikka.shizuku.demo.hidden_api_stub"`

## Build

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
cd ~/ops/stayturgid
just agent-assemble
# APK: device/native-agent/app/build/outputs/apk/debug/app-debug.apk
```

Needs **JDK 17/21** (not 25+). Composite default on; Maven: `just agent-assemble composite=false`.

## Device pilot recipe

```bash
SERIAL=100.65.230.108:5555   # or USB serial
adb -s $SERIAL install -r device/native-agent/app/build/outputs/apk/debug/app-debug.apk
# grant Shizuku (same path as AutoJs6):
python3 - <<'PY'
import os, sys
sys.path.insert(0, "control/lib")
import stayturgid_device as dev
PKG="org.stayturgid.agent.debug"
s=dev.PrivShell("SERIAL_HERE")
uid=s.app_uid(PKG)
s.sh(f"pm grant {PKG} moe.shizuku.manager.permission.API_V23")
cur,ok=s.read_shizuku_json("/data/local/tmp/shizuku/shizuku.json")
assert ok
s.install_shizuku_json(dev.patch_shizuku_json(cur, uid, PKG),
  "/sdcard/Download/shizuku.json", "/data/local/tmp/shizuku/shizuku.json")
print("ok", uid)
PY
# ensure Shizuku server up:
adb -s $SERIAL shell /data/local/tmp/shizuku_starter
adb -s $SERIAL shell input keyevent KEYCODE_WAKEUP
adb -s $SERIAL shell am start -n org.stayturgid.agent.debug/org.stayturgid.agent.MainActivity
adb -s $SERIAL logcat -s StayTurgidHost:I StayTurgidUS:I
```

Notes:

- Do **not** start FGS via `adb shell am start-foreground-service` (denied for shell on API 34+). Use MainActivity (auto-starts host) or BootReceiver.
- After `shizuku.json` patch, restart Shizuku (`shizuku_starter`) if permission still denied.
- Modern Android: use **Context constructor** InputManager path (getInstance removed).

## Phase 2 progress (same session)

| Step                                          | Status                                                      |
| --------------------------------------------- | ----------------------------------------------------------- |
| `runComonitor()` AIDL                         | **done**                                                    |
| `ComonitorProbes` (/proc + settings)          | **done**                                                    |
| Write `/sdcard/stayturgid/logs/agent.log`     | **done**                                                    |
| Device STATUS line on Pixel 7a                | **done** (`port=open shizuku=up sshd=up a11y=up shell=yes`) |
| `control/tools/native-agent/grant_shizuku.py` | **done**                                                    |
| Fleet health dual-read agent.log              | **not started**                                             |
| AutoJs6 still dual-running                    | **yes**                                                     |

Version: `0.2.0-phase2-comonitor` (versionCode 3).

## Phase 3 progress (continued session)

| Step                                              | Status                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------- |
| Fleet health dual-read `agent.log`                | **done** (`agent_age`, STATUS merge; missing agent not a hard fail) |
| `CatastrophicRepair` shell-first + HEADLESS_START | **done** (no a11y)                                                  |
| AIDL `repairCatastrophic()`                       | **done**                                                            |
| Auto-trigger on CLOSED_NO_SHELL                   | **done**                                                            |
| Device reinstall 0.3.0 + STATUS                   | **done** (Pixel 7a; userservice up)                                 |
| Forced CLOSED_NO_SHELL soak                       | **not done**                                                        |
| AutoJs6 rebuild                                   | **not needed** to continue                                          |

Version: `0.3.0-phase3-catastrophic` (versionCode 4).

## Next agent priorities

1. Commit/push if not already on origin.
2. Optional: `control/tools/native-agent/grant_shizuku.py` thin wrapper (package param).
3. Optional: fix BootReceiver logging always showing BOOT_COMPLETED on cold start (investigate redelivery).
4. Phase 2: co-monitor AIDL methods + STATUS log — **do not** remove AutoJs6.
5. Battery unrestricted / unused-app off for agent package (harden path).

## Do not

- Delete AutoJs6.
- Shell-spawn `input` from UserService.
- Use `moe.shizuku.api` client packages.
