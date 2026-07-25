# Handoff — 2026-07-25 fleet-deploy-pipeline debugging

Continuation of [session-2026-07-25-k1-verification.md](session-2026-07-25-k1-verification.md)
("Continued: fleet-deploy-pipeline debugging" section has the full writeup).
This doc is the short version for picking work back up.

## State right now

- **3 commits on `master`, not yet pushed to `origin`:** `0a4c55d`, `5c7f023`,
  `ebf83a0`. Working tree clean. All 133 unit tests pass.
- **s24 and p7a deploy clean end-to-end** (`just deploy s24`, `just deploy p7a`
  — confirmed live, `failed=0` both times, re-verified after each fix).
- **hd8 still fails**, but on a distinct, pre-existing, unrelated issue —
  see "Open: hd8" below.
- No stray `ansible-playbook`/`deploy_fleet.py` processes, no dangling adb
  connections beyond the normal three devices.

## What changed and why (fast version)

1. `stayturgid_repair_check.py` — this ansible-core auto-fails any module
   result with a nonzero `rc` key unless `failed: False` is explicit. Fixed.
2. `obtainium/roles/obtainium_apps/tasks/main.yml` — `operator/Obtainium`
   placeholder → real `djbclark/Obtainium` fork (was 404ing every run).
3. `fleet/roles/post_ui/tasks/main.yml` — deleted the AutoJs6-drawer task
   (dead: AutoJs6 was uninstalled fleet-wide in the K1 cutover).
4. `android_apk.py` — `adb install` had **no timeout at all** (this
   ansible-core's `run_command()` doesn't support one). Confirmed live: hung
   a deploy 90+ minutes with zero error before being diagnosed and killed.
   Wrapped both install call sites in `timeout(1)`, 180s default, clear
   failure message on `rc==124`. Tests added.

## Open: hd8

```
fatal: [hd8]: adb install failed: INSTALL_FAILED_VERSION_DOWNGRADE
```

on `moe.shizuku.privileged.api`. hd8 already has a newer custom build
installed (`versionName=13.7.0-thedjchi+stayturgid-release20`) than whatever
the pinned bootstrap-APK role is trying to push. Not root-caused. Likely
either the pinned release tag/URL for the Shizuku fork needs bumping, or the
role needs an uninstall-before-reinstall path for genuine downgrades. Check
`ansible_collections/stayturgid/android_common/roles/bootstrap_apks/` for
where the Shizuku APK source/version is pinned.

Failed fast with a clear error this time (not a hang) — the timeout fix
didn't regress normal failure handling.

## Issues filed this session, not yet worked

- [#57](https://github.com/djbclark/stayturgid/issues/57) — deploy-speed
  analysis (redundant `ansible-playbook` launches, unconditional
  `ansible-galaxy` reinstall, `linear` strategy, `serial: 1` throttle).
  Recommends adding `ansible.posix.profile_tasks` to measure before changing
  anything.
- [#58](https://github.com/djbclark/stayturgid/issues/58) — no lock/
  coordination between `deploy_fleet.py`, the nightly package-upgrade
  launchd job, and manual deploys touching the same devices concurrently.
  Includes explicit next steps: web search for best practices, then a
  second-opinion prompt, before implementing.
- [#59](https://github.com/djbclark/stayturgid/issues/59) — the adb-install
  timeout fix (#4 above) was narrow; the same unguarded-`run_command`
  pattern exists throughout `android_common`'s other adb-invoking helpers
  (`adb_shell.py`, `adb_resolve.py`, `shizuku_start.py`, `shizuku_grant.py`,
  `autojs6_deploy_util.py`). Full call-site inventory is in the issue body.
  Same explicit next steps: web search, then second-opinion prompt.

## Recommended next steps, in order

1. Push the 3 commits (not done — wasn't asked to this session).
2. Root-cause hd8's `INSTALL_FAILED_VERSION_DOWNGRADE` (see above) so all
   three devices deploy clean.
3. Work #57/#58/#59 in whatever order — none block the others. #58 and #59
   both explicitly want a web search + second-opinion prompt before
   implementing, per this session's established pattern.
4. Return to the K1 verification next-steps list (unchanged, still open):
   watchdog reboot-proof, Tasker investigation, `CLOSED_NO_SHELL` soak
   re-run, Fire-OS adbd-restart decision, AutoJs6 self-heal/health-probe
   cleanup. Full list in the parent session doc.

## Verification commands

```
cd ~/ops/stayturgid
bash tests/test-unit.sh                                    # 133 tests
.venv-test/bin/python -m pytest ansible_collections/stayturgid/android_common/tests/unit/plugins/modules/test_android_apk.py -q
python3 control/bin/deploy_fleet.py s24 --scope full        # confirmed clean
python3 control/bin/deploy_fleet.py p7a --scope full        # confirmed clean
python3 control/bin/deploy_fleet.py hd8 --scope full        # still fails, see above
```
