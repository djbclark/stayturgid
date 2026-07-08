# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** `make test` green. **s24** 16/16 verify + tailscale-down
test pass. **hd8** 16/16 verify after USB bootstrap; wireless adb on Tailscale/LAN.
**p7a** adb-unreachable (Tailscale down, LAN flaky).

**Suggested agent order:** **42** when p7a adb returns. Human: **H3** for full fleet deploy.

---

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials (`GPLAY_*` or gplaycli) for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time Shizuku installer + auto-updates per host | — |
| H3 | human | Fleet deploy go/no-go — hd8 USB bootstrap + all-host `./mac/deploy_fleet.py` | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15 | agent | Wire `stayturgid_ensure_apps` in group_vars with a real app list; prove on s24 | H1 for Play-sourced apps |
| 18 | agent | Neo Store repo DB import path if `fdroid_repo_push` intents fail | logcat / device observation |
| 27 | agent | `./mac/deploy_fleet.py` all hosts | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 42 | agent | `./autojs6/mac/test_tailscale_down.py p7a` (second-host regression) | p7a adb reachable (USB or Tailscale) |

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token.

**Closed this session (2026-07-08):** 31 `stayturgid_repair_check` module; 34 M5 Nexus
launcher (already in agent-presence); 35 M10 termux.properties lineinfile (already in
role); 36 L4 generic-profile warning; 37 termux 1.5.0 tag; 40–41 hd8 deploy+verify.
