# OPTIONS — open work

> **For agents:** When the operator asks for **options** or **next steps**, read this
> file, present the open items **with descriptions and risk**, do any requested work,
> then **replace** this list (drop completed items; keep IDs stable). **Commit and
> push** in the same turn.
>
> **Fleet health (mandatory):** at session start run
> `make health` (or `python3 control/bin/check_fleet_health.py`). If exit ≠ 0, **tell the operator** the
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
> Strategic directions: [docs/handoff.md appendix](handoff.md#appendix--strategic-directions-equal-weight).
> Ansible boundary: [docs/adr/001-ansible-boundary.md](adr/001-ansible-boundary.md),
> [docs/adr/002-ansible-ui-tasks.md](adr/002-ansible-ui-tasks.md).
> Self-heal vs Ansible coverage: [docs/adr/004-self-heal-vs-ansible-coverage.md](adr/004-self-heal-vs-ansible-coverage.md).
> Parked side projects: [docs/incubator/](incubator) — **do not implement**
> unless the operator unparks a named project (Inferno, etc.).

**Fleet snapshot (2026-07-13):** Shell → Python migration complete. Unified syslog
logging with 30-day rotation and remote error scraping. Bootstrap APK automation
deployed (7 APKs). FIRERPA on s24 + p7a (v10.0). Fleet dashboard (Flask + HTMX, :4097)
with device status cards, human-action-needed indicators, live probe buttons, and
long-term stats tracking (JSONL, forever, with selectable timeframe). Network landing
page (:8088, also :443/services/) with MagicDNS / mDNS / LAN / Tailscale service
links and hourly discovery scan. HTTPS consolidation behind Caddy reverse proxy
(mac.greyhound-sidemirror.ts.net) with HTTP→HTTPS redirect. Tailnet renamed to
greyhound-sidemirror.ts.net; all old machine names purged. **Python migration
NOT YET deployed to devices** (see H1). s24: AutoJs6 watchdog stale since Jul 12
16:30 (watchdog_heal ineffective on Android 16 — task stuck after a11y detection).
p7a: port 5555 down (H2), but SSH/ADB probe now works after monitor fix.
Open menu = H1/H3 (deploy), H2 (p7a), H6 (s24 watchdog), H5/38, 43–45, 54, F1–F4.

**Risk scale:** **Low** = reversible / read-mostly · **Medium** = live UI or
config change, recoverable · **High** = fleet-wide or credential/publish blast
radius · **Latent** = only act if a symptom returns.

**Suggested agent order:** `make health` + `make firerpa-health` then
`make verify-bootstrap-apks HOSTS=s24` to check APK freshness, then
`make deploy-check HOSTS=s24` for any soak. H5/38 only if Galaxy publish wanted.
FIRERPA F1–F4 are future enhancements; core integration is done. Bootstrap
B63–B64 are follow-ups needing hardware access.

---

## Pick a track

| Track | Focus | Open IDs | Typical risk |
|-------|-------|----------|--------------|
| **A — Operational** | Live deploy, human unblockers | H5, 38, H6 (s24 watchdog) | Medium–High (live phones / publish) |
| **B — Ansible-native** | Bootstrap APK automation follow-ups | B63, B64 | Low–Medium |
| **D — Reliability** | Symptom-driven hardening | H6, 43–45 | Latent until triggered |
| **E — On-device LLM** | shell-gpt escalation; incubator note | 54 | Medium (mis-scope risk) |
| **F — FIRERPA** | gRPC backup channel enhancements | F1–F4 | Medium (future, core is done) |

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

Run `make deploy --limit <new_device>` from a device with only USB debugging
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

### Track G — Python migration & logging (completed)

**Shipped (2026-07-13):** Shell → Python migration of `start-adb.sh`, `autojs6-bridge.sh`,
`repair-bridge.sh`, `ui_tars_env.sh`, `vlm_migrate_paths.sh`. All old shell files deleted,
Ansible retired lists updated. Unified syslog logging (`control/lib/logging.py`) with
severity levels, 30-day age-based rotation, and remote error scraping (device logs →
local `errors.log`). `/errors` route on fleet dashboard. All monitors use shared logging.

#### ~~G1 — Healing coverage registry + pre-flight checker~~ · **Closed 2026-07-13**

`tests/healing_registry.json` (SSOT of all 27 desired states with must_cover/should_cover
mechanism requirements). `tests/check_healing_coverage.py` runs in `make test` tier:code.

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

#### H1 — Deploy new Python files to devices · Risk: **Medium**

The new `start_adb.py`, `bridges.py`, and updated `stayturgid_repair.py` with severity
logging haven't been deployed yet. Run `make deploy` to push to fleet. Until then,
old shell shims on-device fall through to bare sshd start (no repair loop). P7a is
already in this state (`CLOSED_NO_SHELL` for hours).

#### H2 — p7a port 5555 is down · Risk: **Medium** · Trigger: operator action

p7a wireless debugging (port 5555) has been down since ~06:20 2026-07-13.
`CLOSED_NO_SHELL` in co-monitor. Shizuku daemon IS running (pgrep) but can't
serve shells. Needs manual re-enable in Developer Options → Wireless debugging,
or a reboot. SSH and fleet-health probes work fine via the ADB fallback path.

#### H3 — `make deploy` to push Python runtime to fleet · Risk: **Medium**

Run `make deploy [HOSTS=s24]` to push all new Python scripts (bridges, start_adb, repair
with severity logging) and retire old shell scripts from devices via `stayturgid_retired_scripts`.

#### H6 — s24 AutoJs6 watchdog stale (Android 16) · Risk: **Medium** · Latent

s24's AutoJs6 watchdog has been stuck since Jul 12 16:30 EDT. The watchdog detected
"accessibility disabled" and tried to re-enable it, but the trigger file write failed
(`TypeError: Cannot find function getParent`). After that error, the AutoJs6 main.js
JavaScript task stopped cycling entirely — the app process is alive (including a11y
service IS enabled) but the task won't restart.

**What's been tried:**
- `start_watchdog.py` (Mac → ADB trigger file) — reported success but no new cycle
- `am force-stop` + `monkey` relaunch of AutoJs6 — app restarts but task doesn't
- `am broadcast RunIntentActivity` with main.js path — no effect
- Fleet-health watchdog heal triggered at 09:45 with `start_watchdog.py` — the
  guard log shows the task briefly started then got stuck on the same error

**Root cause speculation:** AutoJs6 v6.7.0 on Android 16 — the `getParent()` API
may have been removed or restricted. The task enters an error loop at startup and
can't proceed past the accessibility check.

**Next steps if fixing:**
1. Check AutoJs6 logs on-device (`logcat -s "AutoJs6:*"` or internal error log)
2. Consider downgrading AutoJs6 or switching to a different approach
3. The dashboard shows `bootloop_down` — confirmed false positive (bootloop IS running)
4. All other services healthy (sshd=ok, shizuku=up, ADB=ok)

**Non-goals / do-not-touch:** MDM / root / Play Protect bypass; full Obtainium
API; Tasker rebuild; AutoJs6 debug APK (#553); aider-chat as fleet heal;
always-on Ollama in Termux:Boot; **any Inferno/`emu`/Styx work** (parked under
[docs/incubator/inferno-styx/](incubator/inferno-styx)).

### Track F — FIRERPA (gRPC backup channel — core shipped 2026-07-12)

**Shipped:** Ansible collection (`ansible_collections/stayturgid/firerpa/`) with
install/configure/service/uninstall; playbook (`fleet/firerpa.yml`); Python heal script
(`firerpa_heal.py`); launchd health monitor (`firerpa_health_monitor.py` every 10 min);
Termux boot integration in `start-adb.sh` (start + monitor); Makefile targets
(`firerpa-deploy`, `firerpa-remove`, `firerpa-heal`, `firerpa-health`). Deployed on
s24 + p7a (v10.0 :65000). hd8 blocked by Fire OS SELinux (peer-bootstrap covers it;
no plan to fix).

**Known limitations (by design, not open work):** FIRERPA built-in SSH blocked
(HOME=/ read-only, key auth needs root — [upstream #145](https://github.com/firerpa/lamda/issues/145));
built-in ADB needs root (stayturgid uses Shizuku's adbd :5555); stale PID on restart
(workaround: `rm -rf /data/local/tmp/usr/` before restart). Architecture docs:
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
`make help`/Makefile ops; `make health` stale LOST fix; docs sweep. **58–59** ADR 002 +
`android_ui` / `post_ui` / `android_a11y_services`. Neo/Aurora parked.
**Closed (2026-07-09 evening):** Aurora CPU thrash policy documented; screen-control hold rule.
**Closed (2026-07-09):** **15b**, **H1**, **H3**, **56**, **46**, **55**, **27**,
**57**, Portfolio 2 **48–52**/53, co-monitor + Mac AutoJs6 heal, Fire F1–F5,
self-heal agent rule.
**Closed (2026-07-08):** drawer profile, a11y, PiP, Aurora order, #553.
**Shipped (2026-07-13):** bootstrap APK automation (version-aware install + verify +
Shizuku start, 7 APKs); `android_apk` resign param; AutoJs6 versionName fix;
`shizuku_start` module (16 unit tests).
