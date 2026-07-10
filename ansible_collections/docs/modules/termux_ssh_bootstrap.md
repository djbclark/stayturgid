# termux_ssh_bootstrap

FQCN: `stayturgid.termux.termux_ssh_bootstrap`

Bootstrap Termux SSH **before** Ansible can connect on port 8022. Installs
control-node public keys into Termux `~/.ssh/authorized_keys` via `adb push` and
`run-as com.termux`, optionally installs `openssh` and starts `sshd`.

Runs on the **control node** with `delegate_to: localhost`. Ongoing key sync
after SSH works belongs in `ansible.posix.authorized_key` (see `termux_userland`
role).

Requires a **debuggable** Termux build where `run-as com.termux` succeeds.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `device` | ADB serial or `host:5555` wireless target (required) |
| `connect` | Run `adb connect` first (default `true`) |
| `keys_dir` | Glob `*.pub` here when `public_key_files` / `public_keys` omitted (default `~/.ssh`) |
| `public_key_files` | Explicit public key paths |
| `public_keys` | Inline public key lines |
| `install_openssh` | `pkg install -y openssh` when sshd binary missing (default `true`) |
| `start_sshd` | Start `sshd` when not running (default `true`) |
| `termux_package` | Termux package name (default `com.termux`) |

## Playbook

```yaml
# ansible/playbooks/fleet/bootstrap.yml
- stayturgid.termux.termux_ssh_bootstrap:
    device: "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
    keys_dir: "{{ stayturgid_ssh_keys_dir }}"
  delegate_to: localhost
```

## CLI wrappers

- `./control/bin/bootstrap_ssh.py` — direct adb path (default) or `--ansible` for the playbook
- `./control/bin/deploy_termux.py` — auto-run `fleet/bootstrap.yml` when SSH preflight fails
- `./control/bin/deploy_fleet.py` / `ansible-playbook site.yml` — conditional bootstrap via `preflight.yml`
