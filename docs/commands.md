# Command reference

Moved out of `AGENTS.md` on 2026-08-24: it is lookup material, not
instruction, and `AGENTS.md` loads into context on every session while
this is read only when needed.

## Key commands

**Targeting one host.** Use the positional form (`just deploy <host>`) or the
environment form (`hosts=<host> just deploy`) exactly as shown per recipe below.
Never use `just --set hosts <h> <recipe>` or `just hosts=<h> <recipe>`: most
recipes re-invoke a nested `just`, which does not see `--set` or command-line
overrides, so the run silently covers the whole fleet (issue #137 audit,
finding A1). Several hosts: `hosts="<h1> <h2>" just deploy`.

| Command                               | Purpose                                                                                                                                                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `just deploy oneui-device`            | Deploy one host (omit the host for the whole fleet); first runs site-sync and the vector serverapp, then commits & pushes only `generated/stayturgid/` in the site (off: `STAYTURGID_SITE_AUTOCOMMIT=0`) |
| `just deploy-check oneui-device`      | Dry-run deploy                                                                                                                                                                                           |
| `hosts=oneui-device just verify`      | Device tier checks (env form only: `verify` ignores a positional host)                                                                                                                                   |
| `just verify-drift oneui-device`      | Ansible-based drift detect                                                                                                                                                                               |
| `hosts=oneui-device just verify-heal` | Verify + auto-heal (env form only: `verify-heal` ignores a positional host)                                                                                                                              |
| `just health`                         | Fleet health summary + device error log                                                                                                                                                                  |
| `just errors`                         | Show recent device errors (7 days)                                                                                                                                                                       |
| `just firerpa-health`                 | FIRERPA fleet health                                                                                                                                                                                     |
| `just firerpa-heal oneui-device`      | Repair via FIRERPA gRPC (positional only: the env form heals every host)                                                                                                                                 |
| `just test`                           | Code-only tests (includes healing coverage check)                                                                                                                                                        |
| `just deploy-mac`                     | Mac workstation (brew, launchd)                                                                                                                                                                          |
| `just ca-status`                      | SSH CA status/fingerprints                                                                                                                                                                               |
| `hosts=oneui-device just cf-run`      | SSH-based manual CFEngine repair (cf-runagent remains the automatic Tier 3a)                                                                                                                             |
| `just opencode-web-status`            | OpenCode web UI status                                                                                                                                                                                   |
| `just hermes-status`                  | Quick gateway status (PID, platform state)                                                                                                                                                               |
| `just landing-status`                 | Network landing page status                                                                                                                                                                              |
| `just web-health`                     | Full web audit: html-validate + lychee + lighthouse + pa11y + puppeteer + vnu (requires :4097)                                                                                                           |
| `just pa11y`                          | Accessibility audit on running dashboard                                                                                                                                                                 |
| `just puppeteer`                      | Rendered-DOM check (visible HTML-as-text, missing JS) on running dashboard                                                                                                                               |
| `just vnu`                            | W3C Nu HTML Checker on rendered pages (requires :4097)                                                                                                                                                   |
| `just lighthouse`                     | Full-page Lighthouse audit (requires Chrome/Chromium on PATH)                                                                                                                                            |
| `just secretspec-check`               | Verify all required secrets are set                                                                                                                                                                      |
| `just ruff`                           | Python lint + format check (ruff)                                                                                                                                                                        |
| `just biome`                          | JavaScript/CSS lint + format check (Biome)                                                                                                                                                               |
| `just shfmt`                          | Shell script format check (shfmt)                                                                                                                                                                        |
| `just markdownlint`                   | Markdown lint check                                                                                                                                                                                      |
| `just prettier`                       | Markdown/HTML/CSS/TOML/INI format check (prettier)                                                                                                                                                       |
| `just typos`                          | Source-code spelling check                                                                                                                                                                               |
| `just lint`                           | All linters (shellcheck, ansible-lint, yamllint, ruff, typos, biome, shfmt, markdownlint, prettier, dotenv-linter, …)                                                                                    |
| `just lint-offline`                   | Same as lint but skip dashboard-dependent checks (lychee, vnu, pa11y, puppeteer)                                                                                                                         |
| `just check`                          | Syntax/import checks + TS/JS mapping (`check-ts`) + ruff + typos + biome + shfmt + justfile fmt + markdownlint + prettier + html-validate + stylelint                                                    |
| `just build-ts`                       | Compile `just/tools`/`docs/research` `.ts` → `.js` (tsc + Biome format + `// @generated` header)                                                                                                         |
| `just validate-identity`              | Hard-fail if production identity leaks outside the active inventory                                                                                                                                      |
