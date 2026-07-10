# ADR 001: Ansible 80/20 boundary

**Status:** Accepted (2026-07-09)  
**Context:** Portfolio 2 — Ansible-forward consolidation (`site.yml`, thin `deploy_fleet.py`)

## Decision

Fleet **declarative state** is managed by Ansible (collections, roles, composed
playbooks). **Screen-control UI automation** and **on-device runtime self-heal**
stay as Python / AutoJs6 / shell outside Ansible execution at runtime.

Target split: **~80% Ansible / ~20% scripts + on-device logic**.

## In Ansible

| Concern | Mechanism |
|---------|-----------|
| Pre-SSH bootstrap | `termux_ssh_bootstrap` + `preflight.yml` / `bootstrap.yml` |
| Termux packages, files, sshd, SSH mesh | `termux_userland` role |
| VPN, app stores, privileges | domain roles + adb modules |
| Deploy orchestration | `site.yml` (preflight → bootstrap → fleet → post-ui → app-stores re-pass → validate → mac-site) |
| Post-deploy checks | `stayturgid.fleet.validate` + `stayturgid_repair_check` |
| Mac Homebrew prereqs | `mac-prereqs.yml` (`community.general.homebrew`) |
| Mac launchd + conf | `mac.yml` + `mac-site.yml` (localhost) |
| Mac VLM sidecar (optional) | `mac-vlm.yml` (brew `llama.cpp`, models, launchd install + `vlm-ensure` health) |

## Out of Ansible (by design)

| Concern | Why |
|---------|-----|
| `stayturgid-repair` loop, boot loop, repair bridge | Must run when SSH/adb is down |
| AutoJs6 `main.js` watchdog | Runtime interval + notifications |
| Obtainium / Aurora / AutoJs6 drawer UI | On-device Python (`stayturgid_*`) via Termux `localhost:5555`; Mac wrappers SSH-invoke with Mac adb fallback (hd8 = Mac adb only — no Fire OS loopback) |
| Catastrophic Shizuku accessibility tap | Only recovery when shell is gone |
| Play silent install | No consumer API without MDM |
| PIN unlock, Play Protect, DHCP LAN | Environmental |
| Optional LLM escalation (shell-gpt) | Future — [docs/incubator/on-device-llm.md](../incubator/on-device-llm.md); never hot-path |

Post-UI scripts are invoked via `stayturgid.android_common.android_ui` and the
`stayturgid.fleet.post_ui` role (`post-ui.yml`) — orchestration is Ansible;
execution prefers on-device SSH (s24/p7a) and falls back to Mac adb (USB or
wireless). hd8 has no Termux→`localhost:5555` privileged shell (Fire OS); Handsets
starts via **peer bootstrap** (SSH to s24/p7a → remote `adb shell app_process`) or Mac
`ui_driver.py` when the Mac is present.

## Consequences

- `deploy_fleet.py` is a thin wrapper: collection install + `ansible-playbook site.yml`
  (SSH preflight is in `preflight.yml`).
- `harden_fleet_apps.py` is redundant with `app_privileges` role; CLI kept for ad-hoc use only.
- New fleet features: default to module/role first; script only when UI or runtime requires it.
- UI automation: see [002-ansible-ui-tasks.md](002-ansible-ui-tasks.md) — named UI tasks, not per-tap modules.
- `make verify` / `device_tier.py` remain the deep TAP harness; `stayturgid.fleet.validate` is the Ansible smoke path.

## Non-goals

MDM, root, rebuilding logic in Tasker, fake declarative modules over UI taps,
waiting for Obtainium state API.
