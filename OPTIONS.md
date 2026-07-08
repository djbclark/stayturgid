# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** HEAD `42c5859`. Drawer defaults, a11y backup/restore,
PiP clearance, Aurora background pre-grant, deploy order fix landed.

**Suggested agent order:** human **H3** deploy approval → **27** full fleet deploy → **H1** if play E2E needed.

---

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials (`GPLAY_*` or gplaycli) for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time confirm (Shizuku installer + auto-updates) per host | — |
| H3 | human | Fleet deploy go/no-go — full `./mac/deploy_fleet.py` (unlock screens for UI steps) | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15b | agent | Add `source: play` entries to `stayturgid_ensure_apps` after H1 | **H1** |
| 27 | agent | `./mac/deploy_fleet.py` all hosts | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 43 | agent | Probe AutoJs6 native timed tasks (WorkManager/AlarmManager) when upstream ships — replace `setInterval` heartbeat | upstream |
| 44 | agent | Evaluate minimal Tasker kicker on **p7a only** if AutoJs6 still stalls after fleet soak | fleet soak |
| 45 | agent | Termux `sshd -D` foreground pattern per Termux #4657 if sshd freeze reports return | symptom |
| 46 | agent | E2E `enable_autojs6_shizuku.py` on s24 with screen unlocked — confirm Foreground service ON | optional |

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token; rebuilding stayturgid logic inside Tasker; self-built
AutoJs6 debug APK for prefs (see AutoJs6 #553).

**Closed (2026-07-08):** AutoJs6 drawer defaults + enable flow; a11y merge/backup tooling;
PiP clearance; Aurora background dialog + deploy order; AutoJs6 #553 filed; p7a a11y restore;
Option B termux-primary; `stayturgid_autojs6_guard.py`; Shizuku drawer automation; prior 42/15/18/31–37/40–41.
