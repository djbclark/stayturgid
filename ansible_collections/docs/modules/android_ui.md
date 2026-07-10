# android_ui

**FQCN:** `stayturgid.android_common.android_ui`

Named screen-control tasks (ADR 002). Wraps existing repo scripts; does not run in
`--check` mode.

## Tasks

| `task` | Script |
|--------|--------|
| `import_obtainium_catalog` | `obtainium/mac/import_catalog.py` |
| `configure_aurora` | `play/mac/configure_aurora.py` |
| `enable_autojs6_drawer` | `autojs6/mac/enable_autojs6_shizuku.py` |

Role: `stayturgid.fleet.post_ui` — playbook `ansible/playbooks/post-ui.yml`
