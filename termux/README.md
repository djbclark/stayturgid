# Termux layer — boot scripts, repair, presence

Shell scripts that run **on the phone** inside Termux. You can use this folder without Tasker, AutoJs6, or Ansible if you deploy the scripts manually (or via your own config management).

**Full project:** [../README.md](../README.md)

## What this module does

| Piece | Role |
|-------|------|
| `stayturgid-repair.sh` | Self-heal sshd, localhost:5555 ADB, Shizuku; prints `STATUS …` for callers |
| `repair-bridge.sh` | Polls `/sdcard/stayturgid_repair_now`; runs repair within ~2s (AutoJs6 path) |
| `claude-presence.sh` | Agent session indicator (torch, notification, optional consent `gate`) |
| `boot/start-adb.sh` | Termux:Boot: sshd, wake-lock, 5-min self-heal loop, battery alarm |
| `boot/start-repair-bridge.sh` | Starts `repair-bridge.sh` at boot |
| `boot/start-autojs6-watchdog.sh` | Nudges AutoJs6 `boot-launcher.js` (no-op when `mode=tasker`) |
| `tasker/stayturgid-repair` | Termux:Tasker wrapper → `~/stayturgid-repair.sh` |

## Standalone use

**Minimum on device:** Termux (GitHub-signed), Termux:Boot, Termux:API, Shizuku with TCP mode (port 5555), `android-tools` in Termux.

```bash
# On device (or push via adb/scp):
mkdir -p ~/.termux/boot ~/.termux/tasker
cp stayturgid-repair.sh repair-bridge.sh claude-presence.sh ~/
cp boot/*.sh ~/.termux/boot/
chmod +x ~/*.sh ~/.termux/boot/*.sh
echo 'allow-external-apps=true' >> ~/.termux/termux.properties

# Packages (always update before install):
pkg update && pkg upgrade -y
pkg update && pkg upgrade -y && pkg install -y openssh android-tools termux-api runit
sshd   # test once; boot script keeps it up
```

Open **Termux:Boot** once after install. No Tasker/AutoJs6 required — something else must **call** `stayturgid-repair.sh` on a schedule (cron-like loop in `start-adb.sh` runs it every 5 min).

**Optional callers:** [Tasker](../tasker/README.md) (Termux:Tasker), [AutoJs6](../autojs6/README.md) (`RUN_COMMAND`), or Ansible over SSH ([../ansible/README.md](../ansible/README.md)).

## Deploy with Ansible (recommended)

```bash
./ansible/mac/deploy-termux.sh s24   # or p7a
```

See [ansible/README.md](../ansible/README.md) — only needs SSH to Termux; does not install Shizuku or watchdog apps.

## Logs and status

```bash
~/stayturgid-repair.sh
# STATUS port=open shizuku=up sshd=up shell=yes

tail -f ~/.stayturgid-repair.log
tail -f /sdcard/stayturgid_watchdog.log   # if storage granted
```

## Related docs

- [HACKING.md §1.4](../HACKING.md) — manual Termux setup
- [HANDOFF.md](../HANDOFF.md) — Termux package policy, repair architecture
- [mac/README.md](../mac/README.md) — Mac-side ADB reconnect (pairs with this layer)
