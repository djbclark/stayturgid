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

### Root cause found (confirmed via live-streamed logcat through a second round of reboots)

Rebooted p7a, hd8, and s24 again with a background script that polled for
Tailscale reachability and started continuous (not post-hoc) `adb logcat`
capture the instant each device reconnected, to catch the actual boot-time
sequence instead of relying on a buffer that rotates within a couple
minutes under full-boot load. p7a and s24 reconnected and captured cleanly
(both needed a physical unlock again — FBE holds Termux/Tailscale until
first unlock); hd8 did not reconnect within the capture window, a separate,
known Fire OS quirk (see the Fire OS 8 ADB investigation referenced below)
possibly compounding the reboot delay — not resolved this session.

**s24's capture caught the exact mechanism, in the log:**

```
06:53:33.018 StayTurgidBoot: starting host for android.intent.action.BOOT_COMPLETED
06:53:33.049 StayTurgidHost: Shizuku not running
06:53:33.052 StayTurgidHost: HostService created screenOn=true
06:53:35.081 StayTurgidHost: comonitor skipped — not bound          <- first (and only near-term) attempt
06:53:37.610 StayTurgidHost: Shizuku binder received                 <- binder ready 2.5s AFTER the skip
06:53:38.593 StayTurgidHost: pingAwake IPC ok
```

`HostService.callComonitor()`
(`device/native-agent/app/src/main/kotlin/org/stayturgid/agent/HostService.kt:307-314`):

```kotlin
private fun callComonitor() {
    var svc = serviceRef.get()
    if (svc == null) {
        ensureBound()
        // Binder connect is async; skip this tick if not ready yet.
        svc = serviceRef.get()
        if (svc == null) {
            Log.w(TAG, "comonitor skipped — not bound")
            ...
```

And `startHeartbeatLoop()` (`HostService.kt:272-286`):

```kotlin
heartbeatJob = scope.launch {
    ensureBound()
    delay(2_000)       // <- fixed 2s gap, assumes Shizuku is bound by then
    callComonitor()     // <- skipped if not, per above
    while (isActive) {
        delay(COMONTOR_INTERVAL_MS)   // 20 minutes
        ensureBound()
        callComonitor()
    }
}
```

The comment on `callComonitor()` ("Binder connect is async; skip this tick
if not ready yet") shows the race was known about — but the consequence
wasn't: since the retry only happens on the next 20-minute tick, **every
real device boot loses its first comonitor cycle if Shizuku's binder takes
longer than the fixed 2-second gap to come up**, which it did on both s24
(2.5s late) and, by strong inference, p7a (5+ minutes of total silence on
two separate reboots is consistent with losing the race and falling into
the 20-minute gap; p7a's capture this round started a couple seconds after
the initial burst and didn't catch the skip line directly, but the
downstream symptom matches exactly).

**Practical implication:** after every real, unattended device reboot,
there's a ~20-minute window where the native agent has no fresh
comonitor/health data and is **not checking for `CLOSED_NO_SHELL` at all**
— directly undermining the "catastrophic" tier's premise for that whole
window. This is a real, fixable bug, not a config or environment issue:
either lengthen/retry the initial delay, or make `ensureBound()`
synchronously await the binder connection before the first `callComonitor()`
attempt. Not fixed in this session — flagged here and on #43 for a
follow-up code change + rebuild/redeploy, which is a bigger scope change
than this session's live diagnosis.

## Next steps

1. **Fix the boot-time race** in `HostService.kt` (see above) — needs a
   code change, rebuild, and fleet redeploy; not done this session.
2. Re-run the `CLOSED_NO_SHELL` soak properly once the race is fixed —
   right now the soak can't be trusted even if it "passes," since the
   agent might just be outside the 20-minute blind window rather than
   genuinely repairing.
3. Get hd8 reconnected and captured — was still booting/reconnecting very
   slowly as of this session's end, consistent with hd8's documented
   history of slow/unreliable post-reboot reachability (see the Fire OS 8
   ADB wireless-debugging investigation from an earlier session — hd8 also
   resets `adb_wifi_enabled` on every reboot per that research, making it
   the device most likely to actually produce `CLOSED_NO_SHELL` for real,
   but also the one most likely to need the longest wait or a manual check).
4. Clean up the AutoJs6-specific self-heal/health-probe staleness (see
   item 2 above) — separate, smaller fix.
