# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview.

## By module

| Module | README | Use when you want… |
|--------|--------|-------------------|
| Termux runtime | [docs/modules/termux.md](modules/termux.md) | Boot self-heal, repair script, presence indicator |
| Ansible | [ansible/README.md](../ansible/README.md) | Idempotent Termux deploy over SSH |
| Control node | [docs/modules/control.md](modules/control.md) | ADB reconnect launchd, outage monitor, deploy |
| AutoJs6 | [docs/modules/autojs6.md](modules/autojs6.md) | JS watchdog (only automation stack in repo) |
| Obtainium | [docs/modules/obtainium.md](modules/obtainium.md) | GitHub APK catalog and updates |
| F-Droid / Neo Store | [docs/modules/fdroid.md](modules/fdroid.md) | F-Droid repos + Neo Store (**parked** by default) |
| Play / Aurora Store | [docs/modules/play.md](modules/play.md) | Aurora + apkeep/gplaycli (**parked** by default) |
| Shared libraries | [control/lib/README.md](../control/lib/README.md) | `resolve-adb`, repo-root discovery, UI parse |

## Project-wide

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Everyone — hub + full-stack quick path |
| [docs/hacking.md](hacking.md) | Developers — clean install, Obtainium, Termux swap |
| [docs/handoff.md](handoff.md) | AI agents / maintainers — **session start:** `make health` |
| [docs/options.md](options.md) | Open work menu |
| [docs/other-sites.md](other-sites.md) | Multi-site adoption, control-node OS matrix |
| [docs/vlm.md](vlm.md) | UI-TARS vision gates |
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
| [version.json](../version.json) | Repo release version; optional on-device version notifier |
| [examples/](../examples/) | Consumer Ansible playbooks (shipping patterns) |

## Typical combinations

- **Termux only:** `device/termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **Full stack:** `device/termux/` + `device/autojs6/` + `catalogs/obtainium/` + `control/bin/` + `make deploy`
  (Neo/Aurora app stores **parked** unless `stayturgid_app_stores_enabled: true`)
- **Obtainium only:** `catalogs/obtainium/` — APK updates without stayturgid watchdog
