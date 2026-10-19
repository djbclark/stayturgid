# GitHub CI for stayturgid (ci/base)

CI for this repo runs on free GitHub-hosted runners through the orphan branch
`ci/base`, which holds only the overlay (workflows, wrapper, this note). The
wrapper builds a commit of target tree + overlay, force-pushes it to
`ci/run/<mode>-<slug>-<sha8>` and watches the run(s).

1. `scripts/github-ci-run [--no-wait] [--tests|--agent|--all] [REF]`
   (REF defaults to HEAD; `just agent-ci-run` calls it with `--agent`)
2. `--tests` (default): `.github/workflows/linux-ci.yml` runs `just test`: shell
   TAP unit tests, the pytest twins, ansible-test units, and the
   ruff/typos/biome/shfmt/justfile/markdown/prettier/html-validate/stylelint/identity
   checks, with tool versions pinned to the control node's.
3. `--agent`: `.github/workflows/agent-ci.yml` builds `device/native-agent`
   (Gradle test, detekt, unsigned release APK) and publishes the GitHub
   prerelease `agent-ci-<version>-<sha8>`.
4. `--all`: both.
5. On the Mac, `just agent-ci-fetch` downloads the APK and signs it with the
   release key, which never leaves the Mac.
6. Not in CI, on purpose: device-tier tests (ADB, SSH, FireRPA), release
   signing, and the Mac control_node apply (launchd, Keychain).
