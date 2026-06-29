# Phase 04: Boot Persistence via Termux:Boot

`persist.adb.tcp.port` is blank on this device, meaning port 5555 dies on every reboot. This phase deploys a Termux:Boot launcher script that fires automatically right after the device powers on, re-enabling tcpip mode on port 5555 before Tasker's 20-minute poll would even notice it was down. This is the first of upmon's two redundancy layers — Tasker's `ADB_Interval_Check` profile (Phase 01) is the second.

## Tasks

- [ ] Create the Termux:Boot directory structure over SSH: `ssh pixel7a-termux 'mkdir -p ~/.termux/boot'`. Verify it exists: `ssh pixel7a-termux 'ls -ld ~/.termux/boot'`.

- [ ] Write the boot launcher script via heredoc over SSH:
  ```
  ssh pixel7a-termux 'cat > ~/.termux/boot/start-adb.sh' << 'SCRIPT'
  #!/data/data/com.termux/files/usr/bin/bash
  sleep 30  # wait for Wi-Fi
  adb connect 127.0.0.1:5555 || true
  adb tcpip 5555 || true
  SCRIPT
  ```
  Confirm the content landed correctly: `ssh pixel7a-termux 'cat ~/.termux/boot/start-adb.sh'`.

- [ ] Make the boot script executable: `ssh pixel7a-termux 'chmod +x ~/.termux/boot/start-adb.sh'`. Confirm with `ssh pixel7a-termux 'ls -la ~/.termux/boot/start-adb.sh'` — should show the executable bit set.

- [ ] Verify the Termux:Boot app is installed and has the necessary permission to run scripts on boot. Run `adb -s 35261JEHN12374 shell pm list packages | grep com.termux.boot` to confirm the package is present. Note for the user: Termux:Boot requires the app to have been opened at least once after install for the boot receiver to register — if the boot script doesn't fire during Phase 05's reboot test, instruct the user to manually open the Termux:Boot app once.

- [ ] Dry-run the boot script logic manually (without rebooting) to confirm the commands inside it are valid in this environment: `ssh pixel7a-termux 'bash -n ~/.termux/boot/start-adb.sh && echo SYNTAX_OK'`. Expected output: `SYNTAX_OK`, confirming no shell syntax errors before relying on it during an actual boot.
