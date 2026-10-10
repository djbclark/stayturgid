# stayturgid Ansible collections

Reusable Ansible content for Android / Termux fleet automation. Install only what
you need — each domain is a separate collection on the `stayturgid` namespace.

## Collections

| Collection                    | Install for…                                   | Module(s)                                                                                                                                                   | Role(s)                                                            |
| ----------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **stayturgid.android_common** | ADB helpers + VPN + Shizuku + APK              | `android_appops`, `android_settings`, `shizuku_grant`, `android_apk`, `android_app_privileges`, `native_agent_config`, `shizuku_start`, `adb_device` lookup | `tailscale_vpn`, `bootstrap_apks`, `ensure_apps`, `app_privileges` |
| **stayturgid.termux**         | Termux over SSH                                | `termux_pkg`, `termux_sshd`, `termux_ssh_bootstrap`                                                                                                         | `termux_userland`                                                  |
| **stayturgid.play**           | Play APK sideload                              | `play_apps`                                                                                                                                                 | `play_store`                                                       |
| **stayturgid.fleet**          | Meta / fleet roles                             | _(redirects to above)_                                                                                                                                      | `post_ui`, `validate`, `shizuku_config`                            |
| **stayturgid.firerpa**        | FIRERPA install (optional gRPC backup channel) | —                                                                                                                                                           | `firerpa`                                                          |

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

1. [docs/adoption.md](../docs/ansible/collections/adoption.md) — how other sites consume modules and roles
2. [docs/std_modules_audit.md](../docs/ansible/collections/std_modules_audit.md) — what uses Ansible builtins vs custom modules
3. [docs/architecture/components/](../docs/architecture/components/) — per-module reference
4. [examples/](../examples/) — consumer site templates (termux-only, full-fleet, firerpa-nonroot)
5. Per-collection `CHANGELOG.md` files
6. [docs/STATUS.md](../docs/STATUS.md) operator-action queue — tasks that need a human

## Layout

```
ansible_collections/stayturgid/
  docs/                     ← shared documentation
  android_common/           ← adb helpers, appops/settings modules, tailscale_vpn role
  termux/                   ← termux_pkg + termux_userland role
  play/                     ← play_apps + play_store role
  fleet/                    ← meta-collection + post_ui, validate, shizuku_config roles
ansible/                    ← site inventory + composed playbooks (site.yml, preflight, …)
```

Fleet-specific roles (`shizuku_config`, `post_ui`, `validate`) live in
`stayturgid.fleet` and reference inventory taxonomy via `device.json.j2`.
