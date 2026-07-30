# Changelog — stayturgid.fleet

## 1.6.0 (2026-07-30)

- Removed dependencies on `stayturgid.obtainium` and `stayturgid.fdroid`.
- Removed legacy FQCN redirects for `obtainium_app` and `fdroid_repos`.
## 1.6.0 (2026-07-07)

- F-Droid (`fdroid_repos`) and Play (`play_store`) roles integrated into fleet playbook.
- `./control/bin/deploy_fleet.py` runs phased deploy: core → Obtainium import → app-stores → Aurora UI.

## 1.5.0 (2026-07-07)

- `autojs6_watchdog` role moved into fleet collection.
- Meta-collection depends on domain collections >= 1.4.0.

## 1.4.0 (2026-07-07)

- Runtime redirects for legacy `stayturgid.fleet.*` FQCNs.
