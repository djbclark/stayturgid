<!-- historical: imported 2026-07-23 from an out-of-git AI planning directory; site facts genericized on import (see docs/architecture/multi-site-topology.md §4.1) -->

# Active/passive monitoring for stayturgid

## Context

You asked whether stayturgid currently has Nagios-style active/passive monitoring, and if not, what modern option fits. This isn't a code-design task — it's an architecture recommendation, so this "plan" is really the writeup of findings plus a suggested next step, which you can act on (or not) as you like.

## Current state (confirmed by reading the code)

**Active checks: yes, and this is the dominant pattern already.**

- `control/bin/access_monitor.py` — runs every 5 min via launchd, probes ADB/SSH reachability per device, fires a macOS notification after 2 consecutive failures. Its own docstring calls it a "dead-man's switch," but architecturally it's an active poller, not a passive push.
- `control/bin/fleet_health_monitor.py`, `fire_help_monitor.py`, `check_fleet_health.py`, `check_et_mac.py` — more active probes (SSH/ADB scrape → log/restart).
- `device/autojs6/lib/watchdog.ts` — on-device watchdog that actively checks freshness of a repair-loop log line, ADB port, sshd, Shizuku, Tailscale.

**Passive/heartbeat checks (the classic Nagios "passive check" — something pushes a result in, and you alert on staleness/absence): no dedicated implementation.**

- The closest thing is the watchdog reading local log staleness ("no `[repair]` line in 15+ min") — but that's a local file read by an active poller, not a push to an external monitor that can alert even if the poller itself dies.
- No healthchecks.io / Cronitor / Nagios / Icinga / Prometheus anywhere in the repo (grepped — zero hits).
- Alerting today is macOS local notifications (`osascript`) and Android in-app notifications only — no Slack/email/webhook. There _is_ a Telegram-based "Hermes Agent" gateway already running (`com.stayturgid.hermes-gateway`, launchd KeepAlive) for an unrelated AI-agent bridge, which is a plausible existing channel to reuse for alerts.
- `docs/research/mobile_first_observability_stack.md` contained prior research on an OTel/Vector/OpenObserve pipeline. **UPDATE (2026-07-21): that stack is no longer just research — it is built and running now**, provisioned by this repo's own `site-sync` / Site Contract Ansible roles. See below.

**The gap:** everything currently alerting depends on the Mac control node itself being up and its launchd agents actually running. There's no independent watchdog that would notice if the Mac control node — or a specific launchd agent — silently stopped. That's exactly the blind spot passive/heartbeat checks are designed to cover.

## UPDATE 2026-07-21 — the premise changed: the observability stack is already live

While answering a follow-up ("can we install Uptime Kuma via brew? what about Zabbix/Netdata/Checkmk/VictoriaMetrics/SigNoz/Healthchecks/Beszel? no Docker, self-hosted only") I inspected the running machine and found the stack from the research doc is **already deployed and running**, managed by `stayturgid site-sync` via `ansible/roles/serverapp_*`:

- **VictoriaMetrics** — running on `127.0.0.1:8428`; launchd `com.<site_ns>.victoriametrics`; role `serverapp_victoriametrics`; scrape config generated at `~/.config/<site_ns>/victoriametrics/scrape.yml` from a Jinja template (marked DO NOT EDIT, drift → site-sync exit 2).
- **Grafana** — running; launchd `com.<site_ns>.grafana`; role `serverapp_grafana`; "Fleet Control Room" dashboard.
- **OpenObserve** — running as a raw binary at `~/.local/bin/openobserve`; role `serverapp_openobserve`. (Proof that the project already accepts non-brew, launchd-managed, Ansible-provisioned binaries.) See the "used and properly managed" note below — it's the reference serverapp implementation.
- **Vector, Caddy, OliveTin, landing** — additional `serverapp_*` roles in the same site-contract pattern.

The real constraint is therefore **self-hosted + no Docker + provisioned by the Site Contract Ansible roles** — _not_ "must be brew." brew is just one of two delivery mechanisms already in use (VM + Grafana via brew; OpenObserve via direct binary).

