# Ansible — Termux userland

Idempotent deploy of the **Termux layer only** over SSH: packages, scripts, boot hooks, `termux.properties`, optional mode/device files. No AutoJs6, Obtainium, or Shizuku automation in this playbook.

**Full project:** [../README.md](../README.md) · **Docs index:** [../docs/README.md](../docs/README.md)

## Standalone use

You need only:

- Ansible on the Mac (`brew install ansible`)
- `ansible-galaxy collection install -r ansible/requirements.yml` (once; deploy scripts do this)
- Termux with `sshd` on port 8022 and your SSH public key in `~/.ssh/authorized_keys` (bootstrap via `./control/bin/bootstrap_ssh.py`, `ansible/playbooks/fleet/bootstrap.yml`, or auto from `control/bin/deploy_termux.py` / `deploy_fleet.py`; fleet deploy keeps keys in sync)
- Inventory host pointing at the device (copy `inventory/hosts.yml` pattern; trim to one host)

```bash
# Custom host — no stayturgid fleet vars required:
ansible-playbook ansible/playbooks/fleet/termux-userland.yml \
  -i 'myphone ansible_host=192.0.2.50 ansible_port=8022 ansible_user=u0_aXXX' \
  -e ansible_python_interpreter=/data/data/com.termux/files/usr/bin/python \
  -e stayturgid_device_id=
```

Omit `stayturgid_device_id` if not using device override files.

Copy [inventory/example-standalone.yml](inventory/example-standalone.yml) as a starting point for a single phone.

**Out of scope** (configure separately): Shizuku pairing, AutoJs6 install, Obtainium bootstrap, `WRITE_SECURE_SETTINGS`. Fleet app permissions, battery-unrestricted, and unused-app restrictions are automated via `stayturgid.android_common.app_privileges` (or ad-hoc `./control/bin/harden_fleet_apps.py`). SSH **bootstrap** before the first Ansible connection: `./control/bin/bootstrap_ssh.py` (adb + `run-as com.termux` on debuggable Termux); ongoing key distribution uses `ansible.posix.authorized_key` plus private-key sync in the `termux_userland` role (`control_node` role renders Mac `~/.ssh/config.d/stayturgid`). Keys live on the control node only — never in git.

The deployed `~/.stayturgid/bin/stayturgid_agent_presence.py` includes the consent `gate` action ([docs/architecture/components/termux.md](../docs/architecture/components/termux.md)).

## Prerequisites

- Ansible 2.14+ on the Mac (`brew install ansible` or `just deploy-mac --tags prereqs`)
- `ansible.posix` + `community.general` collections (`ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections`; `just collections` or `just deploy-mac`)
- SSH to Termux working (`ssh oneui-device` or USB forward to port 8022)
- `~/.ssh/termux_key` authorized on the device (bootstrap once with `ssh-copy-id`; `termux_userland` role manages keys on every deploy)

## Control node (Mac workstation)

Project Mac configuration is Ansible-managed on `localhost` (not your whole Mac — only
stayturgid prerequisites and agents). Logic lives in the `control_node` role; playbooks
are under `playbooks/control_node/`:

```bash
just deploy-mac
# or:
ansible-playbook ansible/playbooks/control_node/site.yml --tags mac
```

| Tag             | What                                                                                                                                               |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `prereqs`       | Homebrew bootstrap (curl install.sh if needed), formulae (adb, python, uv, git, ansible, scrcpy), uv tool install uiautomator2, galaxy collections |
| `agents`        | `devices.conf`, SSH fragment, `com.stayturgid.*` launchd plists, Hermes gateway                                                                    |
| `hermes`        | Hermes Agent brew formula, `~/.hermes` model/config, Telegram gateway launchd                                                                      |
| `agents-ensure` | Load/heal all control-node launchd jobs (`community.general.launchd` + HTTP probes)                                                                |

