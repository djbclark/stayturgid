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

## NEXT STEP (blocked by import mechanism)

**Problem**: Tasker's "Import Project" refuses to import `upmon.prj.xml` because a project named `upmon` already exists on the device.

**Solution options** (try in order):

### Option A — Import task file directly (try first)
Tasker can import `.tsk.xml` files via the TASKS tab import flow:
1. In Tasker, tap the **TASKS** tab
2. Long-press anywhere in the empty task list (or use the menu)
3. Look for **Import Task** option
4. Navigate to `/sdcard/Tasker/tasks/ADB_Core_Watchdog.tsk.xml`

Push the task file first:
```bash
adb -s 35261JEHN12374 push ~/upmon-handoff/ADB_Core_Watchdog.tsk.xml /sdcard/Tasker/tasks/ADB_Core_Watchdog.tsk.xml
```

### Option B — Delete and re-import full project
```bash
# 1. In Tasker: long-press upmon tab → Delete (this removes the empty project)
# 2. Then import the full project:
adb -s 35261JEHN12374 push ~/upmon-handoff/upmon.prj.xml /sdcard/Tasker/projects/upmon.prj.xml
# 3. In Tasker: long-press house icon → Import Project → select upmon
```

### Option C — Use Tasker's internal backup/restore
Navigate to Tasker menu → Data → Restore → and point at the XML.

### After task is imported
1. Move task to `upmon` project (long-press task → Move to Project → upmon)
2. Create the `ADB_Interval_Check` profile:
   - In `upmon` project, PROFILES tab → tap + → Time → Every → 20 minutes
   - Link it to `ADB_Core_Watchdog` task
3. Enable the profile

---

## Step after Tasker import: Termux recovery script

Once SSH is fixed (`ssh u0_a590@pixel7a-termux -p 8022` works):

```bash
# Write this to ~/adb_shizuku_watchdog.sh on the Pixel:
ssh u0_a590@pixel7a-termux -p 8022 'cat > ~/adb_shizuku_watchdog.sh' << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
LOG_FILE="/data/data/com.termux/files/home/adb_shizuku_watchdog.log"
exec 1> >(tee -a "$LOG_FILE") 2>&1

echo "=== $(date) - Watchdog Run ==="

if ss -tln | grep -q ':5555 '; then
    echo "[OK] Port 5555 listening."
    exit 0
fi

echo "[INFO] Port 5555 closed. Attempting recovery..."

CURRENT_PORT=$(ss -tlnp 2>/dev/null | grep -E 'adbd' | head -1 | awk -F: '{print $2}' | cut -d' ' -f1 | tr -d ' ')

if [ -z "$CURRENT_PORT" ]; then
    echo "[WARN] Could not find adb port."
    exit 1
fi

adb connect "127.0.0.1:$CURRENT_PORT" >/dev/null 2>&1
adb -s "127.0.0.1:$CURRENT_PORT" tcpip 5555
sleep 3
adb connect 127.0.0.1:5555 >/dev/null 2>&1

adb -s 127.0.0.1:5555 shell sh /storage/emulated/0/Android/data/moe.shizuku.privileged.api/start.sh

sleep 2
if ss -tln | grep -q ':5555 '; then
    echo "[SUCCESS] Port 5555 now listening."
else
    echo "[ERROR] Failed to restore port 5555."
    exit 1
fi
SCRIPT

ssh u0_a590@pixel7a-termux -p 8022 'chmod +x ~/adb_shizuku_watchdog.sh'
```

Boot persistence via `com.termux.boot`: place a launcher script in `~/.termux/boot/`.

---

## Reboot-persistence problem (unresolved)

`persist.adb.tcp.port` is blank → port 5555 dies on reboot.
Current mitigation: Tasker 20-min profile re-enables it + Termux recovery script.
True fix requires either:
- The custom Shizuku fork (`thedjchi-beta`) that forces `tcpip 5555` on boot/Wi-Fi connect (not installed — stock Shizuku is present)
- Or a Termux:Boot script that runs `adb tcpip 5555` on device boot (simpler, try this first)

Termux:Boot launcher for `~/.termux/boot/start-adb.sh`:
```bash
#!/data/data/com.termux/files/usr/bin/bash
sleep 30  # wait for Wi-Fi
adb connect 127.0.0.1:5555 || true
adb tcpip 5555 || true
```

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
