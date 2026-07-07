# Code Review — stayturgid

> **Status (2026-07-06):** All findings below (H1–H2, M1–M11, L1–L13) were fixed
> in the commit(s) following this review. Fixes are code-only; devices still
> run the old scripts until the next `./mac/deploy-fleet.sh`.

**Scope:** Full-repo review at commit `6b705d5` ("feat(termux): tiered battery alarm with color screen blinks"), 2026-07-06.
**Method:** Every tracked shell/JS/Python/YAML/plist/JSON file read in full; docs skimmed for drift. No code changed — findings only. Smoke/unit tests reportedly pass; several findings below are in paths those tests don't exercise (boot-time process guards, lock-contention branches, DND/quiet paths, cross-device profiles).

**Verification:** H1, H2, M2, and M3 were confirmed empirically (non-destructively): H1 and the battery-alarm findings via sandboxed local runs with stubbed `termux-*`/`adb` commands, H2 via a read-only SSH probe of the live S24. Details inline under each finding.

Severity: **H** = broken behavior in production paths, **M** = incorrect/harmful in realistic conditions, **L** = quality/robustness/docs.

---

## High

### H1. `stayturgid-repair.sh` — functions called before they are defined (lock-contention branch)
`termux/stayturgid-repair.sh:24-44` — the `flock -n 9` failure branch calls `sshd_up` (line 26) and `sshd_listening` (line 28), but both functions are defined *below* it (lines 48–55). Bash resolves functions at call time, so whenever two invocations overlap (exactly the case this branch exists for — the 5-min boot loop, the repair bridge, and AutoJs6 RUN_COMMAND can all fire concurrently), the duplicate caller gets `sshd_up: command not found` on stderr and always reports `sshd=unknown`. The STATUS line consumed by the AutoJs6 watchdog is therefore wrong in precisely the concurrent case that commit `e5d89de` ("serialize invocations") was meant to fix.
**Fix:** move the function definitions above the `exec 9>` / `flock` block.
**Verified:** a local reproduction of the same structure (flock branch above the function definitions) prints `sshd_up: command not found`, `sshd_listening: command not found` and reports `sshd=unknown` — exactly the predicted failure.

### H2. `pgrep -f repair-bridge.sh` self-match — repair bridge never starts
Two occurrences:

- `termux/boot/start-repair-bridge.sh:9` — the guard `! pgrep -f repair-bridge.sh` runs inside a process whose cmdline is `bash …/.termux/boot/start-repair-bridge.sh`. The pattern `repair-bridge.sh` is a substring of `start-repair-bridge.sh`, so pgrep always matches the boot script itself and the `nohup ~/repair-bridge.sh &` line **never executes**. The fast-repair bridge is effectively never started at boot; the `/sdcard/stayturgid_repair_now` trigger-file fallback in `autojs6/lib/termux.js` silently does nothing until someone starts the bridge by hand.
- `autojs6/mac/setup-autojs6.sh:67` — same bug over SSH: the remote command string (`bash -c '… pgrep -f repair-bridge.sh >/dev/null || nohup ~/repair-bridge.sh …'`) itself contains the pattern, so pgrep matches the shell running the check, the `||` short-circuits, and the script prints "repair-bridge.sh started (or already running)" without starting anything.

