# Ansible — Termux userland for stayturgid

Idempotent replay of the manual Termux deploy: packages, `~/stayturgid-repair.sh`, boot scripts, `termux.properties`, and mode/device files.

**Out of scope** (stay manual / device-specific): Shizuku pairing, Tasker/AutoJs6 install, Obtainium, `WRITE_SECURE_SETTINGS`, battery whitelist, SSH `authorized_keys` (manage separately).

The deployed `~/claude-presence.sh` includes the S24 consent gate:

```bash
ssh s24 '~/claude-presence.sh gate "Galaxy S24" Auto'
```

If the phone appears active, it prompts for Continue / Pause / Check again in 10 minutes; timeout defaults to Continue.

## Prerequisites

- Ansible 2.14+ on the Mac (`brew install ansible`)
- SSH to Termux working (`ssh s24` or USB forward to port 8022)
- `~/.ssh/termux_key` authorized on the device

## Run (S24 only)

```bash
# From repo root — uses Tailscale IP in inventory
ansible-playbook ansible/playbooks/termux-userland.yml --limit s24

# Or via wrapper (checks ssh first):
./ansible/mac/deploy-termux.sh s24
```

Validated on S24 2026-07-05: playbook completed with `changed=0` on the final run and repair check returned:

```text
STATUS port=open shizuku=up sshd=up shell=yes
```

## Inventory

| Host | SSH | Mode | Notes |
|------|-----|------|-------|
| `s24` | `100.123.218.30:8022` | `autojs6` | Production AutoJs6 device |
| `p7a` | *(commented — add when needed)* | `tasker` | Maintenance-only; not in default limit |

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
  inventory/hosts.yml
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

See `HANDOFF.md` for the full S24 production checklist.
