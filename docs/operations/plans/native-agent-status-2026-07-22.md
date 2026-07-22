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

## Fleet rollout (2026-07-22, updated after s24/hd8 attach)

| Host                 | Reachability                       | Agent install | Shizuku UserService | `agent.log` STATUS    | AutoJs6  |
| -------------------- | ---------------------------------- | ------------- | ------------------- | --------------------- | -------- |
| **p7a** (Pixel 7a)   | adb wireless OK                    | **0.3.1**     | **bound**           | **writing** (~20 min) | dual-run |
| **s24** (Galaxy S24) | adb wireless `100.123.218.30:5555` | **0.3.1**     | **bound**           | **writing**           | dual-run |
| **hd8** (Fire HD 8)  | USB + TS adb OK                    | **0.3.1**     | **bound**           | **writing**           | dual-run |

### p7a — full

- UserService bound; STATUS with `uid=2000`; fleet `agent_age` when fresh

### s24 — full (rolled out this session)

- Install + grant + Shizuku restart + start OK
- Evidence: userservice pid live;  
  `[agent] STATUS port=open shizuku=up sshd=up a11y=up shell=yes … ts=2026-07-22 12:08:27 uid=2000`

### hd8 — agent APK in; Fire Shizuku/UserService flaky

**Done:** agent 0.3.1 + `shizuku.json` grant.

**Server crash fixed:** fleet release17 packs `librish.so` **Deflated**. Fire
`System.load(…/base.apk!/lib/…)` → `UnsatisfiedLinkError`. Repackage with
**STORED** `.so` + `resources.arsc`, zipalign, re-sign → `shizuku_server` stays up.

**Working:** Started the Shizuku server via USB, and the agent successfully bound to UserService (`uid=2000`).

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

1. ~~**s24 online** → roll out~~ **Done 2026-07-22**
2. ~~**hd8 UserService binder handoff** — Shizuku server fixed (uncompressed libs); still DeadObjectException returning binder to manager. Confirm `agent.log` after fix~~ **Done 2026-07-22**
3. ~~Clear **hd8 maintenance** only when soft-health should resume (site policy)~~ **Done 2026-07-22**
4. Optional soak: 24–48h p7a/s24 overnight → `agent_age` should stay fresh
5. **Shizuku fork packaging** — release APKs with STORED native libs (Fire requires this for `System.load` from APK path)

### B — Hardening before cutover (Phase 3.5)

5. Battery unrestricted + unused-app off for `org.stayturgid.agent(.debug)` (mirror AutoJs6 harden)
6. Release signing key + non-debug `applicationId` without `.debug`
7. Obtainium catalog entry for agent APK updates
8. Ansible: install agent, grant Shizuku, battery flags (new role or bootstrap_apks + grant task)
9. Forced `CLOSED_NO_SHELL` soak: prove `repairCatastrophic` restores 5555 without AutoJs6 a11y
10. Fire-specific: durable Shizuku start (starter/fleet profile) so agent binds after reboot
11. Dashboard: show `agent_age` / agent STATUS card
12. Healing registry: optional `native_agent` mechanism for PORT5555 / SHIZUKU-HEADLESS should_cover

