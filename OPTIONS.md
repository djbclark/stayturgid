# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions: [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](docs/adr/001-ansible-boundary.md).

**Fleet snapshot (2026-07-09):** HEAD `598a4dd` — s24 `site.yml` soak done;
`make verify HOSTS=s24` **16/16 PASS**; `validate.yml` green. Post-UI Obtainium +
Aurora OK; `enable_autojs6_shizuku.py` drawer step still fails (a11y+Shizuku up).

**Suggested agent order:** **46** AutoJs6 drawer on s24 → human **H3** fleet expand → **H1** → **15b**.

---

## Pick a track

| Track | Focus | Open IDs |
|-------|-------|----------|
| **A — Operational** | Live deploy, human unblockers | H1–H3, 15b, 46 |
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
| 38 | agent | Galaxy publish all collections | **H5** |
| 46 | agent | Fix `enable_autojs6_shizuku.py` drawer verify on s24 (Shizuku drawer toggle) | unlocked screen |

---

### Track D — Reliability

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| 43 | agent | AutoJs6 WorkManager when upstream ships | upstream |
| 44 | agent | Tasker kicker on p7a if soak shows stalls | fleet soak |
| 45 | agent | Termux `sshd -D` if freeze returns | symptom |

---

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; Tasker rebuild; AutoJs6 debug APK (#553).

**Closed (2026-07-09):** **27** s24 live deploy + verify (`598a4dd` screen_control + device_tier fixes).
Portfolio 2 — **48–52**, **53**; `termux_ssh_bootstrap`. **Closed (2026-07-08):** drawer, a11y, PiP, Aurora order, #553.
