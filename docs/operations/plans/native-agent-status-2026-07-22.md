# Native agent status & remaining steps

**Date:** 2026-07-22  
**OPTIONS:** K1  
**Plan:** [autojs6-to-native-apk-plan.md](autojs6-to-native-apk-plan.md)  
**Checkpoint:** [session-2026-07-22-native-agent.md](../sessions/session-2026-07-22-native-agent.md)  
**Code:** `device/native-agent/` — package `org.stayturgid.agent` (debug: `.debug`)  
**Current version:** `0.3.1-heartbeat-heal` (versionCode 5)

---

## One-sentence summary

We are **mid dual-run**: a Kotlin/Shizuku UserService APK already does inject +
co-monitor + shell catastrophic repair on pilot hardware, while **AutoJs6 remains
installed** as the safety net (especially Accessibility UI last resort). **Do not
rebuild AutoJs6** to continue agent work unless you change AutoJs6 itself.

---

## What the pieces are for

| Piece                                           | Role                                                                                                                                                       |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Termux** `stayturgid_repair` / `start_adb.py` | **Primary** 5‑min self-heal (sshd, 5555, Shizuku headless, packages, …)                                                                                    |
| **AutoJs6** `device/autojs6/`                   | **Secondary** JS watchdog: co-monitor → `watchdog.log`, catastrophic shell **+ a11y UI tap**, Termux kick, Tailscale, notifications                        |
| **native-agent** `device/native-agent/`         | **Replacement under dual-run**: FGS host + UserService (UID 2000), inject (screen-on), co-monitor → `agent.log`, shell-first catastrophic **without a11y** |
| **Mac** `fleet_health_monitor`                  | Soft health every 5 min; restarts AutoJs6 on `watchdog_stale`; restarts agent on `agent_stale`                                                             |

Routine repair stays **Termux-primary**. Agent does not own the 5‑min repair loop.

---

## Implementation progress (done)

| Phase  | Scope                                                                   | Status                                      |
| ------ | ----------------------------------------------------------------------- | ------------------------------------------- |
| **0**  | Goals G-C end-state, dual-run, package name                             | Assumed / accepted via continuous implement |
| **1**  | Gradle composite Shizuku API, AIDL, FGS, `pingAwake` / InputManager     | **Done** (device-proven p7a)                |
| **2**  | `runComonitor()` STATUS → `agent.log`                                   | **Done**                                    |
| **3**  | `repairCatastrophic()` shell + HEADLESS_START (no a11y)                 | **Done** (code + auto on CLOSED_NO_SHELL)   |
| **3b** | Screen-off heartbeat; Mac `agent_stale` heal; `start_agent` / `rollout` | **Done**                                    |
| **4**  | Cutover: Obtainium, Ansible, remove AutoJs6                             | **Not started**                             |

### Notable commits

| Commit    | Topic                                              |
| --------- | -------------------------------------------------- |
| `61a725c` | Phase 1 scaffold + device inject                   |
| `faf646e` | Phase 2 co-monitor                                 |
| `4aab7c6` | Phase 3 catastrophic + fleet `agent.log` dual-read |
| `f294fbd` | Heartbeat + Mac agent heal                         |

---

## Fleet rollout (2026-07-22)

| Host                 | Reachability                                      | Agent install       | Shizuku UserService | `agent.log` STATUS    | AutoJs6         |
| -------------------- | ------------------------------------------------- | ------------------- | ------------------- | --------------------- | --------------- |
| **p7a** (Pixel 7a)   | adb wireless OK                                   | **0.3.1**           | **bound**           | **writing** (~20 min) | still installed |
| **hd8** (Fire HD 8)  | USB OK today; TS often down; **maintenance** flag | **0.3.1 installed** | **not bound**       | none yet              | still installed |
| **s24** (Galaxy S24) | **unreachable** (TS + LAN timeout)                | **not installed**   | —                   | —                     | unknown offline |

### p7a — fully rolled out

- Grant: `control/tools/native-agent/grant_shizuku.py`
- Status lines like:  
  `[agent] STATUS port=open shizuku=up sshd=up a11y=up shell=yes … uid=2000`
- Fleet health already shows `agent_age=…` without issues when fresh

### hd8 — APK only (blocked on Shizuku server)

- APK + `shizuku.json` grant for `org.stayturgid.agent.debug` **ok**
- `shizuku_starter` reports start but **`shizuku_server` does not stay up** reliably on this Fire session → HostService logs `Shizuku not running` → no UserService
- **Operator follow-up:** open Shizuku on tablet, Start, confirm server process, then:

  ```bash
  just agent-start GN43T503430603PS
  # or: python3 control/tools/native-agent/rollout.py --serial GN43T503430603PS
  ```

