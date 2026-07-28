# Handoff 2026-07-28 — #86 loopback/Shizuku-independent agent liveness + restart

## Executive summary

Implemented the revised #86 plan end-to-end: a durable, Shizuku-independent
heartbeat that `HostService.kt` writes every 120s from its own dedicated
thread; `check_stayturgid_agent` in `stayturgid.cf` now detects liveness from
that heartbeat only (no adb loopback, no dumpsys); `fleet_health.py` reads the
same file so the on-device and Mac-side checks cannot disagree; and a
consecutive-failure counter that flags (never auto-executes) a reboot
candidate after repeated restart failures.

**Verified live on hd8 first, then p7a with the loopback deliberately
disconnected** — both per the plan. On p7a specifically, confirmed
side-by-side that the _old_ loopback-dependent check would still
false-negative in that state while the _new_ heartbeat-based check correctly
reports alive — i.e. reproduced the original bug and confirmed the fix.

Also found and fixed a real, previously-unknown CFEngine parsing quirk along
the way (§4) — worth reading if you touch `.cf` policy next.

PR not yet opened as of writing this section — see §7 for status/link once
pushed.

---

## 1. Design decisions and why

**Heartbeat transport: MediaStore, not the plan's first-choice
ContentProvider.** The revised issue plan preferred a ContentProvider queried
via Termux `content query`. Live-checked via SSH on hd8: Termux's `$PREFIX/bin`
has `am`, `pm`, `settings` but **no `content` binary**. A ContentProvider
would be unreachable from the CFEngine side on the actual fleet, so I used the
plan's own documented fallback: a MediaStore Downloads file
(`/sdcard/Download/stayturgid-agent.heartbeat.txt` — the `.txt` is
MediaStore's own doing, it enforces MIME_TYPE↔extension agreement and
silently appends the extension; also verified live).

**Heartbeat thread: a dedicated `ScheduledExecutorService`, not a coroutine on
the existing `Dispatchers.Main.immediate` scope.** `HostService`'s existing
Shizuku-touching loops run on `Dispatchers.Main.immediate`; a hung Binder call
there blocks the single Main thread. A heartbeat coroutine sharing that
dispatcher could be starved by the exact hang it exists to detect. The new
`HeartbeatWriter` runs on its own daemon thread, entirely decoupled from
Shizuku/coroutine machinery. See `Heartbeat.kt` → `HeartbeatWriter.kt`'s class
doc.

