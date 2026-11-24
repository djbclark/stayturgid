# GitHub CI for stayturgid (ci/base)

CI for this repo runs on free GitHub-hosted runners through the orphan branch
`ci/base`, which holds only the overlay (workflows, wrapper, this note). The
wrapper builds a commit of target tree + overlay, force-pushes it to
`ci/run/<mode>-<slug>-<sha8>` and watches the run(s).

1. `scripts/github-ci-run [--no-wait] [--tests] [REF]`
   (REF defaults to HEAD; `just ci-run` calls it)
2. `--tests` (default): `.github/workflows/linux-ci.yml` runs `just test`: shell
   TAP unit tests, the pytest twins, ansible-test units, and the
   ruff/typos/biome/shfmt/justfile/markdown/prettier/html-validate/stylelint/identity
   checks, with tool versions pinned to the control node's.
3. `--agent` and `--all` are retired (2026-11-21). The agent is built, signed and
   published from master by `.github/workflows/agent-release.yml`; a branch build
   without publishing is `just agent-ci-run BRANCH`. The old `agent-ci.yml` ran
   Gradle beside a write-scoped token, so it was removed.
4. Not in CI, on purpose: device-tier tests (ADB, SSH, FireRPA), release
   signing, and the Mac control_node apply (launchd, Keychain).
