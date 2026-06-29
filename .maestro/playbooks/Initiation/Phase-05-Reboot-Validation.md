# Phase 05: Reboot Validation

This is the proof that upmon actually works end-to-end. A cold reboot is the real-world failure scenario this whole project exists to survive — port 5555 and Shizuku must come back on their own, without anyone touching the device. This phase reboots the Pixel 7a, waits for it to come back online, and verifies wireless ADB, Shizuku, and the Tasker watchdog are all healthy afterward.

## Tasks

- [ ] Capture the pre-reboot baseline state for comparison. Run `adb -s 35261JEHN12374 shell ss -tln | grep 5555` and `adb -s 35261JEHN12374 shell pgrep -f shizuku`, recording that both port 5555 is listening and Shizuku is running before the reboot.

- [ ] Reboot the device via ADB: `adb -s 35261JEHN12374 reboot`. Immediately follow with `adb -s 35261JEHN12374 wait-for-device` to block until USB ADB reconnects after the reboot completes.

- [ ] Once USB ADB is back, wait for the boot sequence to fully settle (Termux:Boot's script itself sleeps 30s for Wi-Fi, so allow a buffer). Poll with a loop checking `adb -s 35261JEHN12374 shell getprop sys.boot_completed` every 5 seconds until it returns `1`, then wait an additional 45 seconds for the Termux:Boot launcher and Wi-Fi to finish settling.

- [ ] Verify wireless ADB reconnects successfully from the Mac: `adb connect 192.168.68.59:5555`. Expected output: `connected to 192.168.68.59:5555`. If this fails, check `adb -s 35261JEHN12374 shell ss -tln | grep 5555` to see if the port is listening at all — if not, the boot script didn't fire (see Phase 04's Termux:Boot permission note) and Tasker's 20-minute poll is now the fallback that will eventually self-heal it.

- [ ] Verify Shizuku is running post-reboot: `adb -s 35261JEHN12374 shell pgrep -f shizuku`. Expected: a process ID is returned (non-empty output).

- [ ] Verify the Tasker `ADB_Interval_Check` profile survived the reboot and is still enabled. Run `adb -s 35261JEHN12374 shell dumpsys activity services net.dinglisch.android.taskerm | head -20` to confirm Tasker's service restarted automatically. On the device, open Tasker's PROFILES tab and visually confirm `ADB_Interval_Check` still shows the green enabled checkmark.

- [ ] Document the final verified state by checking the Termux watchdog log for a fresh post-reboot entry: `ssh pixel7a-termux 'cat ~/adb_shizuku_watchdog.log'`. If Tasker's 20-minute poll has run since the reboot, confirm no failure notification was generated (or if one was, confirm it correctly described the transient state before self-healing). This confirms the full two-layer recovery system — Termux:Boot + Tasker polling — is operational end-to-end.
