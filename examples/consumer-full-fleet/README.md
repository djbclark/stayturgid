# Full stayturgid fleet consumer template

Mirrors `ansible/playbooks/site.yml` for a site that vendors this repo (or
installs collections from Git tags). Requires a **full stayturgid checkout**
(Termux scripts, shared profiles, the bootstrap APK lock).

## Quick start

1. Clone stayturgid (or vendor as a submodule at `../..` relative to this folder).
2. `ansible-galaxy collection install -r requirements.yml -p collections`
3. Copy `inventory/hosts.yml.example` → `inventory/hosts.yml` and edit.
4. `export ANSIBLE_CONFIG=ansible.cfg && ansible-playbook playbook.yml`

`playbook.yml` imports `ansible/playbooks/site.yml` from the checkout:
ensure-bootstrap-apks → verify-bootstrap-apks → ensure-shizuku → **preflight** →
bootstrap (tagged) → fleet → firerpa → post-ui → **validate** → control_node.

## Collections pinned

See `requirements.yml` — `stayturgid.fleet-1.5.0` pulls domain collections.

## Play sideload (optional)

Production fleet parks app stores by default (`stayturgid_app_stores_enabled: false`).
The example inventory leaves the Play role gated the same way. Re-enable the
optional apkeep/gplaycli sideload:

```yaml
stayturgid_app_stores_enabled: true
```

Neo Store, Aurora Store and F-Droid automation were removed (#119, #145).

See [docs/architecture/components/play.md](../../docs/architecture/components/play.md).

## Optional unified app ensure

Set `stayturgid_ensure_apps` in group_vars to dispatch play/apk
sources via `stayturgid.android_common.ensure_apps`.

## Validate / post-UI

Included automatically on full deploy via `site.yml`. Partial runs:

```bash
ansible-playbook playbook.yml --tags validate --limit oneui-device
ansible-playbook playbook.yml --tags post-ui --limit oneui-device
```

See [docs/ansible/collections/roles/validate.md](../../docs/ansible/collections/roles/validate.md).
