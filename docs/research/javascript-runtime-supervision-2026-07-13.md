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
| `runit`/Termux:Boot | Already used for Termux services; appropriate for native on-device daemons | Keep |
| `s6`/`supervisord` | Adds another daemon/config layer and still cannot control AutoJs6 | No |
| Android WorkManager/JobScheduler | Cannot satisfy accessibility/UI recovery and consent gates without an Android app change | No |
| TypeScript tools (`tsx`, `ts-node`, Taskfile/mise) | Developer ergonomics or command running, not Android supervision | Not relevant |

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
- Local source checkout: `~/src/pm2` (shallow clone inspected 2026-07-13)
