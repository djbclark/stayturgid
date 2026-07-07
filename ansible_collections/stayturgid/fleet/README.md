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
| [stayturgid.android_common](../android_common/README.md) | _(helpers)_ | ADB alias resolution |

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
(`termux_userland`, `obtainium_apps`, `fdroid_repos`, `play_store`, etc.).

See [../docs/adoption.md](../docs/adoption.md) and [../docs/std_modules_audit.md](../docs/std_modules_audit.md).
