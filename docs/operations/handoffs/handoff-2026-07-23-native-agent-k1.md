# Handoff — native-agent OPTIONS K1 (2026-07-23)

**Audience:** operator + next agent  
**This session agent:** handoff only (not owning uncommitted worktree)  
**Repo HEAD:** `stayturgid` master **`93e43b5`** (= `origin/master` at handoff write)  
**K1 cutover commit:** **`195c5c7`** — `feat(native-agent): complete K1 rollout, remove autojs6_watchdog, update trust model`  
**Earlier foundation:** through **`9c7067b`** / **`27425a2`** (scaffold, dual-run, soft_health → Vector, 2026-07-22 handoff)  
**Site overlay:** `site-djbclark` has Vector soft_health fragments (**`40655bd`** era; re-sync if drifted)  
**Supersedes:** [handoff-2026-07-22-native-agent-k1.md](handoff-2026-07-22-native-agent-k1.md)  
**Long status:** [native-agent-status-2026-07-22.md](../plans/native-agent-status-2026-07-22.md)  
**Plan:** [autojs6-to-native-apk-plan.md](../plans/autojs6-to-native-apk-plan.md)  
**OPTIONS:** **K1 marked Phase 4 complete** (closed in `docs/options.md` as of `195c5c7`)

---

## One sentence

**K1 code cutover is on master** (native-agent owns the watchdog path; `autojs6_watchdog` role removed); **live fleet is uneven** (s24 agent healthy; p7a/hd8 not adb-reachable at this handoff); **OpenObserve still not trustworthy** until Vector auth is fixed + reingest; **working tree has unrelated staged docs** — do not assume they belong to K1.

---

## Where the code is (committed)

| Topic             | State                                                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Native agent app  | `device/native-agent/` — release build path / signing material may exist locally under that tree                       |
| Mac tools         | `control/tools/native-agent/` — rollout, grant, start, reingest                                                        |
| Soft health       | `fleet_health` / `fleet_health_monitor` — `agent_stale`, `soft_health` events                                          |
| Durable telemetry | `~/.config/stayturgid/stats/soft_health.jsonl` + `events.jsonl` (fsync)                                                |
| Vector → OO       | site-sync fragments: file-tail `soft_health.jsonl` → stream **`soft_health`**                                          |
| Ansible           | `autojs6_watchdog` role **deleted** in `195c5c7`; `shizuku_config` role **added**; bootstrap/obtainium wired for agent |
| Healing registry  | Updated for agent vs AutoJs6 (see `tests/healing_registry.json` on master)                                             |
| Dashboard         | Agent age card changes in `195c5c7` (`dashboard.py`, `_device_card.html`)                                              |

### Important commits

| Commit              | What                                                                    |
| ------------------- | ----------------------------------------------------------------------- |
| `61a725c`…`f294fbd` | Phases 1–3b scaffold, dual-run, heals                                   |
| `9c7067b`           | soft_health.jsonl → Vector → OO                                         |
| `27425a2`           | 2026-07-22 handoff                                                      |
| **`195c5c7`**       | **K1 “complete” cutover** (role removal, trust model, deploy path)      |
| `df1e729`…`93e43b5` | Later work (FIRERPA health, **F1 MCP bridge docs**) — not K1 mid-flight |

---

## Live fleet (checked 2026-07-23 handoff)

| Host                          | adb at handoff | native-agent UserService | Latest `agent.log` STATUS                    |
| ----------------------------- | -------------- | ------------------------ | -------------------------------------------- |
| **s24** `100.123.218.30:5555` | **online**     | **up** (`us=27977`)      | **fresh** (~`2026-07-23 07:08` local device) |
| **p7a**                       | **not found**  | unknown                  | unknown                                      |
| **hd8** USB/TS                | **not found**  | unknown                  | unknown                                      |

`just health` was **nonzero** at handoff (hd8 historical AutoJs6/Shizuku errors in scrapes; recipe exit 1). Treat fleet health as **not clean** until re-checked with all hosts online.

**soft_health.jsonl:** ~231 lines and growing (Mac SSOT still good).  
**Vector:** running; recent log still shows **Unauthorized** on OO sinks — OO SQL still blocked until operator fixes password + reingest.

---

## Working tree at handoff (do not clobber)

`git status` at handoff write:

- **Staged (index):** `docs/options.md` (modified),  
  `docs/research/evaluations/observability-portal-unification-evaluation-2026-07-23.md` (**new**)  
  → looks like **observability portal evaluation**, not unfinished K1 code.  
  **Not owned by this handoff agent** — leave for that author or operator to commit/drop.

- **HEAD == origin/master** (`93e43b5`). No claim of unclean K1 APK/jks tree from the earlier “df1e729 dirty” report — that work was **committed in `195c5c7`** if it was the same stream; anything still untracked locally (`.jks`, APKs, build logs) must stay **out of git** (secrets/artifacts).

