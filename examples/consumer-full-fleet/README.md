# Full stayturgid fleet consumer template

Mirrors `ansible/playbooks/fleet.yml` for a site that vendors this repo (or
installs collections from Git tags). Includes Termux, AutoJs6, Obtainium,
Tailscale, F-Droid/Neo Store, and Play/Aurora roles.

## Quick start

1. Clone stayturgid (scripts + AutoJs6 project still live in the repo checkout).
2. `ansible-galaxy collection install -r requirements.yml -p collections`
3. Copy `inventory/hosts.yml.example` → `inventory/hosts.yml` and edit.
4. `export ANSIBLE_CONFIG=ansible.cfg && ansible-playbook playbook.yml`

## Collections pinned

See `requirements.yml` — tags `stayturgid.*-1.4.0` track tested releases.

## Optional unified app ensure

Set `stayturgid_ensure_apps` in group_vars to dispatch play/fdroid/apk/obtainium
sources via `stayturgid.android_common.ensure_apps` (included in playbook when
non-empty).
