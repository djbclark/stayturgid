# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, present the open items **with descriptions and risk**, do any requested work,
> then **replace** this list (drop completed items; keep IDs stable). **Commit and
> push** in the same turn.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [HANDOFF.md](HANDOFF.md).
> Strategic directions: [HANDOFF.md appendix](HANDOFF.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](docs/adr/001-ansible-boundary.md).
> Parked side projects: [docs/incubator/](docs/incubator/) — **do not implement**
> unless the operator unparks a named project (Inferno, etc.).

**Fleet snapshot (2026-07-09):** Post-UI SSH-first on s24/p7a with Mac adb
fallback; hd8 Handsets via **peer bootstrap** (s24/p7a ADB) or Mac.
Play **H1** + **15b** done — `source: play` ensure_apps canary (metronome)
on s24 only. Item **46** drawer **PASS** on **s24 + hd8 + p7a**. **57**
Handsets + Fire peer path + Aurora/Obtainium Termux twins shipped. Operator
**H2** eyeball (Neo Store / Aurora) remains.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Suggested agent order:** human **H2** confirm (Neo Store / Aurora). Do not
touch incubator (Inferno) or start **54** unless asked.

---

## Pick a track

| Track | Focus | Open IDs | Typical risk |
|-------|-------|----------|--------------|
| **A — Operational** | Live deploy, human unblockers | H2, H5, 38 | Medium–High (live phones / publish) |
| **B — Ansible-native** | *(Portfolio 2 core shipped — 48–52 closed)* | — | — |
| **D — Reliability** | Symptom-driven hardening | 43–45 | Latent until triggered |
| **E — On-device LLM** | shell-gpt escalation; incubator note | 54 | Medium (mis-scope risk) |

Parked (not a track): Inferno/Styx → [docs/incubator/inferno-styx/](docs/incubator/inferno-styx/).

---

### Track A — Operational

#### H2 — Neo Store + Aurora one-time confirm (human) · Risk: **Low**

Per-host UI check after deploy: Neo Store installer = Shizuku + background
updates; Aurora installer = Shizuku + auto-updates; no stuck Fire OS background
dialog on hd8. Mostly already automated; this is operator eyeball confirmation.
Does not change code.

#### H3 — Fleet deploy go/no-go · **DONE** (2026-07-09, partial→complete)

Operator approved expand; s24/hd8 green earlier; **p7a** AutoJs6 drawer
finished 2026-07-09 (Handsets port 9010, probe `operational=true`). Checkpoint
`human/CHECKPOINT-p7a-autojs6.md` closed.

#### H5 — Galaxy publish API token (human, optional) · Risk: **Medium**

Ansible Galaxy token for publishing collections. Optional prestige/distribution;
fleet does not depend on it day-to-day. Unlocks agent item **38**.

#### 38 — Galaxy publish all collections (agent) · Risk: **High** · Blocker: **H5**

Publish `stayturgid.*` collections to Ansible Galaxy. Public/irreversible for
that version; only after H5 and a deliberate version bump review.

#### 57 — Handsets UI driver · **DONE** (2026-07-09)

Mac: `shared/mac/ui_driver.py` primary for AutoJs6 / Aurora / Obtainium.
Termux: `stayturgid_handsets.py` wire client — s24 bench ~12× vs dump;
`enable_autojs6` / `configure_aurora` / `import_catalog` Handsets-primary
(probe OK on s24). Fire OS: peer bootstrap
(`stayturgid_peer_bootstrap` → `stayturgid_peer_help` + shared
`adbkey-fleet`); rish installed by default. Bench/research:
[handsets-vs-u2-bench.md](docs/research/handsets-vs-u2-bench.md),
[handsets-under-termux.md](docs/research/handsets-under-termux.md),
[fire-os-local-adb.md](docs/research/fire-os-local-adb.md).
Ports Mac 9008–9010 / Termux 9012 (hd8 peer port 9008). Never with uiautomator2.

---

### Track D — Reliability (do not start without a symptom)

Mac **soft health** (2026-07-09): dedicated launchd
`com.stayturgid.fleet-health` → `mac/fleet_health_monitor.py` logs
watchdog/repair/a11y/sshd/bootloop/shell5555 every 5 min when reachable
(`~/.config/stayturgid/logs/fleet-health.log`). Reachability stays in
`access-monitor`. Use the health trail before picking 43–45.

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

**Closed (2026-07-09):** **15b** `source: play` ensure_apps (metronome on s24;
split APK `install-multiple`; `deploy_fleet` loads `play.env`). **H1** Play AAS.
**56** post-UI Mac adb fallback. **46** AutoJs6 drawer. **55** on-device post-UI.
**27** s24 live deploy. Portfolio 2 — **48–52**, **53**. Handsets Termux twins
(Aurora + Obtainium catalog).
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
