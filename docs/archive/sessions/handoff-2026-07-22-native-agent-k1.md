# Handoff — native-agent OPTIONS K1 (2026-07-22)

> **Superseded for live ops by**
> [../../operations/sessions/handoff-2026-07-23-native-agent-k1.md](../../operations/sessions/handoff-2026-07-23-native-agent-k1.md)
> (K1 cutover landed in **`195c5c7`**; HEAD moved on). Keep this file as
> historical dual-run / Phase 1–3b context.

**Audience:** operator + next agent  
**Repos (at original write):** `stayturgid` master **`9c7067b`** (pushed)  
**Site overlay:** `site-djbclark` master **`40655bd`** (Vector fragments; pushed)  
**Live status (longer):** [native-agent-status-2026-07-22.md](../plans/native-agent-status-2026-07-22.md)  
**Original plan:** [autojs6-to-native-apk-plan.md](../plans/autojs6-to-native-apk-plan.md)  
**OPTIONS:** **K1**

---

## One sentence

We built and dual-ran a Kotlin/Shizuku **native-agent** that can replace AutoJs6’s
co-monitor / shell catastrophic path over time; **AutoJs6 is still installed**;
telemetry is file-durable; **OpenObserve ingest is blocked on Mac auth** until you fix Vector’s password.

---

## What was done (code + fleet)

### Product (stayturgid)

| Area             | Location                                                                              | Notes                                                                         |
| ---------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Native agent APK | `device/native-agent/`                                                                | `org.stayturgid.agent.debug` **v0.3.1-heartbeat-heal** (versionCode 5)        |
| AIDL             | `pingAwake`, `runComonitor`, `repairCatastrophic`, `destroy`                          | UserService UID 2000                                                          |
| Host             | FGS `specialUse`; inject **screen-on only**; co-monitor heartbeat **always**          |                                                                               |
| Mac tools        | `control/tools/native-agent/`                                                         | `rollout.py`, `grant_shizuku.py`, `start_agent.py`, `reingest_soft_health.py` |
| Just             | `just agent-assemble`, `agent-rollout`, `agent-install`, `agent-grant`, `agent-start` | JDK **17/21** required (not 25+)                                              |
| Soft health      | `fleet_health_monitor` → `stats.record_event(soft_health)`                            | every ~5 min                                                                  |
| Durable files    | `~/.config/stayturgid/stats/events.jsonl` + **`soft_health.jsonl`**                   | whole-line + fsync                                                            |
| Vector → OO      | templates under `control/site_contract/sync_templates/fragments/vector/`              | file tail → stream `soft_health`                                              |

### Key commits (stayturgid)

| Commit                | Topic                                            |
| --------------------- | ------------------------------------------------ |
| `61a725c`             | Phase 1 scaffold + inject                        |
| `faf646e`             | Phase 2 co-monitor                               |
| `4aab7c6`             | Phase 3 catastrophic + fleet agent.log dual-read |
| `f294fbd`             | Screen-off heartbeat + Mac `agent_stale` heal    |
| `660c4a6` / `c77b79b` | Rollout tooling + fleet status docs              |
| `66bb037`             | soft_health stats snapshots                      |
| **`9c7067b`**         | crash-safe soft_health → Vector → OpenObserve    |

### Fleet rollout (verified at handoff write time)

| Host    | Reachability                      | Agent | UserService                    | `agent.log` STATUS    | AutoJs6                                                   |
| ------- | --------------------------------- | ----- | ------------------------------ | --------------------- | --------------------------------------------------------- |
| **s24** | `100.123.218.30:5555`             | 0.3.1 | **up**                         | **writing**           | dual-run (leave installed)                                |
| **p7a** | `100.65.230.108:5555` / LAN       | 0.3.1 | **up**                         | **writing** (~20 min) | dual-run                                                  |
| **hd8** | USB `GN43T503430603PS` (+ TS adb) | 0.3.1 | **up** (as of handoff recheck) | **writing**           | dual-run; **maintenance** flag may still skip soft-health |

**Do not rebuild AutoJs6** unless you change AutoJs6 itself. Dual-run is intentional until Phase 4.

---

## Architecture (mental model)

```text
Termux stayturgid_repair / start_adb.py     ← primary 5-min heal (unchanged)
        │
        ├── AutoJs6  → watchdog.log + a11y UI last resort
        └── native-agent → agent.log + inject + shell catastrophic
                 │
Mac fleet_health_monitor (~5 min)
        │ fsync
        ▼
soft_health.jsonl  ──Vector──►  OpenObserve stream soft_health   (SQL)
events.jsonl                    (local query_events; heals/issues too)
fleet-health.log                (rotating human text)
```

---

## What YOU need to do (operator)

### 1. Fix OpenObserve auth for Vector (blocking OO SQL)

Vector is **running** and **reading** `soft_health.jsonl`, but sinks fail with
**Unauthorized** — `OPENOBSERVE_ROOT_PASSWORD` is empty/wrong in the Vector
LaunchAgent env (`~/Library/LaunchAgents/com.djbclark.vector.plist`).

**Steps:**

