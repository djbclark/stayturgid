# Handoff: #59 close-out (Phase 2)

**Session:** Agent 6, human-relayed orchestration chain (see
`~/ai-orchestration-plan-2026-07-28.md`). **Worktree:**
`~/src/ops-worktrees/adb-timeout-59/stayturgid` (branch `feature/adb-timeout-59`).

## Context

Phase 1 (see `design-2026-07-28-issue-59-adb-timeouts.md`) found that issue
`#59`'s "systemic timeout" migration had already shipped directly to `master`
on 2026-07-26 (commit `db2a852`, before this orchestration chain existed and
before the issue was ever closed), and that it was correct and complete
except for one missed call site. The operator reviewed that design doc,
independently re-verified the `native_agent_config.py:90` gap, found a
second candidate gap (three lookup plugins with local `subprocess.run`-based
`_run_command()` callbacks with no timeout kwarg), and gave go-ahead to fix
everything confirmed real plus the `android_apk.py` dual-mechanism cleanup.

## What I did

### 1. The lookup plugins: initially found not-a-gap, then wrapped anyway on request

`plugins/lookup/{adb_device,android_packages,fdroid_client}.py` each define a
local `_run_command(cmd)` using bare `subprocess.run(cmd, capture_output=True,
text=True, check=False)` with no `timeout=` kwarg, passed as the `run_command`
callback into `resolve_adb()` / `packages_matching()` /
`fdroid_components_for_device()`.

Traced the call chain for all three and confirmed none of them ever invoke
that callback directly — every actual command execution inside
`adb_resolve.py` and `adb_packages.py` (via `adb_shell.py`) already routes
through `run_command_with_timeout()` first, which prefixes the argv with
`timeout <N>` _before_ handing it to the callback. So `_run_command` only
ever received an already-wrapped command like `["/opt/homebrew/bin/timeout",
"30", "adb", "devices"]` and just executed it — the external `timeout(1)`
binary self-bounds the run regardless of whether `subprocess.run` itself has
its own `timeout=` kwarg. `tests/unit/plugins/module_utils/test_adb_resolve.py`
already exercises this (its fake `run()` functions explicitly strip the
`timeout` prefix before matching — `cmd[0].endswith("timeout")`). Also
confirmed `/opt/homebrew/bin/timeout` actually resolves on this control node,
so the fallback path isn't silently degrading here either. That analysis
still stands — it was never a live hang risk.

