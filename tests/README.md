# stayturgid tests

Three equivalent entry points (they call the same scripts — overlap is intentional):

| Way | Tier (a) code only | Tier (b) no device | Tier (c) device, read-only |
|-----|--------------------|--------------------|----------------------------|
| **GNU** | `./configure && make check` | `make test` (= a+b) | `make verify` · `make dryrun` |
| **Ansible-standard** | `ansible-playbook … --syntax-check` (inside `make check`) | module test via `ansible localhost` (inside `make test`) | `ansible-playbook … --check --diff` (= `make dryrun`) |
| **Idiomatic (TAP shell harness)** | `tests/run.sh code` | `tests/run.sh unit` / `local` | `tests/run.sh device [--ansible-check] [host…]` |

- **Tier (a)** catches "different bash/python/node/ansible version breaks parsing" —
  `bash -n`, `py_compile`, `node --check`, JSON/plist validation, playbook syntax
  check, plus shellcheck/ansible-lint/yamllint when installed (`make lint`).
- **Tier (b)** runs the Termux scripts in a sandbox (stubbed `termux-*`, `adb`,
  `pgrep`, `flock`; `HOME`/`PREFIX`/`STAYTURGID_SD` redirected), the AutoJs6 log
  parser under node with a `files{}` shim, and the `termux_pkg` module through
  `ansible localhost` against a fake Termux prefix. Most cases are regression
  tests for CODE-REVIEW.md findings (H1, M1–M8, L12…).
- **Tier (c)** is strictly read-only over SSH: sshd/boot-loop/bridge liveness,
  privileged 5555 shell, watchdog log freshness, battery readability, and
  deployed-script drift vs the repo (drift reports as TAP `# TODO`, not
  failure). `--ansible-check` adds the Ansible dry run. It never invokes the
  self-heal — that's `mac/tests/run.sh device --heal` (ops, not test).

Output is TAP (Test Anything Protocol): `ok N - …` / `not ok N - …`,
plan `1..N`; `# SKIP` for missing tools, `# TODO` for expected failures.

## Project conventions (enforced/assumed by the tests)

- **Exit codes:** `0` success · `1` failure (repair: subsystem still down) ·
  `2` usage error · `75` (EX_TEMPFAIL) presence gate deferred/paused ·
  `130` interrupted (SIGINT/SIGTERM traps in multi-step Mac scripts).
- **Log lines:** `YYYY-MM-DD HH:MM:SS [component] message` (local time);
  logs are bounded (repair trims at >1000 lines to 500, Mac scripts tail -1000).
- **Process liveness:** pidfiles, never `pgrep -f <name>` — on Termux procps
  the pattern matches the caller's own cmdline (CODE-REVIEW.md H2).
- **Never assume the user's default shell.** macOS ships zsh; Termux users may
  switch to fish/zsh (zsh is NOT installed on Termux by default — `pkg install
  zsh` if genuinely needed). Every script declares bash in its shebang, and
  remote commands go to an explicit interpreter — `ssh host 'bash -s'` with a
  heredoc or stdin pipe — never through the login shell. `printf %q` output is
  bash syntax: only feed it to bash.
- **Cleanup traps:** anything that changes screen state (battery alarm)
  restores it on INT/TERM.
- **Non-destructive by default:** device tests read; only deploy scripts write.