**Fix:** anchor the pattern so it can't match wrappers, e.g. `pgrep -f '[r]epair-bridge\.sh$'` won't help against the path suffix — instead match the exact invocation: `pgrep -f "bash $HOME/repair-bridge.sh"` or use a pidfile written by `repair-bridge.sh` itself. (Note `mac/deploy-fleet.sh` and `mac/fleet-health.sh` avoid this class of bug by using `bash -s` heredocs — the pattern isn't in any cmdline — so those checks are fine.)
**Verified on the live S24 (read-only):** `pgrep -laf repair-bridge` run over SSH matched **its own remote shell** (`bash -c echo …; pgrep -laf repair-bridge; …`) in addition to the real bridge — confirming Termux's procps pgrep matches the caller's cmdline. The bridge *is* currently running on the S24 (pid 23005, presumably started by hand or a pre-guard deploy), but after the next reboot the boot guard will self-match and never restart it. Caution for future testing: **macOS/BSD pgrep does not exhibit this self-match** (verified locally), so Mac-side dry-runs of these guards pass while the on-device behavior fails.

---

## Medium

### M1. Battery alarm can permanently destroy the user's wallpaper
`termux/stayturgid-battery-alarm.sh:88-97,109-124` — `blink_screen_color` sets the wallpaper to solid-color PNGs and restores from a one-time backup taken via `adb shell "cmd wallpaper get-image"`. Failure modes:
- If `get-image` fails (live wallpapers don't support it; 5555 down; Samsung builds vary), the empty backup is deleted and `restore_wallpaper` becomes a no-op — the wallpaper is left as `black.png`/`red.png` forever.
- The backup is captured through `adb shell` stdout; without `exec-out`, binary output can be CRLF-mangled depending on adb/shell-protocol version, corrupting the PNG so the "restore" installs garbage.
- If the script is killed mid-blink (deploy-fleet's `pkill`, battery death, Termux OOM), nothing restores wallpaper/brightness; `clear_alert_state` on next charge doesn't try either.

**Fix:** abort the blink path entirely when the backup isn't verifiably a valid image (`file`/magic-byte check); use `adb exec-out cmd wallpaper get-image`; have `clear_alert_state` also run `restore_wallpaper`/`restore_brightness`. Alternatively, blink via brightness + torch only and drop wallpaper swapping — much lower blast radius.

### M2. Battery alarm fires a catch-up cascade of every missed tier
`termux/stayturgid-battery-alarm.sh:203-207` — the loop fires an alert for *every* unalerted tier ≥ current pct. First run of a freshly deployed device at 12% fires tiers 30, 25, 20, 15, 10 back-to-back: five full blink sequences, two torch runs, five notifications. Header comment says "fires once per tier while discharging", which implies crossing events, not backfill.
**Fix:** fire only the lowest applicable tier, then mark that tier *and all higher tiers* as alerted.
**Verified:** sandboxed run (stubbed `termux-*`/`adb`, fresh state, battery JSON `{"percentage": 12, "status": "DISCHARGING"}`) fired 4 tier alerts (30/25/20/15) in one pass: 4 notifications, 4 toasts, 20 wallpaper writes.

### M3. Battery alarm dies before its own guard under `set -euo pipefail`
`termux/stayturgid-battery-alarm.sh:187-189` — if `termux-battery-status` returns JSON without a `percentage` match, the `grep … | grep …` pipeline fails, the assignment fails, and `set -e` kills the script *before* the intended `[ -n "$pct" ] || exit 0` guard runs. The caller ignores the exit code, so the net effect is a silently skipped check — but the guard is unreachable dead code for the case it was written for. Same pattern for `status` on line 188.
**Fix:** append `|| true` inside the substitutions, e.g. `pct="$(… | head -1 || true)"`.
**Verified:** sandboxed run with battery JSON lacking `percentage` exits 1 (killed by `set -e` at the `pct=` assignment) instead of the guard's intended exit 0.

### M4. Consent gate defaults to "continue" when the dialog times out
`termux/claude-presence.sh:103-127` — the gate only appears when the phone *is* actively in use, yet if the user doesn't answer within 30 s (`timeout 30 termux-dialog`), the empty result falls into the `*)` branch and returns 0 ("proceed"). The person demonstrably using the phone gets 30 s to notice a dialog, then the agent takes over anyway. For a consent gate, timeout should fail closed (treat as "Check again in 10 minutes").

### M5. `idle_foreground` allowlist is Samsung-only — Pixel 7a home screen counts as "in use"
`termux/claude-presence.sh:62-70` — the idle list includes `com.sec.android.app.launcher` (Samsung) but not the Pixel launcher (`com.google.android.apps.nexuslauncher`), even though the same script deploys to both phones via Ansible. On the p7a, sitting on the home screen with the screen on triggers the consent dialog instead of proceeding silently. Consider a per-device or pattern-based launcher check (`dumpsys` role `home`), or add the Pixel launcher.

Also: line 29 gives `STAYTURGID_AGENT` precedence over `$3`, while the header comment (line 11) documents the reverse order.

### M6. `termux_pkg` module mutates the system in `--check` mode and triple-runs `pkg update`
`ansible_collections/stayturgid/fleet/plugins/modules/termux_pkg.py` — the module declares `supports_check_mode=True`, but `pkg update` and `apt-get full-upgrade` execute unconditionally, so `ansible-playbook --check` actually upgrades every package on the phone. Only install/remove honor check mode.
Additionally, a normal role run executes `pkg update` up to 3× and `full-upgrade` up to 2×: task 1 (update+upgrade), task 2 (update again), and lines 147-150 repeat update/upgrade before install. Over Termux SSH each pass is slow; guard the lines 146-150 re-run (the cache was refreshed moments earlier) and wrap the update/upgrade calls with `if not module.check_mode`.

### M7. Watchdog notifications use random IDs — unbounded pileup during outages
`autojs6/lib/notify.js:36` — `nm.notify(randomId, …)` means every 20-min cycle of a persistent outage (Tailscale down, sshd down) posts a *new* notification that nothing ever clears. A weekend outage produces ~150 stacked alerts. Use a stable ID per alert type (e.g. hash of the title) so repeats coalesce, and cancel it on recovery.

### M8. Watchdog log grows without bound and is re-read in full every 500 ms
`/sdcard/stayturgid_watchdog.log` is appended by the repair script, the boot loop, and every AutoJs6 cycle, and is never rotated (unlike the Mac logs, which are trimmed to 1000 lines). `autojs6/lib/termux.js:29-46` polls `log.latestRepairTimestampMs()` every 500 ms for up to 12 s, and each call (`autojs6/lib/log.js:52-65`) reads the entire file over FUSE and splits it. Months of operation make every watchdog cycle progressively slower and more battery-hungry. Trim the log (e.g. keep last 500 lines when >1000) in `log.append` or in the repair script, and/or read only the tail.

### M9. `adb-reconnect.sh` posts a macOS notification every 60 seconds while a device is away
`mac/adb-reconnect.sh:70` + `mac/com.djbclark.stayturgid.adb-reconnect*.plist` (`StartInterval` 60) — the failure branch fires `display notification` on *every* run, so a phone that's powered off or out with you generates 60 notifications/hour per device, indefinitely. `mac/access-monitor.sh` already solves this properly (consecutive-failure counter, one alert per outage + one per recovery); the reconnect script should stay silent on failure (or adopt the same state-file debounce) and let access-monitor own alerting.
Minor, same file: line 63 caches whatever address just connected — including the mDNS `_adb-tls-connect` endpoint whose port is ephemeral (changes each boot), poisoning the "last known-good" cache until the next full fallback pass.

### M10. Ansible clobbers `termux.properties` and never reloads settings
`ansible/roles/termux_userland/tasks/main.yml:55-59` — templating `termux.properties` from a one-line template silently deletes any other user properties (extra-keys, bell, etc.). termux/README.md's manual path even documents `>> ~/.termux/termux.properties` (append), so the two paths disagree. Use `ansible.builtin.lineinfile` keyed on `allow-external-apps=`. Also, changed properties only take effect after `termux-reload-settings` (or app restart) — worth a handler, since RUN_COMMAND silently fails until then.

### M11. Shizuku JSON patch can drop other apps' authorizations on transient read failure
`autojs6/mac/grant-shizuku.sh:50` and `obtainium/mac/enable-shizuku-installer.sh:64` — `CURRENT="$(sh_shell "cat $SHIZUKU_JSON" … || true)"`; any transient failure (5555 not connected in the Termux-side adb server, adbd hiccup) yields an empty string, which the Python patcher treats as "fresh config" and rewrites `shizuku.json` containing *only* the one app being granted — revoking every other authorized app. Distinguish "file empty/missing" from "read failed" (check the `cat` exit code before defaulting) and abort on read failure.

---

## Low

### L1. `dnd_or_sleep_quiet` dead read
`termux/stayturgid-battery-alarm.sh:27` — `ringer` is assigned from `zen_mode_ringer_level` and never used before being overwritten at line 33. Either the intended check is missing or the line should be deleted.

### L2. `check-repo-version.sh` uses a variable named `local` at top level
`termux/check-repo-version.sh:18-19` — `local=""` outside a function works (it's just a variable named `local`) but reads as a bug. Rename to `current`/`seen`.

### L3. Blind-coordinate and first-match UI fallbacks
- `autojs6/lib/shizuku.js:50-55` — if the Shizuku manager didn't actually open (slow device, lock screen), `click(profile.shizukuStartCoords…)` taps blind coordinates on whatever is foreground.
- `autojs6/lib/shizuku.js:79-84` — if the "Wireless debugging" entry isn't found, the code clicks the *first* `android.widget.Switch` on the Developer-options screen if unchecked; on some OEM screens that's not the wireless-debugging toggle. Consider verifying the current activity/window title before either fallback.
- `obtainium/mac/enable-shizuku-installer.sh:95,132,147` and `obtainium/mac/apply-updates.sh:25-27,45` — hardcoded tap coordinates are resolution-specific to these two phones; fine for a personal fleet, but the fallbacks fire silently. At least log which path was taken (the scripts mostly do — good).

### L4. `config.detectDeviceProfile()` silently defaults unknown hardware to the p7a profile
`autojs6/lib/config.js:36` — an unrecognized device inherits p7a's `tailscaleIp` and tap coordinates, so `isTunUp`'s self-ping and the catastrophic tap fallback act on wrong data. Log a warning line when defaulting.

### L5. `boot-launcher.js` declares `"auto";`
`autojs6/scripts/boot-launcher.js:5` — the launcher only enumerates engines and execs `main.js`; it doesn't need accessibility. Because `start-adb.sh` re-launches it every 5 minutes, `"auto"` can repeatedly bounce the user to Accessibility settings whenever the service is off. `main.js`/`guard.enforce()` already handles the a11y requirement (and `main.js:14-15` double-calls `auto.waitFor()` — `guard.enforce()` already waits; harmless but redundant).

### L6. `test-tailscale-down-once.js` sleeps 2 ms, not 2 s
`autojs6/scripts/test-tailscale-down-once.js` — `sleep(2)` after `tailscale.relaunch()`; AutoJs6 `sleep()` takes milliseconds. Should be `sleep(2000)`.

### L7. `setup-autojs6.sh` inconsistencies
- Line 64 (`scp … repair-bridge.sh`) is unindented and, unlike its siblings, has no `2>/dev/null ||` fallback — under `set -e` a failure aborts setup halfway (after the repair script but before boot hooks).
- Line 81 recomputes `SCRIPT_DIR` already set at line 7.
- Line 54 `case "$1"` duplicates the alias→SSH-host mapping that exists in three other scripts; a `resolve_ssh_host` next to `resolve_adb` in `shared/mac/` would remove four copies.

### L8. Package/boot-script lists duplicated between `group_vars` and role defaults
`ansible/group_vars/stayturgid.yml` and `ansible/roles/termux_userland/defaults/main.yml` carry identical `stayturgid_termux_packages` / `stayturgid_boot_scripts` lists. group_vars wins, so edits to defaults silently do nothing for the fleet. Keep one (defaults), delete the other.

### L9. `deploy-fleet.sh` aborts remaining hosts on first failure
`mac/deploy-fleet.sh:33-42` — with `set -e`, an s24 failure means p7a is never attempted. For a fleet tool, catch per-host failures, continue, and exit non-zero at the end (fleet-health.sh already does exactly this).

### L10. `fleet-health.sh` ADB diagnosis is misleading
`mac/fleet-health.sh:48-54` — `resolve_adb` returns a Tailscale `ip:5555` without ensuring `adb connect` happened, so a not-currently-connected device prints "(no recent watchdog log)" when the truth is "adb not connected". Also the success branch prints the matched log line but a *missing* log line still takes the success path (grep in `adb shell` returns the shell's exit code inconsistently across devices); consider checking output non-emptiness instead.

### L11. Duplicate-invocation repair path always exits 0
`termux/stayturgid-repair.sh:41-43` — when the lock is held, the script reports rc=0 regardless of what the read-only probes saw (even `PORT=CLOSED_NO_SHELL`). Callers can treat a genuinely broken state as healthy if they race the boot loop. Consider exiting 1 when the probe sees `CLOSED_NO_SHELL`, or at least documenting that a `skipped-duplicate` STATUS is advisory only. (Blocked on H1 — this branch currently can't evaluate sshd at all.)

### L12. `Date.parse("YYYY-MM-DD HH:MM:SST…")` local-time assumption
`autojs6/lib/log.js:60` — staleness detection parses timestamps written in device-local time with `Date.parse(m[1].replace(" ", "T"))`. Whether a no-offset ISO string parses as local or UTC varies by JS engine vintage (ES5 said UTC; ES2016+ says local). Your on-device stale-loop test passing implies Rhino/AutoJs6 does local here, but an AutoJs6 upgrade could silently shift this by the UTC offset (making stale detection either always-stale or never-stale). Constructing the Date from the captured components (or comparing formatted strings) removes the ambiguity.

### L13. Docs nits
- `termux/README.md` standalone section runs `pkg update && pkg upgrade -y` twice in a row (lines ~30-31).
- `termux/README.md` says the torch pulse "count matches tier" from 15% — matches code (`pulse_torch "$blinks"`), but the DND behavior line omits that the *notification* is still posted (silently) in quiet mode; minor drift from the script header, which does say it.
- `obtainium/mac/apply-updates.sh:6` comment says button2 = "positive action on Samsung" — worth a note that this is empirically Samsung-specific, since the script accepts `p7a` too.

---

## What looks good

- The layered repair architecture (Termux 5-min loop → repair bridge → AutoJs6 UI repair) is cleanly separated, and each layer degrades gracefully when the next one is missing.
- `flock`-based serialization of the repair script (modulo H1) and the sticky `setprop service.adb.tcp.port 5555` are the right primitives.
- `mac/access-monitor.sh` is a model citizen: consecutive-failure debounce, single alert per outage, recovery notification, log trimming. Several other scripts should copy it (see M9).
- `shared/mac/resolve-adb.sh` + the compatibility shim in `mac/` is a tidy way to de-duplicate without breaking existing callers; `stayturgid-root.sh`'s marker-directory walk is robust.
- The Ansible role is genuinely idempotent (verified repair run with `failed_when: rc not in (0,1)` is a nice touch), and `example-standalone.yml` keeps the module honest about fleet-specific assumptions.
- Test scripts (`test-stale-loop-once.js`, `test-tailscale-down.sh`) validate real failure paths end-to-end on hardware, not mocks — rare and valuable for this kind of stack.

## Suggested priority

1. **H1, H2** — small diffs, restore intended behavior of existing features.
2. **M1** (wallpaper) and **M4/M5** (consent gate) — user-facing damage/behavior on both phones.
3. **M7, M8, M9** — outage ergonomics; cheap fixes.
4. **M6, M10, M11** — deploy-path correctness.
5. The L items opportunistically.
