# OPTIONS — next work menu

> **For agents:** When the operator asks for **options**, **next steps**, or a **menu**:
> 1. Read this file (latest section is usually current).
> 2. **Append** a new dated section with an updated menu (mark done/superseded items; don't delete history). Use **date and time** in the heading, e.g. `## 2026-07-07 20:19 UTC-4 — …`.
> 3. **Commit and push** to `master` in the same turn.
>
> Human-only tasks stay in [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md).
> Operator answers go in `human/RESPONSES.md` (gitignored).

---

## 2026-07-07 20:19 UTC-4 — Post shell→Python migration & fleet integration

Context: Bourne-shell Mac deploy/orchestration removed; `deploy_fleet.py` is canonical.
F-Droid + Play integrated in `fleet.yml`. Preferred test host: **s24** → **hd8** → **p7a**.

### Needs you first (`human/HANDOFF-HUMAN.md`)

| ID | Item | Why |
|----|------|-----|
| H1 | Play credentials (`GPLAY_*` or gplaycli) | E2E `play_store` / `ensure_apps` with `source: play` |
| H2 | Neo/Aurora one-time Shizuku + auto-update per host | App-store roles assume on-device clients configured |
| H3 | Fleet deploy go/no-go (`deploy_fleet: approved \| s24-only \| …`) | Full `./mac/deploy_fleet.py` on all hosts |
| H4 | p7a optional cleanup (AutoJs6 a11y, mirror pin) | 14/16 verify; lab work prefers s24 |
| H5 | Galaxy publish token (optional) | Public Galaxy; Git tags already work |

### Validation & fleet health (agent-only; start on **s24**)

| ID | Item | Outcome |
|----|------|---------|
| 1 | Live `./mac/deploy_fleet.py s24` (not just `CHECK=1`) | End-to-end phased deploy on lab phone |
| 2 | `make verify HOSTS=s24` (+ hd8) | Confirm integrated fdroid/play didn't regress |
| 3 | `./autojs6/mac/test_tailscale_down.py s24` | Tailscale-down regression test |
| 4 | Investigate p7a “Termux mirror pinned” verify fail | Role vs host state; fix or document |

Related quick fix: **14** (`test-tailscale-down-once.js` `sleep(2)` → `sleep(2000)`).

### Cleanup & consolidation (agent-only)

| ID | Item | Outcome |
|----|------|---------|
| 5 | Remove legacy bash libs + add `resolve_adb.py` CLI | Drop `resolve-adb.sh` / `stayturgid-root.sh` duplicates |
| 6 | Deduplicate `stayturgid_device.resolve_adb` vs Ansible `adb_resolve.py` | Single tested implementation |
| 7 | Refresh stale docs + bump `version.json` | Match post-integrate reality (HANDOFF gap table, etc.) |
| 8 | Release tags `stayturgid.*-1.6.0` fleet-wide | Consumer pin hygiene |

### CODE-REVIEW fixes (agent-only; by severity)

| ID | Item | Notes |
|----|------|--------|
| 9 | **M11** Shizuku JSON clobber on transient read failure | Grants across fdroid/play/autojs6 |
| 10 | **M1–M3** Battery alarm (wallpaper, tier cascade, `set -e`) | User-visible on daily drivers |
| 11 | **M5** Pixel idle detection in agent-presence | p7a home screen counts as “in use” |
| 12 | **M10** Termux properties reload after Ansible | May tie to mirror-pin verify |
| 13 | **L4** AutoJs6 `device=generic` when profile missing | Wrong tap coords on unknown hardware |
| 14 | **L6** `test-tailscale-down-once.js` sleep units | One-line JS fix |

### Features & automation (mostly agent; some need unlocked screen)

| ID | Item | Outcome |
|----|------|---------|
| 15 | Wire `stayturgid_ensure_apps` in group_vars with real apps | Prove unified ensure on s24 |
| 16 | Better Obtainium import failure reporting in `deploy_fleet.py` | Clear mid-deploy failures |
| 17 | `stayturgid_repair_check` module (SSH → parse STATUS) | Less fragile verify shell |
| 18 | Neo Store repo DB import if intents fail | Needs logcat observation (H4.2) |
| 19 | Convert `gplaycli.sh` to Python launcher | Last Mac shell except tests + on-device |

### Release & CI (agent-only unless Galaxy)

| ID | Item | Outcome |
|----|------|---------|
| 20 | Push git tags + verify `collection-build` workflow | Tested consumer releases |
| 21 | Galaxy publish all collections (after **H5**) | External discoverability |
| 22 | CI tests for `deploy_fleet.py` / `adb_cli` (mocked) | Orchestrator regression guard |

### Explicit non-goals

- MDM / root / Play Protect bypass
- Full Obtainium API (doesn't exist)
- Large Ansible refactor without explicit operator approval — see [HANDOFF.md appendix “Architecture research: unified orchestration”](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved) (research only; hybrid Mac Python + partial Ansible is production)
- Galaxy publish without token

### Suggested agent order (no human input)

**7** → **1–2** → **14** → **3** → **9** → **5–6**

Tell the agent: option IDs (e.g. `do 7, 1, 2, 14, 9`) or `read human/RESPONSES.md` for H-items.

---

## 2026-07-07 21:30 UTC-4 — After s24 deploy, mirror-pin, and Tailscale-down fixes

Context since last menu: the agent-only batch from the 20:19/20:22 menus is
complete on **s24**. `make test` is green, live `./mac/deploy_fleet.py s24`
succeeded, `make verify HOSTS=s24` is **16/16 PASS**, and
`./autojs6/mac/test_tailscale_down.py s24` passes after the one-shot AutoJs6
probe was shortened and the Mac driver learned to use any online ADB endpoint.
Termux mirror pinning is now re-applied after `pkg update` rewrites
`sources.list`.

### Needs you first (`human/HANDOFF-HUMAN.md`)

| ID | Item | Why |
|----|------|-----|
| H1 | Play credentials (`GPLAY_*` or gplaycli) | E2E `play_store` / `ensure_apps` with `source: play` |
| H2 | Neo/Aurora one-time Shizuku + auto-update per host | App-store roles assume on-device clients configured |
| H3 | Fleet deploy go/no-go beyond s24 (`all`, `hd8`, `p7a`, or hold) | s24 is healthy; broader rollout still needs operator intent |
| H4 | p7a optional cleanup window | p7a historically had mirror/a11y drift; decide whether to spend lab time there |
| H5 | Galaxy publish token (optional) | Public Galaxy publishing; git tags already work without it |

### Validation & rollout (agent-only unless screen unlock is needed)

| ID | Item | Outcome |
|----|------|---------|
| 23 | Run `make verify HOSTS=hd8` | Confirm second device after s24 stabilization |
| 24 | Run `make verify HOSTS=p7a` and triage remaining drift | Decide whether p7a is healthy or needs targeted cleanup |
| 25 | `./mac/deploy_fleet.py hd8` then `make verify HOSTS=hd8` | Extend successful s24 path to tablet |
| 26 | `./mac/deploy_fleet.py p7a` then `make verify HOSTS=p7a` | Extend only if p7a is reachable and approved |
| 27 | `./mac/deploy_fleet.py` all hosts after H3 approval | Fleet-wide convergence pass |

### Cleanup & consolidation (agent-only)

| ID | Item | Outcome |
|----|------|---------|
| 28 | Mocked tests for `autojs6/mac/test_tailscale_down.py` endpoint resolution | Guard the LAN/Tailscale/USB fallback that fixed the live regression |
| 29 | Add focused tests for `autojs6/lib/log.js` log-directory behavior if JS harness exists | Prevent `ensureDir(filePath)` regression |
| 30 | Convert `gplaycli.sh` to a Python launcher | Last Mac shell outside test/on-device boundaries |
| 31 | `stayturgid_repair_check` module (SSH -> parse STATUS) | Less fragile verify shell snippets |
| 32 | Better Obtainium import failure reporting in `deploy_fleet.py` | Clearer mid-deploy errors |

### CODE-REVIEW fixes still open

| ID | Item | Notes |
|----|------|-------|
| 33 | **M1-M3** Battery alarm wallpaper/tier/`set -e` fixes | User-visible on daily drivers |
| 34 | **M5** Pixel idle detection in agent-presence | p7a home screen can count as "in use" |
| 35 | **M10** Termux properties reload after Ansible | Still worth checking even though s24 mirror-pin is fixed |
| 36 | **L4** AutoJs6 `device=generic` when profile missing | Wrong tap coords on unknown hardware |

### Release & CI

| ID | Item | Outcome |
|----|------|---------|
| 37 | Push collection git tags + verify `collection-build` workflow | Tested consumer releases |
| 38 | Galaxy publish all collections after **H5** | External discoverability |
| 39 | Add CI coverage for `deploy_fleet.py` / `adb_cli` mocked flows | Orchestrator regression guard |

### Suggested agent order (no human input)

**23** -> **25** -> **24** (if p7a reachable) -> **28** -> **32** -> **30**

Highest-leverage human unlock remains **H3**: decide whether the next live
fleet step is `hd8`, `p7a`, or all hosts.

---

## 2026-07-07 21:50 UTC-4 — After hd8/p7a rollout + code consolidation batch

Context since last menu: agent ran suggested order **23 → 25 → 24 → 28 → 32 → 30**.
**p7a** is now **16/16 PASS** after `deploy_fleet.py p7a` + `start_watchdog.py p7a`.
**hd8** termux stack converged (mirror pin + script drift fixed) but full fleet
deploy still fails at Fire-OS AutoJs6 adb push when USB is unplugged; several
hd8 verify checks remain TODO/FAIL without Mac adb. Code landed: tailscale-down
endpoint resolution tests, `deploy_fleet.py` Obtainium/Aurora failure reporting,
`play/mac/gplaycli.py` launcher (`.sh` is a shim).

### Needs you first (`human/HANDOFF-HUMAN.md`)

| ID | Item | Why |
|----|------|-----|
| H1 | Play credentials (`GPLAY_*` or gplaycli) | E2E `play_store` / `ensure_apps` with `source: play` |
| H2 | Neo/Aurora one-time Shizuku + auto-update per host | Neo Store still missing on p7a; Aurora setup flaky |
| H3 | Fleet deploy go/no-go for **hd8 USB** + all-host rollout | hd8 AutoJs6 deploy needs `GN43T503430603PS` plugged in |
| H4 | p7a optional cleanup window | **Resolved** — p7a verify 16/16 after deploy |
| H5 | Galaxy publish token (optional) | Public Galaxy publishing |

### Validation & rollout (agent-only unless noted)

| ID | Status | Notes |
|----|--------|-------|
| 23 | **done** | hd8 verify baseline: termux healthy; Fire-OS TODOs expected |
| 25 | **partial** | hd8 termux converged; AutoJs6 adb push failed (USB offline) |
| 24 | **done** | p7a verify **16/16 PASS** after deploy + watchdog nudge |
| 26 | **done** (as part of 24) | `deploy_fleet.py p7a` succeeded; Aurora UI step noisy but non-fatal |
| 27 | blocked on **H3** | all-host deploy |
| 40 | **new** | Plug hd8 USB → `./autojs6/mac/deploy.py hd8` + re-run `deploy_fleet.py hd8` tail |

### Cleanup & consolidation

| ID | Status | Notes |
|----|--------|-------|
| 28 | **done** | `tests/python/test_tailscale_down_resolve.py` |
| 30 | **done** | `play/mac/gplaycli.py`; `.sh` shim retained |
| 32 | **done** | `deploy_fleet.py` prints FAIL + stderr per host/step |
| 29 | open | JS harness for `log.js` ensureDir |
| 31 | open | `stayturgid_repair_check` module |

### CODE-REVIEW fixes still open

| ID | Item |
|----|------|
| 33 | **M1–M3** Battery alarm |
| 34 | **M5** Pixel idle detection |
| 35 | **M10** Termux properties reload |
| 36 | **L4** AutoJs6 `device=generic` fallback |

### Release & CI

| ID | Item |
|----|------|
| 37 | Push collection git tags + verify `collection-build` workflow |
| 38 | Galaxy publish (needs **H5**) |
| 39 | CI coverage for `deploy_fleet.py` / `adb_cli` mocked flows |

### Suggested agent order (no human input)

**40** (when hd8 USB available) → **29** → **31** → **33** → **39**

Highest-leverage human unlock: **H3** (hd8 USB for AutoJs6) and **H2** (Neo Store on p7a).

---

## 2026-07-07 22:08 UTC-4 — After adb auto-failover + fleet status check

Context since last menu: **s24** and **p7a** both **16/16 verify PASS**;
**hd8** termux healthy over SSH but still has no reachable Mac adb path
(wireless port 5555 closed; USB unplugged). Shared `adb_device` lookup now
auto-selects online endpoints (USB → LAN → Tailscale, with `adb connect` and
`ro.serialno` drift matching) — committed `e9cf428`. `stayturgid_device` and
Ansible modules share one resolver. `make test` green.

### Needs you first (`human/HANDOFF-HUMAN.md`)

| ID | Item | Why |
|----|------|-----|
| H1 | Play credentials (`GPLAY_*` or gplaycli) | E2E `play_store` / `ensure_apps` with `source: play` |
| H2 | Neo/Aurora one-time Shizuku + auto-update per host | Neo Store missing on p7a; Aurora UI setup flaky |
| H3 | **hd8 USB bootstrap** + all-host deploy go/no-go | Fire OS needs one USB/adb session to open wireless path |
| H5 | Galaxy publish token (optional) | Public Galaxy publishing |

### Fleet health snapshot

| Host | Verify | Notes |
|------|--------|-------|
| s24 | **16/16 PASS** | Lab reference; tailscale-down test passes |
| p7a | **16/16 PASS** | Deployed + watchdog nudged |
| hd8 | **partial** | Termux OK over SSH; Mac adb offline; Fire-OS TODOs expected |

### Validation & rollout (agent-only unless noted)

| ID | Status | Item |
|----|--------|------|
| 40 | **blocked on H3** | Plug hd8 USB → `deploy.py hd8` + finish `deploy_fleet.py hd8` |
| 41 | **new** | Re-verify hd8 after USB bootstrap (expect wireless failover thereafter) |
| 27 | blocked on **H3** | `./mac/deploy_fleet.py` all hosts |
| 42 | **new** | `./autojs6/mac/test_tailscale_down.py` on p7a (second-host regression) |

### Cleanup & consolidation

| ID | Status | Item |
|----|--------|------|
| 6 | **done** | `stayturgid_device` delegates to `adb_resolve.py` (single tested resolver) |
| 29 | open | JS tests for `log.js` ensureDir |
| 31 | open | `stayturgid_repair_check` module (SSH → parse STATUS) |
| 43 | **new** | Ansible unit tests for `adb_resolve` in-collection (pytest parity exists in `tests/python/`) |

### CODE-REVIEW fixes still open

| ID | Item |
|----|------|
| 33 | **M1–M3** Battery alarm wallpaper/tier/`set -e` |
| 34 | **M5** Pixel idle detection in agent-presence |
| 35 | **M10** Termux properties reload after Ansible |
| 36 | **L4** AutoJs6 `device=generic` when profile missing |

### Release & CI

| ID | Item |
|----|------|
| 37 | Push collection git tags + verify `collection-build` workflow |
| 38 | Galaxy publish (needs **H5**) |
| 39 | CI coverage for `deploy_fleet.py` / `adb_cli` mocked flows |

### Suggested agent order (no human input)

**29** → **31** → **33** → **39** → **42**

When hd8 USB is available: **40** → **41** first.

Highest-leverage human unlock: **H3** (one hd8 USB session to bootstrap wireless adb).

---

## 2026-07-07 20:22 UTC-4 — After shell test hardening

Context since last menu: shell unit tests added for boot/bridge scripts
(110 TAP tests + `tests/python/test_shell_libs.py`); quoting/pidfile fixes in
`start-adb.sh`, `repair-bridge.sh`, starters; `resolve_adb` no longer emits
`-:5555` when a device row has no Tailscale IP (bash + Python, tested);
obtainium sync-guard test repointed at the collection role path.
**`make test` fully green** (TAP + pytest + ansible-test). Decision recorded:
keep the TAP sandbox harness; no Bats/shunit2 migration unless shell coverage
grows again.

Menu changes vs 2026-07-07 20:19 (IDs unchanged, H-items unchanged):

| ID | Status update |
|----|---------------|
| 5 | Easier now — legacy bash libs (`resolve-adb.sh`, `stayturgid-root.sh`) have pytest coverage proving Python parity, so removal is low-risk |
| 22 | Partially seeded — shell-lib pytest exists; `deploy_fleet.py`/`adb_cli` mocked tests still open |
| All others | Unchanged; see 20:19 menu above |

### Suggested agent order (no human input)

**7** (docs/version refresh — stale after today's churn) → **14** (one-line JS
sleep fix) → **1–2** (live s24 deploy + verify; needs device reachable) →
**3** → **9** (M11 Shizuku JSON clobber) → **5–6** (remove legacy bash libs,
dedup resolve_adb).

Highest-leverage human unlock remains **H3** (fleet deploy go/no-go).
