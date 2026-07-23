<!-- historical: imported 2026-07-23 from an out-of-git AI planning directory; site facts genericized on import (see docs/architecture/multi-site-topology.md §4.1) -->

# Add blackbox_exporter for active multi-protocol monitoring

## Context

`stayturgid` currently has no active check that validates a remote
service actually _responds correctly_ — only raw TCP-connect reachability
(`control/bin/access_monitor.py`, `fleet_health_monitor.py`) and
Prometheus-format metrics self-scraping (VictoriaMetrics). After evaluating
Icinga2 (no macOS packaging — disqualified), Nagios Core (macOS-bottled
only, no Linux bottle, brings its own CGI/config-DSL/alerting stack
parallel to Grafana+VM), Sensu Go (no GitHub release binaries, Linux-first),
and `monitoring-plugins` (authoritative protocol logic but no off-the-shelf
scheduler/pusher into VictoriaMetrics), the confirmed choice — cross-checked
by a second independent review — is **`blackbox_exporter`** (official
Prometheus project): single static Go binary, confirmed prebuilt releases
for `darwin-arm64`/`darwin-amd64`/many `linux-*` archs + `sha256sums.txt`,
~10–20MB idle RSS, no Docker/VM, and it slots into the existing
VictoriaMetrics + Grafana stack as a scrape target rather than standing up
a second TSDB/alerting system.

Decisions already made with the operator:

- **macOS only for this pass.** Every `serverapp_*` role in this repo is
  launchd-only today; there's no Linux host in inventory yet (one is
  anticipated — `the private site overlay inventory (`site-<name>/inventory/hosts.yml`)` already has a
  `vps-primary` placeholder noting "systemd --user unit" for when it's
  provisioned). Structure `defaults/`/`tasks/` so a systemd variant is an
  additive follow-up, not a rework, but don't build/test it now.
- **Seed real targets, not placeholders.** Confirmed via `lsof -iTCP
-sTCP:LISTEN` on this Mac plus the real site inventory
  (`the private site overlay inventory (`site-<name>/inventory/hosts.yml`)`) — see Targets section.
- **Include Grafana alerting-as-code**, even though `serverapp_grafana`
  has no alerting provisioning today (only datasources/dashboards) — see
  the secrets-handling design below, which is the one place this deviates
  from a pure copy-paste of the datasources precedent.

## New role: `ansible/roles/serverapp_blackbox_exporter/`

Mirror `serverapp_openobserve` exactly (it's the existing precedent for
"install a GitHub-release binary Ansible has no dedicated module for"):

