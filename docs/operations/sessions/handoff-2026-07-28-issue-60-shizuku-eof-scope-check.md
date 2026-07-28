# Handoff: #60 hd8 Shizuku EOFException — scope check + residual fix

2026-07-28, Agent 5 of the ops-suite orchestration chain
(`~/ai-orchestration-plan-2026-07-28.md`).

## Task

#60's own last comment deprioritized it in favor of #86, noting it "remains
relevant only for the agent's own Shizuku-gated privileged actions, not for
detecting/restarting the agent." Since then #86 (heartbeat/Shizuku-independent
liveness, PR #113) and #61 (external-ADB peer-start, merged to master via
`7ad421a`/`10a346a`, live-verified in PR #115) both landed. This session's job:
determine whether any genuinely open work remains under #60 for the
"privileged actions" angle.

## What was checked

Read every privileged-action code path the native-agent APK runs once Shizuku
is up:

- `HostService.ensureBound()` / `pingAwake()` / `runComonitor()` — all go
  through `Shizuku.bindUserService()` (Android Binder IPC), never ADB. Once
  the peer-start loop (`HostService.startPeerStartLoop()`, screen-independent,
  every 20 min) has the Fire-OS target's Shizuku daemon running, these never
  touch loopback ADB at all. **Confirmed unaffected by #60.**
- `ShizukuUserService.repairCatastrophic()` → `CatastrophicRepair.repair()` —
  this one **does** touch loopback ADB: `tryShellWirelessRepair()` runs
  `adb connect 127.0.0.1:5555` from *inside* the already-running Shizuku
  UserService process, to open/verify Android's own ADB-over-network debug
  port (5555) for Termux's `localhost:5555`-based scripts. This is the same
  operation class the #60 root-cause investigation identified — an on-device
  process connecting to `adbd` over loopback — so it would hit the identical
  drop on Fire OS.
- `CatastrophicRepair.repairTailscale()` / `ensureAdbBaseline()` — no ADB
  loopback involved (settings puts + `am broadcast`/`am start`). Unaffected.

## Is the loopback step in `repairCatastrophic()` actually live?

Checked hd8 directly (`adb -s 100.124.55.39:5555 shell`, live Tailscale
connection from this Mac):

- `device.json` on hd8 already has `"privilegedShellExpected": false` —
  Termux's own `stayturgid_repair.py`/`stayturgid_shell.py` are **already**
  correctly gated off from ever attempting `localhost:5555` on Fire OS
  (`privileged_shell_expected()` checks this exact flag; predates this
  session, not something #86/#61 needed to touch).
- hd8's live `agent.log` shows `port=open shell=yes` continuously for the
  last several days — meaning `ComonitorProbes.probe().port == "open"`
  (listening on a non-loopback address) has been true throughout, so
  `CatastrophicRepair.repair()`'s early-return (`if port == "open": return
  already-open`) means the loopback-touching step is **not currently
  executing** on hd8. It would only fire in the narrow window right after a
  reboot, before any external/peer ADB connection reopens the port — and
  `tryShellWirelessRepair()`'s own doc comment already acknowledges Fire OS
  can't self-heal this without an external connection.

So this was a **real but narrow, already-mostly-dormant gap**: an
unconditional loopback-ADB attempt inside a Shizuku-gated privileged action,
with no Fire-OS awareness, unlike the equivalent (and already-correct) Python
side. Not touched by #86 or #61 (neither PR modifies `CatastrophicRepair.kt`).

## Fix applied

- Added `DeviceProfile.kt`: reads the same `privilegedShellExpected` field
  from `/sdcard/stayturgid/state/device.json` that Termux already reads,
  via a small regex extraction (not `org.json.JSONObject` — that class is an
  unimplemented Android stub under plain-JVM unit tests, so a testable pure
  function can't use it directly; same reasoning `PeerStartCommands`
  documents for its own dependency-free pure functions).
- Gated `CatastrophicRepair.tryShellWirelessRepair()`'s loopback `adb connect
  127.0.0.1:5555` step behind `DeviceProfile.isPrivilegedShellExpected()` —
  skips cleanly (logged, not a silent no-op) on Fire OS instead of eating the
  doomed connect/timeout every ~20 min post-reboot cycle. `repair()`'s step
  log now distinguishes `shell_wireless_skip` from a real `shell_wireless`
  attempt, so `agent.log` doesn't read as a mystery repeated failure.
  `headlessStart()` (Shizuku's own restart nudge, no ADB involved) still
  runs regardless — unaffected.
- Added `DeviceProfileTest.kt` (4 cases: explicit true/false, missing field,
  empty object).

## Verification

- `just kt-format-check`, `just kt-detekt`, `just kt-test` all clean for the
  changed/added files. `kt-detekt` still reports its **3 pre-existing,
  unrelated** failures in untouched files (`ShizukuUserService.kt`
  `NestedBlockDepth` + `SpreadOperator`, `AuthorizeReminder.kt`
  `MaximumLineLength`) — same ones Agent 3's #113 PR already noted; not
  touched here. `just kt-format-check` on `master` as-is *also* fails on
  `ShizukuUserService.kt` (pre-existing drift from `81baa49`, #64/#65/#66) —
  left as-is, out of this PR's scope.
- Did **not** reboot hd8 to force-exercise the skip path live — hd8 has a
  documented recovery-bootloop hazard on `adb reboot`
  (`memory/project_fireos8_adb_wireless_debugging.md` /
  handoff-2026-07-25 session notes). The next time hd8 reboots naturally
  (or an operator does it deliberately with recovery-menu awareness), confirm
  `agent.log` shows `shell_wireless_skip` instead of a `shell_wireless`
  failure in the post-boot cycle.

## Outcome / recommendation for #60

Not a clean "nothing left" — there was a real, narrow gap, now fixed and
merged into this PR. With this fix, every Shizuku-gated privileged action
either (a) runs over Binder IPC once the peer-start-started daemon is up
(never touches ADB), or (b) is the one loopback-touching best-effort repair
step, which now correctly no-ops on Fire OS instead of attempting a doomed
connect. Recommend **closing #60** once this PR merges, with a comment
summarizing this evidence — posted separately to the issue.
