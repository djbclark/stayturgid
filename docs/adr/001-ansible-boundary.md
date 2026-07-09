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
| Pre-SSH bootstrap | `termux_ssh_bootstrap` + `bootstrap.yml` |
| Termux packages, files, sshd, SSH mesh | `termux_userland` role |
| VPN, app stores, privileges | domain roles + adb modules |
| Deploy orchestration | `site.yml` (bootstrap → fleet → post-ui → validate) |
| Post-deploy checks | `validate.yml` + `stayturgid_repair_check` |
| Mac launchd | `mac.yml` (localhost) |

## Out of Ansible (by design)

| Concern | Why |
|---------|-----|
| `stayturgid-repair` loop, boot loop, repair bridge | Must run when SSH/adb is down |
| AutoJs6 `main.js` watchdog | Runtime interval + notifications |
| Obtainium / Aurora / AutoJs6 drawer UI | On-device Python (`stayturgid_*`) via Termux `localhost:5555`; Mac wrappers SSH-invoke with Mac adb fallback (hd8 = Mac adb only — no Fire OS loopback) |
| Catastrophic Shizuku accessibility tap | Only recovery when shell is gone |
| Play silent install | No consumer API without MDM |
| PIN unlock, Play Protect, DHCP LAN | Environmental |
| Optional LLM escalation (shell-gpt) | Future — [docs/research/on-device-llm.md](../research/on-device-llm.md); never hot-path |

Post-UI scripts (`import_catalog.py`, `configure_aurora.py`,
`enable_autojs6_shizuku.py`) are **invoked from** `post-ui.yml` as
`ansible.builtin.command` — orchestration is Ansible; execution prefers
on-device SSH (s24/p7a) and falls back to Mac adb (USB or wireless). hd8 is
Mac adb only because Fire OS has no Termux→`localhost:5555` privileged shell.

## Consequences

- `deploy_fleet.py` is a thin wrapper: SSH preflight + `ansible-playbook site.yml`.
- `harden_fleet_apps.py` is redundant with `app_privileges` role; CLI kept for ad-hoc use only.
- New fleet features: default to module/role first; script only when UI or runtime requires it.
- `make verify` / `device_tier.py` remain the deep TAP harness; `validate.yml` is the Ansible smoke path.

## Non-goals

MDM, root, rebuilding logic in Tasker, fake declarative modules over UI taps,
waiting for Obtainium state API.
