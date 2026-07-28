# Handoff: #65 Shizuku UserService leak — verification + cleanup

**Session:** Agent 7, human-relayed orchestration chain (see
`~/ai-orchestration-plan-2026-07-28.md`). **Worktree:**
`~/src/ops-worktrees/shizuku-leak-65/stayturgid` (branch
`feature/shizuku-userservice-leak-65`).

## Headline finding: the root-cause fix already shipped

Same pattern this session already hit twice on `#59`: the code fix issue
`#65` asks for was **already committed directly to `master`** before this
orchestration chain existed. Commit `81baa49` ("fix(agent): suppress
Tailscale GUI launch, reap stale UserServices, unify Fire OS target
reminder (#64, #65, #66)"), authored by the operator on 2026-07-26 21:30:56
-0400 — about 10 hours after the operator's own comment on the issue
(11:19 UTC same day) confirming the leak was still live. The issue itself
is still open (never closed/commented since).

The commit implements **both** fix ideas the issue proposed, not just one:

1. **Stable version tag** — `HostService.kt`'s `userServiceArgs` now pins
   `.version(1)` instead of `.version(BuildConfig.VERSION_CODE)`, so Shizuku
   dedupes the daemon UserService across app upgrades going forward instead
   of minting a new one per version bump.
2. **Active reap-on-bind** — `ShizukuUserService`'s constructor (both
   overloads) now calls a new `reapStaleUserServices()`: for each of the two
   possible package ids (`org.stayturgid.agent`, `.debug`), `pidof
   $pkg:userservice`, exclude this process's own pid, `kill` whatever's left.
   This is genuine defense-in-depth beyond the version-pin — it also cleans
   up any stragglers left over from *before* this fix was installed (old
   version-coded UserServices that predate the stable tag).
3. `start_agent.py` also got an inline stale-`:userservice`-pid kill before
   `am start`, covering the direct-start path (not just full rollouts, which
   `rollout.py:stop_stale_user_services()` already covered).

## What I did this unit

### 1. Live-verified the fix is actually working on hd8

Confirmed I have live fleet access from this environment (same `adb`/
`devices.conf` prior agents in this chain used). hd8
(`GN43T503430603PS`) currently runs `org.stayturgid.agent.debug`
versionCode 15 (`0.6.0-boot-stability-debug`), which already includes commit
`81baa49`.

- Baseline: exactly **one** `:userservice` pid (`19465`).
- Triggered **4 explicit screen-off/screen-on cycles** via `adb shell input
  keyevent KEYCODE_POWER` (each cycle exercises `HostService`'s
  `onScreenOff`/`onScreenOn` → `ensureBound()` path — the exact rebind
  trigger the operator's comment identified as the leak source).
- After every cycle: `pidof org.stayturgid.agent.debug:userservice` still
  returned exactly `19465` — no growth, no duplicate spawned.
- Confirmed via `logcat` that a rebind fired a live `pingAwake IPC ok`
  round-trip against that same daemon, so this wasn't a no-op check — the
  service was genuinely being used each cycle, just not respawned.

This is a real, positive live signal, but it's not the *same* trigger the
original bug needed (an actual app **version bump**, which is what produced
the 22-process blowup in the issue's original symptom) — a stable-tag
UserService naturally survives ordinary rebinds even without the fix, since
Shizuku already dedupes identical bind args within a single running app
version. The version-pin's real test is "does upgrading the app from
versionCode N to N+1 spawn a new UserService," which requires building and
installing two different versions back-to-back — a heavier, riskier
operation than this session's scope warranted (and not meaningfully
different from what a normal fleet deploy will do soon anyway once this
ships in a release). **Flagging for the operator**: if you want the
version-bump path itself spot-checked before considering `#65` fully closed
in practice (not just in code), that's the one thing this session didn't
attempt — everything else (dedup-on-rebind, reap-on-bind logic, kill-path
correctness) is verified either live or by unit test below.

### 2. Fixed a real, pre-existing `kt-detekt`/`kt-format-check` failure the shipped fix left behind

`just kt-check` on a clean rebase of current `master` failed *before I
touched anything*:

- `kt-format-check` (spotless): `ShizukuUserService.kt`'s new
  `reapStaleUserServices()` wasn't spotless-formatted.
- `kt-detekt`: `NestedBlockDepth` and `SpreadOperator` findings, both in
  the same new function.

Kotlin CI doesn't gate on these (no `.github/workflows/*.yml` references
`kt-*` at all — these are local/manual checks only), so this wasn't
blocking anything, but since I was already reading this exact function
closely for the live-verification writeup above, fixed it properly rather
than leaving it broken for whoever runs `just kt-check` next:

- Extracted the pure "which pids are stale" decision into a small
  `internal` companion function, `stalePidsToReap(pidofOutput: String,
  myPid: Int): List<Int>` — flattens the nesting (fixes
  `NestedBlockDepth`) and is now directly unit-testable without mocking
  `ProcessBuilder`.
- Split the two `ProcessBuilder` calls into `runPidof(pkg)` /
  `killPids(pids)` helpers. `killPids` now builds its `ProcessBuilder` via
  the `List<String>` constructor overload (`ProcessBuilder(listOf("kill")
  + pids.map { it.toString() })`) instead of the vararg
  `ProcessBuilder(vararg cmd)` + spread-operator form — fixes
  `SpreadOperator` by construction rather than suppressing it.
- Added `ShizukuUserServiceTest.kt` (new file, 5 tests) covering
  `stalePidsToReap`'s actual logic: excludes own pid among several,
  empty pidof output, only-self-running, tab/newline separators (matches
  real `pidof` output shapes), non-numeric-token tolerance. Matches this
  codebase's existing "extract the pure core, unit test that, leave the
  shell-out IO untested" convention (see `PeerStartCommandsTest.kt` for
  the established precedent).

