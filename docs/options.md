# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, present the open items **with descriptions and risk**, do any requested work,
> then **replace** this list (drop completed items; keep IDs stable). **Commit and
> push** in the same turn.
>
> **Fleet health (mandatory):** at session start run
> `just health` (or `python3 control/bin/check_fleet_health.py`). If exit ≠ 0, **tell the operator** the
> host/`issues=` tags in your first reply — do not wait to be asked. Details:
> [docs/handoff.md § Mac fleet health](handoff.md#mac-fleet-health--mandatory-for-agents).
>
> **Health fix → self-heal (mandatory):** when you clear a health issue, also
> update Termux / AutoJs6 co-monitor / Mac launchd so that failure mode
> recovers without a manual one-shot next time. Rule:
> `.cursor/rules/fleet-health-self-heal.mdc`.
>
> Human-only tasks: [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md). Operator
> answers: `human/RESPONSES.md` (gitignored). Session context: [docs/handoff.md](handoff.md).
> Coding and completion rules: [docs/coding-rules.md](coding-rules.md).
> Strategic directions: [docs/handoff.md appendix](handoff.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](adr/001-ansible-boundary.md),
> [docs/adr/002-ansible-ui-tasks.md](adr/002-ansible-ui-tasks.md).
> Self-heal vs Ansible coverage: [docs/adr/004-self-heal-vs-ansible-coverage.md](adr/004-self-heal-vs-ansible-coverage.md).
> Parked side projects: [docs/incubator/](incubator) — **do not implement**
> unless the operator unparks a named project (Inferno, etc.).

**Fleet snapshot (2026-07-13):** Shell → Python migration complete and deployed to
s24 + p7a. Unified syslog
logging with 30-day rotation and remote error scraping. Bootstrap APK automation
deployed (7 APKs). FIRERPA on s24 + p7a (v10.0). Fleet dashboard (Flask + HTMX, :4097)
with device status cards, human-action-needed indicators, live probe buttons, and
long-term stats tracking (JSONL, forever, with selectable timeframe). Network landing
page (:8088, also :443/services/) with MagicDNS / mDNS / LAN / Tailscale service
links and hourly discovery scan. HTTPS consolidation behind Caddy reverse proxy
(mac.greyhound-sidemirror.ts.net) with HTTP→HTTPS redirect. Tailnet renamed to
greyhound-sidemirror.ts.net; all old machine names purged. s24 + p7a: FIRERPA secure
SSH/gRPC live without suppressing AutoJs6, AutoInput, or Octoclip; Python runtime and
watchdogs healthy. Open menu = remaining hd8 deployment under H1/H3, H9
(post-UI foreground cleanup),
H5/38, 43–45, 54, F1–F4. T1 shipped 2026-07-13.
`just firerpa-health` is clean and live health is clean for s24 + p7a. The aggregate
`just health` command remains nonzero only for hd8's documented `watchdog_stale` /
offline state while that USB-only tablet deployment is intentionally deferred.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Suggested agent order:** Follow
[Outstanding Fix Priorities](plans/outstanding-fix-priorities-2026-07-13.md): H1/H3,
H9, B63/B64, F4, then T1. Hardware-blocked items stay open
while independent safe work may continue. H5/38, 43–45, 54, and F1–F3 remain lower
priority or symptom-triggered.

---

## Pick a track

| Track | Focus | Open IDs | Typical risk |
|-------|-------|----------|--------------|
| **A — Operational** | Live deploy, human unblockers, current reliability | H1, H3, H5, H9, 38 | Low–High |
| **B — Ansible-native** | Bootstrap APK automation follow-ups | B63, B64 | Low–Medium |
| **D — Reliability** | Symptom-driven hardening | 43–45 | Latent until triggered |
| **E — On-device LLM** | shell-gpt escalation; incubator note | 54 | Medium (mis-scope risk) |
| **F — FIRERPA** | gRPC backup channel enhancements | F1–F4 | Medium (future, core is done) |
| **T — Tooling** | Planned command-runner migration | T1 | Low–Medium |

Parked (not a track): Inferno/Styx → [docs/incubator/inferno-styx/](incubator/inferno-styx).

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
`autojs6_watchdog` for Fire adb path; `control/tools/autojs6/deploy.py` thin wrapper retained.

#### ~~62 — Remove legacy path aliases and shim-only layout (agent)~~ · **Closed 2026-07-10**

Removed flat `ansible/playbooks/*.yml` shims (keep `site.yml` + `fleet/` +
`control_node/`). Termux callers use `stayturgid_repair.py` /
`stayturgid_agent_presence.py` (shell shims deleted; retired list cleans devices).
`gplaycli.sh` removed; `stayturgid_root.py` legacy markers dropped.

#### B63 — shizuku_start native launch path on real device (agent) · Risk: **Low** · Needs: device with Shizuku stopped

Test the `shizuku_start` module's `libshizuku.so` native launch path on a live
device. The module is idempotent (tested on s24 — already_up path OK). The
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

---

### Track D — Reliability (do not start without a symptom)

Mac **soft health**: launchd `com.stayturgid.fleet-health` →
`control/bin/fleet_health_monitor.py` every 5 min (`~/.config/stayturgid/logs/fleet-health.log`).
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
[docs/incubator/on-device-llm.md](incubator/on-device-llm.md).

- Prefer **shell-gpt**; skip **aider-chat** (wrong job + aarch64 pain).
- Local 1.5B–3B = bounded advisor only; cloud API for quality escalation.
- Mis-scoping (LLM owns heal/GUI, or always-on Ollama in Termux:Boot) is the
  real risk — keep allowlists and consent hard.

---

### Track T — Tooling (deferred)

#### T1 — Make `just` the primary operator interface (agent) · Risk: **Low–Medium** · **Shipped 2026-07-13**

The evaluation is complete and the direction is accepted: replace most of the 494-line,
79-target command-runner Makefile with a root `justfile`, keep substantive logic in
Python or Ansible, and retain a small Make compatibility/bootstrap shim through CI and
live-fleet soak. Do not perform a flag-day Make removal.

**Shipped:** Root `justfile` with 3 imported recipe groups (fleet, services, tests)
providing 84 discoverable recipes via `just --list`. GNU Makefile retired

session-start and deploy examples updated to `just` syntax. `make` targets preserved
as compatibility wrappers for CI and operator muscle memory.

Follow the staged plan, compatibility contract, live S24 gates, rollback rules, and
completion criteria in
[GNU Make to `just` Migration Plan](plans/just-migration-plan.md). Task/Taskfile is the
closest direct alternative; `mise` may be evaluated separately for toolchain pinning,
not as a prerequisite for T1.

#### T2 — Evaluate dashboard/framework options for JS runtime supervision · Risk: **Medium** · Deferred

The research prompt for this work is
[docs/prompts/dashboard-framework-research.md](prompts/dashboard-framework-research.md).
The broader evaluation covers PM2, Uptime Kuma, Pulumi, Jest, `zx`, Shipit, and
Flightplan. A useful candidate must reduce host-side glue or add meaningful job,
approval, or audit support; generic uptime widgets do not count. None should become
an AutoJs6 runtime dependency. Option A is now the host-only ESLint pilot; the
existing Node harness remains the device-test seam. Options B, C, and D are
intentionally deferred for later. Details, compatibility constraints, and bounded
implementation steps are in
[JavaScript Runtime Supervision Evaluation](research/javascript-runtime-supervision-2026-07-13.md).
Also worth a later look: whether packaging the AutoJs6 side as a plugin would make
deployment or recovery easier.

---

### Track G — Python migration & logging (completed)

**Shipped (2026-07-13):** Shell → Python migration of `start-adb.sh`, `autojs6-bridge.sh`,
`repair-bridge.sh`, `ui_tars_env.sh`, `vlm_migrate_paths.sh`. All old shell files deleted,
Ansible retired lists updated. Unified syslog logging (`control/lib/logging.py`) with
severity levels, 30-day age-based rotation, and remote error scraping (device logs →
local `errors.log`). `/errors` route on fleet dashboard. All monitors use shared logging.
**Shim cleanup (2026-07-13):** Remaining thin shell wrappers eliminated — `ui_tars_env.sh`
deleted (replaced with inline `_env()` helper), `vlm_install.sh` deleted (unused),
`start-adb.sh` reduced to 5-line env+exec, bridge scripts reduced to one-liners
(PID guard moved into `stayturgid_bridges.py`), `stayturgid-peer-help-force.sh` reduced
to one-liner (verb whitelist in Python). Fleet devices need `just deploy` to pick up
new boot scripts.

#### ~~G1 — Healing coverage registry + pre-flight checker~~ · **Closed 2026-07-13**

`tests/healing_registry.json` (SSOT of all 28 desired states with must_cover/should_cover
mechanism requirements). `tests/check_healing_coverage.py` runs in `just test` tier:code.
All mandatory coverage is present. Its ten soft `should_cover` TODOs remain visible for
secondary-path hardening: SSHD/port 5555/Shizuku/accessibility/bootloop/device-profile
coverage across Ansible, CFEngine, fleet health, and FIRERPA, plus fleet-health coverage
of secure FIRERPA. They are non-blocking but should not silently disappear from test output.

#### ~~G2 — Shell → Python migration (bridges, boot supervisor, VLM)~~ · **Closed 2026-07-13**

`start_adb.py`, `stayturgid_bridges.py`, `vlm_migrate_paths.py`, `ui_tars_env.py`.
Old `.sh` files deleted from repo, listed in `stayturgid_retired_scripts`.

#### ~~G3 — Remove automatic accessibility repair~~ · **Closed 2026-07-13**

All automatic `settings put` for `enabled_accessibility_services` removed. Detection-only
with notifications directing user to Settings.

#### ~~G4 — Unified syslog logging + rotation + error scraping~~ · **Closed 2026-07-13**

`control/lib/logging.py` with EMERG..DEBUG levels, all monitors refactored to use it,
30-day log rotation, remote device error scraping into `errors.log`, dashboard `/errors` route.

### Track H — Post-migration cleanup (open items)

#### H1 — Finish Python deployment on hd8 · Risk: **Medium**

Completed on s24 + p7a on 2026-07-13. hd8 remains because it was not needed for the
FIRERPA investigation and has a different Fire OS/USB-only recovery profile.

#### ~~H2 — p7a port 5555 restored~~ · **Closed 2026-07-13**

Port 5555, the shell bridge, Shizuku, and accessibility checks are all healthy.
The historical `CLOSED_NO_SHELL` alerts remain in the 24-hour log window but are
not current failures. A second short set at 15:21 occurred while the deployment
restarted its supervisors; fresh 15:25+ repair checks and live validation are green.

#### H3 — `just deploy` to push Python runtime to fleet · Risk: **Medium**

Completed on s24 + p7a. Run the same deploy on hd8 only with USB recovery available.

#### ~~H4 — ruff + uv tooling~~ · **Closed 2026-07-14**

`pyproject.toml` at project root with ruff config (line-length 120, py312 target, E/F/I/W
rules). `just ruff` recipe runs `ruff check` + `ruff format --check`. `just lint` and
`just check` both include ruff. `just test-venv` uses `uv` instead of `pip`. `uv` and
`ruff` installed via `brew install uv ruff`.

#### ~~H5 — pre-commit + typos tooling~~ · **Closed 2026-07-14**

`.pre-commit-config.yaml` runs ruff, typos, shellcheck, yamllint, and the existing
project-scoped Ansible lint command. `.typos.toml` carries approved project vocabulary
such as `lamda` and `AAS`. `just typos`, `just check`, `just test`, and `just lint`
include spelling checks. Hooks are installed with `pre-commit install`.

#### ~~H6 — s24 AutoJs6 watchdog stale (Android 16)~~ · **Closed 2026-07-13**

The accessibility service resumed after the operator toggled it off/on. A later stale
watchdog exposed a separate deterministic bug: `boot-launcher.js` inherited its own
`scripts/` working directory when spawning `main.js`, so the child failed every
`require("./lib/...")`. The launcher now supplies the project directory explicitly.
S24 produced clean boot and interval cycles with `sshd=ok`, Shizuku up, localhost ADB
up, and all three accessibility services bound. The Python/Termux guard and Mac health
monitor retain the automatic stale-engine restart path; accessibility enablement itself
remains a deliberate human action.

**Non-goals / do-not-touch:** MDM / root / Play Protect bypass; full Obtainium
API; Tasker rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal;
always-on Ollama in Termux:Boot; **any Inferno/`emu`/Styx work** (parked under
[docs/incubator/inferno-styx/](incubator/inferno-styx)).

#### ~~H7 — Authorize Termux `rish` bridge~~ · **Closed 2026-07-13**

S24 and P7A were fixed by choosing **Allow all the time** for Termux in Shizuku's
authorization prompt. On both phones, `~/.stayturgid/bin/rish -c 'id -u'` returns UID 2000.
Directly backgrounding FIRERPA through `rish` is not durable because the binder session
owns and kills its child. The supervisor instead uses `rish` to restore shell adbd on
localhost:5555, then launches FIRERPA through that persistent UID-2000 ADB transport.
A controlled S24 stop/start and both phones' secure SSH returned UID 2000.

If authorization is revoked, the supervisor safely reports the privileged shell unavailable.
Localhost ADB remains the other validated path.

#### H8 — Dashboard Shizuku authorization action · **Complete 2026-07-13** · Risk: **Low**

The dashboard now marks `shizuku_down` as actionable and provides an immediate
**open Shizuku and test rish** button. The endpoint opens the Shizuku launcher via
the device shell, runs `~/.stayturgid/bin/rish -c 'id -u'` over Termux SSH, and
requires UID 2000. If Android still needs consent, the response explicitly tells
the operator to tap **Allow all the time** and retry. The implementation never
claims to automate Android consent.

#### H9 — Post-UI unlock and foreground-screen cleanup · Risk: **Low**

Full deploy's `post_ui` phase requires the screen to be on and unlocked; the role now waits
and prints an `ACTION REQUIRED` task instead of silently stalling. The UI sequence can bring
Obtainium, AutoJs6, Termux:API, Shizuku, or Android Settings to the foreground and may leave
an arbitrary screen visible when it finishes. This does not affect service health. In a
future UI pass, inventory every foreground transition, minimize unnecessary launches, and
restore a predictable final screen. Do not block core deployment work on this cleanup.

#### H10 — Fix unsupported AutoJs6 parent-path calls · **Complete 2026-07-13** · Risk: **Medium**

Replaced both unsupported `files.getParent()` calls with the shared AutoJs6-compatible
`config.ensureParentDir()` helper, added missing-parent regression coverage (including
the notification state path), and fixed the standalone deployer's repository import
path. `just test` passed (289 pytest tests plus shell, Ansible, and AutoJs6 suites).
The change was deployed to S24 and P7A; fresh bridge/watchdog runs recreate the S24
bridge successfully and no new `getParent` errors appear. P7A still has the separate,
pre-existing `CLOSED_NO_SHELL`/headless-Shizuku failures tracked by H12.

#### H11 — Move landing discovery runtime state out of Git · **Complete 2026-07-13** · Risk: **Low**

Static definitions now live in tracked `control/landing/services.json`; discovery
and the landing UI use `~/.config/stayturgid/landing/services.json` for timestamps,
reachability, status codes, and hidden entries. First use migrates the prior tracked
state, writes atomically, and tests plus two live discovery runs prove the catalog
remains unchanged.

#### H12 — Summarize recovered errors in default fleet health · **Complete 2026-07-13** · Risk: **Low**

`control/bin/check_fleet_health.py` now preserves the raw log while grouping repeated
messages with counts/latest timestamps and separating active, recovered, and
historical conditions. Exit status remains based on current actionable health;
unit coverage covers repeated and recovered classification.

Execution order, gates, and junior-agent resume prompt:
[Outstanding Fix Priorities](plans/outstanding-fix-priorities-2026-07-13.md).

### Track F — FIRERPA (gRPC backup channel — core shipped 2026-07-12)

**Shipped:** Ansible collection (`ansible_collections/stayturgid/firerpa/`) with
install/configure/service/uninstall; playbook (`fleet/firerpa.yml`); Python heal script
(`firerpa_heal.py`); launchd health monitor (`firerpa_health_monitor.py` every 10 min);
Termux boot integration in Python `start_adb.py` (start + monitor); Makefile targets
(`firerpa-deploy`, `firerpa-remove`, `firerpa-heal`, `firerpa-health`). Deployed on
s24 + p7a (v10.0 :65000). hd8 blocked by Fire OS SELinux (peer-bootstrap covers it;
no plan to fix).

**Known limitations (by design, not open work):** FIRERPA inbound SSH is enabled as
user `shell` with a private custom service certificate (`ssh s24-firerpa`; resolution of
[upstream #145](https://github.com/firerpa/lamda/issues/145)). After reboot the server
archive still needs a UID-2000 bridge: Python `start_adb.py` first tries localhost ADB;
when needed it uses authorized Shizuku `rish` to restart adbd, waits for localhost:5555,
then launches through persistent ADB. Both phones' paths are validated after granting
Termux **Allow all the time**. USB/wireless recovery is required if neither bridge is
available.
Built-in ADB needs root
(stayturgid uses the shell bridge); hd8 remains unsupported. Architecture docs:
`docs/history/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md`,
`docs/history/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md`,
`docs/history/firerpa-install-map-2026-07-12.md`.

#### F1 — MCP bridge extension (agent) · Risk: **Medium** · Core: gRPC heal works without it

Build a lamda MCP extension that exposes stayturgid repair primitives through the
gRPC channel, so any MCP-capable agent can run fleet heal commands. Core gRPC heal
(`firerpa_heal.py`) works today; MCP just provides agent-native tool calling.
See `docs/history/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md` for MCP
extension pattern.

#### F2 — WebRTC remote desktop test (agent) · Risk: **Low**

Test FIRERPA's built-in WebRTC screen mirroring (`scrcpy`-style). Useful for
tablet-control-phone use cases or no-USB glass access. Spike only — scrcpy +
Tailscale already covers this for s24/p7a.

#### F3 — MITM-on-demand playbook (agent) · Risk: **Medium**

Build an Ansible playbook that enables FIRERPA's MITM proxy + Frida on-demand for
debugging, then disables it. FIRERPA ships proxy/Frida modules but they're off
by default (minimal-failsafe config). Useful for debugging app network behavior
on non-rooted devices.

#### F4 — Network isolation (agent) · Risk: **Medium** · Latent

The 163 MB closed-source server binary could phone home. Bind FIRERPA to Tailscale
interfaces only and use Tailscale ACLs to drop outbound WAN access from the lamda
process. Not urgent — gRPC is already on Tailscale IP. Track if upstream changes
or network audit is needed.

**Closed (2026-07-09 night):** **60–61** validate role + preflight + `autojs6_project_deploy`;
`just --list`/Makefile ops; `just health` stale LOST fix; docs sweep. **58–59** ADR 002 +
`android_ui` / `post_ui` / `android_a11y_services`. Neo/Aurora parked.
**Closed (2026-07-09 evening):** Aurora CPU thrash policy documented; screen-control hold rule.
**Closed (2026-07-09):** **15b**, **H1**, **H3**, **56**, **46**, **55**, **27**,
**57**, Portfolio 2 **48–52**/53, co-monitor + Mac AutoJs6 heal, Fire F1–F5,
self-heal agent rule.
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
**Shipped (2026-07-13):** bootstrap APK automation (version-aware install + verify +
Shizuku start, 7 APKs); `android_apk` resign param; AutoJs6 versionName fix;
`shizuku_start` module (16 unit tests); T1 just migration (root justfile + 3 recipe
groups, 84 discoverable recipes, Makefile retired).