**Freshness threshold = 420s (7 min).** 3× the 120s heartbeat interval (360s,
the generous end of the plan's "2-3x") + 60s jitter margin for Doze/scheduler
delay (Fire OS is the aggressive case the plan calls out). This number is
duplicated (by necessity — Kotlin/CFEngine/Python can't share a literal
constant) in three places, all cross-referencing each other in comments:
`HeartbeatWriter.HEARTBEAT_INTERVAL_MS`, `stayturgid.cf`'s `freshness_sec`,
`fleet_health.py`'s `AGENT_HEARTBEAT_FRESH_SEC`. Worst-case detection latency
for a genuinely dead agent: 420s + one local boot-loop cycle (≤300s,
`STAYTURGID_INTERVAL_SEC`) ≈ 12 minutes; a Mac-hailed cf-runagent run can catch
it sooner since it runs the bundle on demand.

**Reboot escalation is alert-only — this bundle never executes a reboot.**
After `reboot_after=3` consecutive not-alive checks (~15 min at the 5-minute
boot-loop cadence) despite both restart attempts, `check_stayturgid_agent`
writes a state file (`$(s)/state/agent_reboot_candidate`) and nothing more.
`fleet_health.py` surfaces it as an `agent_reboot_candidate` issue tag, which
flows into the _existing_ `notify()` desktop-alert path in
`fleet_health_monitor.py` — a human decides. I found two independent, explicit
reasons in this repo's own history not to auto-reboot:
`docs/operations/sessions/handoff-2026-07-26-peer-start-activation.md` — "Do
not `adb reboot` hd8 — recovery-bootloop risk" — and
`docs/notes/lessons-learned.md:120` — reboot generally needs a human to
re-enter the device PIN afterward. An unattended auto-reboot could leave a
device down _harder_ than the failure it was meant to fix. I looked for an
existing auto-reboot mechanism this could hook into (the revised plan says
"confirm prolonged 'not running' is already a reboot candidate") and found
none — `site_logging.py`'s "escalate to reboot" is a docstring example of an
ERR-severity _log line_, not an executed action. So "reboot policy" here means
alert, not act, by design.

**Restart order: Termux `am start` first, adb-loopback `am start` second.**
Matches the revised plan exactly. Verified live on hd8 that Termux's own `am
start` is genuinely flaky — one attempt (via CFEngine, moments after
backgrounding) silently did nothing (no error, no launch); an immediately
following manual attempt (same command) succeeded. This is the documented
Android background-activity-launch restriction, not a bug in the invocation —
don't be surprised by it in future testing.

**`fleet_health.py`: `agent_heartbeat_age` is now authoritative for
`agent_missing`/`agent_stale`; the older `agent_age` (Shizuku-bound co-monitor
STATUS line) is kept as telemetry only, not removed.** Removing it would also
silently regress `shizuku`/`port`/`a11y`/`tailscale` fields, which are parsed
from the same STATUS line and are out of this issue's scope.

## 2. Files changed

- `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/HeartbeatWriter.kt`
  (new) — the heartbeat writer; `HostService.kt` starts/stops it in
  `onCreate()`/`onDestroy()`, before/alongside the existing loops.
- `device/native-agent/app/src/test/kotlin/org/stayturgid/agent/HeartbeatWriterTest.kt`
  (new) — pure formatting tests; the MediaStore write path itself needs a real
  device (no Robolectric in this project) and was exercised live instead.
- `device/termux/cfengine/policy/stayturgid.cf` — `check_stayturgid_agent`
  rewritten (now takes `(p, s)`; the `s` param and the call site in
  `stayturgid_heal` changed accordingly).
- `control/lib/fleet_health.py` — `AGENT_HEARTBEAT_FRESH_SEC`; new
  `_agent_heartbeat_age()`/`agent_reboot_candidate` probes in both
  `HEALTH_GATHER` (SSH path) and `adb_health()` (adb fallback path);
  `evaluate_health()`/`summarize()` updated.
- `tests/python/test_fleet_health.py` — updated the tests that asserted
  `agent_age` drove `agent_missing`/`agent_stale` (it no longer does; see §1)
  to use `agent_heartbeat_age`, plus two new tests
  (`test_evaluate_agent_reboot_candidate`,
  `test_evaluate_agent_age_alone_no_longer_drives_staleness`).

## 3. Verification performed (real devices, not simulated)

1. **hd8, full cycle:** built+installed the debug variant (see §5 for why),
   granted Shizuku, confirmed the heartbeat file appears and ticks
   (`seq` increments every 120s). Ran the _real_ `stayturgid.cf` via
   `cf-agent -Kf` over SSH (not a synthetic copy) and confirmed: fresh
   heartbeat → `stayturgid_agent: running`; heartbeat forced stale → `NOT
RUNNING`, both restart attempts fire, failure counter increments 1→2→3,
   `agent_reboot_candidate` marker appears exactly at 3; heartbeat fresh again
   → counter and marker both clear. Force-stopped the real process and
   confirmed the bundle's restart path can revive it (flaky, as documented
   above).
2. **p7a, loopback down:** installed the same build, then `adb disconnect
localhost:5555` from _inside_ Termux (Termux's own adb client state — does
   not touch the Mac's adb connection to the device, which stayed up for
   testing). With the loopback down, manually ran the **old** check command
   (`adb -s localhost:5555 shell dumpsys ...`) and confirmed it would
   false-negative — then ran the **new** bundle and confirmed it correctly
   reports alive. Reconnected the loopback afterward.
3. **`fleet_health.py` end-to-end:** ran the real, unmodified-by-hand
   `ssh_health()` / `evaluate_health()` / `summarize()` against both live
   devices. Both show fresh `agent_heartbeat_age` and no
   `agent_missing`/`agent_stale`/`agent_reboot_candidate`; p7a's pre-existing,
   unrelated `bootloop_down`/`repair_stale` issues (Python watchdog, not the
   native agent) are unaffected — confirms no regression to other checks.
4. **Preflights:** `just check` (includes `cf-promises` policy validation),
   `just pytest` (594 passed, 1 skipped, unrelated), `just kt-test`, `just
kt-format-check` all clean for the files this PR touches. `just kt-detekt`
   has 3 pre-existing failures in `ShizukuUserService.kt` /
   `AuthorizeReminder.kt` — unrelated to this change (verified: those files
   are untouched by this diff) and not something I fixed — flagging for
   whoever next touches those files, or for a dedicated cleanup.

## 4. CFEngine finding: `$(...)`/`${...}`/`$((...))` inside `returnszero()` shell strings

Root-caused a real bug during this session, not just in my new code: CFEngine
3.27.1's own `$(...)`/`${...}` variable-interpolation scanner also fires
_inside_ a `returnszero(command, "useshell")` string on **shell** command
substitution `$(...)`, parameter expansion `${...}`, and arithmetic expansion
`$((...))` — even when the content clearly isn't a valid CFEngine variable
name. `cf-promises` accepts the policy (syntax-valid), but `cf-agent` silently
never runs the affected shell command: no output file, no error, the class
just never gets set. This is **not** about escaping `%` (I initially thought
so, matching the pre-existing `stat -c %%Y` in `check_bootloop_repair` a few
bundles down — doubling `%` did **not** fix it in an isolated test).

Workaround, verified end-to-end on-device: use backticks for command
substitution and `expr` for arithmetic instead — e.g. `` ts=`grep ...` ``
instead of `ts=$(grep ...)`, `` age=`expr $now - $ts` `` instead of
`$((now - ts))`. Plain `$(cfengine_var)` for genuine CFEngine variable
references is unaffected (confirmed working throughout).

I did **not** fix `check_bootloop_repair`'s pre-existing `repair_recent` class
(`$(stat -c %%Y ...)`, `$(($(date +%s) - 3600))`) — it almost certainly has
the same bug (it uses exactly these constructs), but it's untouched by this
PR's scope and I didn't want to touch a bundle I hadn't otherwise changed.
Flagging clearly here since whoever owns #63 (CFEngine update, later in the
roster) or anyone else touching `.cf` policy should know about this before
assuming a `$(...)`-based freshness check "should just work" because
`cf-promises` accepted it.

## 5. hd8/p7a device-state note (read before assuming "clean baseline")

Both hd8 and p7a were running the **release** build (`org.stayturgid.agent`,
no `.debug` suffix, `versionName=0.6.0-boot-stability`) before this session.
The release signing keystore (`device/native-agent/agent-release.jks`,
gitignored by design) isn't present in this isolated task worktree, so I
could not build/install a matching signed release APK. I installed the
**debug** variant (`org.stayturgid.agent.debug`) instead — `just agent-install`
enforces one agent per device and removed the release build as part of that
(this is a previously-used, supported fleet configuration per
`docs/operations/sessions/handoff-2026-07-26-*.md`, not a novel state). Both
devices are currently on debug with this PR's changes, Shizuku
re-granted, agent running, heartbeat healthy, all test state files
(`~/.stayturgid/state/*`, stray `bisect*.cf` etc.) cleaned up.

**If the operator wants release back on either device**, that needs the real
signing key (not in this worktree) and a normal `assembleRelease` + install —
this PR does not do that.

## 6. Freshness/threshold numbers, for quick reference

| Constant                        | Value                                    | Where                                                                                                |
| ------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Heartbeat write interval        | 120s                                     | `HeartbeatWriter.HEARTBEAT_INTERVAL_MS`                                                              |
| Freshness threshold             | 420s (3× + 60s jitter)                   | `stayturgid.cf` `freshness_sec`, `fleet_health.py` `AGENT_HEARTBEAT_FRESH_SEC` — **must stay equal** |
| Reboot-candidate threshold      | 3 consecutive not-alive checks (~15 min) | `stayturgid.cf` `reboot_after`                                                                       |
| Worst-case dead-agent detection | ≈12 min (420s + ≤300s boot-loop cycle)   | derived                                                                                              |

## 7. Status / next steps

- All code committed on `feature/agent-liveness-86` in
  `~/src/ops-worktrees/agent-liveness-86/stayturgid`.
- Not expected to cut a release for this unit (per brief) — PR should land
  reviewed-ready; merge/release is a separate step.
- Six PRs from Agent 1's overnight work (stayturgid #107-#111, site-djbclark
  #32/#33) and two from Agent 2 (stayturgid #112, site-djbclark #34) were open
  and unmerged when this session started; none touch native-agent/CFEngine/
  fleet_health, so no conflict, but this PR's baseline (branched from master
  before any of those merged) doesn't include them either.
- Possible follow-ons (not done here, out of scope): fix
  `check_bootloop_repair`'s likely-broken `repair_recent` freshness check
  (§4); decide whether to restore release builds on hd8/p7a once the signing
  key is available.
