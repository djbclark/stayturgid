# Handoff — 2026-07-26 VLM cleanup and coordinated release gate

This work restores the public quality gate after the VLM/UI-TARS retirement
and prepares the first coordinated, versioned release of the three ops
repositories.

## Outcome

- Removed the remaining active VLM/UI-TARS probes, recipes, secrets, and
  current-architecture claims without reintroducing screen automation.
- Dropped the orphaned `PLAY-AUTOUPDATE-OFF` healing state, resolving
  [#68](https://github.com/djbclark/stayturgid/issues/68).
- Added a regression test that rejects literal script paths in imported
  justfiles when the target has been deleted.
- Repaired repository-wide gate drift found during the same validation pass:
  Markdown/Ruff formatting, Entangled template parity, the Tailscale
  uid-2000-shell test, and `ansible-test` interpreter selection.
- Moved the site-specific hostname audit out of this public repository and
  into `site-djbclark`; `just validate-identity` is green again.
- Added `ops-release.json` at version `1.0.0`. The matching source branches in
  `site-djbclark` and `site-private` define the coordinated release and deploy
  policy.

## Release contract

All three repositories publish the same annotated
`ops-vMAJOR.MINOR.PATCH` tag and stable GitHub release. The deploy checkouts
under `~/ops` may advance only after all three tags, manifests, reachable
commits, and GitHub releases pass a single preflight. The gate then
fast-forwards all three checkouts to the captured release commits.

`site-private` may remain ahead of its release by `memory/` commits only. Its
memory-sync path is fail-closed: any unreleased code or configuration on
`origin/master` blocks the sync.

The existing `stayturgid/version.json` remains the independent device-agent
version; it is not the coordinated ops suite version.

## Verification

- `just check`: pass.
- `just test`: pass — 21 Tier-A checks, 133 shell/Node unit checks, 566 Python
  tests with one documented skip, and 109 Ansible collection tests.
- `just lint-offline`: pass, including mypy and 855 offline link checks.
- `just kt-check`: pass — Spotless, detekt, and debug/release unit tests.
- `pre-commit run --all-files`: pass, including Bandit, Semgrep, and gitleaks.
- Healing coverage: 28 states across 7 mechanisms.
- `just validate-identity`: pass.
- `site-djbclark`: seven release-gate unit tests and `just lint` pass.

## Operator-gated next steps

1. Review and merge the coordinated PRs in all three repositories.
2. Create and push the annotated `ops-v1.0.0` tag at each merged commit.
3. Publish a stable GitHub release for each tag.
4. Run the coordinated release preflight.
5. Bootstrap the existing deploy checkouts to `ops-v1.0.0`, then use only the
   release deployment command for later updates.

No source branch was merged, no tag or GitHub release was published, and no
deploy checkout was advanced in this session.
