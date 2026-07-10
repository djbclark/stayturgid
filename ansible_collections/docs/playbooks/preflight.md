# SSH preflight (`ansible/playbooks/preflight.yml`)

Runs at the **start of every** `site.yml` invocation (tag `always`). Probes
Termux SSH per host; when down, runs `stayturgid.termux.termux_ssh_bootstrap`
over adb (no Ansible SSH required).

## When it runs

- Full deploy: `./mac/deploy_fleet.py` → `site.yml` → preflight first
- Direct: `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/site.yml`
- Partial tags: preflight still runs (`always` tag) unless you `--skip-tags preflight`

Check mode (`CHECK=1` / `--check`): probe tasks skipped; no adb bootstrap.

## Relationship to `bootstrap.yml`

| Play | Purpose |
|------|---------|
| `preflight.yml` | Conditional bootstrap **only for hosts that fail SSH probe** |
| `bootstrap.yml` (`bootstrap` tag) | Force bootstrap for all limited hosts (manual recovery) |

`deploy_fleet.py` passes `--skip-tags bootstrap` on live deploys because
preflight covers the common cold-start case.

## Manual recovery

```bash
./mac/bootstrap_ssh.py hd8
# or
ansible-playbook ansible/playbooks/bootstrap.yml --limit hd8
```

## Requirements

- `adb` on control node with device reachable (USB or wireless debugging)
- Debuggable Termux (`run-as com.termux`) for key install
- `~/.ssh/*.pub` on control node (same as `bootstrap.yml`)
