# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview.

## By module

| Module                            | README                                                                                                  | Use when you want…                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Termux runtime                    | [docs/architecture/components/termux.md](architecture/components/termux.md)                             | Boot self-heal, repair script, presence indicator                                    |
| Ansible                           | [ansible/README.md](../ansible/README.md)                                                               | Idempotent Termux deploy over SSH                                                    |
| Control node                      | [docs/architecture/components/control.md](architecture/components/control.md)                           | ADB reconnect, fleet health, **Hermes gateway**, **phone→Mac ET** (`et_mac`), deploy |
| AutoJs6 (retired, reference only) | [docs/architecture/components/autojs6.md](architecture/components/autojs6.md)                           | Legacy JS watchdog, replaced fleet-wide by the native agent (K1, 2026-07-22)         |
| Obtainium                         | [docs/architecture/components/obtainium.md](architecture/components/obtainium.md)                       | GitHub APK catalog and updates                                                       |
| F-Droid / Neo Store               | [docs/architecture/components/fdroid.md](architecture/components/fdroid.md)                             | F-Droid repos + Neo Store (**parked** by default)                                    |
| Play / Aurora Store               | [docs/architecture/components/play.md](architecture/components/play.md)                                 | Aurora + apkeep/gplaycli (**parked** by default)                                     |
| Shared libraries                  | [control/lib/README.md](../control/lib/README.md)                                                       | `resolve-adb`, repo-root discovery, UI parse                                         |
| Screen-control lease              | [docs/architecture/components/screen-control-lease.md](architecture/components/screen-control-lease.md) | Cross-project glass lock (DSCL v1; interop prompt)                                   |

## Project-wide