**How B is measured over time** — see [Observability](#observability-for-dual-run--pre-cutover) below.
Fleet soft-health now writes a durable `soft_health` JSONL sample every ~5 min per
reachable host so dual-run regressions are debuggable weeks later.

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

## Observability for dual-run / pre-cutover

Three layers already exist; use them together when debugging “why did agent die
last Tuesday?”

| Layer                    | Where                                                                        | Retention                           | What it captures                                                   |
| ------------------------ | ---------------------------------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------ |
| **Device STATUS**        | `/sdcard/stayturgid/logs/agent.log` (and `watchdog.log`)                     | Device storage (not rotated by Mac) | Co-monitor STATUS, catastrophic lines (`[agent] catastrophic…`)    |
| **Mac soft-health text** | `~/.config/stayturgid/logs/fleet-health.log`                                 | Rotated (~2000 lines)               | Human-readable `agent_age=` / `watchdog_age=` / issues every 5 min |
| **Mac stats JSONL**      | `events.jsonl` + **`soft_health.jsonl`** under `~/.config/stayturgid/stats/` | **Forever**                         | Local SSOT; soft_health.jsonl is Vector-tailed                     |
| **OpenObserve**          | stream `soft_health` (Vector HTTP)                                           | OO retention                        | SQL queries once auth works                                        |

### Already logged forever (`events.jsonl`)

| `type`            | Source                          | Fields of interest                                                                                                                                    |
| ----------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `connection_path` | fleet_health_monitor            | `via` (ssh/adb path)                                                                                                                                  |
| `issue_detected`  | fleet_health_monitor            | `issue` (one event per tag, e.g. `agent_stale`)                                                                                                       |
| `heal_triggered`  | fleet_health_monitor            | `heal=agent\|watchdog\|repair\|…`                                                                                                                     |
| `device_status`   | access-monitor et al.           | online/offline                                                                                                                                        |
| **`soft_health`** | fleet_health_monitor each probe | `agent_age`, `watchdog_age`, `repair_age`, `port`, `shizuku`, `a11y`, `autojs6_a11y`, `sshd`, `shell5555`, `bootloop`, `issues`, `issue_count`, `via` |

### Crash-safe path to OpenObserve (chosen design)

```text
fleet_health_monitor
   │  append whole JSON line + fsync
   ▼
~/.config/stayturgid/stats/soft_health.jsonl   (append-only, never truncated)
   │  Vector file source (device_and_inode fingerprint, checkpoints in data_dir)
   │  remap: drop corrupt lines
   │  HTTP micro-batch (≤100 events / 15s)
   │  disk buffer 512MB, when_full=block, e2e acknowledgements
   ▼
OpenObserve stream soft_health  (SQL)
```

**Why not emit HTTP from Python directly:** process crash loses in-flight events;
OO down for days needs a durable queue. **Why not only `events.jsonl`:** keeps
Vector ingest scoped; other event types stay local unless we add more tails.

**Unclean state recovery:**

| Failure                   | What happens                                                                                              |
| ------------------------- | --------------------------------------------------------------------------------------------------------- |
| Writer crash mid-line     | One corrupt last line; Vector VRL `abort` drops it                                                        |
| Vector crash              | File checkpoint + sink disk buffer; restarts resume unread/unacked                                        |
| OpenObserve down for days | Sink disk buffer blocks; JSONL keeps growing; catch-up when OO returns                                    |
| soft_health.jsonl missing | Vector `ignore_not_found`; first probe `touch`es file                                                     |
| OO Unauthorized           | Pre-existing creds issue — fix `OPENOBSERVE_ROOT_PASSWORD` in Vector launchd env; JSONL still accumulates |

SQL (OpenObserve UI, stream `soft_health`):

```sql
SELECT device, agent_age, watchdog_age, port, shizuku, issues, _timestamp
FROM soft_health
WHERE device = 'p7a'
ORDER BY _timestamp DESC
LIMIT 50;
```

Local query example:

```bash
python3 - <<'PY'
from datetime import datetime, timedelta, timezone
from control.lib import stats
since = datetime.now(timezone.utc) - timedelta(days=7)
for e in stats.query_events(since=since, event_type="soft_health", device="p7a")[-5:]:
    print(e["ts"], e.get("agent_age"), e.get("watchdog_age"), e.get("port"), e.get("issues"))
PY
```

Or: `rg '"type": "soft_health"' ~/.config/stayturgid/stats/events.jsonl | tail`

### Map Phase 3.5 (B) items → what to watch

| B item                    | Metric / log signal                                                          | Pass condition for cutover confidence |
| ------------------------- | ---------------------------------------------------------------------------- | ------------------------------------- |
| Battery unrestricted      | Manual `dumpsys deviceidle` / appops note; optional future soft_health field | No `agent_stale` heals overnight      |
| Release APK / no `.debug` | package name in rollout notes                                                | Release package on all hosts          |
| Obtainium / Ansible       | deploy runbooks + inventory                                                  | `just deploy` installs agent          |
| CLOSED_NO_SHELL soak      | `soft_health.port` spikes + `heal_triggered` / agent.log catastrophic        | Recovery without AJ6 a11y             |
| Fire Shizuku durable      | `soft_health.shizuku` + agent_age missing/stale on hd8                       | Reboot → agent STATUS resumes         |
| Dashboard card            | dashboard UI                                                                 | Operator sees agent_age               |
| Healing registry          | `just test` / coverage                                                       | AGENT-FRESH + optional PORT5555       |

### Also useful to track (recommended next)

| Signal                              | Why                                           | Suggested home                                                                |
| ----------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- |
| **agent package versionCode**       | Correlate regressions with APK builds         | soft_health or weekly inventory scrape                                        |
| **UserService bound?** (pid / peek) | Distinct from “Shizuku up” (hd8 failure mode) | soft_health `userservice=up\|down`                                            |
| **FGS notification present**        | OEM kill of host process                      | soft_health or dumpsys activity services                                      |
| **Catastrophic fire count**         | Dual-run double-heal                          | already agent.log + optional `heal_triggered` detail                          |
| **AJ6 vs agent STATUS agreement**   | Drift between stacks                          | compare soft_health vs watchdog scrape                                        |
| **Battery / standby bucket**        | Screen-off death                              | occasional dumpsys, not every 5 min                                           |
| **Checklist completion**            | B/C items done when                           | keep this status doc + OPTIONS K1 (human SSOT); don’t invent a second tracker |

Avoid logging every dumpsys every 5 min (noise + cost). Prefer: high-cadence **ages/STATUS** (done), low-cadence **inventory** (version, battery, userservice) on demand or daily.

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