- `defaults/main.yml` — `serverapp_blackbox_exporter_version`, per-arch
  `sha256` map (fetch and hash both `darwin-arm64`/`darwin-amd64` archives
  at pin time, same as the OpenObserve role's comment documents), bin path
  `~/.local/bin/blackbox_exporter`, config dir
  `~/.config/{{ site_ns }}/blackbox_exporter/`, HTTP port default `9115`.
- `templates/blackbox.yml.j2` — the exporter's own module definitions:
  `http_2xx` (HTTP/HTTPS via `tls_config`), `tcp_connect`, `ssh_banner`
  (tcp module, `query_response: [{expect: "^SSH-2.0-"}]` — the same
  technique `check_ssh` uses), `smtp_starttls` (tcp module scripted
  `EHLO`/`STARTTLS`/`EHLO` sequence, per blackbox's own example config),
  `icmp` (best-effort — see ICMP note below), `dns_udp`.
- `templates/blackbox_exporter.plist.j2` — launchd plist, same shape as
  OpenObserve's/Grafana's (`--config.file`, `--web.listen-address`).
- `tasks/main.yml` — same lifecycle as `serverapp_openobserve/tasks/main.yml`:
  stat-check → arch detect → fail-closed checksum assert → `get_url` →
  `unarchive` → copy binary → render `blackbox.yml` + plist → legacy-label
  probe/cutover (new role, so this can be simpler — no legacy label to
  migrate away from) → `launchctl bootstrap` by hand (not
  `community.general.launchd`, for the same reason OpenObserve avoids it:
  need the modern per-user `gui/<uid>` domain and persistent enable/disable
  semantics the module doesn't expose) → health check against
  `/probe?target=127.0.0.1&module=http_2xx`.
- **ICMP verification task**: after bootstrap, do one real
  `GET /probe?target=127.0.0.1&module=icmp` and check `probe_success=1` in
  the response body — macOS _usually_ allows unprivileged ICMP via Go's
  `x/net/icmp` datagram-socket path, but this must be confirmed under the
  actual `gui/<uid>` launchd context per the second-opinion review, not
  assumed. If it fails, drop the `icmp` scrape job (module stays defined,
  just unused) and log why, rather than silently shipping a broken check.
- `meta/main.yml` — standard.
- New entry playbook `ansible/playbooks/serverapps/blackbox_exporter.yml`,
  identical shape to `openobserve.yml`.

## Wiring into the Site Contract (mirrors the openobserve/VM precedent)

- `control/site_contract/serverapps.py`: add `"blackbox_exporter"` to
  `KNOWN_APPS`; add `_blackbox_exporter_detect_paths()` (foreign-unit guard,
  same shape as `_openobserve_detect_paths`); add
  `plan_blackbox_exporter()` (same shape as `plan_victoriametrics`/
  `plan_openobserve` — dirs, config render, plist render, health url);
  wire it into the app-dispatch block near the existing
  `if app == "openobserve":` / victoriametrics cases.
- `control/site_contract/site_map.py`: add `"blackbox_exporter"` to
  `ALLOWED_SERVERAPPS` (wherever that frozenset lives alongside
  `ALLOWED_TOP_LEVEL_KEYS`) so site inventory can declare
  `serverapps.blackbox_exporter.mode: own`.
- `control/site_contract/templates/registry/ports.yml`: add a
  `control_node` entry, port `9115`, `bind: 127.0.0.1`, service
  `blackbox-exporter`, `source:` pointing at the new role's defaults.
- `control/site_contract/templates/registry/paths.yml`: add
  `~/.local/bin/blackbox_exporter` and
  `~/.config/stayturgid/blackbox_exporter/**` under the `stayturgid`
  prefix list, with `claim_sources` entries, matching the OpenObserve
  binary/data-dir entries already there.

## VictoriaMetrics scrape wiring

`ansible/roles/serverapp_victoriametrics/templates/scrape.yml.j2` currently
only self-scrapes (confirmed — no target-list variable exists yet). Add:

- A new `serverapp_victoriametrics_blackbox_targets` variable (in
  `defaults/main.yml`, or fed through by `serverapps.py`'s
  `plan_victoriametrics()` the same way other per-role vars are threaded)
  structured as `{module: [target, ...]}` groups.
- Scrape jobs using the standard Prometheus blackbox relabel pattern (one
  job per module, `params: {module: [<name>]}`, target list, then
  `relabel_configs` rewriting `__address__` → the blackbox exporter's own
  `127.0.0.1:9115` and setting `__param_target`/`instance` from the
  original target). This is a well-documented, standard pattern — not
  something to invent per-target.

### Targets to seed (confirmed real, not placeholders)

From `lsof -iTCP -sTCP:LISTEN` on this Mac + the real
`the private site overlay inventory (`site-<name>/inventory/hosts.yml`)`:

- **`ssh_banner` module** — the three actual fleet devices' Termux SSH
  endpoints (port 8022 per `ansible_port` in inventory), over Tailscale:
  `100.0.0.11:8022` (oneui-device), `100.0.0.12:8022` (stock-android-device),
  `100.0.0.13:8022` (fireos-device). This is a real, currently-unmonitored gap:
  `access_monitor.py` checks ADB reachability, not the SSH port itself.
- **`http_2xx` module** — Caddy front door: `127.0.0.1:80`, `127.0.0.1:8080`
  (and `:443` if TLS is locally trusted; check Caddy's cert setup before
  wiring the https target — may need `tls_config.insecure_skip_verify` for
  a local/internal cert).
- **`tcp_connect` module** — the other locally-managed serverapp ports as a
  cheap "did the daemon silently die between deploys" check: Grafana
  `:3000`, OpenObserve `:5080`, VictoriaMetrics `:8428` (redundant with its
  self-scrape `up` series, but cheap), OliveTin `:1337`.

Not in scope for this pass: anything outside current inventory (no blind
LAN/Tailscale nmap sweep — the real inventory already tells us what's
there, scanning further would be probing hosts with no documented purpose).

## Grafana alerting-as-code (the one genuinely new pattern)

`serverapp_grafana`'s provisioning dir
(`{{ site_dir }}/generated/stayturgid/fragments/grafana/`) is a **git-tracked,
site-sync-owned tree** — confirmed by reading `datasources/stayturgid.yaml`,
whose own comment explicitly avoids embedding OpenObserve's basic-auth
credential for exactly this reason ("no secrets here"). A Telegram contact
point's bot token cannot go through that same committed-fragment pipeline.

Split by whether the content is a secret:

- **Notification policy + alert rule group (no secret material)** — add
  through the normal site-sync fragment pipeline, same as datasources:
  - New template `control/site_contract/sync_templates/fragments/grafana/alerting/rules.yaml.j2`
    — one rule group querying `probe_success == 0` (and optionally
    `probe_http_status_code`) from the `stayturgid-victoriametrics`
    datasource UID already defined in `datasources/stayturgid.yaml`,
    routed to a contact point referenced **by UID only**.
  - Register the new file in `control/site_contract/sync_manifest.yml`
    (the manifest that drives which templates site-sync renders — same
    list the datasources/dashboards fragments are already in).
- **Contact point (the Telegram bot token — a real secret)** — do **not**
  render it into the committed fragments tree. Instead, add an idempotent
  `ansible.builtin.uri` task in `serverapp_grafana/tasks/main.yml` (after
  the existing health-check step) that `POST`s/`PUT`s the contact point via
  Grafana's Alerting HTTP API, with the token sourced via
  `lookup('env', 'TELEGRAM_BOT_TOKEN')` and `no_log: true` — the same
  "operator sets an env var once, role applies it, never touches git"
  precedent already used for Hermes's bot token
  (`ansible/roles/control_node/tasks/hermes.yml`). This avoids the secret
  ever landing in a file under the site-sync-managed prefix at all,
  tracked or not.
- Reuse vs. new bot: flag for the operator to decide — reusing the
  existing Hermes bot (separate chat/channel) vs. registering a second
  bot for alerting is a judgment call, not something to assume.

## Verification

1. `ansible-playbook ansible/playbooks/serverapps/blackbox_exporter.yml`
   (or the `site-serverapps apply` entry point) — role converges,
   `launchctl print gui/<uid>/com.<site_ns>.blackbox_exporter` shows loaded.
2. `curl 'http://127.0.0.1:9115/probe?target=127.0.0.1&module=http_2xx'`
   → `probe_success 1`. Repeat for `ssh_banner` against one real device IP,
   and `icmp` against `127.0.0.1` (confirms/denies the permission question
   instead of assuming it).
3. Re-run site-sync / `site-serverapps apply` for `victoriametrics` — confirm
   the regenerated `scrape.yml` includes the new blackbox jobs, and
   `curl 127.0.0.1:8428/api/v1/query?query=probe_success` shows the new
   series.
4. Confirm the new Grafana alert rule fragment renders and Grafana's
   `/api/v1/provisioning/alert-rules` lists it; confirm the contact-point
   API task is idempotent (second run reports `changed: false`) and does
   **not** print the token (`no_log` verified in the run output).
5. Kill one monitored device's SSH (or block port 8022 briefly) and confirm
   a Telegram alert fires within the configured evaluation interval.
6. `just syntax && just check && just lint` (or repo's equivalent) green
   in both `stayturgid` and `site-djbclark`.
