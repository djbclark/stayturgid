# Minimal F-Droid / Neo Store consumer site

Deploys Obtainium catalog + fdroidcl repos + on-device repo push for one phone.

## Quick start

1. `ansible-galaxy collection install -r requirements.yml -p collections`
2. Edit `inventory/hosts.yml` (Termux SSH + optional `target_device` adb alias).
3. Install `fdroidcl` on the Mac: `brew install fdroidcl`
4. `export ANSIBLE_CONFIG=ansible.cfg && ansible-playbook playbook.yml`

Requires Neo Store in the Obtainium catalog (`stayturgid.obtainium.obtainium_app`)
before `fdroid_repos` can push repos to the device.

Pin collections with tags: `version: stayturgid.fdroid-1.4.0`
