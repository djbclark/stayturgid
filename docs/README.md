# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview.

## By module

| Module | README | Use when you want… |
|--------|--------|-------------------|
| Termux scripts | [termux/README.md](../termux/README.md) | Boot self-heal, repair script, presence indicator |
| Ansible | [ansible/README.md](../ansible/README.md) | Idempotent Termux deploy over SSH |
| Mac tools | [mac/README.md](../mac/README.md) | ADB reconnect launchd, outage monitor |
| AutoJs6 | [autojs6/README.md](../autojs6/README.md) | JS watchdog (only automation stack in repo) |
| Obtainium | [obtainium/README.md](../obtainium/README.md) | GitHub APK catalog and updates |
| F-Droid / Neo Store | [fdroid/README.md](../fdroid/README.md) | F-Droid repos + Neo Store (**parked** by default) |
| Play / Aurora Store | [play/README.md](../play/README.md) | Aurora + apkeep/gplaycli (**parked** by default) |
| Shared helpers | [shared/README.md](../shared/README.md) | `resolve-adb`, repo-root discovery |

## Project-wide

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Everyone — hub + full-stack quick path |
| [HACKING.md](../HACKING.md) | Developers — clean install, Obtainium, Termux swap |
| [HANDOFF.md](../HANDOFF.md) | AI agents / maintainers — **session start:** `make health` |
| [OPTIONS.md](../OPTIONS.md) | Open work menu |
| [adr/001-ansible-boundary.md](adr/001-ansible-boundary.md) | Ansible 80/20 boundary (ADR 001) |
| [adr/002-ansible-ui-tasks.md](adr/002-ansible-ui-tasks.md) | UI tasks vs modules (ADR 002) |
| [../ansible_collections/docs/roles/validate.md](../ansible_collections/docs/roles/validate.md) | Post-deploy validate role |
| [../ansible_collections/docs/playbooks/preflight.md](../ansible_collections/docs/playbooks/preflight.md) | SSH preflight playbook |

## `docs/research/` — production-adjacent (agents should read)

Findings that inform **shipping** fleet behavior (Handsets, Fire OS, UI drivers).

| Doc | Topic |
|-----|-------|
| [research/ui-automation.md](research/ui-automation.md) | Handsets vs u2; Mac/Termux driver status |
| [research/handsets-under-termux.md](research/handsets-under-termux.md) | Termux wire client + peer bootstrap |
| [research/handsets-vs-u2-bench.md](research/handsets-vs-u2-bench.md) | Bench numbers |
| [research/fire-os-local-adb.md](research/fire-os-local-adb.md) | Fire HD loopback ADB limits |

## `docs/incubator/` — parked side projects (do not implement)

Speculative / alternate architectures. Index:
[incubator/README.md](incubator/README.md).

| Path | Status |
|------|--------|
| [incubator/inferno-styx/](incubator/inferno-styx/) | Parked — Inferno/Styx fleet control |
| [incubator/on-device-llm.md](incubator/on-device-llm.md) | Optional spike (OPTIONS **54** only if asked) |

## Other

| Path | Notes |
|------|--------|
| [version.json](../version.json) | Repo release version; optional `termux/check-repo-version.sh` notifier |
| [examples/](../examples/) | Consumer Ansible playbooks (shipping patterns) |

## Typical combinations

- **Termux only:** `termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **Full stack:** `termux/` + `autojs6/` + `obtainium/` + `mac/` + `make deploy`
  (Neo/Aurora app stores **parked** unless `stayturgid_app_stores_enabled: true`)
- **Obtainium only:** `obtainium/` — APK updates without stayturgid watchdog
