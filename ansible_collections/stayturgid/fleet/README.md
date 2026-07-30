# stayturgid.fleet (meta-collection)

**New to stayturgid Ansible modules?** Start at [../README.md](../../../control/lib/README.md).

Domain modules were split into installable collections so other sites can depend
on only what they need:

| Collection                                                                 | Module                                                             | Use when                         |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------- |
| [stayturgid.termux](../../../docs/architecture/components/termux.md)       | `termux_pkg`                                                       | Termux `pkg` over SSH            |
| [stayturgid.play](../../../docs/architecture/components/play.md)           | `play_apps`                                                        | apkeep/gplaycli + adb install    |
| [stayturgid.android_common](../android_common/README.md)                   | `android_ui`, `android_a11y_services`, `autojs6_project_deploy`, … | ADB + UI tasks (ADR 002)         |

**Fleet roles:** `stayturgid.fleet.post_ui` (post-deploy screen-control);
`stayturgid.fleet.validate` (repair/sshd/a11y smoke + optional a11y drift merge).

## Backward compatibility

`stayturgid.fleet.termux_pkg` (and siblings) still work via `meta/runtime.yml`
redirects. New playbooks should use the domain FQCNs above.

## Unit tests

Module unit tests live in each domain collection under `tests/unit/`. Run all:

```bash
ansible-test units --local
```

## Site playbooks

Fleet-specific roles and inventory remain in the repo `ansible/` tree
(`termux_userland` via collection, `play_store`,
`post_ui`, `validate`, `autojs6_watchdog`).

See [../docs/adoption.md](../../../docs/ansible/collections/adoption.md), [../docs/roles/validate.md](../../../docs/ansible/collections/roles/validate.md),
[../docs/playbooks/preflight.md](../../../docs/ansible/collections/playbooks/preflight.md), and
[../docs/std_modules_audit.md](../../../docs/ansible/collections/std_modules_audit.md).
