# Design note: #59 systemic adb `run_command` timeouts

**Status: Phase 1 research below, followed by Phase 2 implementation after
operator review and go-ahead. See
`handoff-2026-07-28-issue-59-adb-timeouts.md` for what Phase 2 actually did —
this document is kept as the as-written Phase 1 research record.**

## Headline finding: the systemic fix already shipped

Issue #59 asks for a centralized timeout helper across every `adb`-invoking
`module.run_command()` call in `ansible_collections/stayturgid/android_common/`.
That work **already exists on `master`**, committed directly by the operator on
**2026-07-26 22:21:55**, commit `db2a8520d749970ec68f3a8769af5f67746628dd`
("fix(android_common): systemically wrap all adb and external commands with
timeouts (#59)") — two days before this orchestration chain was created
(2026-07-28) and before issue #59 was closed (it's still open, 0 comments).

The commit added `plugins/module_utils/adb_timeout.py`:

```python
DEFAULT_FAST_TIMEOUT = 30  # queries: adb devices/connect/shell getprop/mdns
DEFAULT_SLOW_TIMEOUT = 180  # transfers: adb push/install, gh release download, apksigner sign


def run_command_with_timeout(run_command_fn, cmd, timeout=DEFAULT_FAST_TIMEOUT, get_bin_path_fn=None):
    """Prefix cmd with coreutils `timeout <seconds>` if available; rc==124 ->
    clear error message appended to stderr. No-op (unbounded) if `timeout`
    binary can't be resolved — same degrade-gracefully posture as before."""
```

This is exactly the design the issue asked for: a single shared helper, a
two-tier default (fast query vs. slow transfer), consistent `rc==124` handling,
resolved once and cached (`resolve_timeout_bin`, checks `module.get_bin_path`
then falls back to `/opt/homebrew/bin/timeout` / `/usr/bin/timeout` /
`/bin/timeout`). It was then wired into every call site the issue lists:

| Issue's call site                                                                                    | Status                                                               |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `adb_shell.py:17,21` (`adb_connect`, `adb_shell`)                                                    | ✅ routed through `run_command_with_timeout`, `DEFAULT_FAST_TIMEOUT` |
| `adb_resolve.py:50,93,128,164` (`adb devices`, `adb connect`, `-s ... getprop`, `adb mdns services`) | ✅ all four routed, `DEFAULT_FAST_TIMEOUT`                           |
| `autojs6_deploy_util.py:56` (`adb push`)                                                             | ✅ routed, `DEFAULT_SLOW_TIMEOUT`                                    |
| `shizuku_start.py:155` (`adb push` fleet profile)                                                    | ✅ routed, `DEFAULT_SLOW_TIMEOUT`                                    |
| `shizuku_grant.py:94` (`adb push`)                                                                   | ✅ routed, `DEFAULT_SLOW_TIMEOUT`                                    |
| `android_apk.py:172,212` (`package_installed`/`installed_version` via `adb_shell.py`)                | ✅ covered transitively (shared helper)                              |
| `download_gh_release()` (`gh release download`)                                                      | ✅ routed, `DEFAULT_SLOW_TIMEOUT`                                    |
| `resign_apk()` (`apksigner sign`)                                                                    | ✅ routed, `DEFAULT_SLOW_TIMEOUT`                                    |

Tests were added/updated in the same commit: `test_adb_timeout.py` (new, 5
cases: bin resolution, prefixing, `rc==124` handling, double-wrap prevention,
graceful no-op when `timeout` binary is missing), plus updates to
`test_adb_resolve.py`, `test_autojs6_deploy.py`, `test_shell_libs.py`,
`test_shizuku_device.py`. I re-ran the full `android_common` unit suite plus
the top-level `tests/python/test_{adb_resolve,autojs6_deploy,shell_libs,
shizuku_device}.py` in a fresh worktree venv — **all green**, no changes
needed to make them pass.

I also confirmed the open-questions the issue explicitly flagged:

- **`gh release download` / `apksigner sign` treatment** — the commit put them
  through the _same_ mechanism (`DEFAULT_SLOW_TIMEOUT`, same helper), not a
  separate one. Reasonable: both are simple "spawn a process, wait, check rc"
  shell-outs with no signal/streaming needs, so a second bespoke mechanism
  would just be duplication.
- **Tiered defaults** — implemented as proposed (fast query vs. slow transfer),
  30s / 180s. 180s matches the pre-existing `install_timeout` default in
  `android_apk.py` (see below), so it's consistent with what's already proven
  survivable in production. 30s for queries is generous relative to typical
  `adb shell getprop`/`pm list` latency (sub-second on a healthy device) while
  leaving headroom for a slow/loaded Fire OS tablet.

## What I did for Phase 1 (per the issue's own process, mirroring #58)

1. **Web search for prior art.** Confirmed `AnsibleModule.run_command()` has no
   native timeout parameter — this is a long-standing, still-open upstream
   limitation (multiple GitHub issues over the years, no resolution). There is
   no `community.general` (or any other) precedent for ADB-specific tooling —
   no such collection exists. The closest matching idiom that does show up
   consistently in community guidance is exactly what's already implemented
   here: wrap the underlying command with the coreutils `timeout(1)` binary
   from inside the module. That's a documented workaround pattern, not
   something invented for this repo — and this repo was already using it
   in `stayturgid_battery_alarm.py` (on-device) and the original narrow #43
   fix in `android_apk.py` before this systemic commit generalized it. So:
   confirmed, same as #58's flock finding — the existing approach **is** the
   standard idiom, nothing to redesign.
2. **Re-audited the issue's inventory against current code** (it can drift —
   the issue was filed, then apparently fixed, without ever being closed or
   commented on). Re-grepped the entire `plugins/` tree for every
   `run_command(` call site, not just the ones the issue names, to catch
   anything added or missed since. Result below.

## Real gap found: `native_agent_config.py` was missed

One call site is **not** covered and was **not** in the issue's original
inventory (the issue's list predates or simply overlooked this module):

```
plugins/modules/native_agent_config.py:90
    rc, _out, err = module.run_command(["adb", "-s", device, "push", tmp.name, staging])
```

This module (`native_agent_config.py`, added at `ops-v1.0.3` — well before the
`db2a852` sweep) writes the native-agent peer-target JSON to each device over
`adb push`, same failure class as the other push call sites already fixed
(`shizuku_start.py`, `shizuku_grant.py`, `autojs6_deploy_util.py`). It's a
straight two-line miss, not a design gap — the fix is the identical pattern
already applied six times in the same commit:

```python
try:
    from ansible_collections.stayturgid.android_common.plugins.module_utils.adb_timeout import (
        DEFAULT_SLOW_TIMEOUT,
        run_command_with_timeout,
    )
except ImportError:
    ...  # same sys.path fallback used in shizuku_start.py / shizuku_grant.py

...
rc, _out, err = run_command_with_timeout(
    module.run_command,
    ["adb", "-s", device, "push", tmp.name, staging],
    timeout=DEFAULT_SLOW_TIMEOUT,
    get_bin_path_fn=module.get_bin_path,
)
```

_(Update: this edit was made in Phase 2 — see the handoff doc.)_

## Minor inconsistency (not a functional gap): dual timeout mechanisms in `android_apk.py`

`android_apk.py`'s `adb install`/`adb uninstall` call sites (lines ~389-449 —
the original #43 narrow fix, which predates and motivated this systemic
commit) still use their own **hand-rolled** prefixing:

```python
timeout_bin = module.get_bin_path("timeout", required=True)
cmd = [timeout_bin, str(module.params["install_timeout"]), "adb", "-s", device, "install", ...]
rc, out, err = module.run_command(cmd)
...
if rc == 124:
    module.fail_json(msg="adb install timed out after %ss ..." % module.params["install_timeout"])
```

rather than the new shared `run_command_with_timeout()` helper. Functionally
this is fine — it has an explicit timeout, `rc==124` handling, and a clear
`fail_json` message, so there's no live hang risk here. But it's now a second,
parallel implementation of the same idea living in the same file that
otherwise imports the new helper for `download_gh_release()`/`resign_apk()`.
Two observations, not a recommendation to act unilaterally:

- Unifying it onto `run_command_with_timeout(..., timeout=module.params["install_timeout"])`
  would remove the duplication and let `install_timeout` flow through the
  shared helper's `rc==124` message instead of a hand-written one — cosmetic
  but real cleanup.
- The `work_profile` install fallback (line 449, `wp_cmd`) doesn't special-case
  `rc==124` at all — a timeout there just falls into the generic "work profile
  install failed (rc=%d)" warn path, losing the specific "may be showing a
  confirmation dialog" message. Low stakes (it's a warn, not a fail, and only
  fires when `work_profile: true` is set), but worth folding into the same
  unification if that cleanup happens.

I'd treat this as optional polish, not required — it doesn't change behavior
under the failure mode #59 is about (an unbounded hang). Recommend leaving it
alone unless the reviewer wants the unification done as part of closing out
the native_agent_config.py gap.

## Recommendation

There is no "broad migration" left to design or implement — it already
happened, matches the idiom the web search confirms is standard, has test
coverage, and is currently green on `master`. The only real remaining work is
the one missed `native_agent_config.py` call site, which is a mechanical
2-line-pattern application of code that already exists six times over in the
same file tree — not a design decision. Suggest the second-opinion review
should be scoped to: **(a) confirm no other call sites were missed** (I did a
full-tree grep, but a second pass is cheap insurance), and **(b) a go/no-go on
whether the `android_apk.py` dual-mechanism unification is worth doing now or
left alone** — then a trivial PR for the `native_agent_config.py` fix (plus
unification if greenlit) closes out #59 for real.

_(Update: the operator reviewed this and confirmed go-ahead on both — see the
handoff doc for the second gap the review found (the lookup-plugin claim,
investigated and found to already be covered — not a live gap) and what
Phase 2 actually shipped.)_
