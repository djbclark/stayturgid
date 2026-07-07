# stayturgid Ansible collections

Reusable Ansible content for Android / Termux fleet automation. Install only what
you need — each domain is a separate collection on the `stayturgid` namespace.

## Collections

| Collection | Install for… | Module(s) | Role(s) |
|------------|--------------|-----------|---------|
| **stayturgid.android_common** | ADB helpers + VPN + Shizuku + APK | `android_appops`, `android_settings`, `shizuku_grant`, `android_apk`, `adb_device` lookup | `tailscale_vpn` |
| **stayturgid.termux** | Termux over SSH | `termux_pkg`, `termux_sshd` | `termux_userland` |
| **stayturgid.obtainium** | Obtainium catalogs | `obtainium_app` | `obtainium_apps` |
| **stayturgid.fdroid** | F-Droid / Neo Store | `fdroid_repos` | `fdroid_repos` |
| **stayturgid.play** | Play APK sideload | `play_apps` | `play_store` |
| **stayturgid.fleet** | Meta / redirects | _(redirects to above)_ | fleet playbooks |

## Quick install

From a clone of this repo (development):

```bash
ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections
export ANSIBLE_CONFIG=ansible/ansible.cfg   # collections_path includes ansible_collections
```

From Git (consumer site, single collection):

```bash
ansible-galaxy collection install \
  git+https://github.com/djbclark/stayturgid.git,ansible_collections/stayturgid/termux
```

## Documentation

1. [docs/adoption.md](docs/adoption.md) — how other sites consume modules and roles
2. [docs/std_modules_audit.md](docs/std_modules_audit.md) — what uses Ansible builtins vs custom modules
3. [docs/modules/](docs/modules/) — per-module reference
4. [examples/](../examples/) — consumer site templates (termux, fdroid, full-fleet)
5. Per-collection `CHANGELOG.md` files

## Layout

```
ansible_collections/stayturgid/
  docs/                     ← shared documentation
  android_common/           ← adb helpers, appops/settings modules, tailscale_vpn role
  termux/                   ← termux_pkg + termux_userland role
  obtainium/                ← obtainium_app + obtainium_apps role
  fdroid/                   ← fdroid_repos module + role
  play/                     ← play_apps + play_store role
  fleet/                    ← meta-collection + runtime redirects
ansible/                    ← site inventory, playbooks, fleet-only roles (autojs6_watchdog)
```

Fleet-specific roles (`autojs6_watchdog`) stay in `ansible/roles/` because they
encode this project's inventory and device taxonomy.
