# stayturgid.fleet

Ansible collection for the stayturgid fleet. Contains:
- `termux_pkg` module (rootless Termux apt with update/upgrade recovery)
- `fdroid_repos` module — declarative `fdroidcl` repo add/enable (control machine); on-device push via role
- `play_apps` module — apkeep/gplaycli download + adb install (Play spoof via `-i com.android.vending`)

Unit-tested via `ansible-test units` (see tests/unit/); run from this directory.

See ansible/roles/fdroid_repos and play_store for usage. Mac tools: `brew install apkeep fdroidcl`; `play/mac/gplaycli.sh` for gplaycli on Python 3.14.
