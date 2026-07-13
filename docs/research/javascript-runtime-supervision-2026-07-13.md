# JavaScript Runtime Supervision Evaluation

**Date:** 2026-07-13  
**Status:** Evaluation complete; no runtime change authorized

## Scope and current architecture

The operational JavaScript is the AutoJs6 project in
[`device/autojs6/`](../../device/autojs6/). It runs `main.js` inside an Android
application process and uses Android accessibility, Shizuku, `shell()`,
`app.startService()`, shared-storage APIs, and AutoJs6 timers. Termux is the primary
repair/supervisor layer; AutoJs6 is the redundant co-monitor and catastrophic
no-shell UI recovery path. The Mac control plane uses Python, Ansible, launchd, ADB,
and FIRERPA.

## PM2 findings

PM2's official documentation supports ecosystem files, restart policies, memory
limits, file-watch restart, startup hooks, log management, and `pm2 monit`. Its
source was inspected in `~/src/pm2` (a shallow clone of `Unitech/pm2`). PM2 is a
Node.js process manager: the managed program must be a Node-compatible executable
that PM2 can spawn and signal.

PM2 could supervise a genuine Node process launched in Termux. It cannot start or
restart the AutoJs6 Android activity, grant or detect accessibility consent, invoke
AutoJs6's Shizuku APIs, repair wireless ADB/Shizuku/SSH, replace Termux:Boot, or
provide fleet-level health and Ansible desired state. Wrapping `main.js` in PM2
would supervise a separate Node process, not the AutoJs6 engine and Android process;
porting it to Node would remove the platform APIs required for catastrophic recovery.

## Alternatives

| Option | Fit | Decision |
|---|---|---|
| PM2 | Good Node process restart/logging; no Android/AutoJs6 lifecycle control | Do not adopt for the watchdog |
| Uptime Kuma | External HTTP/TCP/ping/status-page monitoring and alerting; not process supervision or repair | Consider as a read-only dashboard integration |
| Pulumi | TypeScript/JavaScript infrastructure-as-code with desired state and stacks | Do not replace Ansible for Android fleet state |
| Jest | Node/JavaScript unit-test framework | Optional only if the Node test surface grows |
| `zx` | JavaScript wrapper for local shell commands | Not a reason to move Python orchestration to JavaScript |
| Shipit | SSH deployment task runner for Node applications | Redundant with Ansible; no Android consent/state model |
| Flightplan | Older Node SSH command/deployment library | Do not adopt; overlaps Ansible and has weaker maintenance signals |
| `runit`/Termux:Boot | Already used for Termux services; appropriate for native on-device daemons | Keep |
| `s6`/`supervisord` | Adds another daemon/config layer and still cannot control AutoJs6 | No |
| Android WorkManager/JobScheduler | Cannot satisfy accessibility/UI recovery and consent gates without an Android app change | No |
| TypeScript tools (`tsx`, `ts-node`, Taskfile/mise) | Developer ergonomics or command running, not Android supervision | Not relevant |

## Detailed findings

### Uptime Kuma — useful observer, not a replacement supervisor

Uptime Kuma monitors externally observable services such as HTTP/HTTPS, TCP, ping,
DNS, JSON, and Docker, and offers history, notifications, and status pages. That
maps well to the existing dashboard's public service checks and could provide a
convenient independent view of the landing page, dashboard, SSH/FIRERPA health
endpoints, and selected device ports. It cannot inspect AutoJs6 logs or repair a
phone. If adopted, run it on the Mac or a stable server and feed it read-only
health endpoints; do not install it on the phones or make it the source of truth.

### Pulumi — infrastructure configuration, not JavaScript runtime management

Pulumi runs TypeScript/JavaScript (and other languages) to compute desired
infrastructure state. It could theoretically model cloud DNS, a VPS, or other
provider resources, but the core fleet is Android over ADB/SSH with human-gated
accessibility and Shizuku state. The existing Ansible collection already owns that
boundary, and introducing Pulumi would create two desired-state authorities. Keep
Pulumi out unless a separate cloud-infrastructure project appears.

### Jest — testing only

Jest is a Node/JavaScript test framework, not a monitor or deployment system. The
current AutoJs6 tests intentionally run portable logic under Node with a small fake
AutoJs6 environment. Jest could replace that harness only after a measured migration
benefit; it would not execute AutoJs6 APIs and would not improve device health.

### `zx` — nicer JavaScript shell scripts, but conflicts with the project boundary

`zx` wraps `child_process` with quoting and convenient async command execution. It
could make a small Mac-only command wrapper pleasant, but substantive orchestration,
retries, parsing, and health decisions are explicitly Python in this project. Using
`zx` would add Node/npm dependencies without replacing Ansible or the existing
Python libraries. Prefer Python for new logic; use `zx` only for a clearly bounded
developer convenience script.

### Shipit and Flightplan — deployment helpers superseded here

Both tools express local/remote SSH deployment tasks for Node applications. They do
not understand Ansible inventory, Android package/UI consent, ADB serial selection,
screen-control leases, or the project's healing registry. Shipit is redundant with
the current Ansible deployment roles; Flightplan is an older library with limited
current ecosystem signals. Neither should be introduced into fleet deployment.

## Recommendation

Do not replace AutoJs6's watchdog or the Termux/Python supervisor with PM2. The
existing layers have the privileges and recovery channels they need; PM2 would add
installation, boot, logging, and failure surface without automating the hard Android
work.

If a future feature introduces a genuine long-running Node service in Termux, use a
small additive S24-only pilot: one `ecosystem.config.cjs`, bounded restart/memory
settings, explicit log paths, a fleet-health probe, Termux:Boot integration behind
an explicit flag, resource measurements, and tested rollback. It must not own
AutoJs6, wireless ADB, Shizuku, accessibility, or the Python repair path.

## Sources

- [PM2 overview](https://pm2.io/docs/runtime/overview/)
- [PM2 ecosystem file reference](https://pm2.io/docs/runtime/reference/ecosystem-file/)
- [PM2 process management and `pm2 monit`](https://pm2.io/docs/runtime/guide/process-management/)
- [PM2 startup hook](https://pm2.io/docs/runtime/guide/startup-hook/)
- [Uptime Kuma project](https://github.com/louislam/uptime-kuma)
- [Pulumi JavaScript/TypeScript SDK](https://www.pulumi.com/docs/iac/languages-sdks/javascript/)
- [Jest](https://jestjs.io/)
- [Google `zx`](https://github.com/google/zx)
- [Shipit CLI](https://www.npmjs.com/package/shipit-cli)
- [Flightplan package](https://www.npmjs.com/package/flightplan)
- Local source checkout: `~/src/pm2` (shallow clone inspected 2026-07-13)
