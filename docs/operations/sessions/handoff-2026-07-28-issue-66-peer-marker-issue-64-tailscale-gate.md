# Handoff: #66 peer-start marker unification + #64 repairTailscale GUI-foreground gate

**Session:** Agent 8, human-relayed orchestration chain (see
`~/ai-orchestration-plan-2026-07-28.md`). **Worktree:**
`~/src/ops-worktrees/peer-marker-66-tailscale-64/stayturgid` (branch
`feature/peer-marker-66-tailscale-64`).

## Headline finding: both issues were already mostly fixed directly on `master`

Same pattern this chain has now hit five times (`#59`, `#60`, `#65`, and now
`#66`/`#64`): commit `81baa49` ("fix(agent): suppress Tailscale GUI launch,
reap stale UserServices, unify Fire OS target reminder (#64, #65, #66)"),
authored by the operator on 2026-07-26 21:30:56 -0400, already implements
the great majority of both issues' asks — about 15 hours after the
operator's own issue comments describing the bugs. Neither issue was closed
or updated after that commit landed. Agent 7 (`#65`'s unit) noticed the
bundling and explicitly flagged one loose end in this exact code for
whoever picked up `#66`/`#64` next (that was me — see below).

### What `81baa49` already did for `#66`

- `AuthorizeReminder.kt`: `isPresent`/`clear`/`clearCommand` all now check
  internal `filesDir` first (via `run-as`) with an external-dir fallback —
  exactly the `PeerConfig`-mirroring unification the issue asked for. Works
  on Fire OS and OneUI uniformly.
- `provision_peer.py`'s `set_target_reminder()`: rewrote the write path to
  `run-as <pkg> touch files/authorize_reminder` with an external-dir
  fallback, fixing the Fire-OS `Permission denied` half of the bug.

### The one residual gap (real, confirmed by testing — not just reading)

The issue's second ask — "fix `set_target_reminder()` to use whichever adb
transport the Mac actually has for that specific target (USB serial or
Tailscale), not assume one" — was **not actually fixed** by `81baa49`,
despite looking like it. The commit added a `adb.resolve_target(target)`
call, but `target` here is the Fire-OS device's **Tailscale** `host:port`
(matches the on-device `PeerConfig.targets` schema, e.g. hd8's
`100.124.55.39:5555`) — not a `devices.conf` **alias name** like `"hd8"`.
`resolve_adb()`/`device_row()` match by alias name only, so calling it with
a raw IP:port is a silent no-op (confirmed live):

```
>>> stayturgid_device.resolve_adb("100.124.55.39:5555")
'100.124.55.39:5555'          # unchanged — no alias literally named that
>>> stayturgid_device.resolve_adb("hd8")
'GN43T503430603PS'            # the actual USB serial, only reachable via the alias
```

So the Mac still unconditionally attempted `adb connect <tailscale-ip>:5555`
even when the Mac only has USB-serial access to that physical device — the
exact bug the issue described, just with the giveaway `resolve_target()`
call as a red herring.

## What I did this unit

### 1. Fixed the residual `#66` gap

- **`control/lib/stayturgid_device.py`**: added `alias_for_host(host,
conf_path=None)` — reverse-lookup a `devices.conf` alias by its
  `tailscale_ip` or `lan_ip` (the existing `device_row`/`iter_devices_conf`
  only look up forward, by alias name).
- **`control/lib/adb_cli.py`**: forwarded it as `alias_for_host()`, matching
  the existing `resolve_target`/`resolve_ssh` forwarding pattern.
- **`control/tools/native-agent/provision_peer.py`**:
  `set_target_reminder()` now splits the port off `target`, reverse-looks-up
  the devices.conf alias for that host, and — only if found — resolves via
  `adb.resolve_target(alias)` (USB-preferred) instead of the dead
  pass-through call. Also skips the `adb connect` step entirely when the
  resolved target is a bare USB serial (no colon) — `adb connect` is a
  network-transport command and doesn't apply to a serial that's already a
  live adb transport. Falls back to the raw target unchanged for hosts not
  in `devices.conf` (ad-hoc/one-off targets), preserving prior behavior
  there.
- Tests added: `test_stayturgid_device_conf.py::test_alias_for_host_reverse_lookup`,
  `test_adb_cli.py::test_alias_for_host_forwards_to_stayturgid_device`, and
  two new tests in `test_provision_peer.py` that exercise
  `set_target_reminder()` end-to-end (mocked `adb.*`) proving: (a) a known
  target resolves to its USB serial and issues shell commands against that
  serial with **no** `adb connect` call, and (b) an unknown target still
  falls back to the old best-effort raw-target behavior.

### 2. Fixed the pre-existing `kt-detekt` finding Agent 7 flagged for this unit

`AuthorizeReminder.kt:42` (`MaximumLineLength`) — pre-existing from
`81baa49`, in this issue's own file, explicitly left for whoever picked up
`#66`/`#64` (see Agent 7's handoff,
`handoff-2026-07-28-issue-65-shizuku-userservice-leak.md`, §"One
known-and-deliberately-untouched remaining kt-detekt finding"). Fixed by
extracting the external-path string to a local `val` instead of inlining it
in the `joinToString` lambda — same string, same behavior, just under the
line-length limit. `just kt-detekt` is now fully clean (0 findings, not
just this issue's slice).

### 3. Verified `#64`'s native-agent gate needs no code changes

`CatastrophicRepair.repairTailscale()` (now at lines 186-193, shifted from
the issue's `:177` reference since `81baa49` landed) already has the exact
gate the issue asked for:

```kotlin
if (ComonitorProbes.isTailscaleTunnelUp()) {
    val detail = "tailscale tunnel up; control-plane probe flaky (GUI launch suppressed)"
    appendLog("[agent] $detail")
    return Result(policyOk, detail)
}
shellOut(arrayOf("am", "start", "-n", TAILSCALE_COMPONENT), 8)
```

`isTailscaleTunnelUp()` reads `/proc/net/dev` directly inside
`ComonitorProbes`, which runs in the Shizuku `UserService` process (UID 2000) — the class's own doc comment confirms this, and it's the same
context the co-monitor already uses correctly (per the issue's own
observation that the native agent "reads the tunnel interface correctly,"
unlike Termux's app-uid read). No `EACCES` risk here, so the gate itself is
correct as shipped. No unit tests existed for `CatastrophicRepair.kt` or
`ComonitorProbes.kt` before or after this unit — both are thin,
`ProcessBuilder`/`File`-IO-heavy wrappers with no pure logic to extract in
the style of `AuthorizeReminderTest.kt`/`ShizukuUserServiceTest.kt`
(unlike `#65`'s `reapStaleUserServices()`, there's no obvious pure decision
function buried in `repairTailscale()` to pull out); adding real coverage
would need dependency-injecting the shell-out layer, which is a much larger
change than this narrow verification unit warranted. Flagging as a gap for
whoever next touches this file with a larger budget.

### 4. Verified `#64`'s Termux-side fleet rollout is complete (not guessed)

The issue's "keeping this open" list included "fleet-wide deploy of the
fixed script — the Pixel peer was offline and the Fire host uses the
Mac-adb path at last check, may have changed." Checked live rather than
trusting that stale note:

- `device/termux/py/stayturgid_repair.py` is deployed via the
  `termux_userland` Ansible role ("Deploy Python runtime scripts to
  `~/.stayturgid/bin`"), so it goes out with every `just deploy`.
- Commit `12c0b61` (the actual `_tailscale_runtime_up()` fix) is an ancestor
  of the `ops-v1.0.13` release commit (`ddad7e2`) — confirmed via
  `git merge-base --is-ancestor`.
- **Live-verified all three fleet devices are now directly SSH-reachable**
  (s24, p7a, hd8 — including hd8's Termux over Tailscale, not just the
  Mac-adb path the issue's note described as the prior state) and their
  deployed `stayturgid_repair.py` **byte-for-byte matches** this repo's
  current blob (`git hash-object` comparison, not just a `grep` for the
  function name):

  ```
  repo blob:      713a9fb1384672cf14441706a6877177c200dd48
  s24 live blob:  713a9fb1384672cf14441706a6877177c200dd48  MATCH
  p7a live blob:  713a9fb1384672cf14441706a6877177c200dd48  MATCH
  hd8 live blob:  713a9fb1384672cf14441706a6877177c200dd48  MATCH
  ```

- **No redeploy needed or attempted** — the fleet is already fully current.
  p7a being reachable at all is itself new information (it was offline as
  of Agent 1's handoff a few hours earlier in this same chain, and is still
  flagged `stayturgid_fleet_status: offline` in site-djbclark inventory
  pending `#103`/`#104` — that flag concerns a different liveness signal,
  not adb/SSH reachability, and is out of scope here).

## Verification

- `~/.local/bin/pytest` (project `.venv-test`, via `just test-venv` then
  `just pytest`): **612 passed, 1 skipped** (pre-existing skip, unrelated).
- `just check`: clean (ruff, biome, shfmt, markdownlint, prettier,
  html-validate, stylelint, validate-identity — ran `bun install` in this
  worktree first since node_modules wasn't present).
- `just kt-format-check`: clean.
- `just kt-test`: `BUILD SUCCESSFUL`, 154 tasks.
- `just kt-detekt`: clean (0 findings — includes fixing the one
  pre-existing finding Agent 7 flagged for this unit).
- Live fleet verification for `#64`(a): see §4 above.

## Files changed

- `control/lib/stayturgid_device.py` — new `alias_for_host()` reverse
  lookup.
- `control/lib/adb_cli.py` — forward `alias_for_host()`.
- `control/tools/native-agent/provision_peer.py` — `set_target_reminder()`
  now resolves the Mac's actual adb transport via reverse alias lookup
  instead of a dead pass-through call.
- `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/AuthorizeReminder.kt`
  — pre-existing `kt-detekt` line-length fix (no behavior change).
- `tests/python/test_stayturgid_device_conf.py`,
  `tests/python/test_adb_cli.py`, `tests/python/test_provision_peer.py` —
  new tests for the above.
- This handoff doc.

## Next steps / recommendations

- PR opened against `master` for `#66` (all code changes in this unit are
  scoped to `#66`'s own file — `#64` needed no code changes, see below).
  Needs a coordinated `ops-vMAJOR.MINOR.PATCH` release like everything else
  in this chain before it reaches the fleet.
- **`#64`: recommend closing**, referencing commit `81baa49` (the gate) and
  this handoff's §4 (fleet rollout confirmed complete on all three
  devices) — both items the operator's comment listed as "keeping this
  open for" are now resolved. Posting a closing comment with this evidence
  as part of this unit (no PR needed since no code changed for `#64`).
- **`#66`: recommend closing once this PR merges** — both original asks
  (unify the marker mechanism, fix the Mac-adb-transport assumption) are
  now genuinely fixed and tested.
- If a larger unit ever touches `CatastrophicRepair.kt`/`ComonitorProbes.kt`
  again, worth extracting a pure decision core (as `#65`'s unit did for
  `ShizukuUserService.kt`) so `repairTailscale()`'s branching logic gets
  real unit coverage instead of relying on manual/live verification.
