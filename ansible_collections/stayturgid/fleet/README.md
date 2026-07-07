# stayturgid.fleet

Ansible collection for the stayturgid fleet. Contains:
- `termux_pkg` module (rootless Termux apt with update/upgrade recovery)
- `fdroid_repos` module — declarative `fdroidcl` repo add/enable (control machine); on-device push via role
- (play_store skeleton in roles for Aurora/Play side)

Unit-tested via `ansible-test units` (see tests/unit/); run from this directory.

See ansible/roles/fdroid_repos and play_store for usage.
