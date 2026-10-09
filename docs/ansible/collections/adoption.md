# Consuming stayturgid Ansible modules at another site

## Minimal Termux-only site

1. Install collections:

```yaml
# requirements.yml
collections:
  - name: stayturgid.termux
    source: git+https://github.com/djbclark/stayturgid.git,ansible_collections/stayturgid/termux
  - name: ansible.posix
    version: ">=1.5.0"
```

```bash
ansible-galaxy collection install -r requirements.yml -p collections
```

2. Point `ansible.cfg`:

```ini
collections_path = ./collections
```

3. Use the module or role in a playbook:

```yaml
- hosts: phones
  roles:
    - role: stayturgid.termux.termux_userland
```

Or call the module directly:

```yaml
- hosts: phones
  tasks:
    - stayturgid.termux.termux_pkg:
        name: [openssh, termux-api, python]
        state: present
```

4. Override role defaults (`stayturgid_termux_packages`, `stayturgid_repo_root`, SSH
   key paths) in your inventory or group_vars. The role copies scripts from
   `stayturgid_repo_root/device/termux/` — set that to this repo path or your fork.

## Play and other control-node (adb) modules

These modules run on `localhost` and need:

1. `adb` on PATH
2. Optional `~/.config/stayturgid/devices.conf` (alias → USB serial / Tailscale IP)
3. `apkeep` or `gplaycli` for the optional Play sideload

Use the lookup plugin instead of inline Python in your roles:

```yaml
- ansible.builtin.set_fact:
    adb_target: "{{ lookup('stayturgid.android_common.adb_device', 'myphone') }}"

- stayturgid.android_common.android_settings:
    device: "{{ adb_target }}"
    settings:
      - { namespace: global, key: stay_on_while_plugged_in, value: "3" }
  delegate_to: localhost
```

Installing `stayturgid.play` installs `stayturgid.android_common` automatically
(declared in its `galaxy.yml` dependencies). The `stayturgid.fdroid` and
`stayturgid.obtainium` collections, and the Aurora automation in `play_store`,
were deleted in July 2026 (#119, #145); fleet apps now come from the
checksummed `bootstrap_apks` lock.

Companion roles ship in each collection:

| Collection role FQCN                       | Purpose                                                                                                                                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stayturgid.termux.termux_userland`        | Termux bootstrap over SSH                                                                                                                                                                                           |
| `stayturgid.android_common.bootstrap_apks` | Install the locked bootstrap APKs over ADB (exact tag, version and checksum)                                                                                                                                        |
| `stayturgid.android_common.ensure_apps`    | Per-app ensure that dispatches each spec to the Play or APK module                                                                                                                                                  |
| `stayturgid.android_common.app_privileges` | Battery-unrestricted, unused-app restrictions off, runtime grants for fleet apps                                                                                                                                    |
| `stayturgid.android_common.tailscale_vpn`  | Always-on VPN secure settings                                                                                                                                                                                       |
| `stayturgid.fleet.shizuku_config`          | Shizuku headless configuration                                                                                                                                                                                      |
| `stayturgid.firerpa.firerpa`               | FIRERPA server install and configuration (when `firerpa_enabled`)                                                                                                                                                   |
| `stayturgid.play.play_store`               | Optional apkeep/gplaycli sideload, gated by `stayturgid_app_stores_enabled` (default false)                                                                                                                         |
| `stayturgid.fleet.post_ui`                 | Post-deploy UI tasks (screen-unlock gate for app-stores; the `android_ui` module it used to call was deleted in #162 — its only dispatch entry, the AutoJs6 Shizuku drawer task, was already removed independently) |
| `stayturgid.fleet.validate`                | Post-deploy repair/a11y smoke (role; wired by `validate.yml`)                                                                                                                                                       |

## Backward-compatible FQCNs

If you already use `stayturgid.fleet.termux_pkg`, install `stayturgid.fleet`
(meta-collection). `meta/runtime.yml` redirects to the domain modules.

## Publishing to Ansible Galaxy

Collections are structured for `ansible-galaxy collection build` / `publish`.
This repo currently installs from Git paths; Galaxy publication is optional follow-up.

## Bootstrap vs ongoing key management

1. **First SSH access (pre-Ansible):** `stayturgid.termux.termux_ssh_bootstrap` via
   `ansible/playbooks/fleet/bootstrap.yml`, `ansible/playbooks/fleet/preflight.yml` (auto at
   start of `site.yml`), `./control/bin/bootstrap_ssh.py`, or `./control/bin/deploy_fleet.py`
   (runs `site.yml`, which starts with `preflight.yml`). Requires debuggable
   Termux with `run-as com.termux`.
2. **Ongoing:** `ansible.posix.authorized_key` in `termux_userland` installs every
   `*.pub` from `stayturgid_ssh_keys_dir` (default `~/.ssh` on the control node);
   matching private keys are copied to each device. `termux_sshd` applies
   `PerSourcePenalties no` and detached sshd restart. Keys are never in git.

Full deploy entry point: `ansible/playbooks/site.yml` (or `./control/bin/deploy_fleet.py`).

See also: [playbooks/preflight.md](playbooks/preflight.md),
[roles/validate.md](roles/validate.md).
