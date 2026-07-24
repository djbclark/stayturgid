# Handoff — FIRERPA, Fire OS, and ownership audit

Date: 2026-07-24

This is the public handoff for the next AI session. It is intentionally
self-contained: the next AI must not need `site-private` or this session's
conversation to recover the state.

## First action in the next session

Prompt the operator with the unresolved items in **Loose ends and operator
prompts** before implementing anything. Do not silently choose an ownership
boundary, start the MCP bridge, publish a Shizuku release, or retest p7a with an
unannounced FIRERPA binary.

Also report this worktree warning immediately:

- The local Shizuku checkout has a pre-existing dirty nested `api` submodule.
  Preserve it. Inspect `git diff -- api` before any cleanup; never reset or
  clean that submodule without explicit operator direction.
- The fork's `master` is intentionally ahead of upstream `origin/master`.
  Compare the fork remote with the upstream remote before calling this drift.

## Completed and merged

- stayturgid PR [#52](https://github.com/djbclark/stayturgid/pull/52):
  inventory-derived FIRERPA policy, control-node ADB recovery, Fire OS AppOps
  reconciliation, explicit Shizuku receiver targeting, and just-recipe host
  propagation.
- stayturgid PR [#53](https://github.com/djbclark/stayturgid/pull/53): bounded
  five-minute FIRERPA readiness window for slow Fire HD 8 startup.
- site-djbclark PR [#2](https://github.com/djbclark/site-djbclark/pull/2):
  p7a incompatible-runtime policy and hd8 recovery mode.
- Shizuku PR [#1](https://github.com/djbclark/Shizuku/pull/1): Fire OS
  notification-resource and native-library packaging fixes.
- The ownership inventory is summarized publicly in issue
  [#50](https://github.com/djbclark/stayturgid/issues/50); its seven operator
  decisions are repeated below so this handoff does not depend on a private
  repository.

All required CI/security checks and post-merge targeted checks passed. There
are no open PRs in stayturgid, site-djbclark, or the Shizuku fork.

## Verified device state

- s24: FIRERPA and Shizuku healthy.
- hd8: FIRERPA 10.0, FIRERPA SSH, and Shizuku healthy.
- p7a: Shizuku healthy; FIRERPA intentionally down because the current closed
  runtime exits with `unsupported sdk` on API 37.

Fire HD 8 startup is split across pre-login and post-login phases and can take
about five minutes to settle. The monitor now waits up to that bounded period.

A no-touch reboot test established that Fire OS clears classic TCP ADB and
wireless-debugging state across reboot. No reliable non-root self-bootstrap path
was found. USB/ADB or another already-running control channel is still required
for recovery.

The `adb_enabled=0` then `=1` experiment is unsafe: the first write killed the
only shell before the second command could run. Do not repeat it without an
explicit recovery plan.

## FIRERPA conclusions

- hd8 is binary-compatible with the current official v10 arm64 server. Its
  failure mode was lifecycle/transport, not a need for a rebuilt closed server.
- p7a is genuinely incompatible with the current server. The only rebuild
  request opened is [firerpa/lamda#147](https://github.com/firerpa/lamda/issues/147).
  Upstream said a future version will support Android 17/16KB page size; retest
  only after a concrete release exists.
- The release20 Shizuku APK was built and installed on hd8, but was not tagged
  or published through the normal distribution path.

## Loose ends and operator prompts

Prompt these in this order:

1. **Issue #50 ownership decisions:** dashboard ownership; Eternal Terminal/SSH
   CA; CFEngine retention; VLM site-versus-private ownership; generic app
   defaults versus site catalog; public research provenance; and generic
   peer-help protocol versus site-only feature.
2. **Shizuku release distribution:** decide whether release20 should receive a
   tag/GitHub release and be added to the normal APK/Obtainium path.
3. **p7a FIRERPA:** wait for a compatible upstream release, then retest and
   update the inventory classification.
4. **F1 FIRERPA MCP bridge (#46):** implementation awaits operator approval and
   the consent-surface choice (local dialog/notifications first versus MCP
   elicitation).
5. **Observability:** [#44](https://github.com/djbclark/stayturgid/issues/44)
   (OpenObserve↔Vector 401) blocks [#47](https://github.com/djbclark/stayturgid/issues/47)
   (Grafana/portal follow-ons).
6. **K1 residuals:** [#43](https://github.com/djbclark/stayturgid/issues/43)
   and [#45](https://github.com/djbclark/stayturgid/issues/45) still need
   native-agent cutover verification, soak evidence, and signed-release
   decisions.
7. **Stale backlog:** triage H1/H3, B63/B64, T2/T4, and settings issues
   #41/#42/#16; several may be latent or superseded by K1.
8. **Codex memory ownership:** the live `~/.codex` entries are now symlinks,
   with durable memory/config in `site-private` and generated runtime state in
   its ignored `.codex-runtime/`. Decide which historical project-specific
   notes should be promoted into `stayturgid` or `site-djbclark` documents;
   do not leave new durable product/site facts only in Codex memory.

## Next-session hygiene

At start, inspect all four worktrees with `git status --short --branch`, verify
the active remotes, and read this handoff plus `docs/STATUS.md`. Preserve the
dirty Shizuku `api` submodule. Confirm the operator has seen every prompt above
(including the Codex-memory ownership item) before starting new implementation;
do not merge or publish anything until the applicable decision is answered and
the relevant checks are green.
