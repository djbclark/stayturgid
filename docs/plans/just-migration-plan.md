# GNU Make to `just` Migration Plan

**Created:** 2026-07-13

**Status:** Direction accepted; implementation deferred and tracked as
[OPTIONS T1](../options.md)

**Decision:** Make `just` the primary operator command interface, retain a small
GNU Make compatibility shim during a soak period, and keep substantive logic in
Python or Ansible.

## Outcome

Stayturgid can replace almost all of its GNU Make interface with `just`, and doing
so is a good fit for the project. The current `Makefile` is primarily an operator
command catalog, not an incremental build graph. `just` is designed for that job
and gives the project generated command listings, recipe arguments and help,
imports, dotenv loading, command completion, and a formatter/parser check.

This is not authorization for a flag-day deletion of `Makefile`. The migration
must preserve existing automation and operator muscle memory until the replacement
has passed CI and several live-device deployment/recovery cycles.

## Current Baseline

Measured on 2026-07-13:

- `Makefile` is 494 lines and exposes 79 named targets.
- There are approximately 382 non-history `make` references across 63 files,
  including CI, agent instructions, current documentation, tests, control-node
  scripts, and Ansible material.
- Most targets are `.PHONY` wrappers around Python, Ansible, launchd, SSH, ADB,
  `curl`, or test commands.
- Make-specific computation is limited to a few default variables, conditional
  arguments, command lookup, aliases/dependencies, and a recursive test aggregate.
- `.venv-test/bin/pytest` is the only significant file-producing target. There is
  no compilation graph, pattern-rule system, or use of Make automatic variables
  that would be expensive to replace.
- [`examples/firerpa-nonroot/justfile`](../../examples/firerpa-nonroot/justfile)
  is a successful bounded trial: configuration, dependencies, idempotent setup,
  validation, formatting checks, and live read-only S24 operations have all been
  exercised.

The migration cost is therefore compatibility and documentation, not translating
a build system.

## Architecture Boundary

The target architecture is:

```text
operator / CI
      |
      v
root justfile + imported recipe groups
      |
      +--> Python commands: validation, retries, orchestration, structured output
      +--> Ansible: declared fleet and control-node state
      +--> small direct commands: status, tests, launchctl, curl

temporary Makefile compatibility shim --> just
```

The strong project rule to prefer Python still applies:

- `just` recipes should be thin, discoverable entry points.
- Multi-step control flow, parsing, error classification, retries, and device
  decisions belong in Python.
- Desired-state work continues to belong in Ansible where it crosses the boundary
  described by [ADR 001](../adr/001-ansible-boundary.md).
- Existing substantial shell bodies should be moved to Python when touched unless
  the shell is materially clearer and remains small.
- Do not copy implementation logic into both Make and `just`; Make forwards only.

## Proposed Layout

```text
justfile                 # public entry point, global settings, default listing
just/
  fleet.just             # deploy, verify, bootstrap, health, FIRERPA
  services.just          # Hermes, dashboard, landing, OpenCode, VLM
  tests.just             # configure, check, unit, pytest, ansible-test, lint
Makefile                 # temporary compatibility and bootstrap shim
control/bin/             # substantive Python implementations
```

The exact grouping may change during implementation, but the public commands
should remain easy to discover from the root with `just --list`.

## Operator Interface Contract

The new interface should improve argument clarity while keeping old invocations
working during the compatibility period.

Preferred new forms:

```console
just deploy --hosts s24
just deploy --hosts s24 --scope app-stores
just deploy-check --hosts s24
just verify --hosts s24
just firerpa-health
just test
just --list
```

Compatibility forms during migration:

```console
make deploy HOSTS=s24
make deploy-check HOSTS=s24 SCOPE=app-stores
make verify HOSTS=s24
make test
```

Requirements:

1. Preserve public target names initially; renaming is a separate decision.
2. Support `HOSTS` and `SCOPE` environment overrides for scripts and CI even when
   human-facing recipes also provide `--hosts` and `--scope` flags.