The operator asked for these three to be wrapped anyway, as defense in depth
against a hypothetical future caller that invokes `_run_command` (or
whatever these get refactored into) directly, bypassing `resolve_adb()`/
`packages_matching()`. Implemented that, but **not** with the originally
suggested `shutil.which`-based `get_bin_path_fn` — tracing the double-layer
call pattern (this new inner wrap, invoked as the callback of the outer wrap
`adb_resolve.py`/`adb_shell.py` already apply) showed that would create a
real double-wrapping bug: `shutil.which` searches `$PATH` while the outer,
unannotated `run_command_with_timeout()` calls upstream (`get_bin_path_fn`
never passed, so it defaults to `None`) resolve via a fixed 3-path candidate
scan plus a process-global cache. On a machine where those two mechanisms
disagree about the binary's absolute path, the double-wrap guard's simple
`exec_cmd[0] != timeout_bin` check would fail to recognize an
already-wrapped incoming cmd and prefix `timeout` a second time. Used
`get_bin_path_fn=None` (i.e. don't override it) in the new inner wrap
instead, so it shares the exact same resolution/cache as the outer layer —
correct no-op in the current call pattern, real protection if ever called
standalone. Each lookup plugin's docstring on `_run_command` explains this
in place.

Added `tests/python/test_{adb_device,android_packages,fdroid_client}_lookup.py`
(one file per plugin, script-twin convention — see below for why they don't
live under the collection's `tests/unit/`) with: an isolated `_run_command`
wrapping test, an end-to-end `LookupModule.run()` test confirming the real
public entry point still funnels through the wrapped callback, and (for
`adb_device.py`) an explicit double-wrap-guard regression test. These
required giving `adb_packages.py` (imported by two of the three lookup
plugins) the same try/except-ImportError sys.path-fallback resilience every
other `module_utils` file already has — it previously had a hard,
non-fallback import of `adb_shell`, which only resolved inside
`ansible-test`'s collection-namespace setup and would have made the new
tests uncollectable under plain `pytest` (which `just check`'s
`pytest --collect-only` step
also requires to succeed).

**Why `tests/python/`, not `tests/unit/plugins/lookup/`:** first tried
putting these under the collection's own `tests/unit/plugins/lookup/`
(which didn't exist before this — module_utils/modules were the only two
categories with tests). That triggered a real, pre-existing `ansible-test`
harness bug: `ansible-test units` categorizes unit tests into `module`,
`module_utils`, and (everything else, including `lookup`) `controller`
buckets, and this repo's `--local` invocation mis-builds
`ANSIBLE_COLLECTIONS_PATH` as a malformed colon-joined multi-path string
specifically for the `controller` bucket — `ansible_pytest_collections.py`'s
`collection_resolve_package_path()` then fails every controller-category
test file with `File "..." not found in collection path "..."`. Confirmed
this is unrelated to my code (the module_utils/modules buckets, which this
repo already used, work fine) and is simply never-before-triggered since no
`lookup`/`filter`/other controller-side plugin ever had a unit test in this
collection. Rather than debug vendored `ansible-test` internals for a
tangential infra gap, followed this repo's own established pattern instead:
`tests/python/` already holds plain-pytest "script-twin" tests for several
`module_utils` files (e.g. `test_adb_resolve.py` exists both there and under
the collection) specifically because `ansible-test`'s collection-scoped scan
(`cd ansible_collections/stayturgid/$c && ansible-test units`) never sees
anything under the repo-root `tests/python/` tree at all — sidesteps the bug
entirely, still fully covered by `just pytest`/`just check`'s
`pytest --collect-only` gate. If someone wants controller-category
`ansible-test` coverage for lookup plugins later, that's a separate,
pre-existing infra fix, not in scope here.

### 2. Fixed the real gap: `native_agent_config.py:90`

Routed the staging `adb push` through `run_command_with_timeout()` with
`DEFAULT_SLOW_TIMEOUT` (180s, transfer-class), matching the identical pattern
already used in `shizuku_start.py`/`shizuku_grant.py`/`autojs6_deploy_util.py`.
Added `test_push_command_wrapped_in_timeout` to
`test_native_agent_config.py` asserting the push command is prefixed with
the resolved `timeout` binary + `180`.

### 3. Unified `android_apk.py`'s install/uninstall/work_profile paths

These predated the systemic commit (the original narrow #43 fix) and used
their own hand-rolled `timeout_bin = module.get_bin_path("timeout",
required=True)` + manual argv prefixing instead of the shared helper. Moved
all three call sites (`uninstall`, `install`, the incompatible-upgrade retry
`uninstall`+`install`, and `work_profile` install) onto
`run_command_with_timeout(..., get_bin_path_fn=module.get_bin_path)`.

Preserved the one deliberate behavioral property of the original code: a
**missing** `timeout` binary must fail loudly here (this call site is the one
that caused the original incident), not silently degrade to unbounded like
the shared helper's default posture elsewhere. Kept the explicit
`module.get_bin_path("timeout", required=True)` call as an upfront guard
before the install/uninstall logic runs, then let `run_command_with_timeout`
do the actual wrapping (it re-resolves via the same `get_bin_path_fn`, which
will now succeed since the guard already proved the binary exists).

Also folded in the gap the operator flagged: the `work_profile` install
fallback previously only ever produced a generic `"work profile install
failed (rc=%d)"` warning, even on `rc==124` — losing the specific
"confirmation dialog" hint the primary install path has. Added an explicit
`elif rc2 == 124` branch with the same wording, still a `warn()` not a
`fail_json()` (this path is intentionally best-effort).

Added two tests: `test_android_apk_work_profile_install_wrapped_in_timeout`
(happy path, asserts `reason` mentions the work-profile install) and
`test_android_apk_work_profile_timeout_warns_with_dialog_hint` (asserts the
new rc==124 branch fires, the task doesn't fail, and the warning text
matches).

### 4. Found and fixed a real latent bug this surfaced: `adb_timeout.py` cross-call cache staleness

Adding `android_apk.py`'s install path as a new `get_bin_path_fn`-passing
caller exposed a pre-existing bug in `resolve_timeout_bin()`:
`_CACHED_TIMEOUT_BIN` is a **process-global** cache populated by whichever
call resolves first, and every subsequent call — even ones passing a
different `get_bin_path_fn` — got the _first_ cached value regardless. In
the test suite this manifested as `test_android_apk_install_wrapped_in_timeout`
failing: `test_adb_timeout.py::test_resolve_timeout_bin` (which sorts first —
`module_utils` < `modules`) calls the real unmocked resolver, caching the
real `/opt/homebrew/bin/timeout`; the android_apk test's own mocked
`get_bin_path` (`/usr/bin/timeout`) then got silently ignored.

This isn't just a test artifact — it's a real correctness gap in the
function's contract (a caller-supplied resolver should be authoritative for
that call, not overridden by whatever some earlier unrelated caller found).
Fixed `resolve_timeout_bin()` so a provided `get_bin_path_fn` is always
consulted fresh and wins immediately if it returns a path; only the
hardcoded-candidate filesystem scan (the fallback used when no
`get_bin_path_fn` is available) is memoized process-wide, since that's the
one case representing an expensive, call-independent system fact worth
avoiding repeated `stat()` calls for. Added
`test_resolve_timeout_bin_prefers_fresh_get_bin_path_fn_over_cache` as a
regression test (pre-poisons the cache, then asserts a fresh
`get_bin_path_fn` still wins).

## Addendum: two CodeRabbit findings on PR #117, fixed post-CI-green

CodeRabbit's async review (still pending when CI's `test` check first went
green) surfaced two real findings against the code, not the docs:

1. **MAJOR — clean-uninstall result was discarded.** In `android_apk.py`,
   the `clean` flag's uninstall-before-install call
   (`run_command_with_timeout(module.run_command, ["adb", "-s", device,
"uninstall", package], ...)`) had its return value thrown away entirely —
   no variable assignment. A failed or timed-out uninstall silently fell
   through to the in-place `adb install -r` anyway, so the module could
   report success without ever performing the clean reinstall the `clean`
   flag exists for (defeating the native-lib re-extraction behavior tied to
   this module's `#60` history). This bug predates this PR (the original
   hand-rolled `module.run_command(...)` call had the same discard-the-result
   shape) but this PR touched the line, so fixed it here rather than filing
   a separate issue. Now captures `rc`/`out`/`err` and `fail_json`s on
   nonzero rc or non-"Success" output, mirroring the existing pattern
   immediately below it (the incompatible-upgrade clean fallback). Added
   `test_android_apk_clean_uninstall_failure_fails_before_install` —
   asserts the task fails and that `adb install -r` is never reached when
   the uninstall fails.
2. **Minor — missing device-interaction announcements.** Per
   `AGENTS.md`'s documented convention ("Announce before device interaction:
   🚨📱🚨 USING — host — why — ~N min"), added paired
   `🚨📱🚨 USING — {device} — {why} — ~3 min` /
   `🟢📱🟢 FREE — {device} — {what} complete` announcements around every
   remaining device-mutating `adb` call these two modules make: the clean
   uninstall, primary install, incompatible-upgrade fallback
   uninstall+reinstall, and work-profile install in `android_apk.py`, and
   the staging `adb push` in `native_agent_config.py`. `~3 min` matches
   `DEFAULT_SLOW_TIMEOUT`/`install_timeout`'s 180s **default** — a
   reasonable worst-case estimate for the common case, not a made-up
   number. It's a static string, not dynamically derived from the actual
   configured value: `install_timeout` is a playbook-settable module
   param, so a caller that overrides it to something other than 180s will
   see a slightly inaccurate estimate in the announcement text (harmless —
   it's advisory, not the actual enforced bound, which still comes from
   `install_timeout` itself).

   **Mechanism note:** the existing convention's only prior implementation
   (`control/tools/native-agent/rollout.py`) uses plain `print()`, but that's
   a standalone control-node script, not an `AnsibleModule`. Ansible modules
   communicate their result to the controller via a single JSON blob printed
   to **stdout** at `exit_json`/`fail_json` time; anything else written to
   stdout first would corrupt that parse and crash the module with a
   "not valid JSON" error. Used `sys.stderr.write(...)` instead, matching
   the repo's own existing precedent for this exact situation
   (`control/lib/ui_guard.py`'s `🚨📱🚨 MANUAL ACTION REQUIRED` warning also
   writes to `sys.stderr`, not stdout, for the same reason). `module.warn()`
   was the other candidate but is buffered until task-end by Ansible's
   result protocol, which doesn't satisfy the "before" part of "announce
   before device interaction" — stderr is written immediately, at the point
   of interaction.

Re-verified the full suite after both fixes and pushed as a follow-up
commit; CI's `test` check confirmed green again afterward. (This was an
intermediate checkpoint — later commits on this branch/PR changed the
totals again. **The `## Verification` section below has the final,
as-merged numbers** — treat any counts mentioned inline elsewhere in this
doc as a snapshot of that round only, not the final state.)

