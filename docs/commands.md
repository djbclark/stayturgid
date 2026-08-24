# Command reference

Moved out of `AGENTS.md` on 2026-08-24: it is lookup material, not
instruction, and `AGENTS.md` loads into context on every session while
this is read only when needed.

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
| `just build-ts`                              | Compile `just/tools`/`docs/research` `.ts` → `.js` (tsc + Biome format + `// @generated` header)                                                      |
| `just validate-identity`                     | Hard-fail if production identity leaks outside the active inventory                                                                                   |
