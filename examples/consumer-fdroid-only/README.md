# Minimal F-Droid / Neo Store consumer site

Deploys Obtainium catalog + fdroidcl repos + on-device repo push for one phone.
**Subset** of full fleet — no `preflight.yml`, no `post_ui` import step.

## Quick start

1. `ansible-galaxy collection install -r requirements.yml -p collections`
2. Edit `inventory/hosts.yml` (Termux SSH + adb alias).
3. Set `stayturgid_ensure_neo_store: true` and add Neo Store to
   `stayturgid_obtainium_apps` (copy from `catalogs/obtainium/app-stores-optional.json`
   in the stayturgid repo).
4. Install `fdroidcl` on the Mac: `brew install fdroidcl`
5. `export ANSIBLE_CONFIG=ansible.cfg && ansible-playbook playbook.yml`

Neo must be on the device (Obtainium or manual install) before `fdroid_repos`
can push repos.

Pin collections: see `requirements.yml` (`stayturgid.fdroid-1.4.1`).
