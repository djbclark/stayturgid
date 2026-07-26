# Session 2026-07-26 — Ship coordinated ops-v1.0.3

## Objective

Take the merged deploy-convergence work from open feature PRs through the
coordinated three-repo release gate to a deployed, verified `ops-v1.0.3` on all
three `~/ops` checkouts — under explicit operator confirmation at each gate,
with no development edits or raw pulls in `~/ops`.

## What happened

### Feature merges (operator-confirmed)

- Merged the paired feature PRs with merge commits and deleted their branches:
  - stayturgid **#72** "Make normal fleet deploy converge desired state" →
    merge `48f7dd7`.
  - site-djbclark **#17** "Declare native-agent peer desired state" →
    merge `66d8565`.
- Verified both `master` branches contained every intended feature commit,
  removed the `deploy-convergence/` task workspace and its local branches, and
  pruned the deleted remotes.

### Coordinated ops-v1.0.3 cut (operator-confirmed, separate gate)

- Confirmed `1.0.3` as the next version (all three repos previously at
  `ops-v1.0.2` Latest) and held the release claim
  (`version=1.0.3 operation=cut`).
- Created a `release-ops-v1.0.3/` task workspace with worktrees for all three
  repos branched from the freshly merged `origin/master`.
- Bumped `ops-release.json` `1.0.2` → `1.0.3` (one line each; schema/suite/
  version validated) and opened three version-bump PRs:
  - stayturgid **#73** → merge `3017406`
  - site-djbclark **#18** → merge `79e0d35`
  - site-private **#8** → merge `5f2fff3`
- All PR checks green (stayturgid `test` 6m19s, Semgrep, CodeRabbit; site-djbclark
  Semgrep + CodeRabbit; site-private CodeRabbit). Merged all three after the
  second explicit operator confirmation.

### Tag, release, deploy (operator-confirmed)

- Pushed matching annotated `ops-v1.0.3` tags on each `master` tip
  (`3017406` / `79e0d35` / `5f2fff3`), matching the prior plain-annotated tag
  convention (unsigned; `tag.gpgsign` unset).
- Created three stable, non-draft, non-prerelease GitHub Releases titled
  "djbclark ops 1.0.3"; each repo's `releases/latest` API resolves to
  `ops-v1.0.3`.
- Deployed via `just ops-release-deploy 1.0.3` from the sanctioned
  `~/ops/site-djbclark` path (preflight `ops-release-check` green first). No
  raw `git pull` and no dev edits in `~/ops`.
- Ended the release claim (`claim: none`) and removed the
  `release-ops-v1.0.3/` task workspace.

## Verification

- `just ops-release-status`: stayturgid / site-djbclark / site-private all
  `ops-v1.0.3`.
- Each `~/ops` checkout on `master`, at exact tag `ops-v1.0.3`, clean working
  tree (site-private memory + ignored `codex/config.toml` invariants preserved).
- Release-worktree local checks: site-djbclark `just lint` green (registry-lint
  and 19 unittests). stayturgid `just check` 18/21 green in the fresh worktree;
  the 3 not-run (pytest / ansible-lint / prettier) require per-worktree
  `.venv-test` / `node_modules` absent in a freshly created worktree — not
  regressions (CI ran them clean; identical tree passed all 21 on the feature
  branch). Tracked as follow-up.

## Follow-ups

- **stayturgid #74** — fresh `ops-worktrees` worktrees lack per-worktree
  `.venv-test` / `node_modules`, so `just check` reports false `not ok` for
  pytest / ansible-lint / prettier until manual setup. Proposed a
  `just worktree-setup` bootstrap recipe, an actionable skip/hint in
  `just check`, and a documented one-command step in the ops-worktrees README.

## State at handoff

- Suite fully published and live at `ops-v1.0.3` (tags + stable Releases in all
  three repos; all `~/ops` checkouts deployed and clean).
- No open release/feature branches from this work; both task workspaces
  removed. Release claim released.
- Normal future fleet deploys converge native-agent version/service, peer
  assignments, mutually exclusive APK variants, checksums, and headless
  Obtainium config without ad-hoc provisioning.
