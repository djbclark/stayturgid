# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview.

## By module

| Module | README | Use when you want… |
|--------|--------|-------------------|
| Termux scripts | [termux/README.md](../termux/README.md) | Boot self-heal, repair script, presence indicator |
| Ansible | [ansible/README.md](../ansible/README.md) | Idempotent Termux deploy over SSH |
| Mac tools | [mac/README.md](../mac/README.md) | ADB reconnect launchd, outage monitor |
| AutoJs6 | [autojs6/README.md](../autojs6/README.md) | JS watchdog (only automation stack in repo) |
| Obtainium | [obtainium/README.md](../obtainium/README.md) | GitHub APK catalog and updates |
| F-Droid / Neo Store | [fdroid/README.md](../fdroid/README.md) | F-Droid repos + Neo Store (fleet-integrated) |
| Play / Aurora Store | [play/README.md](../play/README.md) | Aurora Store + apkeep/gplaycli (fleet-integrated) |
| Shared helpers | [shared/README.md](../shared/README.md) | `resolve-adb`, repo-root discovery |

## Project-wide

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Everyone — hub + full-stack quick path |
| [HACKING.md](../HACKING.md) | Developers — clean install, Obtainium, Termux swap |
| [HANDOFF.md](../HANDOFF.md) | AI agents / maintainers — state, roadmap, device fleet |

## Other

| Path | Notes |
|------|--------|
| [version.json](../version.json) | Repo release version; optional `termux/check-repo-version.sh` notifier |

## Typical combinations

- **Termux only:** `termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **Full stack:** `termux/` + `autojs6/` + `obtainium/` + `fdroid/` + `play/` + `mac/` + `./mac/deploy-fleet.sh`
- **Obtainium only:** `obtainium/` — APK updates without stayturgid watchdog
