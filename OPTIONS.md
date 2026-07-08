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
