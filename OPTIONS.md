# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** HEAD `2c38237`. Option B deployed **s24** + **p7a**
(termux + autojs6). Boot loop no longer `am start`s AutoJs6 (PiP fix).

**Suggested agent order:** deploy termux+autojs6 fleet-wide, then **H3** or human
blockers below.

---

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials (`GPLAY_*` or gplaycli) for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time Shizuku installer + auto-updates per host | — |
| H3 | human | Fleet deploy go/no-go — full `./mac/deploy_fleet.py` (not just Termux) | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15b | agent | Add `source: play` entries to `stayturgid_ensure_apps` after H1 | **H1** |
| 27 | agent | `./mac/deploy_fleet.py` all hosts | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 43 | agent | Probe AutoJs6 native timed tasks (WorkManager/AlarmManager) when upstream ships — replace `setInterval` heartbeat | upstream |
| 44 | agent | Evaluate minimal Tasker kicker on **p7a only** if AutoJs6 still stalls after H4 + Option B deploy | **H4**, fleet soak |
| 45 | agent | Termux `sshd -D` foreground pattern per Termux #4657 if sshd freeze reports return | symptom |

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token; rebuilding stayturgid logic inside Tasker.

**Closed (2026-07-08):** AutoJs6 Shizuku drawer automation (`enable_autojs6_shizuku.py`);
Option B termux-primary; `stayturgid_autojs6_guard.py`; AutoJs6 `shizuku()` shell wrapper;
42/15/18/31–37/40–41 prior.
