# Full stayturgid fleet consumer template

Mirrors `ansible/playbooks/site.yml` for a site that vendors this repo (or
installs collections from Git tags). Requires a **full stayturgid checkout**
(AutoJs6 project, Termux scripts, shared profiles).

## Quick start

1. Clone stayturgid (or vendor as a submodule at `../..` relative to this folder).
2. `ansible-galaxy collection install -r requirements.yml -p collections`
3. Copy `inventory/hosts.yml.example` → `inventory/hosts.yml` and edit.
4. `export ANSIBLE_CONFIG=ansible.cfg && ansible-playbook playbook.yml`

`playbook.yml` imports `ansible/playbooks/site.yml` from the checkout:
**preflight** → bootstrap (tagged) → fleet → post-ui → app-stores re-pass → **validate**.

## Collections pinned

See `requirements.yml` — `stayturgid.fleet-1.5.0` pulls domain collections.

## App stores (Neo / Aurora)

Production fleet parks app stores by default (`stayturgid_app_stores_enabled: false`).
The example inventory leaves F-Droid / Play roles gated the same way. Re-enable:

```yaml
stayturgid_app_stores_enabled: true
stayturgid_ensure_neo_store: true
stayturgid_ensure_aurora_store: true
```

See [docs/architecture/components/fdroid.md](../../docs/architecture/components/fdroid.md) and [docs/architecture/components/play.md](../../docs/architecture/components/play.md).

## Optional unified app ensure

Set `stayturgid_ensure_apps` in group_vars to dispatch play/fdroid/apk/obtainium
sources via `stayturgid.android_common.ensure_apps`.

## Validate / post-UI

Included automatically on full deploy via `site.yml`. Partial runs:

```bash
ansible-playbook playbook.yml --tags validate --limit oneui-device
ansible-playbook playbook.yml --tags post-ui --limit oneui-device
```

See [docs/ansible/collections/roles/validate.md](../../docs/ansible/collections/roles/validate.md).