**One known-and-deliberately-untouched remaining `kt-detekt` finding:**
`AuthorizeReminder.kt:42` (`MaximumLineLength`, a genuinely atomic shell
command string that can't be usefully wrapped) — pre-existing from the same
`81baa49` commit, but in the `#64`/`#66` GUI-suppression/peer-marker code,
not `#65`'s. Left alone since Agent 8's row in the orchestration plan
covers `#66`/`#64` and will likely be touching this exact file — flagging
here rather than fixing opportunistically outside my scope.

## Verification

- `just kt-format-check` — clean
- `just kt-test` — 154 tasks, `BUILD SUCCESSFUL`; new
  `ShizukuUserServiceTest` confirmed via
  `build/test-results/testDebugUnitTest/TEST-org.stayturgid.agent.ShizukuUserServiceTest.xml`
  — `tests="5" skipped="0" failures="0" errors="0"` (verified the count
  directly, not just trusting a green build)
- `just kt-detekt` — 1 pre-existing, out-of-scope finding remains (see
  above); the 3 findings actually in `#65`'s code are all fixed
- Live device verification on hd8 — see §1 above

## Files changed

- `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/ShizukuUserService.kt`
  — refactor `reapStaleUserServices()` for `kt-format`/`kt-detekt`
  cleanliness + testability; no behavior change
- `device/native-agent/app/src/test/kotlin/org/stayturgid/agent/ShizukuUserServiceTest.kt`
  — new
- `docs/operations/sessions/handoff-2026-07-28-issue-65-shizuku-userservice-leak.md`
  — this file

## Next steps

- PR opened against `master`. Needs a coordinated `ops-vMAJOR.MINOR.PATCH`
  release like everything else in this chain before it reaches the fleet —
  this unit doesn't touch that.
- Once released and soaked for a real app-version-bump cycle, worth a
  `pidof :userservice` spot-check across the fleet (not just hd8) to close
  the loop the live-verification section above flagged as not-attempted
  here.
- Recommend closing `#65` referencing this handoff + commit `81baa49` once
  this PR merges — the root-cause fix has been on `master` since 2026-07-26,
  this unit's job was verifying it live and cleaning up the fallout it left
  in the build tooling.
