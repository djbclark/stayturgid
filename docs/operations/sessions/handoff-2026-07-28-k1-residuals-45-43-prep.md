# Handoff 2026-07-28 — K1 residuals (#45/#43): prep + physical step both complete

## Executive summary

Agent 9 of the human-relayed orchestration chain (`~/ai-orchestration-plan-2026-07-28.md`).
Unit covers issue [#45](https://github.com/djbclark/stayturgid/issues/45) (K1
residuals: release APK, forced soak, official Shizuku packaging) and
[#43](https://github.com/djbclark/stayturgid/issues/43) (K1 verify post-cutover
fleet state).

**Bottom line:** all four non-physical prep items are done — one fully fixed
and tested (AutoJs6 self-heal noise, expanded into a full repo-wide sweep per
operator request mid-session), three investigated to a concrete, evidence-backed
conclusion (Shizuku watchdog scheduling, release-APK path, Shizuku packaging).
The gated physical step ran in a follow-up continuation of this session once
the operator confirmed availability: s24's binder-race/loopback fixes held on
a third verification, and hd8's `CLOSED_NO_SHELL` trigger reproduced the
condition but surfaced a **more fundamental gap** than the soak was scoped to
find — see §5b. Both devices were left healthy. Worktree:
`~/src/ops-worktrees/k1-residuals-45-43/stayturgid`, branch
`feature/k1-residuals-45-verify-43`. `just check` and `just test` both clean
(592 pytest + 136 shell unit tests + 6 ansible-test collection suites, all
green — see §6 for the itemized breakdown).

---

## 1. AutoJs6 self-heal noise — fixed, tested, and swept fleet-wide

### Original ask (2 files)

`stayturgid_repair.py`'s a11y-check + fleet-profile-reapply, and
`fleet_health.py`'s `autojs6_a11y` probe, were both hardcoded to assume
AutoJs6 might still be present. Since AutoJs6 is fully uninstalled fleet-wide
(confirmed live on s24 + hd8 again this session via `pm path`), both fired
perpetual, misleading signals:

- `stayturgid_repair.py` logged `NOTICE: ACTION_REQUIRED: AutoJs6
accessibility disabled` every ~15 min cycle — **caught live on s24's own
  `repair.log` during this session** (`21:06:32`), confirming the bug was
  actively firing, not theoretical.
- `fleet_health.py` reported `autojs6_a11y=missing` forever in dashboard/health
  summaries (confirmed telemetry-only via the existing
  `test_evaluate_retired_autojs_a11y_is_telemetry_only` test — never actually
  raised an alert, but was permanent noise).

**Fix:** both now check live AutoJs6 install state (`pm path
org.autojs.autojs6`) before running the legacy check at all. If not installed,
they report the new `retired` state and skip the check entirely — no more
false ACTION_REQUIRED, no more perpetual "missing".

### Operator-directed full sweep

Mid-unit, the operator asked for a full repo-wide `grep -ri autojs6` sweep
(`control/`, `device/`, `ansible/`, `docs/`) and a categorized accounting of
every hit — not just the two files that triggered the conversation. ~180
files matched; most are legitimately historical (the retired
`device/autojs6/` project itself, `docs/archive/`, `docs/research/`,
`docs/operations/sessions/` logs, CHANGELOGs) and were left untouched.
Categorized findings below.

#### Fixed this unit (same pattern: check live state, don't assume)

1. **`device/termux/py/stayturgid_repair.py`** — as above, plus fixed two
   stale escalation-path log/docstring lines that still said "AutoJs6 UI
   repair" (now: "native-agent catastrophic repair").
2. **`control/lib/fleet_health.py`** — as above, in both the SSH-path
   (`HEALTH_GATHER`) and the USB-fallback (`adb_health`) probe scripts.
3. **`ansible_collections/stayturgid/fleet/roles/validate/tasks/main.yml`** —
   found during the sweep, same bug pattern, live in the deploy/validate path:
   a "Warn when AutoJs6 accessibility is not enabled" `debug` task fired on
   **every single `just deploy`/validate run, for every device**, since
   AutoJs6 is uninstalled everywhere. Gated the probe and the warning on a new
   `_autojs6_installed` fact (via the `stayturgid.android_common.android_packages`
   lookup, same idiom used elsewhere in this collection).
