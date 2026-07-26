# stayturgid

> **AI agents (any vendor):** this file is the entry point — the AGENTS.md
> convention that coding agents from multiple vendors check first. Project
> overview for humans: [README.md](README.md). Current dated
> state — fleet health, active blockers, operator-action queue — lives in
> [docs/STATUS.md](docs/STATUS.md); the most load-bearing parts are inlined
> below so you have them even if you stop at this file. See "Where
> documentation goes" further down for what belongs where.

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones
across reboots. Generic example fleet hosts (`oneui-device`, `stock-android-device`,
`fireos-device`) live in `ansible/inventory/hosts.yml.example`; live inventory
belongs in a private site overlay (see
[multi-site-topology.md](docs/architecture/multi-site-topology.md) §4).

## Current state (condensed — full/current version: [docs/STATUS.md](docs/STATUS.md))

**This section only lists active blockers and operator-gated items — it is
not the full work menu.** Before selecting new work, check
[docs/options.md](docs/options.md) (strategic/deferred tracks) and the
[open GitHub issues](https://github.com/djbclark/stayturgid/issues) (discrete
bugs/follow-ups) for what's actually available to pick up next.

**Active blockers:**

- K1 native-agent cutover (2026-07-22) is **not fully verified** — AutoJs6
  removal was live-checked 2026-07-25 (the cutover's claim was false; fixed
  fleet-wide now) but the forced `CLOSED_NO_SHELL` soak still hasn't run.
  Tracked in [#43](https://github.com/djbclark/stayturgid/issues/43) and
  [#45](https://github.com/djbclark/stayturgid/issues/45).
- OpenObserve↔Vector auth **fixed 2026-07-25**, pending 24h clean-log
  verification before closing. Tracked in
  [#44](https://github.com/djbclark/stayturgid/issues/44) — see
  [docs/STATUS.md](docs/STATUS.md) for the root cause.

**Operator-action queue (things only a human can do):**

1. Physically check offline fleet devices (Tailscale unreachable).
2. Decide the F1 consent-surface phasing question ([#46](https://github.com/djbclark/stayturgid/issues/46)).
3. Remove (or authorize removal of) a stray `~/stayturgid` file — the real repo is `${OPS_ROOT:-~/ops}/stayturgid`.

If any of this looks stale, trust `docs/STATUS.md` and `git log` over this
section — it's a snapshot, not updated every commit.

## Quick start

```bash
cd ${OPS_ROOT:-~/ops}/stayturgid && git fetch origin --prune && git pull --ff-only origin master
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
- **Site inventory:** resolved via `ANSIBLE_CONFIG`, `STAYTURGID_SITE_DIR`, `OPS_ROOT/.mysite`, or one discovered `site-*` checkout under `OPS_ROOT` (default `${OPS_ROOT:-~/ops}`), excluding `site-private`; see `control/lib/site_discovery.py` and `control/lib/ansible_context.py`. Commands print the selected path and precedence source. A missing private companion is created at `STAYTURGID_PRIVATE_DIR` (default `OPS_ROOT/site-private`) without Git or secret initialization.

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

## Memory & documentation policy (this repo's slice)

There is **no single canonical policy copy**. Each of the three `${OPS_ROOT:-~/ops}`
siblings owns the rules that apply to **it**, in that repo's `AGENTS.md`, and
**must** point at the other two so a full picture requires all three. Cross-repo
links use absolute
`https://github.com/<owner>/<repo>/blob/master/...` URLs (GitHub's renderer
cannot follow relative links across repos); also give the filesystem path
(`${OPS_ROOT:-~/ops}/...`) for local use. Same-repo links stay relative.

**This repo (stayturgid) owns:**

- Durable facts, conventions, and gotchas about developing or operating
  **stayturgid** (code, fleet, CI/review) → commit here under `docs/` (often
  [`docs/notes/lessons-learned.md`](docs/notes/lessons-learned.md) or an
  existing durable doc), **not** into tool-private stores under `~` (Claude
  memory under `~/.claude/`, Cursor/Aider/Copilot caches, etc.).
- **Never** commit passwords or secrets. IPs, hostnames, and machine names are
  fine in public docs when the doc's audience needs them.

**Optional additional rules (not required of every stayturgid user):**

- Non-sensitive site practice others might still benefit from → that operator's
  `${OPS_ROOT:-~/ops}/site-<name>` (example for this machine:
  [`${OPS_ROOT:-~/ops}/site-djbclark/AGENTS.md`](https://github.com/djbclark/site-djbclark/blob/master/AGENTS.md)
  — private repo; expect 404 if you are not the owner).
- Private / Mac-wide / not-for-public extras →
  [`${OPS_ROOT:-~/ops}/site-private/AGENTS.md`](https://github.com/djbclark/site-private/blob/master/AGENTS.md)
  (always private; expect 404 for other readers).

**Symlinks (filesystem) are reserved for** root-level `~` agent/vendor files
(`~/AGENTS.md`, `~/CLAUDE.md`, and any other root-level vendor-specific agent
instruction files), tool memory dirs under `~/.claude/.../memory`, and
optionally `${OPS_ROOT:-~/ops}/.mysite` → `site-<name>` (supported local convenience).
Do **not** use in-repo symlinks to reach sibling repos — use path + https links
in prose instead.

Topology background:
[multi-site-topology.md §4.10](docs/architecture/multi-site-topology.md#410-the-third-repo-opssite-private).

## Where documentation goes

Canonical map — read this before creating a new doc or wondering where
something lives. [`README.md`](README.md) and [`docs/STATUS.md`](docs/STATUS.md)
both point back here rather than duplicating it.

| Location                                                         | What goes here                                                                                                                              | Update cadence                   |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| [`README.md`](README.md)                                         | Human-facing project overview, module list, quick-start                                                                                     | Rare                             |
| `AGENTS.md` (this file)                                          | Durable coding-agent entry point: conventions, commands, protocols, this doc map, **this repo's slice of the three-way memory/docs policy** | Rare                             |
| [`docs/STATUS.md`](docs/STATUS.md)                               | Dated snapshot: fleet health, active workstreams, operator-action queue, known gotchas                                                      | Every session that changes state |
| [`docs/coding-rules.md`](docs/coding-rules.md)                   | Durable implementation, safety, testing, Git, and completion rules                                                                          | Rare                             |
| [`docs/rules/`](docs/rules/)                                     | Always-on agent policies (self-heal, screen-control, GitHub-issues hygiene)                                                                 | Rare                             |
| [`docs/notes/lessons-learned.md`](docs/notes/lessons-learned.md) | Session-learned gotchas/conventions, narrower than coding-rules.md/docs/rules/                                                              | As lessons come up               |
| [`docs/options.md`](docs/options.md)                             | Strategic/deferred work tracks with stable IDs                                                                                              | As tracks open/close             |
| [GitHub issues](https://github.com/djbclark/stayturgid/issues)   | Discrete bugs, ops follow-ups, soak verifications                                                                                           | As they arise                    |
| [`docs/operations/sessions/`](docs/operations/sessions/)         | Session-by-session history and handoffs                                                                                                     | Every session                    |
| [`docs/archive/`](docs/archive/)                                 | Superseded plans and old sessions — historical record only, never treat as current                                                          | Append-only                      |
| `${OPS_ROOT:-~/ops}/site-<name>` (sibling repo)                               | One operator's site overlay — inventory, credentials-adjacent config, **that site's slice of memory/docs policy**                           | As the site changes              |
| `${OPS_ROOT:-~/ops}/site-private` (sibling repo)                              | Private/generic companion — **its** slice of memory/docs policy + Claude generic memory                                                     | As generic notes come up         |

Do not put durable rules in STATUS.md, and do not put dated/volatile state in
AGENTS.md or coding-rules.md — that's the split this table encodes.

## Multi-Agent Protocol

Before any edit: `git fetch origin --prune && git pull --ff-only origin master`.
Always commit and push when done. Leave no uncommitted changes.
If `git pull` fails with a merge conflict, STOP and report it.
Verify changes are yours before editing — if a file has unrelated modifications
from another agent, leave it alone and report it.
