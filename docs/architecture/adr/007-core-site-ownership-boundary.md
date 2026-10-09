# ADR 007: Core versus site ownership boundary and ownership manifest

**Status:** Proposed (2026-10-09). Not yet reviewed by the operator; no
implementation has moved.
**Context:** Issue [#50](https://github.com/djbclark/stayturgid/issues/50)
asks for a source-derived inventory of everything stayturgid declares,
deploys, monitors, repairs, serves or documents, and a disposition for each.
A private concern-level matrix was produced on 2026-07-24 and kept in the
private companion repository. On 2026-07-26 the operator shelved its seven
open decisions
([handoff](../../operations/sessions/handoff-2026-07-26-ops-separation-shelved.md)).
Since then AutoJs6, the Obtainium and F-Droid collections, the UI-TARS/VLM
sidecar, the GUI audit and the versioned release regime have been removed or
retired, and the native agent, USB Shizuku heal, FIRERPA MCP server, update
monitor and on-device telemetry have been added. This ADR records the public,
sanitized boundary and the refreshed inventory as of master `0c6047b`. It is
step 1 of the move order below: describe and check ownership, move nothing.

Related: [ADR 005](005-two-repo-topology.md) (two repo kinds),
[site-contract.md](../site-contract.md),
[multi-site-topology.md](../multi-site-topology.md). The stayturgid 2.0 effort
(first tracked as `djbclark/fleetopia#1`, a repository since renamed to
[frdminc/tendcf](https://github.com/frdminc/tendcf/issues/1)) proposes to
settle this inventory in its Phase 0 ("freeze and map"); this ADR and its
manifest are meant to be that map.

## Decision

### Dispositions

Every managed concern gets exactly one disposition.

| Disposition       | Meaning                                                                                              |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| `core`            | Reusable Android fleet capability that works for another operator with generic example config.       |
| `shared-contract` | Generic schema, resolver, generator or adapter interface upstream; concrete data lives in the site.  |
| `core+site-data`  | The mechanism stays upstream; the catalog, schedule, topology or selection it consumes is site data. |
| `split`           | One file or role mixes core and site concerns and has to be divided before anything moves.           |
| `site`            | This site's identity, allocations, control-node services, dashboards, AI stack or workflow.          |
| `private`         | Private or Mac-wide operator administration; neither product nor reusable site overlay.              |
| `retire`          | Obsolete; remove after a caller scan.                                                                |
| `decision-needed` | Waits on one of the operator decisions D1-D7 below.                                                  |

### What stayturgid owns

1. **Core:** fleet orchestration playbooks, generic Android modules, Shizuku
   install and lifecycle, the native agent, device repair and the Termux
   userland framework, SSHD recovery, screen-lease and UI safety, generic UI
   drivers, battery and locate, Tailscale configuration, generic consumer
   examples, collection tests and the developer tooling.
2. **Shared contract (the interface a site overlay consumes):** ADB and
   device-identity resolution, Ansible context and site discovery
   (`ANSIBLE_CONFIG` > `STAYTURGID_SITE_DIR` > `.mysite` > one discovered
   `site-*`), the Site Contract schemas, generators and serverapp adapter
   engine, and the product version that `site-sync` reads.
3. **Core mechanism, site data:** app privileges, bootstrap APK pins, app
   presence, Play adapter, Termux packages, on-device telemetry and FIRERPA.
   The site supplies the catalogs, pins it chooses, schedules and enablement.

### What a site overlay owns

Concrete inventory and host facts, app and package choices, schedules, peer
topology, alert and notification destinations, the landing portal, the
serverapp stack (Caddy, VictoriaMetrics, Vector, OpenObserve, Grafana,
blackbox exporter, OliveTin), Hermes gateway, OpenCode web, the Termux nightly
upgrade job and the update monitor.

### Machine-checkable manifest

[`docs/architecture/ownership-manifest.yml`](../ownership-manifest.yml) maps git
pathspec globs to concerns. It has 55 concerns and covers every tracked file
under `ansible/`, `ansible_collections/`, `control/`, `device/`, `examples/`,
`just/` and the root `justfile`, with no file in two concerns.

| Disposition       | Concerns |
| ----------------- | -------- |
| `core`            | 13       |
| `site`            | 13       |
| `core+site-data`  | 10       |
| `split`           | 7        |
| `shared-contract` | 4        |
| `decision-needed` | 4        |
| `private`         | 2        |
| `retire`          | 2        |

`tests/python/test_ownership_manifest.py` validates the schema on every run.
It also checks that every glob still matches a tracked file and that every
in-scope file belongs to exactly one concern. Those two checks only warn
unless `STAYTURGID_OWNERSHIP_STRICT=1` is set. Making them fail by default is
an operator decision, because it would make every new playbook or script
classify itself before `just test` passes.

Not yet in the manifest: `tests/**`, `docs/**`, `.github/workflows/*` and root
configuration files. They should be added before the check becomes strict.

## Operator decisions

The 2026-07-24 matrix left seven decisions open. Their status from source on
2026-10-09:

| ID  | Question                                                              | Status from source                                                                                                                                                                                          |
| --- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Fleet dashboard: core surface with injectable site links, or site UI? | Open. `dashboard.py` and its launchd agent are maintained.                                                                                                                                                  |
| D2  | Eternal Terminal and SSH CA: reusable transport or site workflow?     | Open. The ET and CA recipes and playbook are maintained.                                                                                                                                                    |
| D3  | Retain or retire CFEngine?                                            | Open, but the source leans to retain: CFEngine is in `must_cover` for two desired states, gained `cf_run.py`, a version pin and a pinned Homebrew formula, and has fixes through 2026-10. No parity report. |
| D4  | UI-TARS/VLM sidecar: site or private?                                 | Moot. The subsystem was deleted on 2026-07-26.                                                                                                                                                              |
| D5  | Generic default app catalogs or site choices?                         | Narrowed. Obtainium, F-Droid and Aurora were removed and `ensure_apps` defaults to empty. Still open: whether the bootstrap APK lock and `fleet_app_profiles.json` are product defaults or site data.       |
| D6  | Keep public research history for provenance?                          | Open. `docs/research` still holds 42 tracked files, including the retired AutoJs6 project.                                                                                                                  |
| D7  | Peer-help: generic protocol or site-only feature?                     | Leaning core. ADR 006 makes peer-start a native-agent capability with site-supplied `peer.json`. The Termux-era peer scripts and ForceCommand path still ship.                                              |

## Findings from the refresh that need a follow-up

1. `ansible/roles/control_node/tasks/ops_memory_link.yml` (added 2026-10-03)
   links the operator's agent-memory directory into the private companion. It
   is private-companion material inside the public product role.
2. `control/lib/hermes_notify.py` is used by core monitors but is wired to one
   site's notification destination. It is marked `split`.
3. `ansible/roles/control_node/tasks/agents.yml` renders core agents and site
   services from one task file. It is marked `split`.
4. The `ocr`, `ocr-scan` and `agent-review` recipes in the root `justfile` are
   personal review helpers.
5. `tests/healing_registry.json` still lists the deleted
   `obtainium_app.py` module as an `ansible_deploy` path, and still has the
   desired states `A11Y-AUTOJS6` and `AUTOJS6-PROFILE`.
6. ADR 006 says the Termux pull model (`stayturgid_peer_bootstrap.py`) was
   dropped, but `termux_userland` still deploys it.
7. `ops-release.json` has no code caller. The on-device
   `stayturgid_check_repo_version.py` still polls a placeholder `version.json`
   URL.

## Move order (unchanged from the 2026-07-24 matrix)

No move starts until the operator answers D1, D2, D3, D5, D6 and D7. Then,
each as its own reviewable issue with callers, SecretSpec requirement names,
tests on both repositories, a one-device or one-service pilot, a rollback
command and a merge order:

1. This ADR and the manifest (no moves).
2. Move session handoffs, active operator plans and personal research to the
   private companion.
3. Move site-only data: app catalogs, schedules, peer topology, alert
   destinations and control-node package selections.
4. Move the AI and Mac services (Hermes, OpenCode web) with their SecretSpec
   requirement declarations.
5. Move landing and the serverapp adapters one service at a time:
   metrics and log stores, Grafana, blackbox, OliveTin, Caddy, landing.
6. Split dashboard site panels from the core fleet surface, or move the whole
   dashboard, per D1.
7. Retire approved dead paths and the 22 `*-legacy` recipe aliases after
   caller scans and a rollback window.
8. Final generic-checkout acceptance: examples only, no site services, full
   tests and lint, and a disposable one-device deployment.

## Consequences

1. Ownership is now checkable: a new entry point that nobody classified shows
   up as a test warning, or a failure in strict mode.
2. The manifest is a snapshot of master `0c6047b`. Whoever merges it after
   further commits must re-run the test and classify any new files.
3. The private companion's matrix remains the place for site facts, live
   inventory and anything credentials-adjacent. This ADR and the manifest
   carry none.
