<!-- historical: closed/completed entries moved to docs/archive/options-closed-2026-07-23.md; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# OPTIONS — open work (strategic / deferred tracks)

For discrete bugs and ops follow-ups, see
[GitHub issues](https://github.com/djbclark/stayturgid/issues) — this file is
for longer-running, symptom-triggered, or deliberately-deferred tracks with a
stable ID. Current fleet/workstream state lives in
[docs/STATUS.md](STATUS.md), not here.

> **Sequencing note (2026-07-18):** the platform/segmentation workstream
> (identity scrub, O-V-G-O completion, site contract, edge OTel) is sequenced
> by the **site repo's relay**, not this list — see
> `~/ops/site-djbclark/docs/relay/NEXT-PROMPT.md` there. This list remains the
> menu for fleet-reliability work outside that workstream.
>
> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, present the open items **with descriptions and risk**, do any requested work,
> then **replace** this list (drop completed items; keep IDs stable). **Commit and
> push** in the same turn.
>
> **Operator GUI help:** the operator is available to do **manual GUI steps** on
> devices (Accessibility OFF→ON, open Shizuku, dismiss dialogs, USB plug-in).
> When a GUI action would unblock work you are already doing, **ask them**
> rather than spinning on remote-only recovery.
>
> **Fleet health (mandatory):** at session start run `just health` (or
> `python3 control/bin/check_fleet_health.py`). If exit ≠ 0, **tell the
> operator** the host/`issues=` tags in your first reply. Details:
> [docs/STATUS.md](STATUS.md).
>
> **Health fix → self-heal (mandatory):** when you clear a health issue, also
> update Termux / the native agent / Mac launchd so that failure mode
> recovers without a manual one-shot next time. Rule:
> [docs/rules/fleet-health-self-heal.md](rules/fleet-health-self-heal.md).
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context:
> [docs/STATUS.md](STATUS.md). Coding and completion rules:
> [docs/coding-rules.md](coding-rules.md).
> Ansible boundary: [docs/architecture/adr/001-ansible-boundary.md](architecture/adr/001-ansible-boundary.md),
> [docs/architecture/adr/002-ansible-ui-tasks.md](architecture/adr/002-ansible-ui-tasks.md).
> Self-heal vs Ansible coverage: [docs/architecture/adr/004-self-heal-vs-ansible-coverage.md](architecture/adr/004-self-heal-vs-ansible-coverage.md).
> Parked side projects: [docs/research/experiments/](research/experiments) — **do not implement**
> unless the operator unparks a named project (Inferno, etc.).

**Closed/shipped entry bodies** live in
[docs/archive/options-closed-2026-07-23.md](archive/options-closed-2026-07-23.md) —
this file keeps only a one-line pointer per closed ID so the open-work list
stays scannable. Current fleet/workstream snapshot: [docs/STATUS.md](STATUS.md).

**ID collisions (historical, not fixed to avoid renumbering old records):**
`H5` denotes two different items (open: Galaxy token; closed: pre-commit/typos
tooling). `H1`/`H3` denote two different items (open: fireos-device Python
deploy/Ansible push; closed 2026-07-09: an earlier, unrelated scope in the
trailing ledger). `F1` denotes two different items (open: MCP bridge; closed:
"Fire F1–F5" in the 2026-07-09 ledger). Check the surrounding track/date when
an ID is ambiguous.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Post-K1 note (2026-07-22):** the AutoJs6 watchdog/co-monitor runtime was
retired fleet-wide by the native-agent cutover. Entries below that presuppose
a live AutoJs6 runtime (43, 44, T2's device-test seam) need re-scoping against
the native agent before any work starts — see
[docs/STATUS.md](STATUS.md) for the current, **not yet fully verified**,
cutover state.

---

## Pick a track

| Track                  | Focus                                              | Open IDs       | Typical risk                  |
| ---------------------- | -------------------------------------------------- | -------------- | ----------------------------- |
| **A — Operational**    | Live deploy, human unblockers, current reliability | H1, H3, H5, 38 | Low–High                      |
| **B — Ansible-native** | Bootstrap APK automation follow-ups                | B63, B64       | Low–Medium                    |
| **D — Reliability**    | Symptom-driven hardening (needs post-K1 re-scope)  | 43, 44, 45     | Latent until triggered        |
| **E — On-device LLM**  | shell-gpt escalation; incubator note               | 54             | Medium (mis-scope risk)       |
| **F — FIRERPA**        | gRPC backup channel enhancements                   | F1, F3         | Medium (future, core is done) |
| **H — Post-migration** | fireos-device deploy, foreground-screen cleanup    | H1, H3, H9     | Low–Medium                    |
| **T — Tooling**        | Deferred evaluations                               | T2, T4, T5     | Low–Medium                    |

Parked (not a track): Inferno/Styx → [docs/research/experiments/inferno-styx/](research/experiments/inferno-styx).

---

### Track B — Ansible-native (optional follow-ups)

**Closed:** 60, 61, 62 — see [archive](archive/options-closed-2026-07-23.md#track-b--ansible-native).

#### B63 — shizuku_start native launch path on real device (agent) · Risk: **Low** · Needs: device with Shizuku stopped

Test the `shizuku_start` module's `libshizuku.so` native launch path on a live
device. The module is idempotent (tested on oneui-device — already_up path OK). The
native fallback mirrors `fire_peer_help.py:155-182` but has never been exercised
in the Ansible module context. Requires stopping Shizuku first (disrupts services).
Best done during cold-device end-to-end (B64) or with an idle device.

#### B64 — Full cold-device end-to-end (agent) · Risk: **Medium** · Needs: virgin device

Run `just deploy --limit <new_device>` from a device with only USB debugging
enabled. Validates the entire bootstrap chain: APK install → Termux:Boot
launch → Shizuku start → SSH bootstrap → fleet deploy. This is the only way
to test all links in the chain together. Prefer a factory-reset device or one
not in active fleet use.

---

### Track A — Operational

#### H5 — Galaxy publish API token (human, optional) · Risk: **Medium**

Ansible Galaxy token for publishing collections. Optional prestige/distribution;
fleet does not depend on it day-to-day. Unlocks agent item **38**.

#### 38 — Galaxy publish all collections (agent) · Risk: **High** · Blocker: **H5**

Publish `stayturgid.*` collections to Ansible Galaxy. Public/irreversible for
that version; only after H5 and a deliberate version bump review.

**Done:** H14 — see [archive](archive/options-closed-2026-07-23.md#track-a--operational).

---

### Track D — Reliability (do not start without a symptom)

Mac soft health: launchd `com.stayturgid.fleet-health` →
`control/bin/fleet_health_monitor.py` every 5 min
(`~/.config/stayturgid/logs/fleet-health.log`). Post-K1, this restarts the
**native agent** (`agent_stale`/`agent_missing`), not AutoJs6. Reachability in
`access-monitor`. Prefer health trail before 43–45.

**Merged:** A11 — see [archive](archive/options-closed-2026-07-23.md#track-d--reliability).

#### 43 — AutoJs6 WorkManager (agent) · Risk: **Latent** · Needs re-scope

Presupposes a live AutoJs6 runtime, which the K1 cutover retired fleet-wide
(2026-07-22). Likely moot; re-scope against the native agent's own scheduling
model before picking this up, or close as superseded.

#### 44 — Tasker kicker on stock-android-device (agent) · Risk: **Latent** · Needs re-scope

Same caveat as 43 — was scoped against AutoJs6/watchdog stalls, which no
longer exist post-K1. Re-scope against native-agent stalls if the symptom
recurs, otherwise close as superseded.

#### 45 — Termux `sshd -D` if freeze returns (agent) · Risk: **Latent / Medium** · Trigger: sshd freeze

If sshd freezes again (TCP up but `ssh_echo` fails in health log), try
foreground `-D` / supervision. Wrong change can lock out SSH; only with a
reproduced freeze and USB adb recovery.

#### K1 — AutoJs6 → native Kotlin APK (agent) · **Cutover landed 2026-07-22, verification incomplete**

Replaced the Rhino/AutoJs6 watchdog with a purpose-built Kotlin app that binds
a Shizuku **UserService** (UID 2000). Plan:
[AutoJs6 → native Kotlin APK migration plan](archive/plans/autojs6-to-native-apk-plan.md).

**Code:** `device/native-agent/` deployed on s24 + p7a + hd8. Fleet health now
uses `agent_stale`/`agent_missing`, and the `autojs6_watchdog` Ansible role
was retired (195c5c7).

**2026-07-25 correction:** the "AutoJs6 uninstalled" claim above was false —
live-checked all three devices and found AutoJs6 still installed on s24,
p7a, and hd8. Uninstalled for real fleet-wide same day; confirmed via
`pm path` on all three. Reboot-based `CLOSED_NO_SHELL` soak attempts on
s24/p7a found a real bug instead: `HostService`'s first post-boot comonitor
check races Shizuku's binder connection on a fixed 2s delay and silently
loses (confirmed via live logcat), then doesn't retry for 20 minutes — a
window with **no `CLOSED_NO_SHELL` detection at all**. Needs a code fix +
rebuild + redeploy; not done yet. The soak itself still hasn't succeeded —
can't be trusted to mean anything until this is fixed. Full writeup:
[operations/sessions/session-2026-07-25-k1-verification.md](operations/sessions/session-2026-07-25-k1-verification.md).
See also [docs/STATUS.md](STATUS.md) and
[operations/sessions/handoff-2026-07-23-native-agent-k1.md](operations/sessions/handoff-2026-07-23-native-agent-k1.md).
Tracked as [#43](https://github.com/djbclark/stayturgid/issues/43) (fleet-state
verification) and [#45](https://github.com/djbclark/stayturgid/issues/45)
(release APK, forced soak, official Shizuku packaging).

---

### Track E — On-device LLM (future; only if deliberately picked)

#### 54 — shell-gpt escalation spike (agent) · Risk: **Medium** · Needs re-scope

Spike only: after deterministic `stayturgid-repair` fails, optionally ask
shell-gpt for allowlisted shell advice. Consent still required for any `input`.
**Not** in the 5-min repair hot path. The original text pinned "AutoJs6
catastrophic path stays mandatory when 5555 is dead" — that path no longer
exists post-K1; re-scope against the native agent's catastrophic-repair path
before spiking this. Note (incubator):
[docs/research/experiments/on-device-llm.md](research/experiments/on-device-llm.md).

- Prefer **shell-gpt**; skip **aider-chat** (wrong job + aarch64 pain).
- Local 1.5B–3B = bounded advisor only; cloud API for quality escalation.
- Mis-scoping (LLM owns heal/GUI, or always-on Ollama in Termux:Boot) is the
  real risk — keep allowlists and consent hard.

---

### Track T — Tooling (deferred)

**Shipped:** T1, T3 — see [archive](archive/options-closed-2026-07-23.md#track-t--tooling).

#### T2 — Evaluate dashboard/framework options for JS runtime supervision · Risk: **Medium** · Deferred

The research prompt for **this** entry (JS-runtime supervision: PM2, Uptime
Kuma, Pulumi, Jest, `zx`, Shipit, Flightplan) is
[JavaScript Runtime Supervision Evaluation](research/javascript-runtime-supervision-2026-07-13.md) —
**not** the dashboard-framework-research prompt (that link was a stale
cross-reference, flagged by T5 below and fixed here). A useful candidate must
reduce host-side glue or add meaningful job, approval, or audit support;
generic uptime widgets do not count. Option A is the host-only Biome
lint/format pilot (ESLint replaced by Biome; AutoJs6 sources completed a full
TypeScript migration 2026-07-21). Options B, C, D remain deferred. Note: the
"AutoJs6 runtime dependency" framing predates K1 — AutoJs6 is retired
fleet-wide, so this evaluation now concerns any residual JS tooling in
`device/autojs6/` (kept as reference code) plus `just/tools`, not a live
watchdog.

#### T4 — Evaluate `ansible-pull` for fleet policy delivery · Risk: **Medium** · Deferred

Evaluate whether Android/Termux devices should pull a signed or pinned policy
checkout instead of relying primarily on Mac→device SSH push.

**Research complete (2026-07-14):** [Hybrid `ansible-pull` architecture and staged
pilot](research/ansible-pull-architecture-2026-07-14.md). Recommendation: an
opt-in, `oneui-device`-first pilot for a strict device-local, non-secret policy
subset. Mac push Ansible remains authoritative for bootstrap, credentials,
apps, UI, and recovery. A new ADR is required after measured pilot results.

#### T5 — Observability/portal unification (Grafana+OpenObserve, dashboard-framework) · Risk: **Low** · Deferred

**Research complete (2026-07-23):** [Observability unification vs. portal unification
evaluation](research/evaluations/observability-portal-unification-evaluation-2026-07-23.md).
Recommendation: reject Homer/Glance as a portal replacement. Two separable
next steps: (1) wire OpenObserve into Grafana as a Prometheus-compatible
datasource; (2) actually run the dashboard-framework evaluation prompt.
Tracked as [#47](https://github.com/djbclark/stayturgid/issues/47), blocked on
the OpenObserve↔Vector 401 auth break tracked in
[#44](https://github.com/djbclark/stayturgid/issues/44).

---

### Track G — Python migration & logging

**Fully completed 2026-07-13.** See
[archive](archive/options-closed-2026-07-23.md#track-g--python-migration--logging-fully-completed-2026-07-13)
for G1–G4.

### Track H — Post-migration cleanup (open items)

**Closed:** H2, H4, H5 (pre-commit/typos — see the ID-collision note above),
H6, H7, H8, H10, H11, H12, H13 — see
[archive](archive/options-closed-2026-07-23.md#track-h--post-migration-cleanup-closed-items).

#### H1 — Finish Python deployment on fireos-device · Risk: **Medium**

Completed on oneui-device + stock-android-device on 2026-07-13. fireos-device
remains because it was not needed for the FIRERPA investigation and has a
different Fire OS/USB-only recovery profile.

#### H3 — `just deploy` to push Python runtime to fleet · Risk: **Medium**

Completed on oneui-device + stock-android-device. Run the same deploy on
fireos-device only with USB recovery available.

#### H9 — Foreground-screen save/restore disabled · Risk: **Low** · Partially closed 2026-07-14

The unreliable `ScreenControlSession` foreground save/restore has been
disabled (both Mac-side `control/lib/screen_control.py` and on-device
`device/termux/py/stayturgid_screen_control.py`). The `restore_foreground()`
and `parse_foreground_component()` functions remain intact for future use.

**Remaining scope** (deferred, may revisit via FIRERPA OCR/screen-control):

- Inventory every foreground transition across UI roles
- Minimize unnecessary app launches
- Restore a predictable final screen when it becomes reliable to do so

**Non-goals / do-not-touch:** MDM / root / Play Protect bypass; full Obtainium
API; Tasker rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal;
always-on Ollama in Termux:Boot; **any Inferno/`emu`/Styx work** (parked under
[docs/research/experiments/inferno-styx/](research/experiments/inferno-styx)).

### Track F — FIRERPA (gRPC backup channel — core shipped 2026-07-12)

**Shipped:** Ansible collection (`ansible_collections/stayturgid/firerpa/`) with
install/configure/service/uninstall; playbook (`fleet/firerpa.yml`); Python heal script
(`firerpa_heal.py`); launchd health monitor (`firerpa_health_monitor.py` every 10 min);
Termux boot integration in Python `start_adb.py`. Deployed on oneui-device +
stock-android-device (v10.0 :65000). fireos-device blocked by Fire OS SELinux
(peer-bootstrap covers it; no plan to fix).

**Known limitations (by design, not open work):** FIRERPA inbound SSH is
enabled as user `shell` with a private custom service certificate. After
reboot the server archive still needs a UID-2000 bridge: `start_adb.py` first
tries localhost ADB; when needed it uses authorized Shizuku `rish` to restart
adbd, waits for localhost:5555, then launches through persistent ADB.
Built-in ADB needs root (stayturgid uses the shell bridge); fireos-device
remains unsupported. Architecture docs:
`docs/research/evaluations/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md`,
`docs/research/evaluations/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md`,
`docs/research/evaluations/firerpa-install-map-2026-07-12.md`.

**Closed:** F2, F4 — see [archive](archive/options-closed-2026-07-23.md#track-f--firerpa-closed-items).

#### F1 — MCP bridge extension (agent) · Risk: **Medium** · Core: gRPC heal works without it

Build a lamda MCP extension that exposes stayturgid repair primitives through
the gRPC channel. Core gRPC heal (`firerpa_heal.py`) works today; MCP just
provides agent-native tool calling. **Plan finalized:**
[operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md](operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md)
(decisions D1–D3 resolved; implementation gated on operator go). Tracked as
[#46](https://github.com/djbclark/stayturgid/issues/46).

#### F3 — MITM-on-demand playbook (agent) · Risk: **Medium**

Build an Ansible playbook that enables FIRERPA's MITM proxy + Frida on-demand
for debugging, then disables it. FIRERPA ships proxy/Frida modules but they're
off by default (minimal-failsafe config). Useful for debugging app network
behavior on non-rooted devices.

---

Batch closures from 2026-07-08 through 2026-07-14 are recorded in
[docs/archive/options-closed-2026-07-23.md](archive/options-closed-2026-07-23.md#trailing-closed-ledger-batch-closures-2026-07-08-through-2026-07-14).
