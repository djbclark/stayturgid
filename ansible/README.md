# Ansible — Termux userland

Idempotent deploy of the **Termux layer only** over SSH: packages, scripts, boot hooks, `termux.properties`, optional mode/device files. No Tasker, AutoJs6, Obtainium, or Shizuku automation in this playbook.

**Full project:** [../README.md](../README.md) · **Docs index:** [../docs/README.md](../docs/README.md)

## Standalone use

You need only:

- Ansible on the Mac (`brew install ansible`)
- Termux with `sshd` on port 8022 and your SSH public key in `~/.ssh/authorized_keys`
- Inventory host pointing at the device (copy `inventory/hosts.yml` pattern; trim to one host)

```bash
# Custom host — no stayturgid fleet vars required:
ansible-playbook ansible/playbooks/termux-userland.yml \
  -i 'myphone ansible_host=192.168.1.50 ansible_port=8022 ansible_user=u0_aXXX' \
  -e ansible_python_interpreter=/data/data/com.termux/files/usr/bin/python \
  -e stayturgid_automation_mode= \
  -e stayturgid_device_id=
```

Omit or empty `stayturgid_automation_mode` / `stayturgid_device_id` if you are not using AutoJs6/Tasker mode files.

Copy [inventory/example-standalone.yml](inventory/example-standalone.yml) as a starting point for a single phone.

**Out of scope** (configure separately): Shizuku pairing, Tasker/AutoJs6, Obtainium, `WRITE_SECURE_SETTINGS`, battery whitelist, SSH key bootstrap.

The deployed `~/claude-presence.sh` includes the consent `gate` action ([termux/README.md](../termux/README.md)).

## Prerequisites

- Ansible 2.14+ on the Mac (`brew install ansible`)
- SSH to Termux working (`ssh s24` or USB forward to port 8022)
- `~/.ssh/termux_key` authorized on the device

## Run (fleet wrapper)

```bash
# S24 (AutoJs6 production)
./ansible/mac/deploy-termux.sh s24

# 7a (Tasker)
./ansible/mac/deploy-termux.sh p7a
```

Validated on S24 2026-07-05: playbook completed with `changed=0` on the final run and repair check returned:

```text
STATUS port=open shizuku=up sshd=up shell=yes
```

## Inventory

| Host | SSH | Mode | Notes |
|------|-----|------|-------|
| `s24` | `100.123.218.30:8022` | `autojs6` | Production AutoJs6 device |
| `p7a` | `100.65.230.108:8022` | `tasker` | Tasker production device |

To add the 7a later, uncomment/add under `stayturgid.hosts` in `inventory/hosts.yml`.

Termux currently needs an explicit Python interpreter in inventory:

```yaml
ansible_python_interpreter: /data/data/com.termux/files/usr/bin/python
```

**Termux package policy:** the playbook always runs `pkg update && pkg upgrade -y` first, then installs only missing packages (with another `pkg update && pkg upgrade -y` immediately before any `pkg install`). Same rule applies to manual Termux work — see `HANDOFF.md` tooling rules.

## Layout

```
ansible/
  ansible.cfg
  library/termux_pkg.py          — fault-tolerant Termux package module
  inventory/hosts.yml
  inventory/example-standalone.yml
  group_vars/stayturgid.yml
  playbooks/termux-userland.yml
  roles/termux_userland/
    tasks/main.yml
    defaults/main.yml
    templates/termux.properties.j2
  mac/deploy-termux.sh
```

## After playbook

Device-specific steps still required:

1. `autojs6/mac/deploy.sh s24 s24` + `start-watchdog.sh s24`
2. `autojs6/mac/grant-shizuku.sh s24 autojs6`
3. Obtainium catalog / `enable-shizuku-installer.sh s24`
4. Open Termux:Boot app once after fresh install

See [HANDOFF.md](../HANDOFF.md) for the full production checklist, or [termux/README.md](../termux/README.md) if you deploy scripts without Ansible.
