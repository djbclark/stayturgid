# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones across reboots. Fleet: s24, p7a, hd8 managed via Ansible over Tailscale.

## Quick start

```bash
cd ~/stayturgid && git fetch origin --prune && git pull --ff-only origin master
just health && just firerpa-health
```

## Key commands

| Command                             | Purpose                                                                                                                                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `just dotenv-lint`                  | .env file lint check (dotenv-linter)                                                                                                                                                                                                             |
| `just --set hosts s24 deploy`       | Full fleet deploy                                                                                                                                                                                                                                |
| `just --set hosts s24 deploy-check` | Dry-run deploy                                                                                                                                                                                                                                   |
| `just --set hosts s24 verify`       | Device tier checks                                                                                                                                                                                                                               |
| `just --set hosts s24 verify-drift` | Ansible-based drift detect                                                                                                                                                                                                                       |
| `just --set hosts s24 verify-heal`  | Verify + auto-heal                                                                                                                                                                                                                               |
| `just health`                       | Fleet health summary + device error log                                                                                                                                                                                                          |
| `just errors`                       | Show recent device errors (7 days)                                                                                                                                                                                                               |
| `just firerpa-health`               | FIRERPA fleet health                                                                                                                                                                                                                             |
| `just --set hosts s24 firerpa-heal` | Repair via FIRERPA gRPC                                                                                                                                                                                                                          |
| `just test`                         | Code-only tests (includes healing coverage check)                                                                                                                                                                                                |
| `just deploy-mac`                   | Mac workstation (brew, launchd)                                                                                                                                                                                                                  |
| `just ca-status`                    | SSH CA status/fingerprints                                                                                                                                                                                                                       |
| `just cf-run [HOSTS=s24]`           | SSH-based CFEngine repair (replaces cf-runagent)                                                                                                                                                                                                 |
| `just opencode-web-status`          | OpenCode web UI status                                                                                                                                                                                                                           |
| `just hermes-status`                | Hermes worktree status                                                                                                                                                                                                                           |
| `just vlm-check`                    | Check VLM server + cloud                                                                                                                                                                                                                         |
| `just landing-status`               | Network landing page status                                                                                                                                                                                                                      |
| `just web-health`                   | Full web audit: html-validate + lychee + lighthouse + pa11y + puppeteer + vnu (requires :4097)                                                                                                                                                   |
| `just pa11y`                        | Accessibility audit on running dashboard                                                                                                                                                                                                         |
| `just puppeteer`                    | Rendered-DOM check (visible HTML-as-text, missing JS) on running dashboard                                                                                                                                                                       |
| `just vnu`                          | W3C Nu HTML Checker on rendered pages (requires :4097)                                                                                                                                                                                           |
| `just lighthouse`                   | Full-page Lighthouse audit (requires Chrome/Chromium on PATH)                                                                                                                                                                                    |
| `just secretspec-check`             | Verify all required secrets are set                                                                                                                                                                                                              |
| `just ruff`                         | Python lint + format check (ruff)                                                                                                                                                                                                                |
| `just biome`                        | JavaScript/CSS lint + format check (Biome)                                                                                                                                                                                                       |
| `just shfmt`                        | Shell script format check (shfmt)                                                                                                                                                                                                                |
| `just markdownlint`                 | Markdown lint check                                                                                                                                                                                                                              |
| `just prettier`                     | Markdown/HTML/CSS/TOML/INI format check (prettier)                                                                                                                                                                                               |
| `just typos`                        | Source-code spelling check                                                                                                                                                                                                                       |
| `just lint`                         | All linters: shellcheck, ansible-lint (incl. examples), yamllint (incl. examples), ruff, typos, biome, shfmt, justfile fmt, markdownlint, prettier, dotenv-linter, caddy-fmt, pyinilint, html-validate, stylelint, lychee, vnu, pa11y, puppeteer |
| `just lint-offline`                 | Same as lint but skip dashboard-dependent checks (lychee, vnu, pa11y, puppeteer)                                                                                                                                                                 |
| `just check`                        | Syntax/import checks + ruff + typos + biome + shfmt + justfile fmt + markdownlint + prettier + html-validate + stylelint                                                                                                                         |

