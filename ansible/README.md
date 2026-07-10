# Ansible — Termux userland

Idempotent deploy of the **Termux layer only** over SSH: packages, scripts, boot hooks, `termux.properties`, optional mode/device files. No AutoJs6, Obtainium, or Shizuku automation in this playbook.

**Full project:** [../README.md](../README.md) · **Docs index:** [../docs/README.md](../docs/README.md)

## Standalone use

You need only:

- Ansible on the Mac (`brew install ansible`)
- `ansible-galaxy collection install -r ansible/requirements.yml` (once; deploy scripts do this)
- Termux with `sshd` on port 8022 and your SSH public key in `~/.ssh/authorized_keys` (bootstrap via `./mac/bootstrap_ssh.py`, `ansible/playbooks/bootstrap.yml`, or auto from `deploy_termux.py` / `deploy_fleet.py`; fleet deploy keeps keys in sync)
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

**Out of scope** (configure separately): Shizuku pairing, AutoJs6 install, Obtainium bootstrap, `WRITE_SECURE_SETTINGS`. Fleet app permissions, battery-unrestricted, and unused-app restrictions are automated via `stayturgid.android_common.app_privileges` (or ad-hoc `./mac/harden_fleet_apps.py`). SSH **bootstrap** before the first Ansible connection: `./mac/bootstrap_ssh.py` (adb + `run-as com.termux` on debuggable Termux); ongoing key distribution uses `ansible.posix.authorized_key` plus private-key sync in the `termux_userland` role (`mac.yml` renders Mac `~/.ssh/config.d/stayturgid`). Keys live on the control node only — never in git.

The deployed `~/.stayturgid/bin/agent-presence.sh` includes the consent `gate` action ([termux/README.md](../termux/README.md)).

## Prerequisites

- Ansible 2.14+ on the Mac (`brew install ansible`)
- `ansible.posix` collection (`ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections`)
- SSH to Termux working (`ssh s24` or USB forward to port 8022)
- `~/.ssh/termux_key` authorized on the device (bootstrap once with `ssh-copy-id`; `termux_userland` role manages keys on every deploy)

## Full fleet deploy

```bash
./mac/deploy_fleet.py s24              # ansible/playbooks/site.yml
CHECK=1 ./mac/deploy_fleet.py s24      # dry run
ansible-playbook ansible/playbooks/site.yml --limit s24   # direct
```

`site.yml` chains: `preflight.yml` → `bootstrap.yml` (tagged; skipped by
`deploy_fleet.py` on live deploy) → `fleet.yml` → `post-ui.yml` → app-stores
re-pass → `validate.yml`. See [docs/adr/001-ansible-boundary.md](../docs/adr/001-ansible-boundary.md).

## Run (Termux only)

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
| `s24` | `100.123.218.30:8022` | `autojs6` | Galaxy S24 |
| `p7a` | `100.65.230.108:8022` | `autojs6` | Pixel 7a |
| `hd8` | `100.124.55.39:8022` | `autojs6` | Kindle Fire HD 8 (Mac adb for AutoJs6 deploy) |

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
  requirements.yml               — ansible.posix + stayturgid.* (via deploy install)
  inventory/hosts.yml
  playbooks/site.yml             — preflight → bootstrap → fleet → post-ui → re-pass → validate
  playbooks/preflight.yml        — SSH probe + conditional adb bootstrap
  playbooks/fleet.yml
  playbooks/bootstrap.yml
  playbooks/post-ui.yml
  playbooks/validate.yml
  playbooks/termux-userland.yml
  ansible/mac/deploy_termux.py
ansible_collections/stayturgid/  — modules + roles (incl. fleet.autojs6_watchdog, post_ui, validate)
```

## After playbook (first-time / edge cases)

Full `site.yml` deploy covers Termux, AutoJs6 project, Obtainium catalog render,
post-UI import (`post_ui` / `android_ui`), app privileges, and validate smoke.

**First-time on a blank phone** may still need:

1. Termux + Obtainium + AutoJs6 APKs (Obtainium catalog or `setup_autojs6.py`)
2. Shizuku pairing (see HACKING.md)
3. Open Termux:Boot once after fresh install
4. Fire HD (`hd8`): USB/wireless adb for `autojs6_project_deploy` when not on USB

**Routine updates** after `git pull`:

```bash
./mac/deploy_fleet.py          # or ansible-playbook ansible/playbooks/site.yml
make verify                    # deep TAP (optional)
```

Manual recovery scripts remain under `autojs6/mac/` and `mac/bootstrap_ssh.py`.