## Addendum 2: two more CodeRabbit findings, same PR

Another CodeRabbit pass found:

1. **MAJOR — the three lookup plugins were also missing the
   device-interaction announcement.** Same `AGENTS.md` convention as
   `android_apk.py`/`native_agent_config.py` above, just not yet applied to
   `_raw_run_command()` in `adb_device.py`/`android_packages.py`/
   `fdroid_client.py`. Added it there too, wrapping the actual
   `subprocess.run()` call (the one true device-interaction point regardless
   of which lookup-level function invoked it) rather than the `_run_command`
   timeout-wrapping layer above it. Since `_raw_run_command(cmd)` only
   receives an argv list (no separate `device` parameter — lookup plugins
   don't thread one through the way the two Ansible modules do), added a
   small `_target_from_cmd(cmd)` helper per file that best-effort extracts a
   `-s <serial>` or `adb connect <endpoint>` target from the (possibly
   already timeout-prefixed) argv, falling back to a generic
   `"control-node adb"` label for target-less queries (`adb devices`,
   `adb mdns services`). Used `~30s default` instead of `~3 min` for the
   duration, matching these files' `DEFAULT_FAST_TIMEOUT` (they're
   query-class, not transfer-class). Added `test_target_from_cmd_*` and
   `test_raw_run_command_announces_before_and_after` (using `capsys` to
   assert on the actual stderr output) to each of the three lookup-plugin
   test files.
