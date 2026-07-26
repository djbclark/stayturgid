# Session 2026-07-26 — Normal deploy convergence

## Objective

Make the normal fleet deploy the only authoritative path from an arbitrary
device state, including a factory reset, to the intended fleet configuration.
Do not create working states that the same deploy cannot reproduce.

## Implemented

- Replaced repository-wide GitHub `latest` lookups with an immutable bootstrap
  APK lock: exact release tag, asset pattern, `versionName`, and SHA-256.
- Pinned the native agent to `agent-v0.6.0` / `app-release.apk` /
  `0.6.0-boot-stability`.
- Made APK installation checksum-aware and reinstall stale versions.
- Made the deploy ensure APKs before it verifies their versions.
- Made release/debug package variants mutually exclusive.
- Reconciled native-agent peer configuration from site inventory and triggered
  the agent's headless peer-start receiver on every deploy.
- Verified `HostService` after the headless trigger.
- Removed the duplicate mutable Obtainium `latest` installer, disabled
  Obtainium background updates for ops-locked applications, and made the
  headless catalog import part of every normal deploy.
- Removed the second full fleet-role pass and the legacy UI-driven Obtainium
  import. App-store UI work now remains in the post-UI play, while the normal
  fleet role stack runs exactly once.
- Made the post-UI unlock prompt conditional on an enabled UI-driven app-store
  task, so a normal deploy with app stores parked remains fully headless.
- Pinned the external Ansible collection dependencies exactly and made the
  normal test/lint recipes provision those exact versions when absent.
- Added an exact checksum to the FIRERPA binary install.
- Taught the shared Ansible resolver to preserve multiple inventory sources and
  to supply product role/collection paths for every product entry point.
- Added the normal-deploy convergence rule and healing-registry coverage.
- Declared the site-owned s24 and p7a native-agent peer targets for hd8.

## Verification checkpoint

- Targeted Python/unit suite: 35 tests passed before the resolver additions.
- Resolver and fleet-entry regression suite: 41 tests passed.
- Healing registry: 31 desired states and 7 mechanisms covered.
- Changed Python passes Ruff; changed YAML passes yamllint.
- `site.yml` syntax check passes against the site overlay.
- `ansible-lint` production profile passed across 68 files before the final
  resolver/variant-cleanup edits.
- Read-only s24 convergence check proved all seven immutable APK locks.
- First real normal-wrapper canary exposed and fixed:
  1. comma-separated inventory sources treated as one path;
  2. product role search path missing from direct wrapper invocation;
  3. Samsung's error when uninstalling an already-absent debug package.
- The p7a canary exposed a stale-package signing-lineage case. The APK module
  now tries its data-preserving in-place upgrade first, then automatically
  uninstalls and retries once for Android's package/signature/shared-user/
  version incompatibility errors. Matching versions never enter this fallback.
- The retry then converged p7a from a stale release agent plus an installed
  debug variant: removed the debug package, upgraded the release package to
  `0.6.0-boot-stability`, reconciled peer config, started and verified
  `HostService`, passed all seven APK locks, completed headless Obtainium
  import, and finished final validation (`ok=319`, `failed=0`). The wrapper's
  Mac phase also passed (`ok=59`, `failed=0`); terminal result:
  `Fleet deploy complete`.
- The retry canary reached the native-agent milestones successfully:
  exact agent version, reconciled peer config, headless start, running
  `HostService`, and post-convergence verification.
- The final p7a normal-wrapper canary after the single-pass cleanup completed
  with exactly one `stayturgid fleet deploy` play. The already-current agent
  install and absent debug-variant cleanup both skipped; the release agent
  remained `0.6.0-boot-stability`; peer reconciliation, headless service
  trigger, foreground-service verification, headless Obtainium catalog import,
  and final validation all passed. The UI unlock and Aurora tasks skipped.
  Recaps: device `ok=198`, `failed=0`; Mac `ok=59`, `failed=0`; terminal result
  `Fleet deploy complete`.
- Full product `just test` passed with 133 shell/unit checks, 585 Python tests
  passed and 1 skipped, and all six collection unit suites green.
- Full product `just lint-offline` passed, including Ruff, mypy (234 source
  files), Biome, shell formatting, Markdown/Prettier, HTML, CSS, offline link
  checks, generic identity drift, and secret-shape validation.
- The private site `just lint` passed its registry guard and all 19 unit tests.
- PR review follow-up added asynchronous `HostService` verification retries,
  explicit Obtainium intent routing, empty-lock rejection, safe checksum
  normalization for managed Python 3.6+, visible/optional destructive APK
  cleanup, quoted native-agent config paths, strict package override behavior,
  stale Ansible collection detection, and the corresponding regressions.

## Final state

The earlier s24 retry identified mutually exclusive Obtainium import
parameters; the follow-up leaves headless import as the sole role mode. The
subsequent p7a proofs are complete and green. Their logs are intentionally
outside the repository at `/tmp/deploy-convergence-p7a-retry.log` and
`/tmp/deploy-convergence-p7a-single-pass.log`.

## Remaining before merge

Product PR [#72](https://github.com/djbclark/stayturgid/pull/72) and paired
private site PR #17 are open. Review findings are resolved and the local gates
have been rerun; updated GitHub checks and operator merge confirmation remain.