## Environment

- **Orchestration:** `just` (command runner, replaces `make`). The Makefile was migrated to a `justfile` in July 2026. Install: `brew install just`. Run `just --list` to see all targets or `just` for categorized help.
- **Mac shell:** `/bin/bash` (dotfiles: `~/.bash_profile`, `~/.bashrc`)
- **FIRERPA venv:** Python 3.12 at `/tmp/lamda-venv` — `source /tmp/lamda-venv/bin/activate`
- **Python tooling:** `uv` (package manager) + `ruff` (linter/formatter) — `brew install uv ruff`
- **JavaScript tooling:** `bun` (package manager) — `brew install oven-sh/bun/bun`; `biome` (linter/formatter) — `brew install biome`
- **Shell tooling:** `shellcheck` (linter) + `shfmt` (formatter) — `brew install shellcheck shfmt`
- **Markdown tooling:** `markdownlint` (linter) + `prettier` (formatter) — `brew install markdownlint-cli prettier`
- **Ansible tooling:** `ansible-lint` (linter) + `yamllint` (linter) — `uv tool install ansible-lint yamllint`
- **INI tooling:** `pyinilint` (linter) — `uv tool install pyinilint`
- **Web tooling:** `html-validate`, `stylelint`, `pa11y`, `puppeteer`, `vnu-jar` — `bun install` (devDependencies); `lychee` (link checker) — `brew install lychee`; `lighthouse` (full-page audit) — `npm install -g lighthouse` (requires Chrome)
- **Other linters:** `dotenv-linter` (.env) — `brew install dotenv-linter`; `caddy` (Caddyfile fmt) — `brew install caddy`
- **Git tooling:** `pre-commit` (hooks) + `typos` (spell check) — `brew install pre-commit typos-cli`; run `pre-commit install`
- **SSH CA:** `~/.ssh/stayturgid_ca` — `just ca-status`
- **OpenCode web:** http://100.113.53.87:4096
- **Secrets:** managed via `secretspec` (`brew install secretspec`). Spec at `secretspec.toml` (project root). All secrets defined there; run `just secretspec-check` before deploys.

## Fleet (s24, p7a, hd8)

| Device | Tailscale      | USB Serial       | SSH       |
| ------ | -------------- | ---------------- | --------- |
| s24    | 100.123.218.30 | RFCX219CHKA      | `ssh s24` |
| p7a    | 100.65.230.108 | 35261JEHN12374   | `ssh p7a` |
| hd8    | 100.124.55.39  | GN43T503430603PS | `ssh hd8` |

## Conventions

- Use bash (not zsh). Termux has no zsh by default.
- Announce before device interaction: 🚨📱🚨 USING — host — why — ~N min
- Screen control requires `ScreenControlSession` (fail-closed).
- Accessibility is detection-only. Never `settings put` accessibility services automatically.
- Logging uses syslog severity levels (EMERG..DEBUG). See `control/lib/logging.py`.
- Every desired state gets a unique ID in `tests/healing_registry.json`. Pre-flight
  `just test` fails if a `must_cover` ID is missing from any healing mechanism.
- Follow multi-agent protocol at bottom of AGENTS.md (fetch-pull before edits).
- See full policies at `.cursor/rules/*.md`

## Handoff

Full details: `docs/handoff.md` (cold-start, architecture, known issues)
Coding and completion rules: `docs/coding-rules.md`
Ordered current work: `docs/plans/outstanding-fix-priorities-2026-07-13.md`
Open item status: `docs/options.md`
Session history: `docs/history/session-*.md`

## Multi-Agent Protocol

Before any edit: `git fetch origin --prune && git pull --ff-only origin master`.
Always commit and push when done. Leave no uncommitted changes.
If `git pull` fails with a merge conflict, STOP and report it.
Verify changes are yours before editing — if a file has unrelated modifications
from another agent, leave it alone and report it.
