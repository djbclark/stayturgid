# Minimal Termux-only consumer site

Copy this directory to bootstrap a single-phone Termux deployment using only
`stayturgid.termux` from Git — no fleet inventory required.

## Quick start

1. Install collections:

```bash
ansible-galaxy collection install -r requirements.yml -p collections
```

2. Bootstrap SSH (once) — requires working SSH, or cold start via
   `./mac/bootstrap_ssh.py` / `preflight.yml` from a full stayturgid checkout:

```bash
ssh-copy-id -p 8022 -i ~/.ssh/termux_key user@YOUR_PHONE_IP
```

3. Edit `inventory/hosts.yml` — set `ansible_host`, `ansible_user`, `ansible_port`.

4. Deploy:

```bash
export ANSIBLE_CONFIG=ansible.cfg
ansible-playbook playbook.yml
```

## What it installs

`stayturgid.termux.termux_userland` — packages, scripts, boot hooks, sshd keys.

Obtainium / AutoJs6 / F-Droid are out of scope; add collections from
`requirements.yml` when needed.

## Pinning a release

Tags like `stayturgid.termux-1.8.0` point at tested collection versions (see
`ansible_collections/stayturgid/termux/galaxy.yml`):

```yaml
# requirements.yml
collections:
  - name: stayturgid.termux
    source: git+https://github.com/djbclark/stayturgid.git,ansible_collections/stayturgid/termux
    version: stayturgid.termux-1.8.0
```
