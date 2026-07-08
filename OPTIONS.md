# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, do the work, then **replace** this list (drop completed items; keep IDs
> stable for in-flight references). **Commit and push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).

**Fleet snapshot (2026-07-08):** `make test` green at `2d7f142`. **s24** 16/16
verify + tailscale-down test pass. **hd8** termux OK over SSH; Mac adb needs
USB bootstrap for AutoJs6 deploy tail. **p7a** was 16/16 after deploy; currently
adb-unreachable (Tailscale down, LAN flaky).

**Suggested agent order (no human input):** **31** → **34** → **36** → **35** → **37**

When hd8 USB is available: **40** → **41** first. Item **42** when p7a adb returns.

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
| 31 | agent | `stayturgid_repair_check` Ansible module (SSH → parse watchdog STATUS) | — |
| 34 | agent | **M5** Pixel idle detection — add Nexus launcher to agent-presence allowlist | — |
| 35 | agent | **M10** Termux `termux.properties` — `lineinfile` + `termux-reload-settings` handler | — |
| 36 | agent | **L4** AutoJs6 — warn when `device=generic` (missing `device.json`) | — |
| 37 | agent | Push collection git tags + verify `collection-build` GitHub workflow | — |
| 38 | agent | Galaxy publish all collections | **H5** |
| 40 | agent | hd8 USB → `./autojs6/mac/deploy.py hd8` + finish `deploy_fleet.py hd8` tail | **H3** (USB) |
| 41 | agent | `make verify HOSTS=hd8` after USB bootstrap (expect wireless failover) | **40** |
| 42 | agent | `./autojs6/mac/test_tailscale_down.py p7a` (second-host regression) | p7a adb reachable (USB or Tailscale) |

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; large Ansible
refactor without operator approval ([HANDOFF.md appendix](HANDOFF.md#appendix--architecture-research-unified-orchestration-research-only--not-approved));
Galaxy publish without token.
