# Design: Scoping issue #18 (periodic job timing/spacing, Efficiency/Debug modes)

Investigation-only unit. No feature code changed. Goal: determine whether #18's
own stated dependency is met, inventory the periodic jobs it would apply to,
and break the issue into sub-items a future unit can actually pick up.

## 1. Is the "logging system overhaul" dependency met?

**Verdict: partially met — met for the Termux/Python side, not met for the
native-agent (Kotlin) side, which is where most of the jobs #18 cares about
actually live.**

Issue #18 §6 says: *"This feature depends on the completion of the new
logging system... Implement this feature after the logging system overhaul is
complete."* Two overhauls are plausible candidates; both were checked.

### 1a. The OTel/Vector/OpenObserve pipeline (docs/archive/plans/logging)

`docs/archive/plans/logging/01-implementation-plan.md` and
`02-implementation-plan.md` describe exactly this: migrating on-device logging
to structured JSONL, dual-writing for compat, and shipping it through an
on-device `otelcol-contrib` → Vector → OpenObserve pipeline on the Mac. Commit
history confirms it shipped (`e47cfde`, `3659b0d`, `ffdad675`, `062cfac`, and
more, 2026-07-26 era) and the plan docs were subsequently archived as
superseded/complete (commit `1dbfcc1`, "archive superseded plans/sessions").

This session's own work is directly relevant: **issue #44** (OpenObserve↔Vector
auth returning 401 fleet-wide) was the thing actually blocking this pipeline
from working end-to-end, and Agent 6 closed it this session — reset
credentials, verified `reingest_soft_health.py` posting real records and a
direct SQL query returning a matching count. So as of this session, the
transport/ingest layer is not just built, it is **live and confirmed
queryable**.

Current wiring, confirmed by reading `ansible_collections/stayturgid/termux/
roles/termux_userland/templates/otel-config.yaml.j2` (origin/master tip):
`otelcol-contrib` runs as its own Termux:Boot-launched daemon
(`stayturgid_otelcol_boot_script`) and tails exactly two files —
`repair.jsonl` (written by `stayturgid_repair.py`, Termux Python) and
`watchdog.jsonl` (originally written by AutoJs6's `comonitor.js`).

**This is where the gap is.** AutoJs6 was fully uninstalled fleet-wide during
the K1 native-agent cutover (2026-07-25, issue #43 — confirmed via
`termux_userland/defaults/main.yml`'s own `stayturgid_retired_boot_scripts`
comment on origin/master). Nothing writes to `watchdog.jsonl` anymore. The
native-agent Kotlin app that replaced AutoJs6 — and that owns essentially
every periodic job #18 is about — has **zero structured logging**:

- `grep -rl "android.util.Log\|Timber\|Logger\b" device/native-agent/app` →
  12 of 18 Kotlin files use plain `android.util.Log` calls (logcat only).
- `grep -rl "jsonl\|JSONL\|structured.*log" device/native-agent/app` → no hits.
- No file matching `watchdog.jsonl`/`state.json` is referenced anywhere in
  `device/native-agent/app`.
- No `otlphttp`/OTel exporter, no log-level switch, no retention/export path.

So: the *infrastructure* half of the overhaul (transport, ingest, storage,
query) is done and verified working. The *on-device emitter* half is done for
Termux/Python, retired-along-with-AutoJs6 for the JS side, and **was never
built for native-agent** — which didn't exist yet when the logging plan was
written. Issue #18's own acceptance criteria (§6: "dynamic log level
switching," "structured logging format," "performant... high-frequency Debug
mode logging," "log persistence and export") describe exactly the missing
native-agent piece. Read literally against the code that would actually carry
#18's periodic jobs, **the dependency is not met**.

## 2. Periodic job inventory (Android side, as #18 asks for)

Note on architecture: **none of these use WorkManager, AlarmManager, or a
`Handler`** — issue #18's own text assumed one of those, but the actual
implementation (post K1/native-agent cutover) is Kotlin coroutine `delay()`
loops running inside one long-lived foreground service, `HostService`. This
matters for scoping §3/§4 below: there's one scheduling substrate to change,
not three independent Android scheduler APIs.

### native-agent (Kotlin, `HostService.kt`) — current, in production

| Job | Interval | Notes |
|---|---|---|
| Ping loop (`startPingLoop`) | 5 min (`PING_INTERVAL_MS`) | Screen-on only; keeps the Shizuku binder awake (`callPingAwake`). Stops on screen-off. |
| Co-monitor / heartbeat loop (`startHeartbeatLoop`) | 20 min (`COMONTOR_INTERVAL_MS`) | Screen-independent. Already has a one-time **per-device phase stagger** (`AgentSchedule.staggerMs`, keyed off `ANDROID_ID` hash) so fleet devices don't all wake at once — this is effectively a primitive, undocumented-as-such "Efficiency mode" behavior already shipped. |
| Peer-start loop (`startPeerStartLoop`) | 20 min steady-state, 3 min (`PEERSTART_PENDING_INTERVAL_MS`) while an authorization is pending | Also staggered (same `AgentSchedule` mechanism), staggering skipped while "urgent" (pending auth). |

`AgentSchedule.kt` (the stagger utility) is already a real, tested precedent
for "site-wide behavior with a per-device deterministic offset" — exactly the
shape §2 of #18 wants, just not surfaced as a user-facing mode toggle.

Config-storage precedent: `PeerConfig.kt` already implements the exact
per-device-override pattern #18 asks for in §7 — `filesDir/peer.json` (or
`getExternalFilesDir/peer.json`), first-file-found-wins, absent ⇒ default
no-op behavior, provisioned via ansible/adb. A schedule-mode config file would
follow this same shape.

