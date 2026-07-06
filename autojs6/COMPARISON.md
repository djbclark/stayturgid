# Tasker+AutoInput vs AutoJs6 — comparison framework

**Modules:** [autojs6/README.md](README.md) · [tasker/README.md](../tasker/README.md) · [docs/README.md](../docs/README.md)

Fill this in after running both stacks on the **same device** (never simultaneously). The goal is an evidence-based pick for the stayturgid watchdog/UI-repair layer.

## Test matrix

Run each scenario on Pixel 7a and Galaxy S24 with **cold reboot + single PIN unlock**, no USB intervention:

| Scenario | Tasker+AutoInput | AutoJs6 | Notes |
|----------|------------------|---------|-------|
| Healthy steady state (20 min cycle) | ✅ 7a Tasker 20 min + Termux 5 min loop | ✅ S24 `main.js` interval + Termux 5 min nudge (2026-07-05) | AutoJs6 also needs battery whitelist |
| Port 5555 slow recovery post-boot (~5 min) | ✅ ~5 min (7a historical) | ✅ ~2 min via boot-launcher + repair (S24 2026-07-05) | Termux adb needs TMPDIR set |
| sshd down (kill in Termux) | ✅ Termux repair restarts (7a) | ✅ repair-bridge ~2s restart; watchdog `invoke=ok` (S24 2026-07-05) | Watchdog notifies if `sshd=FAILED` |
| `CLOSED_NO_SHELL` catastrophic | ✅ 7a log-injection + AutoInput tap (2026-07-05) | ✅ UI tap via text match `Start` (S24 2026-07-05); full port-down injection not attempted (5555 too resilient) | Use `scripts/test-catastrophic-once.js` for UI path |
| Locked screen during catastrophic | ✅ notify fires; tap waits (7a) | ✅ screen off → `ok=false`, Start skipped (S24 2026-07-05) | `test-locked-screen-catastrophic-once.js` |
| Repair loop stale (Termux frozen) | | ✅ synthetic 20-min-old line → stale notify before invoke (S24 2026-07-05) | `test-stale-loop-once.js` (no 15-min wait) |
| Tailscale down | | ✅ live test: force-stop → probe `up=false` → watchdog notify+relaunch → recovery (S24 2026-07-05) | `autojs6/mac/test-tailscale-down.sh` (USB) |
| Auto-update 4-dialog import | | | Tasker only today |

## Technical criteria

| Criterion | Tasker+AutoInput | AutoJs6 | Winner |
|-----------|------------------|---------|--------|
| **Element finding vs coordinates** | AutoInput Gestures = inline coords; fragile on scroll/layout | `text("Start")` + coord fallback — **text match validated S24** | AutoJs6 |
| **Git-friendliness** | Tasker XML (verbose, IDs fragile) | Plain JS modules in repo | AutoJs6 |
| **Real-time Termux repair** | Termux:Tasker plugin (7a implemented) | RUN_COMMAND + trigger-file fallback — **validated S24** | Tie |
| **Background survival** | Tasker profiles + Termux loop | AutoJs6 script + Termux boot/5-min nudge; cold reboot validated S24 | Tie (watch a11y stability) |
| **Android 16 resilience** | Custom Setting namespace gotchas; AutoInput aborts task | a11y service randomly disables (known AutoJs6 issue) | Tasker (today) |
| **Install / signature** | Tasker beta + AutoInput plugins | Single APK; Obtainium-tracked | AutoJs6 |
| **Battery / Doze** | Tasker whitelisted | AutoJs6 whitelisted on S24 | Tie |
| **Catastrophic repair** | AutoInput gesture (validated 7a) | Accessibility text-tap **validated S24** (`test-catastrophic-once.js`) | Tie |
| **Samsung quirks** | `adb_wifi_enabled` write is no-op | UI toggle fallback available (`samsungWirelessDebugFallback`) | AutoJs6 (slightly) |
| **Debugging from Mac** | `tasker-io/` import, XML export | `adb push` deploy, shared watchdog log | AutoJs6 |

## Managerial criteria

| Criterion | Tasker+AutoInput | AutoJs6 | Winner |
|-----------|------------------|---------|--------|
| **Maintainability** | XML action codes, Bundle JSON | Readable JS, `require()` modules | AutoJs6 |
| **Collaboration / AI editing** | Harder (XML discovery) | Easier (text files) | AutoJs6 |
| **Versioning** | GitHub `version.json` + raw XML | Git-only | AutoJs6 |
| **Learning curve** | Tasker UI + plugin ecosystem | JavaScript + AutoJs6 APIs | Depends on author |
| **Fork / maintenance risk** | Tasker stable; AutoInput maintained | AutoJs6 active fork; a11y bugs reported | Tasker (slightly) |
| **Mutual exclusivity ergonomics** | Disable profiles + a11y | Mode file + stop script + a11y swap | Tie |

## Decision log

| Date | Device | Tester | Observation | Lean |
|------|--------|--------|-------------|------|
| 2026-07-05 | 7a | AI | AutoJs6 installed; RUN_COMMAND granted; repair-bridge trigger ~2s; full watchdog cycle blocked until AutoJs6 a11y enabled | TBD |
| 2026-07-05 | S24 | AI | Cold reboot + one unlock: Termux boot → `boot-launcher.js` → `main.js`; watchdog `trigger=boot` `invoke=ok`; sshd self-restarted; Shizuku+5555 up; TMPDIR fix needed for Termux `adb` repair checks | AutoJs6 lean for dev |
| 2026-07-05 | S24 | AI | Runtime tests: sshd kill → repair-bridge restart ~2s; `test-watchdog-once` invoke=ok; `test-catastrophic-once` Shizuku Start text-tap ok=true | **AutoJs6 for S24 production** |
| 2026-07-05 | S24 | AI | Tailscale-down live test via USB: coord ping fail after force-stop, watchdog `tun=false ping=false`, relaunch → `up=true` | AutoJs6 production hardened |

## Recommendation template (complete after testing)

**Pick one for production:**

- [ ] **Stay on Tasker+AutoInput** because …
- [x] **Switch to AutoJs6** on **S24** — cold reboot, sshd self-heal, RUN_COMMAND bridge, and Shizuku Start text-tap all validated 2026-07-05. Keep Tasker on **7a** until explicitly migrated.
- [ ] **Hybrid** (not recommended per HANDOFF): …

**Keep the other stack as:** Tasker+AutoInput archived on S24 (profiles disabled); emergency fallback on 7a.
