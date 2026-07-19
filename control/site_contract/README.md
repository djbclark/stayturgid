# Site-contract scaffolding

This directory contains the Phase C1 scaffold inputs for the site contract in
`docs/architecture/site-contract.md`.

- `templates/` mirrors the files that a later `site-init` implementation will
  create. Files ending in `.j2` are Jinja2 templates; other files are copied
  without rendering.
- `registry_sources.yml` maps product-owned claims to their authoritative role
  defaults or other checked-in product declarations. It deliberately contains
  no port numbers or path literals.
- `generate_registry_seeds.py` resolves that source map and writes the
  committed `templates/registry/{ports,paths}.yml` seeds.

Regenerate the registry templates from the repository root after changing a
mapped product default:

```bash
python3 -m control.site_contract.generate_registry_seeds
```

The focused tests compare generated output with the committed seeds, so a
changed default cannot silently leave a stale site scaffold.
