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
> On-device LLM research: [docs/research/on-device-llm.md](docs/research/on-device-llm.md).

**Fleet snapshot (2026-07-09):** Post-UI SSH-first on s24/p7a with Mac adb
fallback; hd8 Mac adb only. Play **H1** + **15b** done — `source: play`
ensure_apps canary (metronome) on s24 only. Item **46** drawer **PASS** on
**s24 + hd8 + p7a** (probe `operational=true`). **57** Handsets UI driver
piloted on all three hosts. H3 fleet expand largely landed — operator
**H2** eyeball (Neo Store / Aurora) remains.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Suggested agent order:** human **H2** confirm (Neo Store / Aurora).
Consider **54** only as a deliberate future spike.

---

## Pick a track

| Track | Focus | Open IDs | Typical risk |
|-------|-------|----------|--------------|
| **A — Operational** | Live deploy, human unblockers | H2, H5, 38 | Medium–High (live phones / publish) |
| **B — Ansible-native** | *(Portfolio 2 core shipped — 48–52 closed)* | — | — |
| **D — Reliability** | Symptom-driven hardening | 43–45 | Latent until triggered |
| **E — On-device LLM** | shell-gpt escalation; not hot-path | 54 | Medium (new attack surface if mis-scoped) |

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

`shared/mac/ui_driver.py` is the **primary Mac** UI path for AutoJs6, Aurora,
Obtainium import, and Obtainium Shizuku installer. Bench vs u2/raw:
[docs/research/handsets-vs-u2-bench.md](docs/research/handsets-vs-u2-bench.md)
(Handsets 17–42× faster hierarchy; Fire Settings 5/5 vs raw 0/5). Raw dump
fallback + Termux on-device dump unchanged. Ports: s24 9009 / hd8 9008 /
p7a 9010. Never concurrent with uiautomator2.

---

### Track D — Reliability (do not start without a symptom)

#### 43 — AutoJs6 WorkManager (agent) · Risk: **Latent / Low until upstream**

Adopt WorkManager-based scheduling when AutoJs6 upstream ships it. Idle until
upstream; implementing early would fight the current watchdog model.

#### 44 — Tasker kicker on p7a (agent) · Risk: **Latent / Medium** · Trigger: soak stalls

Only if p7a soak shows AutoJs6/watchdog stalls. Reintroduces a Tasker nudge
path we otherwise removed — keep narrow and host-scoped.

#### 45 — Termux `sshd -D` if freeze returns (agent) · Risk: **Latent / Medium** · Trigger: sshd freeze

If sshd freezes again under OpenSSH/Termux, try foreground `-D` / supervision
tweaks. Wrong change can lock out SSH; only with a reproduced freeze and a
recovery plan (USB adb / reboot).

---

### Track E — On-device LLM (future; always surface when asked for options)

#### 54 — shell-gpt escalation spike (agent) · Risk: **Medium**

Spike only: after deterministic `stayturgid-repair` fails, optionally ask
shell-gpt for allowlisted shell advice. Consent still required for any `input`.
**Not** in the 5-min repair hot path; AutoJs6 catastrophic path stays mandatory
when 5555 is dead. Research:
[docs/research/on-device-llm.md](docs/research/on-device-llm.md).

- Prefer **shell-gpt**; skip **aider-chat** (wrong job + aarch64 pain).
- Local 1.5B–3B = bounded advisor only; cloud API for quality escalation.
- Mis-scoping (LLM owns heal/GUI, or always-on Ollama in Termux:Boot) is the
  real risk — keep allowlists and consent hard.

---

**Non-goals:** MDM / root / Play Protect bypass; full Obtainium API; Tasker
rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal; always-on Ollama
in Termux:Boot.

**Closed (2026-07-09):** **15b** `source: play` ensure_apps (metronome on s24;
split APK `install-multiple`; `deploy_fleet` loads `play.env`). **H1** Play AAS.
**56** post-UI Mac adb fallback. **46** AutoJs6 drawer. **55** on-device post-UI.
**27** s24 live deploy. Portfolio 2 — **48–52**, **53**.
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