| Doc                                                                                                              | Audience                                                                                                                            |
| ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [README.md](../README.md)                                                                                        | Everyone — hub + full-stack quick path                                                                                              |
| [docs/hacking.md](hacking.md)                                                                                    | Developers — clean install, Obtainium, Termux swap                                                                                  |
| [docs/STATUS.md](STATUS.md)                                                                                      | **Start here** — current fleet/workstream state, known gotchas, operator queue                                                      |
| [docs/handoff.md](handoff.md)                                                                                    | Thin pointer to STATUS.md + sessions + the private site overlay contract                                                            |
| [docs/coding-rules.md](coding-rules.md)                                                                          | Durable implementation, device-safety, test, Git, and done rules                                                                    |
| [`docs/rules/`](rules/)                                                                                          | Always-on AI agent rules (normal-deploy convergence, self-heal, screen-control hold, GitHub issues) — **read on handoff**            |
| [docs/notes/lessons-learned.md](notes/lessons-learned.md)                                                        | Session-learned gotchas and conventions, narrower than coding-rules.md/docs/rules/                                                  |
| [docs/architecture/core-architecture.md](architecture/core-architecture.md)                                      | Repo layout (`control/`, `device/`, `catalogs/`, `docs/`)                                                                           |
| [docs/options.md](options.md)                                                                                    | Strategic/deferred work menu with stable IDs (discrete bugs live in [GitHub issues](https://github.com/djbclark/stayturgid/issues)) |
| [operations/sessions/](operations/sessions/)                                                                     | Session-by-session history, newest handoffs included                                                                                |
| [docs/archive/](archive/)                                                                                        | Superseded plans and old sessions — historical record only                                                                          |
| [operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md](operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md) | Active F1 FIRERPA MCP bridge implementation plan (decisions D1–D3 resolved)                                                         |
| [prompts/dashboard-framework-research.md](research/prompts/dashboard-framework-research.md)                      | Self-contained prompt for evaluating dashboard / ops frameworks as a foundation                                                     |
| [docs/architecture/multi-site-topology.md](architecture/multi-site-topology.md)                                  | Multi-site adoption, control-node OS matrix                                                                                         |
| [adr/001-ansible-boundary.md](architecture/adr/001-ansible-boundary.md)                                          | Ansible 80/20 boundary (ADR 001)                                                                                                    |
| [adr/002-ansible-ui-tasks.md](architecture/adr/002-ansible-ui-tasks.md)                                          | UI tasks vs modules (ADR 002)                                                                                                       |
| [ansible_collections/roles/validate.md](ansible/collections/roles/validate.md)                                   | Post-deploy validate role                                                                                                           |
| [ansible_collections/playbooks/preflight.md](ansible/collections/playbooks/preflight.md)                         | SSH preflight playbook                                                                                                              |

## `docs/research/` — production-adjacent (agents should read)

Findings that inform **shipping** fleet behavior (Handsets, Fire OS, UI drivers).

| Doc                                                                                                          | Topic                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| [research/ui-automation.md](research/ui-automation.md)                                                       | Handsets vs u2; Mac/Termux driver status                                                                                      |
| [research/handsets-under-termux.md](research/handsets-under-termux.md)                                       | Termux wire client + peer bootstrap                                                                                           |
| [research/handsets-vs-u2-bench.md](research/handsets-vs-u2-bench.md)                                         | Bench numbers                                                                                                                 |
| [research/fire-os-local-adb.md](research/fire-os-local-adb.md)                                               | Fire HD loopback ADB limits                                                                                                   |
| [research/fire-os-google-play.md](research/fire-os-google-play.md)                                           | Fire HD Google Play / GMS stack                                                                                               |
| [research/mac-android-ui-automation.md](research/mac-android-ui-automation.md)                               | Mac→Android UI playbook                                                                                                       |
| [research/autojs6-project-import-questions.md](research/autojs6-project-import-questions.md)                 | Questions for AutoJs6 maintainer about existing-project import and launch                                                     |
| [research/autojs6-fireos-device-project/](research/autojs6-fireos-device-project/)                           | Reference copy of the fireos-device AutoJs6 project files that actually ran                                                   |
| [research/text-based-android-config.md](research/text-based-android-config.md)                               | Best practices for adding text-based configuration to Android apps; candidate apps in the stayturgid stack                    |
| [research/ansible-pull-architecture-2026-07-14.md](research/ansible-pull-architecture-2026-07-14.md)         | Hybrid `ansible-pull` architecture, security model, staged pilot, and junior-developer implementation guide                   |
| [research/site-identity-source-of-truth-2026-07-14.md](research/site-identity-source-of-truth-2026-07-14.md) | Single authority for hostnames, addresses, serials, generated consumers, runtime observations, and SecretSpec-managed secrets |

## `docs/research/experiments/` — parked side projects (do not implement)

Speculative / alternate architectures. Index:
[incubator/README.md](research/experiments/README.md).

| Path                                                                              | Status                                                                                |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [incubator/inferno-styx/](research/experiments/inferno-styx/)                     | Parked — Inferno/Styx fleet control                                                   |
| [incubator/on-device-llm.md](research/experiments/on-device-llm.md)               | Optional spike (OPTIONS **54** only if asked)                                         |
| [incubator/tablet-control-phone.md](research/experiments/tablet-control-phone.md) | Parked proposal — fireos-device→oneui-device Termux:X11 + scrcpy at tablet native res |

## Other

| Path                                                                                                  | Notes                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [version.json](../version.json)                                                                       | Repo release version; optional on-device version notifier                                                    |
| [examples/](../examples/)                                                                             | Consumer Ansible playbooks plus standalone FIRERPA non-root `justfile`                                       |
| [history/code-and-docs-review-2026-07-10.md](research/evaluations/code-and-docs-review-2026-07-10.md) | Full code + docs review (2026-07-10); see also [history/code-review.md](research/evaluations/code-review.md) |
| [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md)                                                   | Operator tasks (credentials, deploy approval) — human-only                                                   |

## Typical combinations

- **Termux only:** `device/termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **Full stack:** `device/termux/` + `device/autojs6/` + `catalogs/obtainium/` + `control/bin/` + `just deploy`
  (Neo/Aurora app stores **parked** unless `stayturgid_app_stores_enabled: true`)
- **Obtainium only:** `catalogs/obtainium/` — APK updates without stayturgid watchdog
