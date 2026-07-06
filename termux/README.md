# Termux layer — boot scripts, repair, presence

Shell scripts that run **on the phone** inside Termux. Usable without AutoJs6 or Ansible if you deploy manually.

**Full project:** [../README.md](../README.md)

## What this module does

| Piece | Role |
|-------|------|
| `stayturgid-repair.sh` | Self-heal sshd, localhost:5555 ADB, Shizuku; prints `STATUS …` for callers |
| `repair-bridge.sh` | Polls `/sdcard/stayturgid_repair_now`; runs repair within ~2s (AutoJs6 fallback) |
| `claude-presence.sh` | Agent session indicator (torch, notification, optional consent `gate`) |
| `check-repo-version.sh` | Optional: notify when `version.json` on GitHub is newer |
| `boot/start-adb.sh` | Termux:Boot: sshd, wake-lock, 5-min self-heal loop, battery alarm |
| `boot/start-repair-bridge.sh` | Starts `repair-bridge.sh` at boot |
| `boot/start-autojs6-watchdog.sh` | Launches AutoJs6 `boot-launcher.js` after boot |

## Standalone use

**Minimum on device:** Termux (GitHub-signed), Termux:Boot, Termux:API, Shizuku with TCP mode (port 5555), `android-tools` in Termux.

```bash
mkdir -p ~/.termux/boot
cp stayturgid-repair.sh repair-bridge.sh claude-presence.sh ~/
cp boot/*.sh ~/.termux/boot/
chmod +x ~/*.sh ~/.termux/boot/*.sh
echo 'allow-external-apps=true' >> ~/.termux/termux.properties

pkg update && pkg upgrade -y
pkg update && pkg upgrade -y && pkg install -y openssh android-tools termux-api runit
sshd
```

Open **Termux:Boot** once after install. `start-adb.sh` runs repair every 5 min; for watchdog notifications and Shizuku UI repair, add [AutoJs6](../autojs6/README.md).

**Callers:** [AutoJs6](../autojs6/README.md) (`RUN_COMMAND`), [Ansible](../ansible/README.md) over SSH.

## Deploy with Ansible (recommended)

```bash
./ansible/mac/deploy-termux.sh s24   # or p7a
```

## Logs and status

```bash
~/stayturgid-repair.sh
tail -f ~/.stayturgid-repair.log
tail -f /sdcard/stayturgid_watchdog.log
```

## Related docs

- [HACKING.md §1.4](../HACKING.md) — manual Termux setup
- [HANDOFF.md](../HANDOFF.md) — repair architecture, Tasker removal notes
- [autojs6/README.md](../autojs6/README.md) — watchdog layer
