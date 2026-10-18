# GitHub stayturgid-agent CI (ci/base)

Builds `device/native-agent` on free GitHub-hosted runners via `ci/base` +
`ci/run/**`, publishing unsigned APKs as GitHub prereleases
`agent-ci-<version>-<sha8>` (same naming as the Forgejo flow).

1. Workflow: `.github/workflows/agent-ci.yml` on `ci/base`
2. Wrapper: `scripts/github-ci-run [REF]`
3. Fetch/sign on the Mac: `just agent-ci-fetch` currently talks to Forgejo
   (`control/tools/native-agent/ci_fetch_sign.py`). Point it at GitHub releases
   on `djbclark/stayturgid` before deleting the Forgejo repo.
4. APKs are unsigned in CI; the release key never leaves the Mac.
