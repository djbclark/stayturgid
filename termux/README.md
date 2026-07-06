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
| `stayturgid-battery-alarm.sh` | Tiered low-battery alerts (screen color blinks, torch, notification) |
| `boot/start-adb.sh` | Termux:Boot: sshd, wake-lock, 5-min self-heal loop, battery tier check |
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

pkg update && pkg upgrade -y && pkg install -y openssh android-tools termux-api runit
sshd
```

Open **Termux:Boot** once after install. `start-adb.sh` runs repair every 5 min; for watchdog notifications and Shizuku UI repair, add [AutoJs6](../autojs6/README.md).

**Low-battery alarm:** `stayturgid-battery-alarm.sh` runs every 5 min from the boot loop. While discharging, fires **once per tier**: 30%, 25%, 20%, 15%, 10%, 5%, then each 1% below 5 (when several tiers are crossed at once — e.g. first run at low battery — only the lowest fires; higher tiers are marked done). Each tier blinks the screen a solid color (purple @30 → red @5+) with brightness pulses; from 15% also pulses the flashlight (count matches tier). During DND/silent ringer: screen blink + one quick torch only (no toast/vibrate). Resets when charging or above 30%. Requires Termux:API + color PNGs in `~/.stayturgid/battery-colors/` (deployed by Ansible).

**Repo version check:** `check-repo-version.sh` runs at most once per day from the boot loop (notify only; deploy from Mac).

**Callers:** [AutoJs6](../autojs6/README.md) (`RUN_COMMAND`), [Ansible](../ansible/README.md) over SSH.

## Deploy with Ansible (recommended)

Deploys `stayturgid-repair.sh`, `repair-bridge.sh`, `claude-presence.sh`, `check-repo-version.sh`, and boot hooks.

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
- [HANDOFF.md](../HANDOFF.md) — repair architecture
- [autojs6/README.md](../autojs6/README.md) — watchdog layer