4. **`ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml`**
   — `start-autojs6-bridge.sh` and `start-autojs6-watchdog.sh` were still in
   the live `stayturgid_boot_scripts` deploy list. Both scripts' entire job is
   launching/restarting AutoJs6's `boot-launcher.js` — with AutoJs6 gone,
   every device boot ran a dead `am start` against an uninstalled package plus
   a wasted 45s sleep in the boot sequence, fleet-wide, forever. Moved both to
   `stayturgid_retired_boot_scripts` (an already-established convention in
   this file — next deploy removes them from `~/.termux/boot/` on every
   device). Underlying script files and `stayturgid_bridges.py --mode
autojs6` left in place, now unreachable in production — flagged below for
   a follow-up decision, not deleted here.
5. **`stayturgid_automation_mode: autojs6`** stale default, found in three
   places: `SITE-CONTRACT.md` (source of truth — this repo uses Entangled
   literate programming; `control/site_contract/templates/inventory/hosts.yml`
   is _tangled from_ SITE-CONTRACT.md, not hand-editable — learned this the
   hard way when a direct edit broke `just site-contract-check`'s parity
   check; fixed correctly by editing the source doc and re-tangling with the
   pinned `.venv-test/bin/entangled` 2.4.0, not the system's 2.4.3, which has
   an incompatible DB version), and `ansible/inventory/hosts.yml.example`.
   Traced every consumer of this field: it's written to an on-device state
   file (`automation_mode.txt`) on every deploy and shown in
   `validate_site_identity.py`'s site-identity report as if meaningful, but
   the **only actual reader** anywhere in the repo is
   `device/autojs6/scripts/switch-to-autojs6.{ts,js}` — itself part of the
   retired AutoJs6 project. Changed the default to `""` (falls through to
   `site_identity.py`'s existing `"none"` fallback) with an explanatory
   comment. **Note:** the _live_ production inventory value for hd8/p7a/s24
   lives in `site-djbclark`'s own inventory (different repo, out of this
   unit's scope/worktree) — this fix only corrects the template/example
   defaults used when scaffolding _new_ sites or devices.
6. **`tests/lib.sh` + `tests/test-unit.sh`** — my repair.py fix broke 3
   existing shell-suite tests that assumed AutoJs6 was always "installed"
   (`repair[py]: healthy STATUS line` expected `a11y=up`; two tests expected
   ACTION_REQUIRED to fire unconditionally). Added an `ADB_AUTOJS6_INSTALLED`
   stub knob (default: not installed, matching real fleet state) and updated
   those 3 tests to explicitly mock AutoJs6-installed for the legacy-path
   assertions, plus added 3 new tests for the retired-state path
   (`a11y=retired`, no ACTION_REQUIRED, `auto_profile=retired`). Net: 133 → 136
   shell tests, all green.

#### Confirmed real bugs, deliberately deferred (need a Kotlin build/verify cycle)

7. **`device/native-agent/app/src/main/kotlin/org/stayturgid/agent/ComonitorProbes.kt:23-24,104`**
   — the native agent's _own_ accessibility probe (`A11Y_AUTOJS6` constant +
   list-contains check) is hardcoded to AutoJs6's accessibility-service
   string. This is exactly the same bug pattern as items 1-2, just in
   Kotlin — the native agent's own STATUS/`agent.log` `a11y=` field will read
   `down` fleet-wide, permanently. This is the exact gap the operator's own
   2026-07-26 comment on #43 flagged ("This does NOT mean the native agent has
   its own accessibility service..."). Still present in current `master`.
   Needs `kt-format-check`/`kt-detekt`/`kt-test` + a rebuild + device verify —
   deliberately not attempted in this unit (see §3 for why a Kotlin rebuild
   is already independently needed for the release-APK item; recommend
   bundling this fix into that work).
8. **`device/native-agent/app/src/main/res/values/strings.xml:15`** — the
   `main_hint` UI string says "AutoJs6 stays installed", which is now false.
   Trivial, but bundled with the Kotlin cycle above rather than a
   one-line-only PR.

#### Real functionality gap, not yet migrated (needs a decision, not a quick fix)