### brew / no-Docker availability of the tools asked about

| Tool                         | brew formula?                                         | No-Docker self-host?                                   | Verdict                                                                                          |
| ---------------------------- | ----------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| **Uptime Kuma**              | ❌ none (`uptimed` is an unrelated uptime-record toy) | Node app — git-clone + `npm ci` + build, under launchd | Ansible _can_ manage it (see note below), but heavier / weaker supply-chain than a single binary |
| **Zabbix**                   | ✅ `zabbix` 7.4.12                                    | Yes, but server + DB + PHP frontend + agents           | Far too heavy                                                                                    |
| **Netdata**                  | ✅ `netdata` 2.10.4                                   | Yes (native alarms + parent/child streaming)           | Works, but duplicates the TSDB already running                                                   |
| **Checkmk**                  | ❌ none                                               | Server is Linux-only (OMD)                             | Not viable on macOS w/o Docker/VM                                                                |
| **VictoriaMetrics**          | ✅ `victoriametrics` 1.148                            | **Already installed & running here**                   | The incumbent — build on it                                                                      |
| **SigNoz**                   | ❌ none                                               | Docker + ClickHouse only                               | Violates no-Docker                                                                               |
| **Healthchecks (self-host)** | ❌ none                                               | Django + Postgres, bare or Docker                      | Passive-only, unmanaged                                                                          |
| **Beszel**                   | ❌ none                                               | Go binary under launchd                                | Off-pattern, unmanaged                                                                           |

(`gatus`, `alertmanager`, `vmalert`, `vmagent`, `blackbox_exporter`, `pushgateway` also have **no** brew formulae. The `victoriametrics` formula installs only the `victoria-metrics` binary — vmalert/vmagent are separate downloads.)

### "brew" is not the real gate — Ansible can install from git/releases directly

Correcting an overstatement in an earlier draft: a non-brew tool is **not** "unmanageable." Ansible (core 2.21.2, `community.general` 13.2.0 installed here) has all the modules for git/release installs, and they resolve in this env:

