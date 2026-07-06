# stayturgid documentation index

Central map of all docs. **Start at the [project README](../README.md)** for overview and module picker.

## By module (use one without the rest)

| Module | README | Use when you want… |
|--------|--------|-------------------|
| Termux scripts | [termux/README.md](../termux/README.md) | Boot self-heal, repair script, presence indicator |
| Ansible | [ansible/README.md](../ansible/README.md) | Idempotent Termux deploy over SSH |
| Mac tools | [mac/README.md](../mac/README.md) | ADB reconnect launchd, outage monitor |
| Tasker | [tasker/README.md](../tasker/README.md) | Watchdog + GitHub auto-update |
| Tasker import tool | [tasker-io/README.md](../tasker-io/README.md) | Import/overwrite Tasker XML via ADB |
| Tasker auto-update | [tasker/auto-update/README.md](../tasker/auto-update/README.md) | `version.json` release flow |
| AutoJs6 | [autojs6/README.md](../autojs6/README.md) | JS watchdog instead of Tasker |
| AutoJs6 vs Tasker | [autojs6/COMPARISON.md](../autojs6/COMPARISON.md) | Pick a stack |
| Obtainium | [obtainium/README.md](../obtainium/README.md) | GitHub APK catalog and updates |
| Shared helpers | [shared/README.md](../shared/README.md) | `resolve-adb`, repo-root discovery |

## Project-wide

| Doc | Audience |
|-----|----------|
| [README.md](../README.md) | Everyone — hub + full-stack quick path |
| [HACKING.md](../HACKING.md) | Developers — clean install, Tasker XML, Obtainium, Termux swap |
| [HANDOFF.md](../HANDOFF.md) | AI agents / maintainers — state, roadmap, tooling rules, architecture research |

## Other

| Path | Notes |
|------|--------|
| [version.json](../version.json) | Tasker auto-update version source (GitHub raw) |
| [.maestro/playbooks/](../.maestro/playbooks/) | Legacy Maestro initiation flows (debug only) |

## Typical combinations

- **Termux only:** `termux/` + manual Shizuku
- **Termux + Ansible:** `ansible/` + SSH keys
- **7a-style:** `termux/` + `tasker/` + `tasker-io/` + `mac/`
- **S24-style:** `termux/` + `autojs6/` + `obtainium/` + `mac/`
- **Obtainium only:** `obtainium/` — no stayturgid watchdog required
