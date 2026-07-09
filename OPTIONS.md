# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions: [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](docs/adr/001-ansible-boundary.md).

**Fleet snapshot (2026-07-09):** HEAD Portfolio 2 landed — `site.yml`, `post-ui.yml`,
`validate.yml`, thin `deploy_fleet.py`, ADR 001.

**Suggested agent order:** human **H3** → **27** live deploy s24 then fleet → **H1** → **15b**.

---

## Pick a track

| Track | Focus | Open IDs |
|-------|-------|----------|
| **A — Operational** | Live deploy, human unblockers | H1–H3, 27, 15b, 46 |
| **B — Ansible-native** | *(Portfolio 2 core shipped — 48–52 closed)* | — |
| **D — Reliability** | Symptom-driven | 43–45 |

---

### Track A — Operational

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time confirm per host | — |
| H3 | human | Fleet deploy go/no-go — `./mac/deploy_fleet.py` (unlock screens) | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15b | agent | Add `source: play` entries to `stayturgid_ensure_apps` after H1 | **H1** |
| 27 | agent | Live `./mac/deploy_fleet.py` — s24 first, then full fleet | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 46 | agent | E2E AutoJs6 foreground service on s24 | optional |

---

### Track D — Reliability

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| 43 | agent | AutoJs6 WorkManager when upstream ships | upstream |
| 44 | agent | Tasker kicker on p7a if soak shows stalls | fleet soak |
| 45 | agent | Termux `sshd -D` if freeze returns | symptom |

---

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; Tasker rebuild; AutoJs6 debug APK (#553).

**Closed (2026-07-09):** Portfolio 2 — **48–52**, **53** (`adoption.md`); `site.yml` graph;
`termux_ssh_bootstrap`. **Closed (2026-07-08):** drawer, a11y, PiP, Aurora order, #553.