9. **`CatastrophicRepair.kt:17`** ("No Accessibility UI taps here — that
   remains AutoJs6-only until a fork intent path is proven") and
   **`HostService.kt:472`** ("AutoJs6 still owns UI fallback until cutover")
   — both point at a real, unresolved capability gap: AutoJs6 used to own an
   Accessibility-based UI-tap fallback for catastrophic-repair scenarios that
   has **not** been reimplemented in the native agent. This is category (a)
   from the operator's framing — real functionality not yet migrated, not
   stale wording. Worth an explicit operator decision: accept the gap
   permanently (native-agent's Shizuku-based repair path already covers the
   documented failure modes per Agents 3-8's work this session), or scope a
   dedicated feature-parity issue. Not scoped or implemented here.

#### Dormant/dead code, not touched (recommend a dedicated decommission issue if wanted)

10. **`device/termux/py/stayturgid_autojs6_guard.py`** — still invoked
    unconditionally every `daemon_loop()` cycle (5-15 min) via
    `start_adb.py`. Its `action_check()` now always short-circuits to a
    benign one-line "no watchdog cycle in log yet" log entry (its input
    signal can never appear again) — low-severity noise, not an alert, but a
    genuinely dead invocation.
11. **`device/termux/py/stayturgid_bridges.py --mode autojs6`** — unreachable
    in production after fix #4 above (its only launcher was just retired),
    but the mode's code (and `stayturgid_autojs6_guard.py`'s matching
    `maybe_restart_trigger()`) is still in the tree.
12. **Entire dedicated legacy AutoJs6 tooling stack**, left as-is
    (dormant — only runs if explicitly invoked, causes no active noise post-fix):
    `device/autojs6/` (already documented as historical-reference-only per
    `docs/architecture/components/autojs6.md`), `control/tools/autojs6/` (8
    scripts), `device/termux/py/stayturgid_enable_autojs6.py` +
    `stayturgid_grant_shizuku.py`, `control/lib/adb_cli.py` (AutoJs6
    script-launch helper library), `ansible_collections/stayturgid/android_common/plugins/modules/autojs6_project_deploy.py`
    and its `module_utils/autojs6_deploy_util.py`. (`android_a11y_services.py`
    and `a11y_services_util.py` are _not_ in this bucket — they're now also
    used generically by fix #3 above, kept.)
13. **`control/bin/dashboard.py`**'s `HUMAN_ACTIONS["autojs6_a11y_missing"]`
    / `["autojs6_a11y_stale"]` entries — already-dead before this session
    (the issue tags they key off are never actually generated by
    `evaluate_health()`, confirmed by the pre-existing
    `test_evaluate_retired_autojs_a11y_is_telemetry_only` test). Pre-existing,
    harmless, unrelated to anything changed here — noted for completeness
    only.
14. **Prose docs** (`docs/architecture/platform-architecture.md:755`,
    `docs/architecture/multi-site-topology.md:237`) still show the stale
    `stayturgid_automation_mode: autojs6` example in narrative text — not
    tangled/enforced, cosmetic only, not fixed.

---

## 2. Shizuku/Termux liveness watchdog — is it actually scheduled?

**Yes.** The brief's framing (from the 2026-07-26 #43 comment) was: "no evidence
[the restart mechanism is] wired into a recurring schedule (checked device
crontab, Mac launchd, found no match)." That check looked in the wrong two
places — the real mechanism is neither.

**What actually happens, traced end-to-end:**

1. `device/termux/boot/start-adb.sh` (a Termux:Boot script, deployed to
   `~/.termux/boot/`) launches `start_adb.py`'s `daemon_loop()` once per boot.
2. That loop (default `STAYTURGID_INTERVAL_SEC=300`, i.e. every 5 min — 900s
   per the Ansible role default) runs `stayturgid_repair.py` on every
   iteration, which is where `ensure_shizuku_watchdog()` (§3 of that script)
   lives.
3. `ensure_shizuku_watchdog()` is idempotent: if a detached, `setsid`-spawned,
   `ppid=1`, UID-2000 shell loop isn't already running, it spawns one. That
   loop independently `pgrep`s for `shizuku_server` every 60s and restarts it
   via `shizuku_starter` if dead — this is genuinely independent of Shizuku's
   own app-level `WatchdogService`.
4. If `start_adb.py`'s daemon loop itself dies, CFEngine's
   `check_bootloop_repair` bundle (`device/termux/cfengine/policy/stayturgid.cf`)
   detects it (`pgrep -f start_adb.py` failing) and restarts it.

**None of this is crontab or launchd** — it's a self-perpetuating on-device
Python daemon loop, kept alive by CFEngine, that's been present since commit
`fab6889` ("K1 (#43): fix Termux self-heal permission bug, add Shizuku
watchdog", 2026-07-25 08:57 EDT — same day as, and evidently _before_, the #43
comment describing this as unscheduled). That commit's own message
explains the earlier "~20-30s death" observation was root-caused as a
multi-layer shell-quoting bug in an earlier watchdog implementation attempt
(inline `sh -c` with nested escaped quotes silently truncating the loop to
one pass) — not a real OS kill — and fixed by pushing the loop as a script
file instead. It also explicitly dropped the old `HEADLESS_START`
broadcast-based restart entirely (confirmed dead: requires
`INTERACT_ACROSS_USERS_FULL`, a permission Termux can never hold) rather than
trying to fix it. **`docs/options.md`'s K1 section is stale** — it still
describes this as "Fix in progress (same day)" rather than shipped and
verified; not updated in this pass (documentation-only, lower priority than
the live findings below).

**Live-verified this session** (not just read the code):

- **s24**: `shizuku_server` running (pid 17853, up since 18:22), the watchdog
  script itself running (pid 26129, up since 18:29) — both confirmed via
  direct `ps -ef` over the Mac's USB adb (uid 2000 shell, no loopback needed).
  `repair.log` shows fresh STATUS lines every ~15 min with `shizuku=up`.
- **hd8**: **no** `shizuku_server` process and **no** watchdog process
  running via the Termux-side loopback path — but this is _expected_, not
  broken: hd8's `repair.log` shows `port=skip shizuku=skip shell=no` (Termux
  correctly declines to even attempt the loopback, per `device.json`'s
  `privilegedShellExpected: false` flag for Fire OS — the same gate Agent 5's
  #60 work confirmed is correctly wired). The native agent's _own_, separate
  Shizuku UserService connection (Kotlin, doesn't go through Termux's
  loopback at all) is independently healthy: `agent.log` STATUS lines show
  `shizuku=up` continuously through the last cycle at 20:24, and
  `moe.shizuku.privileged.api` is a live running process (pid 13197) on the
  device right now.
- **hd8 also has a real, live, unrelated problem worth flagging**:
  `repair.log` shows `Tailscale repair FAILED (runtime=down policy=down)` as
  of the last two cycles (20:46, 21:03) tonight. Not part of this unit's
  scope, not touched — flagging since it affects hd8's non-USB reachability
  during any coordinated physical-step work.

**Net:** the watchdog mechanism is real, deployed, and working as designed.
The "is it scheduled" question is answered — yes. hd8's lack of a running
Termux-side watchdog reflects an intentional Fire-OS gate, not a gap; its
native-agent-side Shizuku connection (the one that actually matters for
catastrophic repair) is healthy independent of it.

---

## 3. Release-APK path (#45) — infrastructure already exists and works; narrower remaining work than assumed

This item's brief asked me to assess honestly whether it's tractable in this
unit or deserves its own issue. Investigated thoroughly; the picture is
better than #45's own text implies, and the remaining work is real but
narrower and well-precedented — **not attempted here since it's live
device-mutating fleet work**, same category of risk as the gated physical
step.

**What already exists and already works (verified, not assumed):**

- Signing config is real: `device/native-agent/app/build.gradle.kts` has a
  working `release` signing config pointing at `../agent-release.jks`. The
  keystore itself isn't tracked in git (`.gitignore: *.jks`, by design) but
  **does exist** at `~/ops/stayturgid/device/native-agent/agent-release.jks`
  on this Mac.
- `just kt-build-release` (→ `./gradlew assembleRelease`) is a working,
  already-used recipe.
- **A signed release build already exists and is already published**: GitHub
  release [`agent-v0.6.0`](https://github.com/djbclark/stayturgid/releases/tag/agent-v0.6.0)
  (2026-07-26, tag commit `agent: bump to 0.6.0-boot-stability`), with asset
  `app-release.apk` — matching the Obtainium catalog's existing
  `apkFilterRegEx: "app-release\\.apk"` filter for `org.stayturgid.agent`
  exactly. The catalog entry (`catalogs/obtainium/stayturgid-apps.json`) is
  already correctly configured (repo URL, filter, prerelease/fallback
  settings) — this part of #45 is done, not just unverified-done like the
  AutoJs6 uninstall claim was.
- **s24 is already running this exact release build right now**: live
  `dumpsys package org.stayturgid.agent` shows `versionCode=15
versionName=0.6.0-boot-stability`, matching current `master`'s
  `build.gradle.kts` exactly, and it's the actively-running foreground
  process (confirmed via `ps -ef`), not just installed-and-dormant.
- The Ansible install path's idempotency concern is also already
  substantially addressed: `ansible_collections/stayturgid/android_common/roles/bootstrap_apks/`
  is a checksum-pinned, version-aware APK installer (`install_apk.yml`)
  with a built-in `_apk.remove_packages` mechanism specifically for cleanly
  uninstalling a conflicting package variant (e.g. `.debug`) before
  installing the locked one, plus a version-check that skips reinstall if
  already current. This is the same general mechanism already used for
  Termux/Shizuku/Obtainium bootstrap installs.

**What's actually still missing (real, but narrower than "build the whole
pipeline"):**

- **hd8 and p7a do not have the release variant installed at all** (`pm path
org.stayturgid.agent` returns nothing on either; both run
  `org.stayturgid.agent.debug` only) — live-confirmed this session via USB
  (hd8) and Tailscale (p7a, reachable at `100.65.230.108:5555` despite not
  being on USB).
- **`agent-v0.6.0` is now stale relative to current `master`**: several
  native-agent PRs have merged since that tag was cut (2026-07-26 10:57) —
  notably Agent 7's #65 UserService-leak fix (`81baa49`) and Agent 8's #66/#64
  work (`PR #125`), both already merged. **Installing the existing
  `agent-v0.6.0` asset as-is onto hd8/p7a would actually regress them** —
  their current `.debug` installs already include these later fixes (debug
  builds track `master` directly via `just agent-install`), while
  `agent-v0.6.0`'s release APK does not. A fresh `kt-build-release` +
  `gh release create` from current `master` is needed before any release
  rollout, not just re-publishing what's already tagged.
- No `stayturgid_bootstrap_apks` lock entry for the native agent itself was
  found anywhere in this repo — it's likely defined in `site-djbclark`'s own
  inventory (a different repo, outside this worktree/unit's scope to
  inspect further), where the actual `gh_tag`/`sha256` pin for a fresh
  release build would need to be added or updated.

**Recommendation:** this is tractable as a **follow-up unit**, not a
from-scratch build — likely a single focused session: rebuild against
current `master` (bundling the Kotlin a11y-probe fix from §1 item 7 and the
`strings.xml` fix from item 8 while a rebuild is already required), publish a
new tag, add/update the `site-djbclark` bootstrap-apk lock entry, then a
careful, coordinated (device-mutating, same care level as the physical step
below) rollout to hd8 and p7a with s24 re-verified to stay on release
throughout.

---

## 4. Official Shizuku packaging (#45) — confirmed done, exceeds the issue's own claim

Live-checked all three reachable devices this session (`dumpsys package
moe.shizuku.privileged.api`):

| Device | versionName                            | versionCode |
| ------ | -------------------------------------- | ----------- |
| s24    | `13.7.0-thedjchi+stayturgid-release23` | 51384       |
| hd8    | `13.7.0-thedjchi+stayturgid-release23` | 51384       |
| p7a    | `13.7.0-thedjchi+stayturgid-release23` | 51384       |

All three fleet-wide on the **same** official release build —
`release23`, which is _newer_ than the `release21` #45's own comment thread
references (that comment predates further Shizuku fork iteration this
session). No debug-repackaged workaround remains anywhere in the fleet. This
item is genuinely done; recommend closing this specific sub-item of #45 once
the release-APK and forced-soak items are also resolved (see #45's own
acceptance criteria — each sub-item gets recorded here, issue closes once
all are done).

---

## 5. The physical step — not attempted, stopping to check in

Per the brief's explicit gate: "stop and report what you've found so far
before triggering any reboot... don't assume standing-by-now still means
available whenever you get there; ask." A large amount of non-physical work
above (in particular the operator-directed full AutoJs6 sweep) extended this
unit well past the point where "operator standing by" at the start can be
assumed to still hold. Devices are confirmed on USB right now
(`RFCX219CHKA` = s24, `GN43T503430603PS` = hd8, both `device` state) and both
were left in their original, healthy states — nothing was rebooted, reset,
or otherwise mutated on either device this session; all changes are
control-node-only, in this git worktree.

**Update — operator confirmed available and the physical step was completed
in a follow-up continuation of this session; full results in §5b.**

---

## 5b. Physical step — completed

### s24: third verification of the binder-race and loopback fixes — holds

Full reboot (`adb reboot`), live logcat captured via `logcat -d` dump
immediately after reconnect (a `logcat -v` background stream started
pre-reboot dies when the USB transport drops on reboot — the OS's own
logcat ring buffer survives the reboot and a post-hoc `-d` dump against it
works fine; no need for a fragile live stream). USB re-enumeration took
~6.5 minutes this time (longer than prior sessions, no explanation found,
not investigated further — not a regression in anything this unit touched).

```
07:25:23.707 W Shizuku not running        <- retry #1
07:25:23.714 I HostService created screenOn=true
07:25:23.717 W Shizuku not running        <- retry #2
07:25:25.712 W Shizuku not running        <- retry #3
07:25:27.716 W Shizuku not running        <- retry #4
07:25:28.166 I Shizuku binder received    <- succeeds within ~4.5s
07:25:28.174 I bindUserService requested
07:25:28.632 I UserService connected
07:25:28.654 I pingAwake IPC ok
07:25:30.635 I comonitor: [agent] STATUS port=open shizuku=up sshd=down ...
```

Full comonitor cycle completed 7s after `HostService` creation — well
within the documented 2s-poll/20s-window retry design. Confirmed the
reported `port=open` was a **true** positive, not a repeat of the loopback
false-positive bug: connected to s24's Tailscale IP
(`100.123.218.30:5555`) directly from the Mac and got a genuine external
connection, not just a same-device loopback echo. Device left healthy:
Shizuku up, agent running, watchdog script alive.

### hd8: `CLOSED_NO_SHELL` initial trigger — a more fundamental finding

**The `CLOSED_NO_SHELL` condition triggered genuinely.** `adb reboot`;
`service.adb.tcp.port` stayed empty (wireless ADB never came back) for the
first ~68 minutes post-boot, confirmed via repeated direct `getprop`
polling, not inferred.

**But the native agent's own detection/repair pipeline never got that
far.** `BootReceiver` itself was slow to fire — no third-party evidence of
our package in `dumpsys activity broadcasts history`, no app-level log
line, and no process at all until **uptime ≈232s** (~3.9 min post-boot) —
even though other third-party apps (Tailscale) had already started by
then. This reproduces the exact "boot-vs-manual-start gap" the
2026-07-25 session flagged but never root-caused. Once `HostService` did
start, its bind-retry loop correctly began polling — but the retry window
is **`INITIAL_BIND_RETRY_MS = 300_000L` (5 minutes)**, not the ~20s figure
an earlier summary implied (that number was probably from an early draft
of the fix; the shipped constant is far more generous, seemingly
deliberately sized for exactly this slow-Fire-OS-boot case). Even across
the full 5-minute window, `Shizuku.pingBinder()` never returned true —
`shizuku_server` itself never started — and the loop fell through to
`comonitor skipped — not bound`. **Net: `CLOSED_NO_SHELL` was never
actually logged by the agent's own STATUS line, and `CatastrophicRepair`
was never dispatched at all**, because the whole comonitor path requires a
bound Shizuku UserService to run over, and Shizuku itself never came up
unattended. This is a strictly earlier-stage failure than the
already-documented "detects it correctly but the port never reopens" gap.

**Root cause, confirmed live:** the same Fire-OS loopback-EOF problem
issue #60 and a 2026-07-26 handoff doc already identified — Fire OS's
`adbd` drops connections whose peer is device-local, so Shizuku's own
self-start (whether triggered by `stayturgid_repair.py`'s watchdog, an
app-level restart, or a raw `shizuku_starter` invocation over _any_
transport including USB) can't bootstrap on its own once the wireless port
is fully closed, because that self-start's internal pairing check is
inherently a loopback connection from hd8 to itself.

**Recovery attempted and found to need two separate, non-obvious steps —
neither sufficient alone:**

1. First tried the already-documented "safe" external-ADB peer-start
   (`just agent-peer-start s24`, targeting hd8's provisioned
   `100.124.55.39:5555`). **This alone did not work** — it failed with a
   fast `ECONNREFUSED` (not a timeout), because peer-start's own external
   connection _also_ needs the target's wireless ADB port already
   listening, which it wasn't. This is a genuinely new finding: the
   external-ADB peer-start mechanism (issue #61/#65's `PeerStarter`) is
   not sufficient to bootstrap Shizuku from a fully-cold, wireless-off
   `CLOSED_NO_SHELL` state — only to _reconnect_ Shizuku once the port is
   already open by some other means.
2. Reopened the port from the Mac via a **plain `adb tcpip 5555` client
   command over the already-authenticated USB transport** (not `adb
shell` — this issues a low-level protocol command that makes the
   existing `adbd` instance restart in TCP-listening mode, rather than a
   shell-level property/settings toggle that a previous session found
   _doesn't_ reliably force a real restart). Confirmed genuinely external
   (not loopback-only) by connecting to hd8's Tailscale IP directly from
   the Mac afterward.
3. **Then** `just agent-peer-start s24` succeeded: `shizuku_server`
   started on hd8 within ~1s of the peer-start dispatch, `HostService`
   picked up the bound Shizuku within 2 more seconds (`Shizuku binder
received` → `UserService connected` → `pingAwake IPC ok`), all
   confirmed via direct `ps -ef`/`dumpsys` checks, not just log lines.

**Net for #45/#43:** the accepted, documented Fire-OS limitation ("physical
recovery is the accepted fallback, not a bug to keep chasing in software")
needs a more precise restatement — it's not just "plug in a USB cable and
retry the same self-start," it's specifically **a Mac-issued `adb tcpip`
client command (USB-transport-level, not a device-shell command) followed
by an external peer-start** (not a same-device restart). The existing
peer-start mechanism, on its own, cannot recover from a fully-cold boot
where wireless ADB never came back at all — only from a live-but-Shizuku-
died state. `docs/options.md`'s K1 section and the peer-start
docs/`PeerStarter.kt` docstring don't currently document this two-step
requirement or the cold-boot gap; worth a follow-up doc update (not done
in this pass — device-recovery work took priority over documentation
during a live session).

**Devices left in a healthy state:** confirmed via direct process checks
on both (`shizuku_server`, `UserService`, agent process all running;
`service.adb.tcp.port=5555` on hd8, both USB and externally reachable via
Tailscale). No natural comonitor STATUS line had logged on hd8 by the time
this write-up was finished (steady-state interval is 20 minutes,
component-level checks already confirm health) — expected to self-resolve
on its own schedule, not blocking anything.

---

## 6. Verification

- `just check` — clean (`RESULT: PASS (code)`).
- `just test` — clean: 592 pytest tests + 1 skipped, 136 shell unit tests (was
  133; +3 from this fix), 6 ansible-test collection suites (65+16+20+8+15+7
  passed), `just site-contract-check` clean (Entangled parity restored after
  the SITE-CONTRACT.md / template edit).
- `ansible-lint -q playbooks/ ../ansible_collections/stayturgid/` — 0
  failures, 0 warnings, production profile.
- No device was rebooted, reset, or had its running state changed this
  session — all live-device interaction was read-only (`adb shell`
  `dumpsys`/`ps`/`cat`/`id`/`pm path`, `stat` on log files).

## Files changed

```
SITE-CONTRACT.md
ansible/inventory/hosts.yml.example
ansible_collections/stayturgid/fleet/roles/validate/tasks/main.yml
ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml
control/lib/fleet_health.py
control/site_contract/templates/inventory/hosts.yml  (re-tangled, not hand-edited)
device/termux/py/stayturgid_repair.py
tests/lib.sh
tests/test-unit.sh
```