- Fire also often uses split storage / `NO_LOCAL_ADB`; agent log path is still `/sdcard/stayturgid/logs/agent.log` when shell can write

### s24 — blocked offline

- No adb/ssh as of 2026-07-22 afternoon
- When back:

  ```bash
  just agent-rollout s24
  # or: python3 control/tools/native-agent/rollout.py s24
  ```

---

## Operator commands

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home   # AGP needs 17/21

just agent-assemble                    # build debug APK
just agent-rollout                     # all resolvable hosts from devices.conf
just agent-rollout p7a s24             # subset
just agent-install <serial-or-ip:5555>
just agent-grant <host-or-serial>
just agent-start <host-or-serial>

python3 control/tools/native-agent/rollout.py
python3 control/tools/native-agent/rollout.py --serial GN43T503430603PS
```

**AutoJs6:** leave running. Rebuild only if you change `device/autojs6/**` or the AutoJs6 APK fork.

---

## Remaining steps (ordered)

### A — Finish dual-run fleet coverage (now)

1. **s24 online** → `just agent-rollout s24` → confirm `agent.log` + `agent_age` in `just health`
2. **hd8 Shizuku stable** → start server, `just agent-start` USB serial → confirm UserService + STATUS
3. Clear **hd8 maintenance** only when soft-health should resume (site policy)
4. Optional soak: 24–48h p7a with screen off overnight → `agent_age` should not go `agent_stale` if heartbeat lives

### B — Hardening before cutover (Phase 3.5)

5. Battery unrestricted + unused-app off for `org.stayturgid.agent(.debug)` (mirror AutoJs6 harden)
6. Release signing key + non-debug `applicationId` without `.debug`
7. Obtainium catalog entry for agent APK updates
8. Ansible: install agent, grant Shizuku, battery flags (new role or bootstrap_apks + grant task)
9. Forced `CLOSED_NO_SHELL` soak: prove `repairCatastrophic` restores 5555 without AutoJs6 a11y
10. Fire-specific: durable Shizuku start (starter/fleet profile) so agent binds after reboot
11. Dashboard: show `agent_age` / agent STATUS card
12. Healing registry: optional `native_agent` mechanism for PORT5555 / SHIZUKU-HEADLESS should_cover

### C — Phase 4 cutover (retire AutoJs6)

Only after B soaks pass on all fleet hosts you care about:

13. Agent owns co-monitor + shell catastrophic exclusively
14. Decide a11y UI last resort: **keep tiny companion**, **fork Shizuku intent**, or **accept peer-ADB**
15. Stop deploying AutoJs6 project; remove Mac `start_watchdog` heal for AJ6 (or gate on package absent)
16. Uninstall AutoJs6 from pilot → soak → fleet
17. Drop `watchdog_stale` / `autojs6_a11y_*` as primary signals; prefer `agent_stale`
18. Docs + OPTIONS K1 close; update handoff / component pages

### D — Explicitly out of scope for agent

- Replacing Termux 5‑min repair
- FIRERPA / Obtainium for other apps
- Accessibility auto-enable (`settings put` banned)
- Keep-awake productization beyond inject proof unless G-A is confirmed for a host

---

## Risk register (current)

| Risk                         | Mitigation                                                                                                     |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Dual-run double catastrophic | Shell-first on both; AJ6 a11y only if shell fails; monitor spam                                                |
| Screen-off OEM kills FGS     | Battery unrestricted; Mac `agent_stale` heal                                                                   |
| Fire Shizuku flaky           | USB starter; document manual Start; peer-ADB                                                                   |
| s24 offline                  | No code risk; backlog install                                                                                  |
| Composite Shizuku build      | Fork fixes in `~/src/Shizuku/api` (demo proguard + stub namespace); Maven `-Pshizuku.composite=false` fallback |

---

## Success criteria for “agent replaces AutoJs6”

- [ ] All fleet hosts run release agent, fresh `agent.log`
- [ ] CLOSED_NO_SHELL recovery without AutoJs6 installed (pilot ≥1 week)
- [ ] Fleet health / deploy / boot paths do not require AJ6
- [ ] Operator accepts residual a11y policy (or has replacement)
- [ ] Rollback recipe tested once (reinstall AJ6 project + APK)

---

## Quick recovery for another agent

```bash
cd ~/ops/stayturgid && git pull --ff-only origin master
# status doc: docs/operations/plans/native-agent-status-2026-07-22.md
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
just agent-assemble
just agent-rollout          # reachable only
# p7a already good; s24 when online; hd8 needs Shizuku server first
```
