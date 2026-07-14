# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview.

## By module

| Module | README | Use when you want… |
|--------|--------|-------------------|
| Termux runtime | [docs/modules/termux.md](modules/termux.md) | Boot self-heal, repair script, presence indicator |
| Ansible | [ansible/README.md](../ansible/README.md) | Idempotent Termux deploy over SSH |
| Control node | [docs/modules/control.md](modules/control.md) | ADB reconnect, fleet health, **Hermes gateway**, **phone→Mac ET** (`et_mac`), deploy |
| AutoJs6 | [docs/modules/autojs6.md](modules/autojs6.md) | JS watchdog (only automation stack in repo) |
| Obtainium | [docs/modules/obtainium.md](modules/obtainium.md) | GitHub APK catalog and updates |
| F-Droid / Neo Store | [docs/modules/fdroid.md](modules/fdroid.md) | F-Droid repos + Neo Store (**parked** by default) |
| Play / Aurora Store | [docs/modules/play.md](modules/play.md) | Aurora + apkeep/gplaycli (**parked** by default) |
| Shared libraries | [control/lib/README.md](../control/lib/README.md) | `resolve-adb`, repo-root discovery, UI parse |
| Screen-control lease | [docs/modules/screen-control-lease.md](modules/screen-control-lease.md) | Cross-project glass lock (DSCL v1; interop prompt) |

## Project-wide

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Everyone — hub + full-stack quick path |
| [docs/hacking.md](hacking.md) | Developers — clean install, Obtainium, Termux swap |
| [docs/handoff.md](handoff.md) | AI agents / maintainers — **session start:** `make health`; **2026-07-10 reorg:** read Cold-start first; **[`.cursor/rules/`](../.cursor/rules/)** |
| [docs/coding-rules.md](coding-rules.md) | Durable implementation, device-safety, test, Git, and done rules |
| [`.cursor/rules/`](../.cursor/rules/) | Always-on AI agent rules (self-heal, screen-control hold, …) — **read on handoff** |
| [docs/architecture.md](architecture.md) | Repo layout (`control/`, `device/`, `catalogs/`, `docs/`) |
| [docs/options.md](options.md) | Open work menu |
| [plans/outstanding-fix-priorities-2026-07-13.md](plans/outstanding-fix-priorities-2026-07-13.md) | Ordered reliability work + junior-agent resume prompt |
| [plans/just-migration-plan.md](plans/just-migration-plan.md) | Staged GNU Make → `just` migration after reliability fixes |
| [prompts/dashboard-framework-research.md](prompts/dashboard-framework-research.md) | Self-contained prompt for evaluating dashboard / ops frameworks as a foundation |
| [docs/other-sites.md](other-sites.md) | Multi-site adoption, control-node OS matrix |
| [docs/vlm.md](vlm.md) | UI-TARS vision gates |
| [adr/001-ansible-boundary.md](adr/001-ansible-boundary.md) | Ansible 80/20 boundary (ADR 001) |
| [adr/002-ansible-ui-tasks.md](adr/002-ansible-ui-tasks.md) | UI tasks vs modules (ADR 002) |
| [ansible_collections/roles/validate.md](ansible_collections/roles/validate.md) | Post-deploy validate role |
| [ansible_collections/playbooks/preflight.md](ansible_collections/playbooks/preflight.md) | SSH preflight playbook |

## `docs/research/` — production-adjacent (agents should read)

Findings that inform **shipping** fleet behavior (Handsets, Fire OS, UI drivers).

| Doc | Topic |
|-----|-------|
| [research/ui-automation.md](research/ui-automation.md) | Handsets vs u2; Mac/Termux driver status |
| [research/handsets-under-termux.md](research/handsets-under-termux.md) | Termux wire client + peer bootstrap |
| [research/handsets-vs-u2-bench.md](research/handsets-vs-u2-bench.md) | Bench numbers |
| [research/fire-os-local-adb.md](research/fire-os-local-adb.md) | Fire HD loopback ADB limits |
| [research/fire-os-google-play.md](research/fire-os-google-play.md) | Fire HD Google Play / GMS stack |
| [research/mac-android-ui-automation.md](research/mac-android-ui-automation.md) | Mac→Android UI playbook |
| [research/autojs6-project-import-questions.md](research/autojs6-project-import-questions.md) | Questions for AutoJs6 maintainer about existing-project import and launch |
| [research/autojs6-hd8-project/](research/autojs6-hd8-project/) | Reference copy of the hd8 AutoJs6 project files that actually ran |
| [research/text-based-android-config.md](research/text-based-android-config.md) | Best practices for adding text-based configuration to Android apps; candidate apps in the stayturgid stack |

## `docs/incubator/` — parked side projects (do not implement)

Speculative / alternate architectures. Index:
[incubator/README.md](incubator/README.md).

| Path | Status |
|------|--------|
| [incubator/inferno-styx/](incubator/inferno-styx/) | Parked — Inferno/Styx fleet control |
| [incubator/on-device-llm.md](incubator/on-device-llm.md) | Optional spike (OPTIONS **54** only if asked) |
| [incubator/tablet-control-phone.md](incubator/tablet-control-phone.md) | Parked proposal — hd8→s24 Termux:X11 + scrcpy at tablet native res |

## Other

| Path | Notes |
|------|--------|
| [version.json](../version.json) | Repo release version; optional on-device version notifier |
| [examples/](../examples/) | Consumer Ansible playbooks plus standalone FIRERPA non-root `justfile` |
| [history/code-and-docs-review-2026-07-10.md](history/code-and-docs-review-2026-07-10.md) | Full code + docs review (2026-07-10); see also [history/code-review.md](history/code-review.md) |
| [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md) | Operator tasks (credentials, deploy approval) — human-only |

## Typical combinations

- **Termux only:** `device/termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **Full stack:** `device/termux/` + `device/autojs6/` + `catalogs/obtainium/` + `control/bin/` + `make deploy`
  (Neo/Aurora app stores **parked** unless `stayturgid_app_stores_enabled: true`)
- **Obtainium only:** `catalogs/obtainium/` — APK updates without stayturgid watchdog