**Rule for next agent:** if you did not create a dirty path, **do not** `git reset --hard` or clean it without operator OK.

---

## What the operator should do

### P0 — OpenObserve / Vector (still open from 2026-07-22)

1. Set `OPENOBSERVE_ROOT_EMAIL` + `OPENOBSERVE_ROOT_PASSWORD` for Vector LaunchAgent  
   (`~/Library/LaunchAgents/com.djbclark.vector.plist` and/or observability.env).
2. Restart Vector (`bootout` / `bootstrap` gui agent).
3. Reingest:

   ```bash
   cd ~/ops/stayturgid
   python3 control/tools/native-agent/reingest_soft_health.py --dry-run
   python3 control/tools/native-agent/reingest_soft_health.py
   ```

4. Confirm OpenObserve stream **`soft_health`** has rows (SQL in OO UI).

Until then: trust **`soft_health.jsonl`** + device **`agent.log`**, not OO.

### P1 — Reconnect fleet devices

```bash
adb connect 100.65.230.108:5555   # p7a
adb connect 100.124.55.39:5555    # hd8 TS
# or USB for hd8
just health
# per host STATUS:
adb -s <serial> shell tail -3 /sdcard/stayturgid/logs/agent.log
```

Confirm agent FGS + UserService after reconnect; redeploy only if missing:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
just agent-rollout p7a
# hd8: just agent-start <serial> after Shizuku is healthy
```

### P2 — Decide staged docs

- Commit or discard the staged **observability-portal-unification** evaluation + related `options.md` edits (separate track from K1).

### P3 — Post–K1 hardening (still valuable even if OPTIONS says “complete”)

Not all Phase 3.5 items are “done just because cutover landed.” Still worth tracking:

| Item                                                 | Why                                                            |
| ---------------------------------------------------- | -------------------------------------------------------------- |
| Release APK / Obtainium / Ansible idempotent install | Day-2 updates without ad-hoc rollout                           |
| Battery unrestricted / unused-app off for agent      | Overnight FGS survival                                         |
| Fire Shizuku official packaging (STORED `.so`)       | Avoid debug-repack stopgap                                     |
| CLOSED_NO_SHELL soak without AutoJs6                 | Trust catastrophic path                                        |
| OO soft_health green for 7+ days                     | Pre-cutover/post-cutover evidence                              |
| hd8 AutoJs6 residual errors                          | Health noise; AJ6 may still be partially present or logs stale |

If AutoJs6 was **uninstalled** fleet-wide in `195c5c7` ops, verify on each device (`pm path org.autojs.autojs6`). If still installed on a host, document dual-run exception.

---

## What the next agent should do

1. Read this handoff + `195c5c7` full diff.
2. **Do not** mix F1 MCP work with K1 cleanups unless operator asks.
3. Prefer **verify live fleet + OO** over rewriting agent architecture.
4. Only touch staged observability docs if that is the assigned task.
5. If continuing agent product work: prefer **harden + soak evidence** over more features.
6. Multi-agent: `git fetch && git pull --ff-only`; leave foreign dirty files alone.

### Suggested next tasks (pick one)

| Priority | Task                                                            |
| -------- | --------------------------------------------------------------- |
| A        | Operator OO password + reingest (blocks log SQL)                |
| B        | Bring p7a/hd8 online; verify agent STATUS + soft_health samples |
| C        | Confirm AutoJs6 gone (or intentional residual) on all hosts     |
| D        | Release/Obtainium/Ansible day-2 path                            |
| E        | Fire Shizuku packaging fix in `~/src/Shizuku`                   |

---

## Commands cheat sheet

```bash
cd ~/ops/stayturgid && git pull --ff-only origin master
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home

just agent-assemble
just agent-rollout
just agent-start <serial>

tail -f ~/.config/stayturgid/stats/soft_health.jsonl
tail -f ~/.config/stayturgid/logs/fleet-health.log
python3 control/tools/native-agent/reingest_soft_health.py

# after Vector template edits:
just site-sync --dir ~/ops/site-djbclark --mode apply --force-generated=1
# restart Vector launchd agent
```

---

## Explicit non-goals unless asked

- Re-opening full AutoJs6 as default watchdog
- Force-push / reset of foreign worktrees
- Claiming K1 “ops complete” while OO 401 and half the fleet offline

---

## Handoff checklist (this writer)

- [x] Documented committed K1 cutover (`195c5c7`) vs current HEAD
- [x] Documented live s24 vs offline p7a/hd8
- [x] Documented OO/Vector 401 + reingest
- [x] Documented staged non-K1 docs (leave alone)
- [x] Push this handoff to GitHub