Notification precedent: `HostService` already manages persistent
`NotificationCompat` notifications (peer-nag, target-reminder) via
`updateActionNotifications()`. There is **no existing ephemeral Toast
framework** — `MainActivity.kt` imports `android.widget.Toast` only for a
one-off clipboard-copy confirmation. The toast-per-job-lifecycle ask in #18 §4
is genuinely net-new.

### Termux (Python) — current, in production

| Job | Interval | Notes |
|---|---|---|
| `stayturgid_repair.py` (via `start_adb.py`'s daemon loop) | 300s default, `STAYTURGID_INTERVAL_SEC` env override | Already has a basic per-device override mechanism (env var) — no site-wide/per-device precedence system, just whatever `.stayturgid/env` sets on that device. |
| `stayturgid_bridges.py` (`--mode repair`) | 2s poll (`POLL_SEC`) | Local IPC/socket bridge, not a background "job" in the WorkManager sense — continuous fast poll, out of scope for clock-minute scheduling. |
| `otelcol-contrib` | continuous tail, `batch` processor flushes every 30s | Infra process, not a "job." |

`stayturgid_bridges.py --mode autojs6` and both `start-autojs6-*.sh` boot
scripts are retired (removed from `stayturgid_boot_scripts`, deleted from
devices on next deploy per `stayturgid_retired_boot_scripts`) — dead, left in
repo per issue #43's own no-delete-yet decision. Not part of this inventory's
"active" set.

Scope note: #18's title says "for Android," and the Mac-side CFEngine
`cf-agent` schedule / launchd timers are a different tier (control node, not
a fleet device) — out of scope for this feature, not inventoried here.

## 3. Sub-item breakdown, with effort and dependency

Ordered by dependency, not by priority — §3.1 gates several others.

1. **Native-agent structured logging + OTel integration** (Medium-Large).
   Closes the literal dependency gap found in §1. Give native-agent a JSONL
   emitter (mirroring `site_logging.py`'s schema so `otelcol-contrib` can tail
   it the same way `repair.jsonl` is tailed today — likely a new
   `filelog/agent` receiver in `otel-config.yaml.j2` pointed at a
   native-agent-writable path), plus log levels. **No other sub-item below
   should ship its "enhanced logging" pieces before this lands** — there's
   nowhere for that data to go yet.
2. **Efficiency-mode formalization** (Small). Mostly already implemented:
   `AgentSchedule`'s per-device stagger + screen-on-gated ping loop already
   *are* efficiency behavior. This is closer to naming/documenting the
   existing behavior as "Efficiency mode (default)" than new engineering —
   good first PR, low risk, no dependency on #1.
3. **Mode config storage + site-wide/per-device precedence** (Small-Medium).
   New config file (e.g. `schedule.json`) following `PeerConfig.kt`'s exact
   pattern; site-wide default shipped via ansible template, per-device
   override via the same `filesDir`/`getExternalFilesDir` search order.
   Independent of #1; a prerequisite for #4 and #6.
4. **Debug-mode clock-minute scheduling** (Medium). The real architectural
   change: replace the three independent `delay()` loops in `HostService`
   with a shared clock-aligned scheduler so a job can be pinned to `:03`,
   `:23`, etc., plus collision detection across jobs. Depends on #3 for where
   the per-job minute assignment lives.
5. **Toast notification framework (Debug mode only)** (Medium). Net-new —
   no existing ephemeral-notification code to build on. Needs its own
   queue/stacking logic since Android can only show one `Toast` at a time.
   Depends on #4 for job start/end lifecycle hooks to notify from.
6. **Schedule-viewer UI** (Small-Medium). A list/timeline screen in (or
   alongside) `MainActivity` showing each job's assigned marker / next run.
   Depends on #3 + #4 existing first.
7. **Enhanced Debug-mode logging content + export** (Medium, depends on #1).
   Structured lifecycle/error logging is a direct extension of #1's schema.
   Export (7-day retention, compressed bundle, in-app share) is new but
   modest — Android's `Intent.ACTION_SEND` covers the share step;
   `site_logging.py`'s existing 30-day text-log rotation is a ready template
   for JSONL retention.
8. **Per-job resource/network telemetry** (issue §5: CPU/memory/I/O,
   network requests/latency, thread/process info) — **recommend descoping**.
   Android doesn't expose per-thread CPU/memory cheaply without extra
   instrumentation libraries, and a 3-device fleet gets little practical
   value from it relative to the effort. Flag as an explicit "no" rather than
   silently dropping it — revisit only if a concrete debugging need for it
   shows up.

## 4. Recommendation for a first implementation unit

**Ship #3.1 (native-agent structured logging) as its own issue/unit first.**
It's the literal blocking dependency #18 names, it's independently useful
(native-agent currently has *no* durable log trail beyond ephemeral logcat —
a real gap for debugging #86/#60/#65-style issues this session kept finding),
and it unblocks §3.7 (enhanced logging/export) for later.

**#3.2 (Efficiency-mode formalization) can ship any time, independently** —
it's nearly free and has no dependency on #1. Good filler/quick-win unit.

**Everything else (§3.3–§3.7) should wait** until #1 lands, and even then
should be scoped as separate small units rather than attempted together —
the issue as currently written is "medium effort" on paper but is actually
7 independently-shippable pieces plus one that should be cut.

**Do not close #18.** Leave it open with a summary comment pointing at this
doc and recommending sub-issues be spun for #3.1–#3.7 as they're picked up
(same pattern Agent 7 used for #62 this session) — matches the issue's own
framing as a large feature request, not a single fixable bug.
