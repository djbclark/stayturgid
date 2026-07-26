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

## Checkpoint state

The earlier s24 retry identified mutually exclusive Obtainium import
parameters; the follow-up leaves headless import as the sole role mode. The
subsequent p7a proof is complete and green. Its log is intentionally outside
the repository at `/tmp/deploy-convergence-p7a-retry.log`.

## Remaining before merge

1. Split the post-UI app-store pass so normal deploy does not run the entire
   Termux/fleet role stack twice; remove the now-redundant Obtainium UI import
   and require an unlocked screen only when a genuinely UI-driven app-store
   task is enabled.
2. Re-run the normal canary after that cleanup.
3. Run the full repository and site quality gates.
4. Inspect the final diffs, push both task branches, open paired PRs, and
   present verification for operator merge confirmation.