**Idempotency:** a second `control_node/site.yml` run on a healthy Mac should report
`changed=0`. `agents-ensure` probes `launchctl list` before touching jobs — interval
agents idle between `StartInterval` runs are left alone; plist reload runs only when
templates changed; keepalive services restart only when stopped or `/health`
fails. Verify: `ansible-playbook ansible/playbooks/control_node/site.yml` twice.

`site.yml` imports `control_node/site.yml` at the end. `deploy_fleet.py` re-runs it on partial
(`--limit`) deploys because Ansible skips localhost when a device limit is set.

Still manual: Handsets, `termux_key` / `adbkey` generation, `play.env`, Claude Code, Node.

## Full fleet deploy

```bash
./control/bin/deploy_fleet.py oneui-device              # ansible/playbooks/site.yml
CHECK=1 ./control/bin/deploy_fleet.py oneui-device      # dry run
ansible-playbook ansible/playbooks/site.yml --limit oneui-device   # direct
```

`site.yml` chains: `fleet/preflight.yml` → `fleet/bootstrap.yml` (tagged; skipped by
`deploy_fleet.py` on live deploy) → one `fleet/fleet.yml` convergence pass →
optional `fleet/post-ui.yml` → `fleet/validate.yml`. See
[docs/architecture/adr/001-ansible-boundary.md](../docs/architecture/adr/001-ansible-boundary.md).

## Run (Termux only)

```bash
# oneui-device
./control/bin/deploy_termux.py oneui-device

# stock-android-device
./control/bin/deploy_termux.py stock-android-device
```

Validated on `oneui-device` (Galaxy S24 hardware) 2026-07-05: playbook completed with `changed=0` on the final run and repair check returned:

```text
STATUS port=open shizuku=up sshd=up shell=yes
```

## Inventory

| Host                   | SSH               | Notes                                       |
| ---------------------- | ----------------- | ------------------------------------------- |
| `oneui-device`         | `100.0.0.11:8022` | Galaxy S24                                  |
| `stock-android-device` | `100.0.0.12:8022` | Pixel 7a                                    |
| `fireos-device`        | `100.0.0.13:8022` | Kindle Fire HD 8 (Mac adb for native-agent) |

Both hosts are defined in `inventory/hosts.yml`.

Termux currently needs an explicit Python interpreter in inventory:

```yaml
ansible_python_interpreter: /data/data/com.termux/files/usr/bin/python
```

**Termux package policy:** the playbook always runs `pkg update && pkg upgrade -y` first, then installs only missing packages (with another `pkg update && pkg upgrade -y` immediately before any `pkg install`). Same rule applies to manual Termux work — see `docs/handoff.md` tooling rules.

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
  requirements.yml               — ansible.posix + community.general
  inventory/hosts.yml
  roles/control_node/            — Mac control-node role (defaults, tasks, templates)
  playbooks/site.yml             — top-level orchestrator
  playbooks/control_node/        — localhost: prereqs, agents, agents-ensure
  playbooks/fleet/               — device plays: preflight, fleet, termux-userland, …
control/bin/deploy_termux.py       — Termux-only deploy wrapper
ansible_collections/stayturgid/  — modules + roles (incl. fleet.post_ui, validate)
```

## After playbook (first-time / edge cases)

Full `site.yml` deploy covers Termux, the headless Obtainium catalog import,
app privileges, optional app-store UI setup, and validate smoke.

**First-time on a blank phone** may still need:

1. Termux APKs, native-agent APK (`just agent-rollout <host>`)
2. Shizuku pairing (see docs/hacking.md)
3. Open Termux:Boot once after fresh install
4. Fire HD (`fireos-device`): USB/wireless adb for native-agent rollout when not on USB

**Routine updates** after deploying a coordinated version with the sibling
`site-djbclark` `just ops-release-deploy` recipe:

```bash
./control/bin/deploy_fleet.py          # or ansible-playbook ansible/playbooks/site.yml
just verify                    # deep TAP (optional)
```

Manual recovery scripts remain under `control/tools/native-agent/` and `control/bin/bootstrap_ssh.py`.
