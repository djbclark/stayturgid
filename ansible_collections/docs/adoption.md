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
   `stayturgid_repo_root/termux/` — set that to this repo path or your fork.

## F-Droid / Play modules (control-node adb)

These modules run on `localhost` and need:

1. `adb` on PATH
2. Optional `~/.config/stayturgid/devices.conf` (alias → USB serial / Tailscale IP)
3. `brew install fdroidcl` (fdroid) or `apkeep` / `gplaycli` (play)

Use the lookup plugin instead of inline Python in your roles:

```yaml
- ansible.builtin.set_fact:
    adb_target: "{{ lookup('stayturgid.android_common.adb_device', 'myphone') }}"

- stayturgid.fdroid.fdroid_repos:
    repos: "{{ my_fdroid_repos }}"
    device: "{{ adb_target }}"
  delegate_to: localhost
```

Install `stayturgid.android_common` automatically when you install `stayturgid.fdroid`
or `stayturgid.play` (declared in `galaxy.yml` dependencies).

Companion roles ship in each collection:

| Collection role FQCN | Purpose |
|---------------------|---------|
| `stayturgid.termux.termux_userland` | Termux bootstrap over SSH |
| `stayturgid.obtainium.obtainium_apps` | Render Obtainium catalog on device |
| `stayturgid.fdroid.fdroid_repos` | fdroidcl + Neo Store repo push |
| `stayturgid.play.play_store` | Aurora Shizuku grant + `play_apps` |
| `stayturgid.android_common.tailscale_vpn` | Always-on VPN secure settings |

## Obtainium (on-device over SSH)

`stayturgid.obtainium.obtainium_app` renders JSON on the device via Termux SSH.
Applying the catalog in Obtainium still requires Mac-side `obtainium://` deep link
(`obtainium/mac/import_catalog.py` in this repo) — Obtainium has no stable CLI.

## Backward-compatible FQCNs

If you already use `stayturgid.fleet.termux_pkg`, install `stayturgid.fleet`
(meta-collection). `meta/runtime.yml` redirects to the domain modules.

## Publishing to Ansible Galaxy

Collections are structured for `ansible-galaxy collection build` / `publish`.
This repo currently installs from Git paths; Galaxy publication is optional follow-up.

## Bootstrap vs ongoing key management

1. **First SSH access:** `ssh-copy-id` once (or manual `authorized_keys` entry).
2. **Ongoing:** `ansible.posix.authorized_key` in `termux_userland` installs every
   `*.pub` from `stayturgid_ssh_keys_dir` (default `~/.ssh` on the control node);
   matching private keys are copied to each device. `termux_sshd` applies
   `PerSourcePenalties no` and detached sshd restart. Keys are never in git.
