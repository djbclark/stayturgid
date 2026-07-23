# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones
across reboots. Generic example fleet hosts (`oneui-device`, `stock-android-device`,
`fireos-device`) live in `ansible/inventory/hosts.yml.example`; live inventory
belongs in a private site overlay (see
[multi-site-topology.md](docs/architecture/multi-site-topology.md) §4).

## Quick start

```bash
cd ~/ops/stayturgid && git fetch origin --prune && git pull --ff-only origin master
just health && just firerpa-health
```

## Key commands

| Command                                      | Purpose                                                                                                                                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `just dotenv-lint`                           | .env file lint check (dotenv-linter)                                                                                                                  |
| `just --set hosts oneui-device deploy`       | Full fleet deploy                                                                                                                                     |
| `just --set hosts oneui-device deploy-check` | Dry-run deploy                                                                                                                                        |
| `just --set hosts oneui-device verify`       | Device tier checks                                                                                                                                    |
| `just --set hosts oneui-device verify-drift` | Ansible-based drift detect                                                                                                                            |
| `just --set hosts oneui-device verify-heal`  | Verify + auto-heal                                                                                                                                    |
| `just health`                                | Fleet health summary + device error log                                                                                                               |
| `just errors`                                | Show recent device errors (7 days)                                                                                                                    |
| `just firerpa-health`                        | FIRERPA fleet health                                                                                                                                  |
| `just --set hosts oneui-device firerpa-heal` | Repair via FIRERPA gRPC                                                                                                                               |
| `just test`                                  | Code-only tests (includes healing coverage check)                                                                                                     |
| `just deploy-mac`                            | Mac workstation (brew, launchd)                                                                                                                       |
| `just ca-status`                             | SSH CA status/fingerprints                                                                                                                            |
| `just cf-run [HOSTS=oneui-device]`           | SSH-based CFEngine repair (replaces cf-runagent)                                                                                                      |
| `just opencode-web-status`                   | OpenCode web UI status                                                                                                                                |
| `just hermes-status`                         | Hermes worktree status                                                                                                                                |
| `just vlm-check`                             | Check VLM server + cloud                                                                                                                              |
| `just landing-status`                        | Network landing page status                                                                                                                           |
| `just web-health`                            | Full web audit: html-validate + lychee + lighthouse + pa11y + puppeteer + vnu (requires :4097)                                                        |
| `just pa11y`                                 | Accessibility audit on running dashboard                                                                                                              |
| `just puppeteer`                             | Rendered-DOM check (visible HTML-as-text, missing JS) on running dashboard                                                                            |
| `just vnu`                                   | W3C Nu HTML Checker on rendered pages (requires :4097)                                                                                                |
| `just lighthouse`                            | Full-page Lighthouse audit (requires Chrome/Chromium on PATH)                                                                                         |
| `just secretspec-check`                      | Verify all required secrets are set                                                                                                                   |
| `just ruff`                                  | Python lint + format check (ruff)                                                                                                                     |
| `just biome`                                 | JavaScript/CSS lint + format check (Biome)                                                                                                            |
| `just shfmt`                                 | Shell script format check (shfmt)                                                                                                                     |
| `just markdownlint`                          | Markdown lint check                                                                                                                                   |
| `just prettier`                              | Markdown/HTML/CSS/TOML/INI format check (prettier)                                                                                                    |
| `just typos`                                 | Source-code spelling check                                                                                                                            |
| `just lint`                                  | All linters (shellcheck, ansible-lint, yamllint, ruff, typos, biome, shfmt, markdownlint, prettier, …)                                                |
| `just lint-offline`                          | Same as lint but skip dashboard-dependent checks (lychee, vnu, pa11y, puppeteer)                                                                      |
| `just check`                                 | Syntax/import checks + TS/JS mapping (`check-ts`) + ruff + typos + biome + shfmt + justfile fmt + markdownlint + prettier + html-validate + stylelint |
| `just build-ts`                              | Compile `device/autojs6`/`tests/js`/`just/tools`/`docs/research` `.ts` → `.js` (tsc + Biome format + `// @generated` header)                          |
| `just validate-identity`                     | Hard-fail if production identity leaks outside the active inventory                                                                                   |

## Environment

- **Orchestration:** `just` (command runner, replaces `make`). The Makefile was migrated to a `justfile` in July 2026. Install: `brew install just`. Run `just --list` to see all targets or `just` for categorized help.
- **Mac shell:** `/bin/bash` (dotfiles: `~/.bash_profile`, `~/.bashrc`)
- **FIRERPA venv:** Python 3.12 at `~/.venv-stayturgid-firerpa` — `source ~/.venv-stayturgid-firerpa/bin/activate`
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
- **OpenCode web:** site-local service (see site overlay / landing); not a public fixed IP
- **Secrets:** managed via `secretspec` (`brew install secretspec`). Spec at `secretspec.toml` (project root). All secrets defined there; run `just secretspec-check` before deploys.
- **Site inventory:** resolved via `ANSIBLE_CONFIG`, `STAYTURGID_SITE_DIR`, or a single discovered `site-*` checkout under `OPS_ROOT` (default `~/ops`); see `control/lib/ansible_context.py`

## Example fleet (generic — not a live site)

| Device               | Tailscale  | USB Serial           | SSH                        |
| -------------------- | ---------- | -------------------- | -------------------------- |
| oneui-device         | 100.0.0.11 | EXAMPLE-SERIAL-ONEUI | `ssh oneui-device`         |
| stock-android-device | 100.0.0.12 | EXAMPLE-SERIAL-STOCK | `ssh stock-android-device` |
| fireos-device        | 100.0.0.13 | EXAMPLE-SERIAL-FIRE  | `ssh fireos-device`        |

## Adding a launchd service

See [docs/adding-a-launchd-service.md](docs/adding-a-launchd-service.md) — two
paths: `control_node` role for fleet-wide agents, `site_agents` role for
per-site agents.

## Conventions

- Use bash (not zsh). Termux has no zsh by default.
- Announce before device interaction: 🚨📱🚨 USING — host — why — ~N min
- Screen control requires `ScreenControlSession` (fail-closed).
- Accessibility is detection-only. Never `settings put` accessibility services automatically.
- Logging uses syslog severity levels (EMERG..DEBUG). See `control/lib/logging.py`.
- Every desired state gets a unique ID in `tests/healing_registry.json`. Pre-flight
  `just test` fails if a `must_cover` ID is missing from any healing mechanism.
- Follow multi-agent protocol at bottom of AGENTS.md (fetch-pull before edits).
- See full policies at `docs/rules/*.md`

## Handoff

Current state: `docs/STATUS.md` (fleet/workstream snapshot, known gotchas, operator queue)
Coding and completion rules: `docs/coding-rules.md`
Open work: [GitHub issues](https://github.com/djbclark/stayturgid/issues) (discrete items) + `docs/options.md` (strategic/deferred tracks)
Session history: `docs/operations/sessions/session-*.md`
Superseded plans and old sessions: `docs/archive/`

## Multi-Agent Protocol

Before any edit: `git fetch origin --prune && git pull --ff-only origin master`.
Always commit and push when done. Leave no uncommitted changes.
If `git pull` fails with a merge conflict, STOP and report it.
Verify changes are yours before editing — if a file has unrelated modifications
from another agent, leave it alone and report it.
