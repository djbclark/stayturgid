# Ansible — Termux userland

Idempotent deploy of the **Termux layer only** over SSH: packages, scripts, boot hooks, `termux.properties`, optional mode/device files. No AutoJs6, Obtainium, or Shizuku automation in this playbook.

**Full project:** [../README.md](../README.md) · **Docs index:** [../docs/README.md](../docs/README.md)

## Standalone use

You need only:

- Ansible on the Mac (`brew install ansible`)
- `ansible-galaxy collection install -r ansible/requirements.yml` (once; deploy scripts do this)
- Termux with `sshd` on port 8022 and your SSH public key in `~/.ssh/authorized_keys` (one-time bootstrap via `ssh-copy-id`; fleet deploy keeps keys in sync)
- Inventory host pointing at the device (copy `inventory/hosts.yml` pattern; trim to one host)

```bash
# Custom host — no stayturgid fleet vars required:
ansible-playbook ansible/playbooks/termux-userland.yml \
  -i 'myphone ansible_host=192.168.1.50 ansible_port=8022 ansible_user=u0_aXXX' \
  -e ansible_python_interpreter=/data/data/com.termux/files/usr/bin/python \
  -e stayturgid_device_id=
```

Omit `stayturgid_device_id` if not using device override files.

Copy [inventory/example-standalone.yml](inventory/example-standalone.yml) as a starting point for a single phone.

**Out of scope** (configure separately): Shizuku pairing, AutoJs6 install, Obtainium bootstrap, `WRITE_SECURE_SETTINGS`. Fleet app permissions, battery-unrestricted, and unused-app restrictions are automated via `android_common.app_privileges` / `./mac/harden_fleet_apps.py`. SSH key **bootstrap** (first key before Ansible can connect) is still manual/`ssh-copy-id`; ongoing key distribution is handled by `termux_sshd` in the `termux_userland` role.

The deployed `~/agent-presence.sh` includes the consent `gate` action ([termux/README.md](../termux/README.md)).

## Prerequisites

- Ansible 2.14+ on the Mac (`brew install ansible`)
- `ansible.posix` collection (`ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections`)
- SSH to Termux working (`ssh s24` or USB forward to port 8022)
- `~/.ssh/termux_key` authorized on the device (bootstrap once with `ssh-copy-id`; `termux_userland` role manages keys on every deploy)

## Run (fleet wrapper)

```bash
# S24 (AutoJs6 production)
./ansible/mac/deploy_termux.py s24

# 7a (AutoJs6)
./ansible/mac/deploy_termux.py p7a
```

Validated on S24 2026-07-05: playbook completed with `changed=0` on the final run and repair check returned:

```text
STATUS port=open shizuku=up sshd=up shell=yes
```

## Inventory

| Host | SSH | Mode | Notes |
|------|-----|------|-------|
| `s24` | `100.123.218.30:8022` | `autojs6` | Production AutoJs6 device |
| `p7a` | `100.65.230.108:8022` | `autojs6` | Production AutoJs6 device |

Both hosts are defined in `inventory/hosts.yml`.

Termux currently needs an explicit Python interpreter in inventory:

```yaml
ansible_python_interpreter: /data/data/com.termux/files/usr/bin/python
```

**Termux package policy:** the playbook always runs `pkg update && pkg upgrade -y` first, then installs only missing packages (with another `pkg update && pkg upgrade -y` immediately before any `pkg install`). Same rule applies to manual Termux work — see `HANDOFF.md` tooling rules.

## Collections

Reusable modules live in domain collections under `ansible_collections/stayturgid/`
(`termux`, `obtainium`, `fdroid`, `play`, `android_common`). See
[../ansible_collections/README.md](../ansible_collections/README.md) for install
and adoption docs. In development, `ansible.cfg` discovers collections from
`../ansible_collections` — no separate `ansible-galaxy install` for stayturgid
modules beyond `ansible.posix`.

Playbooks reference collection roles by FQCN (e.g. `stayturgid.termux.termux_userland`).

## Layout

```
ansible/
  ansible.cfg
  requirements.yml               — ansible.posix
  inventory/hosts.yml
  playbooks/termux-userland.yml
  roles/autojs6_watchdog/        — fleet-only (not in collections)
  ansible/mac/deploy_termux.py
ansible_collections/stayturgid/  — modules + roles per domain
```

## After playbook

Device-specific steps still required on each host:

1. `autojs6/mac/setup_autojs6.py <host> <device-id>` — first-time AutoJs6 install, storage grant, project deploy
2. `autojs6/mac/set_automation_mode.py <host>` — Shizuku grant + AutoJs6 drawer (`enable_autojs6_shizuku.py`)
3. `autojs6/mac/start_watchdog.py <host>` — launch `main.js`
4. Obtainium catalog / `obtainium/mac/enable_shizuku_installer.py <host>`
5. Open Termux:Boot app once after fresh install

For routine updates after `git pull`, steps 1–3 reduce to `deploy_termux.py` + `autojs6/mac/deploy.py` + `start_watchdog.py`.

See [HANDOFF.md](../HANDOFF.md) for the full production checklist, or [termux/README.md](../termux/README.md) if you deploy scripts without Ansible.
