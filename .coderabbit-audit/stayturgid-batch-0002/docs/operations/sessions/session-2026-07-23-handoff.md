# Handoff: Settings-state corruption investigation (2026-07-23)

## Summary

This handoff documents recent findings and next actions for two related bugs:

- Issue #41: Battery percentage display resets sporadically
- Issue #42: Portrait lock mode changes to free rotating unexpectedly

Both issues appear to share a root-cause hypothesis: Android system settings/state corruption (sleep/wake lifecycle or concurrent writes, possibly involving Shizuku).

## What was done

- Created GitHub issues #41 and #42 with impact, hypothesis, and investigation notes.
- Created tracked todos in the session tracker:
  - healing-registry-add-settings-state-corruption
  - annotate-mechanisms-settings-state
  - investigate-settings-state-corruption (now in_progress)

## Immediate next steps (investigation)

1. Collect device-side state around repro times. Run on each device:

   adb shell dumpsys settings > /tmp/settings-<device>-$(date -u +%Y%m%dT%H%M%SZ).txt
   adb shell dumpsys battery > /tmp/battery-<device>-$(date -u +%Y%m%dT%H%M%SZ).txt
   adb logcat -b all -d > /tmp/logcat-<device>-$(date -u +%Y%m%dT%H%M%SZ).txt

2. If Shizuku is present, collect its logs and recent activity timestamps.
3. Correlate with system sleep/wake cycles (use `dumpsys power` and kernel uptime) and automation task timestamps.
4. Attach all artifacts to both issues (#41 and #42) and summarize correlations.

## Where to store artifacts

- **Do not attach raw dumps to the public GitHub issues.** Raw `dumpsys`/logcat
  output contains device identifiers, account hints, and network details; this
  is a public repository. Store raw artifacts in the private site overlay repo
  (or a private location the operator names) and reference them from the issue.
- Post only short, sanitized excerpts (the specific corrupted settings rows,
  correlated timestamps) plus your summary/hypotheses as issue comments on
  #41/#42.

## Who should take this

- Investigator: (assign a human) — recommended: on-call device engineer or the person who observed the failures.
- Estimated time: 1–2 hours for initial data collection and correlation.

## Notes for healers

- After the investigation, add a `desired_states` entry to tests/healing_registry.json (ID: SETTINGS-STATE-CORRUPTION) and annotate the implementing mechanisms: device/termux/py/stayturgid_repair.py, the native agent (device/native-agent/ — the AutoJs6 repair.js/watchdog.js layer was retired by the K1 cutover, commit 195c5c7), and control/bin/firerpa_heal.py.
- Run `check_healing_coverage.py` to ensure tests/gates are satisfied.

## Contact

For clarifications, reply on issues #41/#42.

<!-- Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com> -->
