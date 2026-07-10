# stayturgid.fleet (meta-collection)

**New to stayturgid Ansible modules?** Start at [../README.md](../README.md).

Domain modules were split into installable collections so other sites can depend
on only what they need:

| Collection | Module | Use when |
|------------|--------|----------|
| [stayturgid.termux](../termux/README.md) | `termux_pkg` | Termux `pkg` over SSH |
| [stayturgid.obtainium](../obtainium/README.md) | `obtainium_app` | Obtainium catalog JSON on device |
| [stayturgid.fdroid](../fdroid/README.md) | `fdroid_repos` | `fdroidcl` repos on Mac |
| [stayturgid.play](../play/README.md) | `play_apps` | apkeep/gplaycli + adb install |
| [stayturgid.android_common](../android_common/README.md) | `android_ui`, `android_a11y_services`, `autojs6_project_deploy`, … | ADB + UI tasks (ADR 002) |

**Fleet roles:** `stayturgid.fleet.post_ui` (post-deploy screen-control);
`stayturgid.fleet.validate` (repair/sshd/a11y smoke + optional a11y drift merge).

## Backward compatibility

`stayturgid.fleet.termux_pkg` (and siblings) still work via `meta/runtime.yml`
redirects. New playbooks should use the domain FQCNs above.

## Unit tests

Module unit tests live in each domain collection under `tests/unit/`. Run all:

```bash
make ansible-test
```

## Site playbooks

Fleet-specific roles and inventory remain in the repo `ansible/` tree
(`termux_userland` via collection, `obtainium_apps`, `fdroid_repos`, `play_store`,
`post_ui`, `validate`, `autojs6_watchdog`).

See [../docs/adoption.md](../docs/adoption.md), [../docs/roles/validate.md](../docs/roles/validate.md),
[../docs/playbooks/preflight.md](../docs/playbooks/preflight.md), and
[../docs/std_modules_audit.md](../docs/std_modules_audit.md).