3. Default to listing commands rather than running a live fleet action.
4. Provide descriptions and argument help from the recipes themselves; do not
   reproduce the current manually synchronized 100-line help target.
5. Use validation patterns or Python validation for host and scope arguments.
6. Preserve exit-code behavior relied on by CI and health monitoring.
7. Retain the screen-control lease and device-interaction announcement rules;
   changing task runners does not weaken safety policy.
8. Add explicit confirmation only where it improves protection for destructive or
   fleet-wide actions. Noninteractive automation must have a documented opt-in.

## Compatibility and Bootstrap

Do not require an already-installed `just` binary as the only way to install
`just`. At least one dependency-light bootstrap path must remain available.

During migration:

- Keep a small explicit `Makefile` that forwards supported targets and exports
  compatibility variables to `just`.
- Keep `./configure` usable without `just`, or replace it with a Python bootstrap
  command before making `just` mandatory.
- Install `just` through the Mac control-node provisioning and explicitly in CI.
- Declare and check a minimum supported `just` version based on the recipe features
  actually used.
- Give a clear missing-tool error containing the Homebrew and upstream installation
  commands.

The compatibility Makefile should be small enough to audit at a glance. It must
not contain alternate implementations of the recipes.

## Alternatives Considered

### Task / Taskfile

[Task](https://taskfile.dev/) is the closest direct alternative. It has strong
cross-platform support, parallel dependency execution, and checksum/timestamp
caching. Those features would matter more for a generated-artifact build graph.
Stayturgid is dominated by imperative operator commands, and embedding its command
surface in YAML plus Go templates would add quoting and maintenance overhead without
enough benefit. Reconsider Task if Windows becomes a supported control node or
content-based build caching becomes important.

### `mise`

[`mise` tasks](https://mise.jdx.dev/tasks/) can combine tool-version management,
environment setup, and task execution. It may be valuable later for pinning Python,
Node, `just`, and related developer tools. Adopting it now as the task interface
would combine two architectural changes and overlap with the existing Homebrew and
Ansible control-node provisioning. Evaluate `mise` separately as a toolchain manager,
not as a prerequisite for this migration.

### Nox

[Nox](https://nox.thea.codes/en/latest/) is a good Python test-session manager but
is not a natural interface for ADB, SSH, fleet deployments, launchd services, and
Ansible. It could improve the Python test subsystem later, but splitting everyday
commands between Nox and another runner would hurt discoverability.

### Full Python CLI

A typed Python CLI remains the preferred implementation layer for complicated or
high-risk operations. Replacing all 79 thin wrappers with a bespoke CLI immediately
would add more code and documentation than `just`. The two approaches are
complementary: migrate complex recipes into Python commands over time and let `just`
provide memorable project-local entry points.

## Migration Phases

### Phase 0 — Inventory and parity contract

- Capture the authoritative public target list and categorize each target as a
  direct command, Python wrapper, Ansible wrapper, alias/aggregate, or bootstrap.
- Record expected exit codes and environment inputs for CI- and monitoring-facing
  targets.
- Decide the minimum `just` version and installation path.
- Add an automated parity check so public Make targets cannot silently disappear.

**Gate:** Every current public target has an explicit disposition and test level.

### Phase 1 — Add `just` without changing the default interface

- Add the root `justfile` and imported recipe groups.
- Port simple wrappers first.
- Move complicated shell bodies to Python as they are encountered.
- Add `just --fmt --check` and a recipe parse/list check to CI.
- Keep all existing Make commands operational through their original definitions
  until their corresponding recipes pass parity checks.

**Gate:** `just check`, `just test`, and all read-only status recipes match current
behavior on the Mac control node.

### Phase 2 — Make Make a compatibility shim

- Convert migrated Make targets into thin forwarding targets.
- Exercise both interfaces in CI for the core commands.
- Update `README.md`, `AGENTS.md`, `docs/handoff.md`, `docs/hacking.md`, and active
  module documentation to present `just` first and Make as compatibility syntax.
- Do not rewrite historical session documents merely to change command spelling.

**Gate:** The Makefile contains no substantive task logic and CI proves forwarding
for at least `check`, `test`, and one parameterized dry-run command.

### Phase 3 — Live fleet soak

Use S24 as the primary device, with P7A and HD8 only where their different paths add
coverage. Exercise at minimum:

- read-only health, verify, FIRERPA health, and service status;
- S24 `deploy-check` and a host-limited deployment;
- one bootstrap or recovery flow with USB available;
- a parameterized operation using both new flags and old Make variables;
- expected failure paths for an invalid host, missing dependency, and offline host.

Follow normal device announcement, screen-control lease, and recovery rules.

**Gate:** Several real operating sessions complete without falling back to substantive
Make logic, and warnings/errors are either fixed or recorded in `docs/options.md`.

### Phase 4 — Make `just` primary

- Change CI and current operator documentation to use `just` exclusively in the
  primary examples.
- Keep the forwarding Makefile for at least one release/soak interval.
- Search active code and documentation for stale direct Make dependencies.
- Decide whether the small shim continues to earn its maintenance cost.

**Gate:** A clean machine can bootstrap, list commands, run tests, and perform a
host-limited dry run using the documented path.

### Phase 5 — Optional Make removal

Deleting Make is optional, not a success criterion. Remove the shim only if:

- bootstrap no longer depends on it;
- active automation and CI have no Make dependency;
- current documentation has no compatibility promise requiring it;
- at least one full soak interval has passed without a reported need for it; and
- the removal has an obvious rollback commit.

A permanent 10–30 line Make shim is acceptable if it remains useful to contributors
and costs essentially nothing to maintain.

## Verification

Each migration change should run the tests appropriate to its scope. The completed
migration must include:

```console
just --fmt --check
just --list
just check
just test
make check
make test
```

Also verify:

- recipe-list parity for all intentionally supported targets;
- `HOSTS=s24 make deploy-check` and the corresponding `just` command produce the
  same effective host limit without unintended changes;
- clean-machine bootstrap on macOS;
- CI installation does not rely on mutable, unaudited download execution;
- no secrets appear in `just --list`, command echo, logs, or generated help;
- imported recipes work when invoked from repository subdirectories;
- failed commands propagate a nonzero exit code.

## Rollback

Migration commits should be staged so that rollback never requires reconstructing
task logic:

1. While Make still owns a target, adding its `just` peer is reversible by removing
   the peer.
2. When a Make target begins forwarding, its previous implementation remains in Git
   immediately before that commit.
3. If live soak exposes a regression, restore the affected Make implementation,
   keep the `just` recipe for diagnosis, and record the failure under OPTIONS T1.
4. Do not combine final Make removal with unrelated fleet or service changes.

## Completion Criteria

T1 is complete when:

- `just` is the documented primary command interface;
- every retained public operation has discoverable recipe help;
- substantive task logic lives in Python or Ansible, not duplicated runner files;
- CI uses `just` and tests the compatibility shim while it exists;
- clean bootstrap and live S24 deploy/recovery paths have passed;
- active docs and agent instructions are migrated;
- all observed warnings/errors are fixed or tracked; and
- the operator has made a separate decision to retain or remove the final Make shim.

## References

- [`just` manual](https://just.systems/man/en/)
- [`just` recipe parameters and flags](https://just.systems/man/en/recipe-parameters.html)
- [`just` imports](https://just.systems/man/en/imports.html)
- [`just` formatting check](https://just.systems/man/en/formatting-and-dumping-justfiles.html)
- [Standalone FIRERPA `justfile`](../../examples/firerpa-nonroot/justfile)
- [GNU Make interface](../../Makefile)
- [CI workflow](../../.github/workflows/test.yml)
