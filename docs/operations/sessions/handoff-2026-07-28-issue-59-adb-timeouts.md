# Handoff: #59 close-out (Phase 2)

**Session:** Agent 6, human-relayed orchestration chain (see
`~/ai-orchestration-plan-2026-07-28.md`). **Worktree:**
`~/src/ops-worktrees/adb-timeout-59/stayturgid` (branch `feature/adb-timeout-59`).

## Context

Phase 1 (see `design-2026-07-28-issue-59-adb-timeouts.md`) found that issue
#59's "systemic timeout" migration had already shipped directly to `master`
on 2026-07-26 (commit `db2a852`, before this orchestration chain existed and
before the issue was ever closed), and that it was correct and complete
except for one missed call site. The operator reviewed that design doc,
independently re-verified the `native_agent_config.py:90` gap, found a
second candidate gap (three lookup plugins with local `subprocess.run`-based
`_run_command()` callbacks with no timeout kwarg), and gave go-ahead to fix
everything confirmed real plus the `android_apk.py` dual-mechanism cleanup.

## What I did

### 1. Verified the lookup-plugin claim — not a real gap

`plugins/lookup/{adb_device,android_packages,fdroid_client}.py` each define a
local `_run_command(cmd)` using bare `subprocess.run(cmd, capture_output=True,
text=True, check=False)` with no `timeout=` kwarg, passed as the `run_command`
callback into `resolve_adb()` / `packages_matching()` /
`fdroid_components_for_device()`.

Traced the call chain for all three and confirmed none of them ever invoke
that callback directly — every actual command execution inside
`adb_resolve.py` and `adb_packages.py` (via `adb_shell.py`) already routes
through `run_command_with_timeout()` first, which prefixes the argv with
`timeout <N>` *before* handing it to the callback. So `_run_command` only
ever receives an already-wrapped command like `["/opt/homebrew/bin/timeout",
"30", "adb", "devices"]` and just executes it — the external `timeout(1)`
binary self-bounds the run regardless of whether `subprocess.run` itself has
its own `timeout=` kwarg. `tests/unit/plugins/module_utils/test_adb_resolve.py`
already exercises this (its fake `run()` functions explicitly strip the
`timeout` prefix before matching — `cmd[0].endswith("timeout")`). Also
confirmed `/opt/homebrew/bin/timeout` actually resolves on this control node,
so the fallback path isn't silently degrading here either.

**No changes made to the three lookup plugins** — there was nothing to fix.
Recorded this reasoning here so it's checkable independently rather than
just asserted.

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
different `get_bin_path_fn` — got the *first* cached value regardless. In
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

## Verification

- `ansible_collections/stayturgid/android_common/tests/unit` — 87 passed
- `tests/python` (top-level Termux-script-twin suite) — 592 passed
- `just check` — clean (ruff check+format, biome, shfmt, markdownlint,
  prettier, html-validate, stylelint, site-contract, identity/drift/secrets
  checks all pass)
- `just ansible-test` — all five collections (`android_common`, `termux`,
  `obtainium`, `fdroid`, `play`) green, 118 total ansible-test-harness unit
  tests passed

No manual on-device verification was done or needed — this is a pure
control-node argv-wrapping change with unit coverage; the existing db2a852
commit's identical pattern across 6+ other call sites has already been
running in production deploys since 2026-07-26 with no reported regressions.

## Files changed

- `plugins/modules/native_agent_config.py` — timeout-wrap the staging push
- `plugins/modules/android_apk.py` — unify install/uninstall/work_profile
  onto the shared helper; fold in work_profile rc==124 handling
- `plugins/module_utils/adb_timeout.py` — fix cross-call cache staleness
- `tests/unit/plugins/modules/test_native_agent_config.py` — new test
- `tests/unit/plugins/modules/test_android_apk.py` — two new tests
- `tests/unit/plugins/module_utils/test_adb_timeout.py` — new regression test
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
