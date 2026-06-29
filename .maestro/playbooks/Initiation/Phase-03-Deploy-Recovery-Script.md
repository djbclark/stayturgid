# Phase 03: Deploy Termux Recovery Script

With SSH access working, this phase writes the `adb_shizuku_watchdog.sh` recovery script to the Termux home directory on the Pixel 7a. This script is the active-recovery half of upmon: if port 5555 ever closes, it detects the current adb port, re-enables tcpip mode on 5555, and re-launches Shizuku — all without any manual intervention.

## Tasks

- [ ] Write the recovery script to the device over SSH using a heredoc, then confirm it landed with the expected content:
  ```
  ssh pixel7a-termux 'cat > ~/adb_shizuku_watchdog.sh' << 'SCRIPT'
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
  ```
  Verify with `ssh pixel7a-termux 'cat ~/adb_shizuku_watchdog.sh | head -5'` — should show the shebang line and `LOG_FILE` assignment.

- [ ] Make the script executable: `ssh pixel7a-termux 'chmod +x ~/adb_shizuku_watchdog.sh'`. Confirm permissions with `ssh pixel7a-termux 'ls -la ~/adb_shizuku_watchdog.sh'` — should show `-rwx` in the permission bits.

- [ ] Run the script once over SSH to validate it executes cleanly: `ssh pixel7a-termux '~/adb_shizuku_watchdog.sh'`. Since port 5555 should currently be open (from earlier phases), expected output is `[OK] Port 5555 listening.` with no errors.

- [ ] Inspect the log file the script writes to, confirming it's accumulating run history correctly: `ssh pixel7a-termux 'cat ~/adb_shizuku_watchdog.log'`. Confirm the log contains a timestamped `=== ... - Watchdog Run ===` header followed by the `[OK]` or recovery-path output from the test run above.
