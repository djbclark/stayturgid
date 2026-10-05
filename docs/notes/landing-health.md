# Jobber landing-health

Hourly Jobber job `landing-health` on the Mac control node.

## What it is

1. Jobber `~/.jobber` → `~/.local/bin/landing-health` (site-djbclark `roles/site_agents`).
2. That wrapper runs `control/landing/discover.py --health-check`.
3. Exit 1 pages Telegram Inbox. Jobber's snippet is **stderr-only**.

## What is allowed to fail the check

1. A Mac `must_be_up` listener (site/stayturgid-owned, `status: active`, `must_be_up` not false) whose port does not accept TCP.
2. A `dashboard: true` launchd job that is not running (`launchd://…`).

## What must not page

1. Offline phones and Android devices (`group: devices` / `android`) — p7a/hd8 being off Tailscale is expected.
2. Unmanaged / observed apps.
3. Registry rows with `must_be_up: false` (ephemeral IPC, deliberately disabled Open WebUI, etc.).
4. HTTP 4xx on a port that **is** listening — that is not an outage.

## Do not

1. Treat three `site directory` lines as the diagnosis — that is the site-discovery announce on stderr, not the check result.
2. Probe hosts serially in `--health-check` (Jobber hung ~90s on dead SSH).
3. "Fix" landing-health by disabling the Jobber job or widening notifyOnError.
4. Count every registered port as must-be-up. Default-up is only local Mac listeners that this machine is supposed to run.

## Diagnose

```bash
landing-health
python3 ~/ops/stayturgid/control/landing/discover.py --health-check
```

A healthy run prints `registered-down` 0 and may print `Expected-offline: N`.