2. **Minor — inconsistent verification-count reporting.** This doc had
   accumulated test-count numbers from three separate verification rounds
   (87/592/118 → 88/592/118 → 87/599/137) reported inline at each round
   without saying which was final, since each addendum was written
   immediately after that round's fix rather than going back to update
   earlier numbers. Fixed by making the `## Verification` section below the
   single labeled source of truth (final numbers only) and pointing back to
   it from the earlier inline mentions instead of leaving stale figures
   presented as current.

## Verification (final, as of the last commit on this branch)

- `ansible_collections/stayturgid/android_common/tests/unit` — 87 passed
- `tests/python` (top-level Termux-script-twin suite, via `just pytest`) —
  605 passed, 1 skipped (592 baseline + 7 lookup-plugin tests from Addendum
  1 + 6 announcement/`_target_from_cmd` tests from Addendum 2)
- `just check` — clean, all 21 tier-a checks including `pytest: tests
collect cleanly` (ruff check+format, biome, shfmt, markdownlint, prettier,
  html-validate, stylelint, site-contract, identity/drift/secrets checks
  all pass)
- `just ansible-test` — all five collections (`android_common`, `termux`,
  `obtainium`, `fdroid`, `play`) green, 137 total ansible-test-harness unit
  tests passed (70+17+20+8+15+7, no controller-category errors)

No manual on-device verification was done or needed — this is a pure
control-node argv-wrapping change with unit coverage; the existing db2a852
commit's identical pattern across 6+ other call sites has already been
running in production deploys since 2026-07-26 with no reported regressions.

## Files changed

- `plugins/modules/native_agent_config.py` — timeout-wrap the staging push;
  device-interaction announcement
- `plugins/modules/android_apk.py` — unify install/uninstall/work_profile
  onto the shared helper; fold in work_profile rc==124 handling; fix the
  discarded clean-uninstall result; device-interaction announcements
- `plugins/module_utils/adb_timeout.py` — fix cross-call cache staleness
- `plugins/module_utils/adb_packages.py` — add the same
  try/except-ImportError sys.path-fallback resilience every other
  module_utils file already has (needed so the lookup plugins below are
  testable outside `ansible-test`'s collection namespace)
- `plugins/lookup/adb_device.py`, `plugins/lookup/android_packages.py`,
  `plugins/lookup/fdroid_client.py` — timeout-wrap `_run_command` as
  defense in depth (see §1 above for why `get_bin_path_fn` is deliberately
  left at its default rather than `shutil.which`); device-interaction
  announcement around the actual `subprocess.run()` in `_raw_run_command`
  plus a `_target_from_cmd()` helper to label it (Addendum 2)
- `tests/unit/plugins/modules/test_native_agent_config.py` — new test
- `tests/unit/plugins/modules/test_android_apk.py` — three new tests (one
  parametrized over failure/timeout, so four test cases total)
- `tests/unit/plugins/module_utils/test_adb_timeout.py` — new regression test
- `tests/python/test_adb_device_lookup.py`,
  `tests/python/test_android_packages_lookup.py`,
  `tests/python/test_fdroid_client_lookup.py` — new (script-twin location;
  see §1 above for why not under the collection's own `tests/unit/`);
  `_target_from_cmd`/announcement tests added in Addendum 2
- `docs/operations/sessions/design-2026-07-28-issue-59-adb-timeouts.md` —
  status annotations pointing at this doc
- `docs/operations/sessions/handoff-2026-07-28-issue-59-adb-timeouts.md` —
  this file

## Next steps

- PR opened against `master` (stayturgid). Once merged, #59 can be closed
  referencing this handoff + the design doc.
- Not part of any release yet — needs a coordinated `ops-vMAJOR.MINOR.PATCH`
  per `docs/OPS-RELEASES.md` like every other change in this chain. Purely a
  control-node Ansible collection change (no on-device APK/native-agent
  changes), so low deploy risk whenever it's bundled into the next release.
