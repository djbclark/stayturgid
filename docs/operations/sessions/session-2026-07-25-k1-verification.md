# Session — K1 fleet-state verification (2026-07-25)

**Audience:** operator + next agent
**Tracks:** [#43](https://github.com/djbclark/stayturgid/issues/43) (fleet-state verification), [#44](https://github.com/djbclark/stayturgid/issues/44) (OpenObserve auth, fixed same session), [#45](https://github.com/djbclark/stayturgid/issues/45) (release APK, referenced)
**Repo commits this session:** `40e9fce` (#44 fix), `2c9d7c6` (AutoJs6 uninstall), `6925e2d` (a11y correction)

## Summary

Started from #43's claim that the 2026-07-22 K1 cutover's fleet-state was
unverified. Live-checked all three devices (s24, hd8, p7a — all reachable
over Tailscale + adb this session) rather than trusting the commit's claims.

## 1. AutoJs6 removal — was claimed done, was actually false

`pm path org.autojs.autojs6` returned a real installed APK on **all three**
devices, including s24, the one device the 2026-07-22 cutover session
claimed to have confirmed live. The Ansible uninstall task's
`failed_when: false` meant this went undetected.

**Fixed:** uninstalled via `adb shell pm uninstall org.autojs.autojs6` on
all three. `pm path` now empty everywhere. Agent core health unaffected
(`shizuku=up sshd=up shell=yes`) immediately after removal on all three.

Also checked and ruled out a live risk: `device/termux/cfengine/policy/stayturgid.cf`
has `check_autojs6`/`check_a11y` bundles that would restart AutoJs6 if it
saw it not running — but nothing on the Mac side currently invokes that file
via `cf-runagent` (confirmed via repo-wide grep), and the deployed
`masterfiles/promises.cf` on-device is just CFEngine's stock example policy.
Dead code, not a live resurrection risk — but worth removing/cleaning up
since it references a package that's now gone for good.

## 2. `a11y` probe — corrected a same-day mistake

Right after uninstalling AutoJs6, `agent.log` briefly still showed
`a11y=up` on all three devices. I initially read this as "the native agent
has its own accessibility service" and said so in `docs/STATUS.md`,
`docs/options.md`, and a GitHub comment on #43. **That was wrong**, and I
posted a correction to all three once I caught it.

`ComonitorProbes.probeA11yListed()` (`device/native-agent/app/src/main/kotlin/org/stayturgid/agent/ComonitorProbes.kt:23,99`)
only ever checks for AutoJs6's specific accessibility-service component
string. The `a11y=up` reading was a stale `enabled_accessibility_services`
settings-db entry that hadn't been purged yet; within minutes it correctly
settled to `a11y=down` on all three devices, where it will now stay
permanently — the native agent has no accessibility service of its own.

**Follow-up not yet done:** `stayturgid_repair.py`'s self-heal loop
(`device/termux/py/stayturgid_repair.py:914-951`, "detection only — user
must enable manually") and `control/lib/fleet_health.py`'s `autojs6_a11y`
probe are both still hardcoded to AutoJs6 and will keep
logging/reporting `ACTION_REQUIRED: AutoJs6 accessibility disabled` /
`autojs6_a11y=missing` fleet-wide, forever, now that AutoJs6 is
intentionally gone. Noise, not a functional break. Needs a follow-up patch
to either remove this check entirely or repoint it at whatever (if
anything) is meant to replace AutoJs6's a11y role.

## 3. Debug vs. release build — confirmed live

Every device has **both** packages installed side by side:

- `org.stayturgid.agent` — versionCode 5, `0.3.1-heartbeat-heal`, not
  debuggable, untouched since 2026-07-22 (stale).
- `org.stayturgid.agent.debug` — versionCode 10, `0.3.6-diagnostics-debug`,
  `DEBUGGABLE`, last updated 2026-07-24.

Fresh `agent.log` timestamps confirm `.debug` is the one actually running
fleet-wide. Matches the known gap tracked in #45 — no surprise, but now
directly confirmed instead of assumed.

## 4. `CLOSED_NO_SHELL` soak — attempted, not yet achieved; found a bigger issue instead

Goal: force port 5555 closed on a live device and confirm the native
agent's `CatastrophicRepair` (`device/native-agent/app/src/main/kotlin/org/stayturgid/agent/CatastrophicRepair.kt`)
restores it unassisted.

**s24 (Samsung/One UI):** tried `adb shell settings put global adb_wifi_enabled 0`
and `adb -s <dev> usb` to force classic TCP ADB closed. Neither worked —
port 5555 stayed open through both. This ROM appears to keep the network
debugging listener alive independently of those levers, unlike stock AOSP
behavior (`adb_wifi_enabled` controls the newer TLS wireless-debugging
flow, not classic `service.adb.tcp.port`, and `adb usb`'s effect on an
already-open Samsung listener didn't stick). Restored to original state,
no residual changes.

**p7a (Pixel 7a, closer to stock AOSP):** rebooted for real — the actual
real-world trigger this whole mechanism exists for. Required a physical
unlock partway through boot (Android FBE holds user-space app data,
including Termux/Tailscale, until first unlock) — operator was on-site and
unlocked it.

Port 5555 came back on its own after boot on this device — `CLOSED_NO_SHELL`
was never actually triggered, so the repair path itself remains untested.
**But the reboot surfaced a more significant finding:**

### The real finding: boot-triggered start doesn't reliably run the comonitor loop

`BootReceiver` fired correctly (`logcat` confirms
`am_foreground_service_start` for `HostService` via `BOOT_COMPLETED`
within ~1s of boot completing), and the process stayed alive
(`dumpsys activity services` showed a live `ServiceRecord`, `ps` showed both
the host and `:userservice` processes running). **But no new line appeared
in `agent.log` for 5+ minutes** — the comonitor heartbeat loop
(`HostService.startHeartbeatLoop()`, 20-minute interval, should fire once
~2s after `onCreate()` regardless of screen state per the code) never
visibly ran.

Comparison: manually restarting the same app via
`control/tools/native-agent/start_agent.py` (force-stop, then
`am start` on `MainActivity`) produced a clean, fast sequence in the logs —
`Shizuku binder received` → `bindUserService requested` → `SCREEN_ON` →
`HostService created screenOn=true` → `UserService connected` →
`pingAwake IPC ok` → a fresh comonitor STATUS line — all within **3 seconds**.

Root cause not yet identified. Hypothesis to check next: `onCreate()`'s
early registration of the dynamic `screenReceiver` for
`ACTION_SCREEN_ON`/`ACTION_SCREEN_OFF` may behave differently when the
process is cold-started directly by `BootReceiver` (no Activity, no
already-on-screen context) versus started via `MainActivity` (screen
already known-on). `startHeartbeatLoop()` is called unconditionally from
`onCreate()` per the code and shouldn't depend on screen state at all —
but the observed behavior says otherwise. Needs a live, filtered logcat
capture **during** a real boot (this session's post-hoc `logcat -d --pid=<pid>`
came up completely empty for the boot-triggered process, most likely
because Android's logcat ring buffer had already rotated past those lines
under the load of every other app's `BootReceiver` firing in the same
window — not concluded to be a functional silence, just an evidence gap).

**Practical implication if this holds up:** if a fleet device reboots for
real with nobody around, the catastrophic-repair path may never actually
engage on its own, undermining the "catastrophic" tier's whole premise.
This is now the top-priority open question for #43, ahead of finishing the
`CLOSED_NO_SHELL` soak itself.

## Next steps (not yet done this session)

1. Root-cause the boot-vs-manual-start gap with a live, streaming logcat
   capture started **before** triggering a reboot, filtered by package name
   from t=0 (not a post-hoc dump).
2. Repeat the reboot test on hd8 and s24 to see whether the same gap
   reproduces fleet-wide, and whether `CLOSED_NO_SHELL` can actually be
   triggered on either of them (hd8 in particular: an earlier, separate
   investigation into Fire OS 8 wireless-debugging persistence found that
   Fire OS resets `adb_wifi_enabled` on every reboot — see the Claude
   memory note from that session — so hd8 may be the device most likely to
   actually produce `CLOSED_NO_SHELL` for real, but also the one with the
   most documented history of `BOOT_COMPLETED` reliability problems on this
   OS).
3. Once/if the boot-start gap is understood, fix it and re-run the soak
   properly.
4. Clean up the AutoJs6-specific self-heal/health-probe staleness (item 2
   above) — separate, smaller fix.
