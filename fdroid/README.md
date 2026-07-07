# F-Droid / Neo Store support (fdroid_repos side project)

This complements the Obtainium/GitHub path with first-class support for F-Droid repositories and the recommended GUI client (Neo Store).

## What was added / status
- `fdroidcl` on Mac (`brew install fdroidcl`).
- Neo Store + Aurora Store in Obtainium catalog.
- `stayturgid.fleet.fdroid_repos` module (fdroidcl repo add/enable; unit-tested).
- `ansible/roles/fdroid_repos` (module + on-device `fdroidrepos://` push + Shizuku grant).
- `fdroid/mac/grant_neo_store_shizuku.py` uses `PrivShell` (privileged adb).
- **Not wired into fleet.yml** — side project; use `./mac/deploy-fdroid.sh [host]`.

## How to use
After `obtainium_apps` (Neo Store installed):

```bash
brew install fdroidcl   # control machine
./mac/deploy-fdroid.sh p7a
ANDROID_SERIAL=<target> fdroidcl install <appid>
```

Or run the playbook directly: `ansible/playbooks/fdroid.yml`.

The role ensures repos in fdroidcl (use `fdroidcl install <id>` to push to device) and to on-device Neo Store (via explicit intent, no chooser).

See role README for details.

## Client setup (Shizuku + background updates) — per review requirement
- If no GUI F-Droid client: install "Neo Store" (via Obtainium catalog we added) + configure.
- If already installed: still configure Shizuku (if not) and background auto-updates (if not).
- Use the helper: `fdroid/mac/grant_neo_store_shizuku.py <p7a|s24|...>` (reuses shared shizuku.json patch, idempotent).
- Then in the Neo Store app (on device):
  - Settings → Installer → select Shizuku / Dhizuku / Sui.
  - Enable automatic background updates.
- After installing at least one app *through* Neo Store, it gains background update capability for those apps.

The `fdroid_repos` Ansible role calls the grant helper automatically when `stayturgid_ensure_neo_store: true`.

See the role README for details.

See `HANDOFF.md` (search for "Side project: fdroid_repos") for full status, next actions, and handoff notes.

This is a side project and does not affect the main device onboarding work.
