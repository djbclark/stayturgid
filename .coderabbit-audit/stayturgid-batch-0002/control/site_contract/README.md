# Site-contract scaffolding

This directory implements Phase C of the site contract in
`docs/architecture/site-contract.md`.

- Product-root `SITE-CONTRACT.md` is the human-readable contract and Entangled
  literate source for the non-registry C1 scaffold templates (spec §7).
- `entangled.toml` (product root) configures naked-annotation tangling for that
  document only. Product roles/adapters are **not** literate.
- `check_entangled.py` fails closed when the document and literate templates
  drift (`just site-contract-check`).
- `templates/` mirrors the files `site-init` creates. Files ending in `.j2` are
  Jinja2 templates; other files are copied without rendering. Literate
  templates must match `SITE-CONTRACT.md` fenced blocks exactly.
- `registry_sources.yml` maps product-owned claims to their authoritative role
  defaults or other checked-in product declarations. It deliberately contains
  no port numbers or path literals.
- `generate_registry_seeds.py` resolves that source map and writes the
  committed `templates/registry/{ports,paths}.yml` seeds (single authority —
  those two files are intentionally **not** Entangled targets).
- `site_init.py` is the `site-init` CLI (apply / dry-run / docs). `mode=docs`
  emits `SITE-CONTRACT.md` (generic-only, write-free).
- `site_map.py` loads and fail-closed validates optional Site Contract v1
  `site-map.yml` files for `site-init` and `site-sync`.
- `sync_manifest.yml` is the product sync manifest (files under
  `generated/<product>/` that `site-sync` owns).
- `sync_templates/` holds Jinja2 sources for those generated files.
- `site_sync.py` is the `site-sync` CLI (apply / dry-run / docs + lockfile).

## site-init

From the product checkout:

```bash
just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
# or:
python3 -m control.site_contract.site_init --sitename <name> [--dir <path>] [--mode apply|dry-run|docs]
```

- Default destination: `$OPS_ROOT/site-<name>` (`OPS_ROOT` defaults to `${OPS_ROOT:-~/ops}`).
- `mode=apply` (default): create the §3 scaffold; never overwrite differing
  user-owned files (exit 2); identical re-apply is a no-op.
- `mode=dry-run`: print per-file `create` / `skip` / `overwrite` actions; no writes.
- `mode=docs`: emit product-root `SITE-CONTRACT.md` (generic example values
  only; no writes; no live-site identity).
- Exit codes: `0` success/no-op; `1` precondition/input failure; `2` would overwrite.
- `map=` loads an explicit Site Contract v1 map; otherwise a map at
  `<site-dir>/site-map.yml` is auto-discovered. Supported C4 path keys are
  `inventory`, `registry_ports`, and `registry_paths`.
- Relative contract paths resolve from the site directory and may not escape
  it or enter site-sync's `generated/stayturgid/` area. Unknown top-level,
  path, serverapp, and per-app keys fail closed.
- Serverapp mappings are validated for forward compatibility but no adapter
  behavior or inject-mode writes occur in C4.
- A destination nested inside this product checkout is rejected (ADR 005).

## site-sync

```bash
just site-sync [dir=<path>] [mode=apply|dry-run|docs] [force-generated=1]
# or:
python3 -m control.site_contract.site_sync [--dir <path>] [--mode apply|dry-run|docs] [--force-generated]
```

- Destination: explicit `dir=`, else `STAYTURGID_SITE_DIR`, else
  `$OPS_ROOT/.mysite`, else exactly one `site-*` under `$OPS_ROOT`, excluding
  reserved `site-private`. The command prints the selected path and source.
- Resolution creates a missing `STAYTURGID_PRIVATE_DIR` (default
  `$OPS_ROOT/site-private`) as an owner-only empty directory; it never guesses
  a Git remote or creates secrets.
- Auto-discovers `<site-dir>/site-map.yml` and reads inventory/registry facts
  from mapped locations while keeping generated output under
  `generated/stayturgid/`.
- Re-renders every path in `sync_manifest.yml` into `generated/stayturgid/` and
  maintains `generated/stayturgid/.lockfile.yml` (spec §4).
- Before overwriting, compares on-disk content hash to the lockfile hash. Drift
  (hand edit) → exit 2 listing paths; `force-generated=1` overwrites only
  inside the generated area.
- Paths removed from the manifest are deleted from the generated area (dry-run
  lists `delete` first).
- Never writes outside `generated/stayturgid/` in Phase C3.
- Exit codes: `0` success/no-op; `1` precondition/input failure; `2` drift.

## Registry seeds

Regenerate the registry templates from the repository root after changing a
mapped product default:

```bash
python3 -m control.site_contract.generate_registry_seeds
# or check for drift:
python3 -m control.site_contract.generate_registry_seeds --check
```

The focused tests compare generated output with the committed seeds, so a
changed default cannot silently leave a stale site scaffold. Registry seeds
are not fenced in `SITE-CONTRACT.md` (single authority).

## Entangled parity (literate templates)

```bash
# Full check (Entangled parity + registry seed freshness):
just site-contract-check
# or:
python3 -m control.site_contract.check_entangled
# Tangle after editing SITE-CONTRACT.md fenced blocks:
entangled tangle --force
```

`annotation = "naked"` keeps tangled bytes identical to the fenced sources.
Entangled's local `.entangled/` state is gitignored; the parity check uses the
API and does not require a committed filedb.
