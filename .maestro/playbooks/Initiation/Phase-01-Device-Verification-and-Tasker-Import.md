# Phase 01: Device Verification & Tasker Watchdog Import

This phase verifies that the Pixel 7a is reachable over USB ADB, pushes the pre-built upmon project XML onto the device, and completes the Tasker import sequence. By the end, the `ADB_Core_Watchdog` task and `ADB_Interval_Check` profile are live in Tasker — the core 20-minute polling watchdog is up and running.

## Tasks

- [ ] Verify USB ADB connectivity to the Pixel 7a. Run `adb devices` and confirm serial `35261JEHN12374` appears as `device` (not `unauthorized` or `offline`). If it shows `unauthorized`, the user must unlock the phone and tap "Always allow from this computer." Confirm shell access with `adb -s 35261JEHN12374 shell echo OK` — expected output: `OK`.

- [ ] Verify all required project files are present in `~/upmon-handoff/`. Run `ls -la ~/upmon-handoff/*.xml` and confirm these three files exist with nonzero size:
  - `upmon.prj.xml` — full Tasker project (includes task + profile, preferred import)
  - `ADB_Core_Watchdog.tsk.xml` — standalone task XML (fallback only)
  - `tasker_schema_reference.xml` — schema reference

- [ ] Push the Tasker project file to the device and confirm it landed. Run these three commands in sequence:
  - `adb -s 35261JEHN12374 shell mkdir -p /sdcard/Tasker/projects`
  - `adb -s 35261JEHN12374 push ~/upmon-handoff/upmon.prj.xml /sdcard/Tasker/projects/upmon.prj.xml`
  - `adb -s 35261JEHN12374 shell ls -la /sdcard/Tasker/projects/upmon.prj.xml`
  Expected: file appears with nonzero size. If push fails with "permission denied", push to `/sdcard/upmon.prj.xml` first then run `adb -s 35261JEHN12374 shell mv /sdcard/upmon.prj.xml /sdcard/Tasker/projects/upmon.prj.xml`.

- [ ] On the Pixel 7a, complete the Tasker import (two steps — takes about 30 seconds total):
  1. Open Tasker → long-press the **upmon** tab at the bottom bar → tap **Delete** (the project is empty, nothing to lose)
  2. Long-press the **house icon** (home/projects button at bottom-left) → tap **Import Project** → navigate to `Tasker/projects/` → select `upmon`
  After import, confirm: the TASKS tab shows `ADB_Core_Watchdog` and the PROFILES tab shows `ADB_Interval_Check`.

- [ ] Enable the `ADB_Interval_Check` profile in Tasker. In the PROFILES tab, tap the profile row so the green checkmark is lit. Then verify Tasker is still running in the background: `adb -s 35261JEHN12374 shell dumpsys activity services net.dinglisch.android.taskerm | head -20` — should show Tasker's service is active.

- [ ] Smoke-test the watchdog task manually. In Tasker TASKS tab, tap `ADB_Core_Watchdog` → tap the play button (▶) to run it immediately. Expected behavior: if port 5555 is open and Shizuku is running, the task completes silently. If either is down, a high-priority notification fires — that confirms the alerting logic works. Either outcome is a success for this test.