- `ansible.builtin.git` — clone + checkout a pinned tag/commit (idempotent)
- `community.general.npm` / `ansible.builtin.npm` — `npm ci` against a locked tree
- `ansible.builtin.get_url` (+ `checksum:`) — fetch a release tarball, sha256-verified
- `community.general.github_release` — resolve latest/specific GitHub release tag (**the direct Obtainium analogue** — track a repo's releases)
- `ansible.builtin.command`/`shell` — run a `npm run setup` / build step

**The repo already does the Obtainium-style thing:** `serverapp_openobserve/tasks/main.yml` fetches a pinned upstream release via `get_url`, verifies a per-arch `sha256`, `assert`s **fail-closed** on an unverified binary, extracts to `~/.local/bin`, templates a launchd plist, bootstraps, health-checks. `github_release` would add auto-track-latest if ever wanted (their pattern deliberately pins instead).

So a `serverapp_uptimekuma` role (git → `npm ci` → build → plist → bootstrap → health) is entirely feasible. The reasons to still prefer a single binary (gatus / Beszel / extending VM / OpenObserve) are cost, not capability:

1. **No clean checksum pin.** Single-binary roles hash-verify one artifact and fail closed; `git clone + npm ci` resolves a large transitive dep tree at deploy — reproducible against a committed `package-lock.json` but not hash-pinnable like a tarball (much larger supply-chain surface).
2. **Runtime dependency.** Kuma needs a maintained, version-compatible Node present; single static Go/Rust binaries (VM, OpenObserve, Beszel, gatus) have none.
3. **A deploy-time build that can fail** (node-gyp / better-sqlite3 native modules) vs "download + chmod."
4. **Muddier idempotency** — checkout+rebuild vs "install-if-absent, never upgrade."

### Is OpenObserve used-but-unmanaged, or mismanaged? Neither — it's the reference serverapp

A follow-up asked whether OpenObserve is used but not managed, or improperly managed (wrong Ansible module). Checked against the repo: **both used and properly managed.**

**Used:**

- `serverapp_vector` wires OpenObserve as its sink (`OPENOBSERVE_ROOT_EMAIL/PASSWORD` in the vector plist; sink→openobserve health noted in tasks). It's the log/metrics backend of the pipeline.
- Surfaced in the control plane via `control/landing/discover.py` and the Grafana "Fleet Control Room."

**Managed — arguably the most thorough app in the stack:**

- Role `serverapp_openobserve` + entry playbook `ansible/playbooks/serverapps/openobserve.yml`.
- Orchestrated by `control/site_contract/serverapps.py` — in the `SERVERAPPS` apply/dry-run list, with **foreign-unit detection** (`_openobserve_detect_paths` guards homebrew/legacy/other-site plists), plus port/path registry entries (`registry/ports.yml`, `paths.yml`) and `site_sync.py` / `site_map.py` integration.
- Full own-mode lifecycle: fail-closed checksum'd install → templated launchd plist → health-gated legacy cutover → bootstrap-with-retries → health poll.

**"Best module" — the one deviation is deliberate and correct.** Install uses the right modules (`get_url` + pinned per-arch `sha256` + fail-closed `assert`). The one place it does _not_ use the obvious module is launchd: it hand-rolls `launchctl bootstrap / bootout / enable / disable / print-disabled` via `command`/`shell` instead of `community.general.launchd`. That is **not** a shortcoming — the module only speaks the legacy `launchctl load/unload` API (states `started/stopped/reloaded/restarted/unloaded`) and cannot target the modern per-user `gui/<uid>` domain with bootstrap/bootout, nor persistently enable/disable a specific label — exactly what this role's session-scoped-bootout-plus-persistent-disable legacy migration requires. Using the module here would be a regression.

**Genuine minor nits (tightening, not "improper"):**

1. Downloads to a fixed `/tmp/openobserve.tar.gz` rather than a `tempfile`-created path — predictable-path nit, mitigated by the checksum verify.
2. "Install-if-absent, never upgrade" is intentional (comment says so), but a `serverapp_openobserve_version` bump won't roll forward without manually removing the binary first.

## Recommendation (revised)

**Do not adopt any tool on the list. Extend the VictoriaMetrics + Grafana + OpenObserve stack you already own.** Every candidate is either not brew-installable, needs Docker, or duplicates VictoriaMetrics — and none is provisioned by your site-contract, so each would be an unmanaged one-off.

The active+passive gap closes with **zero new platform**:

- **Active checks:** keep `access_monitor.py` / `fleet_health_monitor.py`. Have them emit metrics (a `probe_up{device=…}` gauge) instead of only firing macOS notifications, so Grafana/VM sees reachability history.
- **Passive/heartbeat:** already works today — verified: `POST http://127.0.0.1:8428/api/v1/import/prometheus` with `heartbeat_probe 1` returned **HTTP 204**. Each watchdog / `stayturgid_repair.py` loop pushes a `heartbeat_timestamp{source=…}` metric on each cycle; you alert on staleness (`time() - heartbeat_timestamp > threshold`). No new software.
- **Alerting** — two in-stack options, no Docker:
  1. **OpenObserve built-in alerts** (lower effort) — it's already running; native alert rules + webhook destination → the existing **Hermes Telegram gateway**.
  2. **vmalert** — Prometheus-style rules over VM. No brew formula, so add a direct-binary launchd role (`serverapp_vmalert`) exactly like `serverapp_openobserve` already does. More work but keeps alerting rules next to the TSDB.

## Suggested next step (only if you want to proceed)

Pilot the passive side first, since it needs no new binary: add a `heartbeat_timestamp` push (single `curl -XPOST …/api/v1/import/prometheus`) into `stayturgid_repair.py`'s loop and into the AutoJs6 watchdog cycle, add one OpenObserve alert rule on staleness wired to the Hermes Telegram gateway, and confirm the alert fires when a source goes dark. Roll out to the rest of the fleet checks after that proves out.
