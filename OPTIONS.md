# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** `make test` green. **s24** 16/16 + tailscale-down +
`ensure_apps` fdroid (metronome). **hd8** 16/16 after USB bootstrap. **p7a**
adb/SSH unreachable.

**Suggested agent order:** **42** when p7a returns. Human: **H3** full fleet deploy.

---

| ID | Who | Item | Blocker |
|----|-----|------|---------|
| H1 | human | Play credentials (`GPLAY_*` or gplaycli) for E2E `play_store` / `ensure_apps` | — |
| H2 | human | Neo Store + Aurora one-time Shizuku installer + auto-updates per host | — |
| H3 | human | Fleet deploy go/no-go — all-host `./mac/deploy_fleet.py` | — |
| H5 | human | Galaxy publish API token (optional) | — |
| 15b | agent | Add `source: play` entries to `stayturgid_ensure_apps` after H1 | **H1** |
| 27 | agent | `./mac/deploy_fleet.py` all hosts | **H3** |
| 38 | agent | Galaxy publish all collections | **H5** |
| 42 | agent | `./autojs6/mac/test_tailscale_down.py p7a` (second-host regression) | p7a adb reachable |

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token.

**Closed (2026-07-08):** 15 fdroid `ensure_apps` (metronome on s24); 18 fdroid client
detect (`>-` YAML fold broke `android_packages` lookup); collection-build CI
`--output-path`; prior session 31–37, 40–41.
