# Site-contract scaffolding

This directory implements Phase C of the site contract in
`docs/architecture/site-contract.md`.

- `templates/` mirrors the files `site-init` creates. Files ending in `.j2` are
  Jinja2 templates; other files are copied without rendering.
- `registry_sources.yml` maps product-owned claims to their authoritative role
  defaults or other checked-in product declarations. It deliberately contains
  no port numbers or path literals.
- `generate_registry_seeds.py` resolves that source map and writes the
  committed `templates/registry/{ports,paths}.yml` seeds.
- `site_init.py` is the `site-init` CLI (apply / dry-run / docs).

## site-init

From the product checkout:

```bash
just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
# or:
python3 -m control.site_contract.site_init --sitename <name> [--dir <path>] [--mode apply|dry-run|docs]
```

- Default destination: `$OPS_ROOT/site-<name>` (`OPS_ROOT` defaults to `~/ops`).
- `mode=apply` (default): create the §3 scaffold; never overwrite differing
  user-owned files (exit 2); identical re-apply is a no-op.
- `mode=dry-run`: print per-file `create` / `skip` / `overwrite` actions; no writes.
- `mode=docs`: emit self-contained Markdown with generic example values only.
- Exit codes: `0` success/no-op; `1` precondition/input failure; `2` would overwrite.
- `map=` is reserved for Phase C4 and is rejected until then.
- A destination nested inside this product checkout is rejected (ADR 005).

## Registry seeds

Regenerate the registry templates from the repository root after changing a
mapped product default:

```bash
python3 -m control.site_contract.generate_registry_seeds
# or check for drift:
python3 -m control.site_contract.generate_registry_seeds --check
```

The focused tests compare generated output with the committed seeds, so a
changed default cannot silently leave a stale site scaffold.
