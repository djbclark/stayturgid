# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions (equal weight): [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).

**Fleet snapshot (2026-07-09):** HEAD `d1f915e`. `termux_ssh_bootstrap` module +
`bootstrap.yml`; deploy preflight auto-bootstrap; SSH mesh 1.7–1.8.

---

## Pick a track (equal weight)

| Track | Focus | Open IDs |
|-------|-------|----------|
| **A — Operational** | Live deploy, human unblockers, fleet soak | H1–H3, 27, 15b, 46 |
| **B — Ansible-native** | `site.yml`, dedupe orchestration, `validate.yml`, modules | 48–52 |
| **C — Hybrid polish** | Keep `deploy_fleet.py`; incremental fixes only | 53–54 |
| **D — Reliability** | Symptom-driven hardening | 43–45 |

Operator can mix tracks (e.g. **A then B**). No track is pre-approved or forbidden.

---

### Track A — Operational

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials (`GPLAY_*` or gplaycli) for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time confirm per host | — |
| H3 | human | Fleet deploy go/no-go — full `./mac/deploy_fleet.py` (unlock screens) | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15b | agent | Add `source: play` entries to `stayturgid_ensure_apps` after H1 | **H1** |
| 27 | agent | `./mac/deploy_fleet.py` all hosts (validates bootstrap + mesh) | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 46 | agent | E2E `enable_autojs6_shizuku.py` on s24 — Foreground service ON | optional |

**Suggested order:** H3 → 27 → H1 → 15b.

---

### Track B — Ansible-native consolidation

| ID | Who | Item | Effort | Notes |
|----|-----|------|--------|-------|
| 48 | agent | Compose `ansible/playbooks/site.yml` (bootstrap → fleet → post-ui → validate) | M | Single graph; `deploy_fleet.py` → thin wrapper |
| 49 | agent | Remove `harden_fleet_apps.py` post-step; order `app_privileges` in playbook before Aurora | S | Role already in `fleet.yml` |
| 50 | agent | Add `validate.yml` using `stayturgid_repair_check` + SSH/adb smoke tasks | M | Complements `make verify` |
| 51 | agent | Post-UI steps as tagged playbook `script:` tasks (import_catalog, configure_aurora, enable_autojs6) | M | Not new modules — orchestration only |
| 52 | agent | ADR: 80/20 Ansible boundary + explicit non-goals | S | Locks scope for future agents |

**Suggested order:** 49 → 48 → 51 → 50 → 52. Can start 49 without H3.

---

### Track C — Hybrid polish (minimal Ansible growth)

| ID | Who | Item | Notes |
|----|-----|------|-------|
| 53 | agent | Update `adoption.md` bootstrap section (`termux_ssh_bootstrap`, not ssh-copy-id) | Docs only |
| 54 | agent | Inventory var for `stayturgid_ssh_public_key_files` documented in HACKING | Operator ergonomics |

Defer 48–52 unless operator picks track B.

---

### Track D — Reliability (symptom-driven)

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| 43 | agent | Probe AutoJs6 WorkManager/AlarmManager when upstream ships | upstream |
| 44 | agent | Tasker kicker on p7a only if AutoJs6 stalls after soak | fleet soak |
| 45 | agent | Termux `sshd -D` foreground if sshd freeze returns | symptom |

---

**Non-goals (all tracks):** MDM / root / Play Protect bypass; full Obtainium API;
rebuilding stayturgid logic inside Tasker; self-built AutoJs6 debug APK (see #553).

**Closed (2026-07-09):** `termux_ssh_bootstrap` module + `bootstrap.yml` + deploy
preflight; SSH mesh 1.7–1.8. **Closed (2026-07-08):** drawer defaults, a11y tooling,
PiP clearance, Aurora background + deploy order, AutoJs6 #553 filed.
