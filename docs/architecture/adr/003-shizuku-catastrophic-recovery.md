# ADR 003: Shizuku catastrophic recovery architecture

**Status:** Accepted (2026-07-11)  
**Context:** AutoJs6 watchdog Shizuku recovery when port 5555 is down

## Decision

The Shizuku catastrophic recovery path (`device/autojs6/lib/shizuku.js`) uses a **shell-first, UI-last** strategy:

1. **`serverRunning()`** — quick check; if Shizuku server is alive, proceed to wireless repair.
2. **`tryShellWirelessRepair()`** — shell-based wireless debugging enable + `adb connect 127.0.0.1:5555`.
3. **`tryShellWirelessRepair()` retry** — one more attempt in case of transient failure.
4. **`tapStartButton()`** — UI automation fallback via accessibility API.
5. **`enableWirelessDebuggingUi()`** — Samsung-specific developer-settings toggle.

## Rationale

**Why UI fallback still exists:**

- Shizuku (official RikkaApps) has no hidden intent/API to restart its daemon or toggle wireless debugging. The only headless path is `/sdcard/Android/data/moe.shizuku.privileged.api/start.sh`, which requires a working ADB/root shell — the exact resource being re-established (chicken-and-egg).
- `settings put global adb_wifi_enabled 1` does not stick on Fire OS, leaving UI tap as the only recovery path on those devices.
- Community forks (timschneeb/ShizukuExt-SystemUID, thedjchi/Shizuku) add start/stop intents, but switching forks is a separate fleet decision with its own risk assessment.

**Why shell path was improved:**

- Added `settings put global adb_enabled 1` — some ROMs require USB ADB enabled before wifi ADB works.
- Added `setprop service.adb.tcp.port 5555` — forces adbd to listen on TCP 5555, making the connection deterministic rather than relying on the random TLS-paired port.

## Consequences

- UI fallback is a deliberate last resort, reached only after two failed shell attempts.
- Fire OS devices with persistent shell failures after OTA may still need a reboot or peer ADB.
- Switching to a Shizuku fork with intents would remove the need for `tapStartButton()` entirely.

## Alternatives considered

| Alternative                                     | Reason rejected                                                            |
| ----------------------------------------------- | -------------------------------------------------------------------------- |
| `cmd` subcommand for wireless debugging         | No such service exposed via `cmd`                                          |
| `am broadcast` to toggle wireless debug         | No system intent exists; Shizuku broadcasts require per-install auth token |
| Writing to `/data/misc/adb/adb_keys` from shell | Not writable by uid 2000; requires root                                    |
| Switching to timschneeb/ShizukuExt immediately  | Separate decision; needs pilot on 1-2 devices first                        |

## Next actions

- Monitor catastrophic recovery frequency in fleet health logs.
- Consider piloting timschneeb/ShizukuExt-SystemUID on one device after next OTA.
