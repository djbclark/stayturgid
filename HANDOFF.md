# upmon — Full Project Handoff

## How to restart this session cheaply

**USE CLAUDE CODE IN THE TERMINAL, NOT WARP.**

Warp's agent burns API credits for every message. Claude Code in the terminal (once you're on Pro) uses your subscription's session limits instead — no per-token billing.

```bash
claude   # opens interactive session in terminal
```

Then paste the contents of this file as your opening message, or say:
> "Read ~/upmon-handoff/HANDOFF.md and resume the upmon project from where we left off."

Make sure `claude --version` shows you're on your Pro subscription account (Danny's account), not an API key. Run `/status` inside Claude Code to confirm plan type shows "Pro" or "Max", not "API".

---

## Device & connectivity facts (verified)

- **Device**: Google Pixel 7a, Android 16, serial `35261JEHN12374` (USB) or `192.168.68.59:5555` / `192.168.68.59:46809` (LAN)
- **USB adb**: `adb -s 35261JEHN12374 <cmd>` — most reliable, use this
- **Static port 5555**: adbd IS listening on `:5555` right now (`service.adb.tcp.port=5555`), but `persist.adb.tcp.port` is blank → NOT reboot-persistent (key watchdog problem to solve)
- **Wireless debug dynamic port**: `46809` (rotates on reconnect/reboot)
- **SSH to Termux**: `ssh u0_a590@pixel7a-termux -p 8022` — currently FAILS (key auth rejected). User offered to fix this. Fix it before the Termux script step.
- **Tasker**: v6.7.5-beta, package `net.dinglisch.android.taskerm`, `WRITE_SECURE_SETTINGS` granted (user 0) ✅
- **Shizuku**: `moe.shizuku.privileged.api` installed (stock, not custom fork)
- **Termux**: `com.termux`, `com.termux.tasker`, `com.termux.boot`, `com.termux.api` all installed ✅

## Shell commands verified to work in Android shell (adb shell / Tasker Run Shell)

```bash
# Port check (works despite "Cannot open netlink socket" warning — warning is harmless):
ss -tln 2>/dev/null | grep -q ":5555" && echo "PORT_OK" || echo "PORT_CLOSED"

# Shizuku process check:
pgrep -f shizuku > /dev/null 2>&1 && echo "SHIZUKU_OK" || echo "NO_SHIZUKU"
```

---

## Tasker project state on device

- **`upmon` project tab** EXISTS in Tasker (bottom bar: house icon · Stubs · 1:1 · **upmon**)
- The project is currently **empty** (no tasks, no profiles yet)
- The files below need to be imported INTO the existing upmon project

### Files in this directory

| File | Purpose |
|------|---------|
| `ADB_Core_Watchdog.tsk.xml` | Task XML ready to import — the main watchdog task |
| `upmon.prj.xml` | Full project XML (not directly importable because project name conflicts) |
| `tasker_schema_reference.xml` | Frozen Auditor project — reference for exact Tasker v6.7.5 XML schema |

---

## What ADB_Core_Watchdog.tsk.xml does

Task: `ADB_Core_Watchdog` (7 actions):

1. **Secure Settings Global** `adb_enabled = 1`
2. **Secure Settings Global** `adb_wifi_enabled = 1`
3. **Run Shell** → `ss -tln | grep -q ":5555" && echo PORT_OK || echo PORT_CLOSED` → stored in `%PORT_CHECK`
4. **Run Shell** → `pgrep -f shizuku && echo SHIZUKU_OK || echo NO_SHIZUKU` → stored in `%SHIZUKU_CHECK`
5. **If** `%PORT_CHECK ~ PORT_CLOSED` **OR** `%SHIZUKU_CHECK ~ NO_SHIZUKU`
6. **Notify** (high priority, title: "⚠ Wireless ADB / Shizuku Failure", body includes both variable values)
7. **End If**

Profile to create: `ADB_Interval_Check` — Time type, every 20 minutes, triggers `ADB_Core_Watchdog`.

---

## COMPLETED STEPS (as of 2026-06-29)

### ✅ Step 1 — Tasker project imported and active
- Deleted empty upmon project via maestro flow (`.maestro/playbooks/tasker_import_upmon.yaml`)
- Imported `upmon.prj.xml` via Tasker UI (long-press house → Import Project)
- **TASKS tab**: `ADB_Core_Watchdog` present ✅
- **PROFILES tab**: `ADB_Interval_Check` present and **enabled** (toggle ON) ✅

### ✅ Step 2 — Termux SSH fixed
- Key generated: `~/.ssh/termux_key` (ed25519)
- Installed via Termux UI (bash script on /sdcard, typed into Termux terminal)
- **Direct WiFi SSH is blocked by Android firewall** — use ADB port forward instead:
  ```bash
  adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
  ssh -i ~/.ssh/termux_key -p 8022 localhost
  ```

### ✅ Step 3 — Recovery script deployed
- `~/adb_shizuku_watchdog.sh` deployed on device via SSH-over-ADB-forward
- Checks port 5555, attempts recovery via `adb tcpip 5555` if closed
- Logs to `~/adb_shizuku_watchdog.log`

### ✅ Step 4 — Termux:Boot persistence configured
- `~/.termux/boot/start-adb.sh` deployed — fires on boot, waits 30s for WiFi, runs `adb tcpip 5555`

---

## REMAINING STEP

### Step 5 — Test: reboot and verify ← **DO THIS NEXT**

```bash
# 1. Reboot the device (physically or via adb):
adb -s 35261JEHN12374 reboot

# 2. Wait ~90 seconds for boot + WiFi + Termux:Boot 30s delay

# 3. Re-establish ADB (USB auto-reconnects):
adb -s 35261JEHN12374 shell "ss -tln | grep :5555"
# Expected: LISTEN line on :5555

# 4. Optionally re-establish ADB forward for SSH:
adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost 'cat ~/adb_shizuku_watchdog.log | tail -10'
```

If port 5555 is listening after cold reboot without any manual intervention, upmon is working.

**Note**: `adb -s 35261JEHN12374 forward tcp:8022 tcp:8022` must be re-run after each USB reconnect (forwards don't persist across adb server restarts).

---

## Claude Code model to use

The default model has already been set to `claude-sonnet-4-6` in `~/.claude/settings.json`.
This uses the Pro subscription session limits, not API credits.

---

## Key file paths on Mac

- Handoff dir: `~/upmon-handoff/`
- Claude Code settings: `~/.claude/settings.json` (model: claude-sonnet-4-6)
- Tasker XML on device: `/sdcard/Tasker/tasks/`, `/sdcard/Tasker/projects/`

## Key file paths on Pixel 7a

- Tasker data: `/sdcard/Tasker/`
- Shizuku start script: `/storage/emulated/0/Android/data/moe.shizuku.privileged.api/start.sh`
- Termux home: `/data/data/com.termux/files/home/`
- Termux boot dir: `/data/data/com.termux/files/home/.termux/boot/`