1. Put real credentials where Vector loads them (typically  
   `~/.config/djbclark/observability.env` or the plist `EnvironmentVariables`):
   - `OPENOBSERVE_ROOT_EMAIL`
   - `OPENOBSERVE_ROOT_PASSWORD`
2. Restart Vector:

   ```bash
   launchctl bootout "gui/$(id -u)/com.djbclark.vector" 2>/dev/null || true
   launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.djbclark.vector.plist
   ```

3. Re-post any lines dropped during 401s (JSONL is still complete on disk):

   ```bash
   cd ~/ops/stayturgid
   python3 control/tools/native-agent/reingest_soft_health.py --dry-run
   python3 control/tools/native-agent/reingest_soft_health.py
   ```

4. In OpenObserve (`http://localhost:5080/oo/` or HTTPS `/oo/`), stream
   **`soft_health`**, e.g.:

   ```sql
   SELECT device, agent_age, watchdog_age, port, shizuku, issues, _timestamp
   FROM soft_health
   ORDER BY _timestamp DESC
   LIMIT 50;
   ```

Until this works, **local files remain the SSOT** — nothing is lost for soaks.

### 2. Confirm / clear hd8 maintenance (optional)

If soft-health still says `hd8 via bypass: issues=maintenance`, soft probes and
`soft_health` samples for hd8 may be skipped. Clear only when you want soft-health
on Fire again:

```bash
# typical path (confirm before rm):
ls ~/.config/stayturgid/state/fleet-health/hd8.maintenance
# rm when ready
```

### 3. Overnight soak (no code)

- Leave s24/p7a (and hd8 if soft-health enabled) running overnight.
- Next day: check `soft_health.jsonl` / OO for rising `agent_age` / `agent_stale`
  without screen interaction.
- `just health` / fleet-health.log for `agent_age=… issues=none`.

### 4. Do **not** do yet

- Do **not** uninstall AutoJs6.
- Do **not** treat OpenObserve as authoritative until reingest succeeds.
- Do **not** need a new AutoJs6 APK build for this workstream.

---

## What the next agent should do

### Immediate (if operator finished §1)

1. Verify Vector log has **no** `Unauthorized` for `stayturgid_soft_health_oo_sink`.
2. Confirm OO stream `soft_health` has s24/p7a (and hd8) rows.
3. If hd8 UserService dies again: Fire Shizuku packaging + binder handoff (see status doc).

### Phase 3.5 / B (before AutoJs6 cutover)

Tracked in status doc § Remaining steps B:

1. Battery unrestricted + unused-app off for agent package
2. Release signing (drop `.debug`)
3. Obtainium catalog entry
4. Ansible install + grant + battery flags
5. Forced `CLOSED_NO_SHELL` soak without AutoJs6 a11y
6. Fire: durable Shizuku after reboot (uncompressed native libs in **official** Shizuku release build — debug-repack was a stopgap)
7. Dashboard card for `agent_age`
8. Optional healing-registry `native_agent` mechanism

### Phase 4 (cutover)

Only after B soaks pass: agent owns co-monitor + shell catastrophic; decide a11y
policy; stop AJ6 deploy/heal; uninstall AJ6 pilot → fleet; close OPTIONS K1.

---

## Commands cheat sheet

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
cd ~/ops/stayturgid
git pull --ff-only origin master

just agent-assemble
just agent-rollout                    # reachable hosts
just agent-rollout s24 p7a
just agent-start GN43T503430603PS     # hd8 USB serial

# telemetry
tail -f ~/.config/stayturgid/stats/soft_health.jsonl
tail -f ~/.config/stayturgid/logs/fleet-health.log
python3 control/tools/native-agent/reingest_soft_health.py

# after product Vector template change:
just site-sync --dir ~/ops/site-djbclark --mode apply --force-generated=1
# then restart Vector (see operator §1)
```

---

## Known issues (do not re-discover)

| Issue                                            | Status                                                                  |
| ------------------------------------------------ | ----------------------------------------------------------------------- |
| Soft_health → OO **401 Unauthorized**            | **Operator must fix Vector env password**; reingest after               |
| Fire Shizuku release APK compressed `librish.so` | Server crash; fixed temporarily via STORED-lib repack + debug sign      |
| Fire UserService binder handoff flaky earlier    | Recheck at handoff showed us+STATUS; still treat Fire as soak-sensitive |
| Vector `retry_attempts: u64::MAX` invalid        | Fixed to `1000000` in sink template                                     |
| JDK 25+ breaks AGP                               | Use OpenJDK 21 for `just agent-assemble`                                |
| `just agent-install serial=…`                    | Use positional: `just agent-install 100.x:5555`                         |

---

## Success criteria (unchanged)

- [ ] All fleet hosts: release agent, fresh `agent.log`
- [ ] CLOSED_NO_SHELL recovery without AutoJs6 (pilot ≥1 week)
- [ ] Deploy/boot/health do not require AJ6
- [ ] OO soft_health SQL usable for week-scale soaks
- [ ] Rollback recipe tested (reinstall AJ6)

---

## Files to open first (next session)

1. This handoff
2. [native-agent-status-2026-07-22.md](../plans/native-agent-status-2026-07-22.md)
3. `device/native-agent/README.md`
4. `control/tools/native-agent/README.md`
5. OPTIONS **K1** in `docs/options.md`
