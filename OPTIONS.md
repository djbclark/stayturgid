# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** HEAD `ab05d4b`. Termux + AutoJs6 deployed all hosts;
watchdog nudged s24+p7a. **s24**/**p7a**/**hd8** SSH + adb online. **hd8** 16/16
verify; s24/p7a watchdog fresh after nudge.

**Suggested agent order:** none without human input. **H3** for full
`./mac/deploy_fleet.py` (Obtainium import + Aurora post-steps).

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

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token.

**Closed (2026-07-08):** PiP fix (skip blind AutoJs6 `am start` when watchdog fresh);
termux deploy s24+p7a+hd8 @ `ab05d4b`; 42 tailscale-down p7a; wireless-debug
auto-repair; boot-launcher stale restart; adb_resolve mDNS; 15/18/31–37/40–41.
