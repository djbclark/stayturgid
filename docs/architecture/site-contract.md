# Site Contract v1 (specification)

**Status:** Shipped (Phase C+D). See the root `SITE-CONTRACT.md` for the living literate contract. This document serves as the historical architecture specification.
**Authored:** 2026-07-18 by a senior model so junior implementers do not have
to make design decisions. Implementers: follow this spec; deviations require
operator approval. Companion: [ADR 005](adr/005-two-repo-topology.md), the
site repo's `docs/plans/site-djbclark-step1-segmentation-architecture-v1.md`
(§5, §5a), and [docs/architecture/multi-site-topology.md](multi-site-topology.md) §4.

## 1. Purpose and terms

The site contract is the interface between a **product** (this repo; later
possibly others) and a **site** (one operator's private repo). It lets a user
who knows nothing about Ansible or brew bootstrap and maintain a working site
directory, while letting an experienced user map the contract onto an
existing layout.

| Term           | Meaning                                                                                                                     |
| -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| product        | Public repo shipping roles, defaults, adapters, fragments, and this tooling                                                 |
| site dir       | The operator's private directory/repo (`site-<name>`)                                                                       |
| generated area | `generated/<product>/` inside the site dir; owned by `site-sync`; never hand-edited                                         |
| user area      | Everything else in the site dir; never touched by product tooling                                                           |
| fragment       | A product-contributed piece of a shared serverapp's config (Caddy route, vector source, Grafana dashboard, OliveTin action) |
| adapter        | A product role that installs-or-injects a serverapp (see §5)                                                                |

## 2. CLI surface

Implemented in the product (v1: `just` recipes + one Python module under
`control/site_contract/`; no new top-level tools):

```text
just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
just site-sync [dir=<path>] [mode=apply|dry-run|docs]
```

- `mode=apply` (default): perform actions.
- `mode=dry-run`: print the exact action list (create/overwrite/skip per
  file, daemon reloads) and exit 0 without changes.
- `mode=docs`: emit a self-contained Markdown document describing every step
  and its manual equivalent, for users who refuse automation. With the
  Entangled layout (§7) this is a render of `SITE-CONTRACT.md`.

Exit codes: 0 success / no-op; 1 precondition failure (missing tools, bad
map); 2 would-overwrite-user-file (never proceeds without `--force-generated`,
which still only ever overwrites inside the generated area).

## 3. Site dir layout (what `site-init` creates)

```text
site-<name>/
  README.md                  # generated once, then user-owned (never resynced)
  ansible.cfg                # inventory here; collections/playbooks -> product checkout
  justfile                   # thin wrappers; OPS_ROOT/product path detection
  inventory/
    hosts.yml                # from product's hosts.yml.example; user edits
    group_vars/
  registry/
    ports.yml                # seeded with the product's port claims
    paths.yml                # seeded with the product's prefix claims
  secretspec.toml            # product's secret declarations, site profile
  generated/
    <product>/
      .lockfile.yml          # see §4
      ...                    # rendered fragments, wrapper playbooks
  docs/                      # user area (operator notes)
```

Baseline `.gitignore` (created by `site-init`): ignores secrets patterns
(`*.env`, `*.pem`, `*.key`, `*.crt`, `id_*`), never ignores `generated/`
(generated content is _committed_ in the site repo — it is identity-bearing
and reviewable; regeneration is idempotent).

## 4. Sync model and lockfile

`generated/<product>/.lockfile.yml`:

```yaml
contract_version: 1
product: stayturgid
product_version: <version.json version>
product_commit: <git sha of product checkout at sync time>
synced: <ISO-8601>
files:
  - path: generated/stayturgid/caddy.d/stayturgid.caddy
    sha256: <hash of rendered output>
```

Rules:

1. `site-sync` re-renders every file in the manifest from the _currently
   checked-out_ product version, using site facts from `inventory/` and
   `registry/`.
2. Before overwriting, compare the on-disk hash to the lockfile hash. If they
   differ (someone hand-edited a generated file), **stop with exit 2** and
   list the drifted files. `--force-generated` overwrites them.
3. Files that disappear from the product manifest are deleted from the
   generated area (they are listed in dry-run first).
4. `site-sync` never writes outside `generated/<product>/` **except** through
   serverapp adapters in inject mode (§5), and those writes are only into
   include/fragment locations declared in `site-map.yml` or auto-detected
   per §5.3.

## 5. Serverapp adapters

One adapter per shared daemon. v1 set: `caddy`, `vector`, `openobserve`,
`victoriametrics`, `grafana`, `olivetin`, `landing`.

### 5.1 Modes

- **own** — the adapter installs the daemon (brew), renders a base config
  whose only site-specific content comes from inventory/registry, reserves a
  user fragment directory, and manages the launchd/systemd unit under the
  _site_ namespace label (default `com.<site_ns>.<app>`; `site_ns` is a site
  fact, e.g. `operator`).
- **inject** — the adapter leaves the user's daemon and base config alone and
  only maintains the product's fragment files inside the app's include
  location.

### 5.2 Mode selection (deterministic, in order)

1. Site var `serverapp_<app>_mode` if set (`own` / `inject` / `off`).
2. Else **inject** if an existing config is detected (§5.3).
3. Else **own**.

### 5.3 Detection and include mechanisms

| App                           | Detect existing config at                                                   | Native include mechanism the adapter uses                                                                                                                                                            |
| ----------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| caddy                         | `$XDG_CONFIG_HOME/caddy/Caddyfile`, `/opt/homebrew/etc/Caddyfile`, site-map | `import <dir>/*.caddy` line; adapter verifies the import exists, adds it in own mode, asks (exit 2) in inject mode if missing                                                                        |
| vector                        | existing `vector.yaml`/`vector.toml` service config                         | multiple `--config` args in the unit, or a conf-dir glob; product fragments are standalone source/transform/sink files with product-prefixed component ids (`stayturgid_*`) to avoid name collisions |
| grafana                       | brew grafana ini / provisioning dir                                         | provisioning dirs: drop dashboards + datasource YAML in `provisioning/{dashboards,datasources}/<product>/`                                                                                           |
| openobserve / victoriametrics | running service or unit file                                                | no include mechanism — single-owner daemons; inject mode means "reuse endpoint only" (product just reads the endpoint from registry; no file writes)                                                 |
| olivetin                      | existing config.yaml                                                        | no include mechanism — config is a **projection**: site-sync merges product action files + user action files into the final config.yaml (generated, single writer)                                   |
| landing                       | n/a (product-internal today)                                                | becomes an own-mode adapter in Phase D; port default fixed to 8088                                                                                                                                   |

### 5.4 Invariants

- Adapters never modify user-authored config _content_ — only add a
  verified include line (own mode) or files under an include dir.
- Every rendered file starts with a generated header naming the product,
  source template, and sync time.
- Port and label values come **only** from the site registry/inventory;
  role defaults are used solely to seed `site-init` registry entries.
- A site repo must never live inside a product working tree (ADR 005).

## 6. site-map.yml (existing-layout mapping)

Optional file at the site dir root; consulted before all defaults:

```yaml
contract_version: 1
paths:
  inventory: ansible/inventories/home/hosts.yml # example remap
  registry_ports: infra/registry/ports.yml
serverapps:
  caddy:
    config: /opt/homebrew/etc/Caddyfile
    fragment_dir: /opt/homebrew/etc/caddy.d
    mode: inject
```

Unknown keys are an error (fail closed — typos must not silently fall back
to defaults).

## 7. Literate layout (Entangled)

`SITE-CONTRACT.md` in the product is the human-readable contract document;
its fenced blocks tangle (via [Entangled](https://entangled.github.io/)) into
the scaffold templates under `control/site_contract/templates/`. CI runs the
Entangled check so document and templates cannot drift. Scope discipline per
site step1 doc §6: only the contract is literate; roles and adapters are
conventional code.

## 8. Acceptance tests (implementers must ship these)

1. `site-init` in an empty dir, `mode=dry-run` → action list, no writes.
2. `site-init` apply → layout of §3 exists; `registry/ports.yml` contains
   every port the product's role defaults declare; second run is a no-op.
3. Hand-edit a generated file → `site-sync` exits 2 naming the file.
4. `site-map.yml` with a remapped inventory path → sync reads/writes the
   mapped location and nothing at the default location.
5. caddy adapter, own mode on a clean prefix → daemon runs under
   `com.<site_ns>.caddy`, fragment dir importable; inject mode against a
   pre-existing Caddyfile without the import line → exit 2 with instructions.
6. `mode=docs` output contains no site-specific values (RFC 5737 / example
   names only).
