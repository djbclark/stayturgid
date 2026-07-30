# Handoff: site-sync portable paths (Agent 2)

Date: 2026-07-28
Issue: stayturgid#100

## Work Completed

- Fixed `site_sync.py` to emit the portable `${OPS_ROOT:-/Users/djbclark/ops}/...` form for `site_dir` and `product_root` in Jinja contexts by default, allowing it to correctly generate `provider.yaml` and `stayturgid_actions.yaml` paths regardless of the sync execution directory (worktree or not).
- Made `_make_product_file_filter` accept real `Path` objects, decoupling the real lookup path from the portable strings passed to template bodies.
- Tested `just site-sync` successfully within the worktree to demonstrate it no longer bakes absolute worktree paths into the generated files.
- Implemented a drift guard in `site-djbclark/bin/registry_lint.py` that specifically inspects the two path-bearing artifacts and exits with code 2 if it finds any line starting with `cd /` or `path: /` (enforcing the `${OPS_ROOT...}` prefix).
- Verified `just lint` correctly executes and tests the drift guard.
- Opened PRs against `stayturgid` and `site-djbclark`.

## Next Steps

- Review and merge PRs.
- Once deployed, `~/.config/djbclark/olivetin/config.yaml` will be re-synced via `site-serverapps`/`site-sync` against `~/ops` to correctly point to the `${OPS_ROOT}`-based path instead of the legacy `brew-pinning` path.
- The `~/src/ops-worktrees/brew-pinning/` directory can then be safely removed by the operator.
