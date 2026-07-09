# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions: [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](docs/adr/001-ansible-boundary.md).
> On-device LLM research: [docs/research/on-device-llm.md](docs/research/on-device-llm.md).

**Fleet snapshot (2026-07-09):** On-device post-UI + screen-control on s24/p7a;
item **46** AutoJs6 drawer verify **PASS** on s24 (`shizuku operational=true`).
See track **E** whenever options are requested.

**Suggested agent order:** human **H3** fleet expand → **H1** → **15b**. Consider **54** only as a future spike.

---

## Pick a track

| Track | Focus | Open IDs |
|-------|-------|----------|
| **A — Operational** | Live deploy, human unblockers | H1–H3, 15b, 46 |
| **B — Ansible-native** | *(Portfolio 2 core shipped — 48–52 closed)* | — |
| **D — Reliability** | Symptom-driven | 43–45 |
| **E — On-device LLM (future)** | shell-gpt escalation; not hot-path | 54 |

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
| 46 | agent | Fix AutoJs6 drawer verify on s24 (on-device `stayturgid_enable_autojs6.py`) | unlocked screen |

---

### Track D — Reliability

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| 43 | agent | AutoJs6 WorkManager when upstream ships | upstream |
| 44 | agent | Tasker kicker on p7a if soak shows stalls | fleet soak |
| 45 | agent | Termux `sshd -D` if freeze returns | symptom |

---

### Track E — On-device LLM (future; always consider when asked for options)

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| 54 | agent | Spike shell-gpt escalation after deterministic repair fails (allowlisted cmds; consent for `input`) | research note |

**Research verdict** ([docs/research/on-device-llm.md](docs/research/on-device-llm.md)):

- **shell-gpt** on Termux is the right experiment; **aider-chat** is a poor fit (install pain + wrong job).
- **Local 1.5B–3B** models on s24/p7a are smart enough as a *bounded advisor*, **not** to own self-heal or GUI.
- **Never** put LLM in the 5-min repair hot path; AutoJs6 catastrophic path stays mandatory when 5555 is dead.
- Prefer cloud API for quality escalation; local Ollama only for offline/privacy spikes.

---

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; Tasker rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal; always-on Ollama in Termux:Boot.

**Closed (2026-07-09):** **55** on-device deterministic GUI/self-heal (Termux post-UI + `ScreenControlSession` + PiP clearance; Mac wrappers SSH-invoke; hd8 USB fallback). **27** s24 live deploy. Portfolio 2 — **48–52**, **53**. **Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
