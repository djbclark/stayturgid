# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, present the open items **with descriptions and risk**, do any requested work,
> then **replace** this list (drop completed items; keep IDs stable). **Commit and
> push** in the same turn.
>
> **Fleet health (mandatory):** at session start run
> `make health` (or `python3 mac/check_fleet_health.py`). If exit ≠ 0, **tell the operator** the
> host/`issues=` tags in your first reply — do not wait to be asked. Details:
> [HANDOFF.md § Mac fleet health](HANDOFF.md#mac-fleet-health--mandatory-for-agents).
>
> **Health fix → self-heal (mandatory):** when you clear a health issue, also
> update Termux / AutoJs6 co-monitor / Mac launchd so that failure mode
> recovers without a manual one-shot next time. Rule:
> `.cursor/rules/fleet-health-self-heal.mdc`.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions: [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](docs/adr/001-ansible-boundary.md),
> [docs/adr/002-ansible-ui-tasks.md](docs/adr/002-ansible-ui-tasks.md).
> Parked side projects: [docs/incubator/](docs/incubator/) — **do not implement**
> unless the operator unparks a named project (Inferno, etc.).

**Fleet snapshot (2026-07-09 night, post Ansible batch):** `make health` → exit 0
(all hosts OK). Neo Store + Aurora **parked** — not in Obtainium catalog, deploy,
gui-audit, or fleet-health. Core stack = Termux + AutoJs6 + Obtainium + Tailscale.
Deploy = `make deploy` → `site.yml` (preflight → fleet → post-ui → validate).
Track B Ansible-native items **closed** (58–61); open menu = H5/38, 43–45, 54.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Suggested agent order:** H5/38 only if Galaxy publish wanted; soft-heal p7a if
soak stalls. Do not touch incubator.

---

## Pick a track

| Track | Focus | Open IDs | Typical risk |
|-------|-------|----------|--------------|
| **A — Operational** | Live deploy, human unblockers | H5, 38 | Medium–High (live phones / publish) |
| **B — Ansible-native** | ADR 002 follow-ups (optional) | — | — |
| **D — Reliability** | Symptom-driven hardening | 43–45 | Latent until triggered |
| **E — On-device LLM** | shell-gpt escalation; incubator note | 54 | Medium (mis-scope risk) |

Parked (not a track): Inferno/Styx → [docs/incubator/inferno-styx/](docs/incubator/inferno-styx/).

---

### Track B — Ansible-native (optional follow-ups)

**Shipped (2026-07-09):** ADR 002 accepted; `android_ui` + `android_a11y_services`
modules; `stayturgid.fleet.post_ui` role; `stayturgid.fleet.validate` role;
`preflight.yml` SSH probe + conditional adb bootstrap in `site.yml`;
`autojs6_project_deploy` module (hd8 full fleet deploy path).

#### ~~60 — Expand Ansible validate + a11y in deploy (agent)~~ · **Closed 2026-07-09**

`stayturgid.fleet.validate` (repair/sshd/a11y asserts + optional a11y drift merge);
`preflight.yml` replaces `deploy_fleet.py` SSH preflight.

#### ~~61 — autojs6_project_deploy module (agent)~~ · **Closed 2026-07-09**

`stayturgid.android_common.autojs6_project_deploy` + shared util; wired in
`autojs6_watchdog` for Fire adb path; `autojs6/mac/deploy.py` thin wrapper retained.

---

### Track A — Operational

#### H5 — Galaxy publish API token (human, optional) · Risk: **Medium**

Ansible Galaxy token for publishing collections. Optional prestige/distribution;
fleet does not depend on it day-to-day. Unlocks agent item **38**.

#### 38 — Galaxy publish all collections (agent) · Risk: **High** · Blocker: **H5**

Publish `stayturgid.*` collections to Ansible Galaxy. Public/irreversible for
that version; only after H5 and a deliberate version bump review.

---

### Track D — Reliability (do not start without a symptom)

Mac **soft health**: launchd `com.stayturgid.fleet-health` →
`mac/fleet_health_monitor.py` every 5 min (`~/.config/stayturgid/logs/fleet-health.log`).
Restarts stale AutoJs6 `main.js` when `watchdog_stale`/`watchdog_missing`.
Reachability in `access-monitor`. Prefer health trail before 43–45.

#### 43 — AutoJs6 WorkManager (agent) · Risk: **Latent / Low until upstream**

Adopt WorkManager-based scheduling when AutoJs6 upstream ships it. Idle until
upstream; implementing early would fight the current watchdog model.

#### 44 — Tasker kicker on p7a (agent) · Risk: **Latent / Medium** · Trigger: soak stalls

Only if Mac health / soak shows AutoJs6/watchdog stalls. Reintroduces a Tasker
nudge path we otherwise removed — keep narrow and host-scoped.

#### 45 — Termux `sshd -D` if freeze returns (agent) · Risk: **Latent / Medium** · Trigger: sshd freeze

If sshd freezes again (TCP up but `ssh_echo` fails in health log), try
foreground `-D` / supervision. Wrong change can lock out SSH; only with a
reproduced freeze and USB adb recovery.

---

### Track E — On-device LLM (future; only if deliberately picked)

#### 54 — shell-gpt escalation spike (agent) · Risk: **Medium**

Spike only: after deterministic `stayturgid-repair` fails, optionally ask
shell-gpt for allowlisted shell advice. Consent still required for any `input`.
**Not** in the 5-min repair hot path; AutoJs6 catastrophic path stays mandatory
when 5555 is dead. Note (incubator):
[docs/incubator/on-device-llm.md](docs/incubator/on-device-llm.md).

- Prefer **shell-gpt**; skip **aider-chat** (wrong job + aarch64 pain).
- Local 1.5B–3B = bounded advisor only; cloud API for quality escalation.
- Mis-scoping (LLM owns heal/GUI, or always-on Ollama in Termux:Boot) is the
  real risk — keep allowlists and consent hard.

---

**Non-goals / do-not-touch:** MDM / root / Play Protect bypass; full Obtainium
API; Tasker rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal;
always-on Ollama in Termux:Boot; **any Inferno/`emu`/Styx work** (parked under
[docs/incubator/inferno-styx/](docs/incubator/inferno-styx/)).

**Closed (2026-07-09 night):** **60–61** validate role + preflight + `autojs6_project_deploy`;
`make help`/Makefile ops; `make health` stale LOST fix; docs sweep. **58–59** ADR 002 +
`android_ui` / `post_ui` / `android_a11y_services`. Neo/Aurora parked.
**Closed (2026-07-09 evening):** Aurora CPU thrash policy documented; screen-control hold rule.
**Closed (2026-07-09):** **15b**, **H1**, **H3**, **56**, **46**, **55**, **27**,
**57**, Portfolio 2 **48–52**/53, co-monitor + Mac AutoJs6 heal, Fire F1–F5,
self-heal agent rule.
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
