# Quality Toolchain

The standard toolchain used across stayturgid and derived projects. Every layer
(local edits, pre-commit hooks, CI) runs the same tools with the same configs.

## Architecture (N+1 pattern)

Every tool appears in four places — changing one means updating all four:

| Layer      | File                                                  | Purpose                                            |
| ---------- | ----------------------------------------------------- | -------------------------------------------------- |
| Manual     | `justfile`                                            | `just check` / `just lint` / `just format` recipes |
| Pre-commit | `.pre-commit-config.yaml`                             | Automatic gate on `git commit`                     |
| Config     | `pyproject.toml`, `package.json`, standalone dotfiles | Tool-specific settings                             |
| CI         | `.github/workflows/`                                  | Runs the same `just` recipes                       |

This intentionally duplicates command lines across justfile and pre-commit —
they must stay in sync, but the payoff is that `just check` matches `pre-commit`
exactly, and CI can be `just lint`.

## Tool Inventory

### Python (pyproject.toml dev deps)

| Tool         | Version  | Config                                     | What it checks                                   |
| ------------ | -------- | ------------------------------------------ | ------------------------------------------------ |
| **ruff**     | v0.15.21 | `pyproject.toml [tool.ruff]`               | Python lint (E/F/I/W) + deterministic formatting |
| **mypy**     | ≥1.19    | `pyproject.toml [tool.mypy]`               | Static type checking                             |
| **pytest**   | ≥8.0     | `pyproject.toml [tool.pytest.ini_options]` | Test runner                                      |
| **bandit**   | ≥1.7.9   | `pyproject.toml` (dev dep)                 | Python security linting                          |
| **yamllint** | ≥v1.35.1 | `.yamllint`                                | YAML syntax / style                              |

Ruff config (`[tool.ruff]`):

```toml
line-length = 120
target-version = "py312" # or "py311" for projects requiring 3.11

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["E501", "E402"]

[tool.ruff.format]
line-ending = "lf"
```

Mypy config (`[tool.mypy]`):

```toml
python_version = "3.12"       # match target-version
explicit_package_bases = true
ignore_missing_imports = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_unreachable = true
exclude = ['^\.venv/']        # or '.venv-test/' for stayturgid
```

### Node (package.json devDependencies, run via bunx)

| Tool                     | Version | Config                    | What it checks             |
| ------------------------ | ------- | ------------------------- | -------------------------- |
| **prettier**             | ^3.8    | `.prettierrc` or CLI args | Markdown + TOML formatting |
| **prettier-plugin-toml** | ^2.0    | same                      | TOML support for prettier  |
| **markdownlint-cli**     | ^0.48   | `.markdownlint.json`      | Markdown style rules       |

Markdownlint config (`.markdownlint.json`):

```json
{
  "default": true,
  "MD013": false,
  "MD024": false,
  "MD028": false,
  "MD029": false,
  "MD031": false,
  "MD033": false,
  "MD034": false,
  "MD036": false,
  "MD038": false,
  "MD040": false,
  "MD041": false,
  "MD046": false,
  "MD056": false
}
```

### System (installed on PATH, not in venv or node_modules)

| Tool         | Version | Config                   | What it checks              |
| ------------ | ------- | ------------------------ | --------------------------- |
| **typos**    | v1.48.0 | `.typos.toml` (optional) | Source-code spelling        |
| **semgrep**  | latest  | CLI `--config auto`      | Pattern-based security scan |
| **gitleaks** | v8.18.4 | none (default rules)     | Secret-leak detection       |

Optional `.typos.toml` (only needed for project-specific false positives):

```toml
[default.extend-words]
myterm = "myterm" # suppress typos flag
```

Yamllint config (`.yamllint`):

```yaml
extends: default
rules:
  comments: { min-spaces-from-content: 1 }
  comments-indentation: false
  octal-values: { forbid-implicit-octal: true, forbid-explicit-octal: true }
  braces: { max-spaces-inside: 1 }
  line-length: { max: 160 }
  truthy: { allowed-values: ["true", "false"] }
ignore: |
  tests/
```

## Justfile Recipe Standards

Every project that imports the toolchain should have these `just` recipes:

```just
set shell := ["bash", "-uc"]

# Run the test suite (adjust for project)
test:
    uv run --extra dev pytest
    # or: pytest
    # or: python -m pytest

# Ruff lint and format verification
ruff:
    uv run --extra dev ruff check .
    uv run --extra dev ruff format --check .

# Static type checking
mypy:
    uv run --extra dev mypy src tests

# YAML linting
yamllint:
    uv run --extra dev yamllint -c .yamllint .github .pre-commit-config.yaml .yamllint

# Markdown linting
markdownlint:
    bunx markdownlint --config .markdownlint.json README.md

# Markdown + TOML formatting verification
prettier:
    bunx prettier --plugin=prettier-plugin-toml --check README.md pyproject.toml

# Source-code spelling
typos:
    typos

# Python security linting
bandit:
    uv run --extra dev bandit -ll -r src

# Pattern-based security scan
semgrep:
    semgrep scan --config auto --quiet --error --exclude .github

# Secret-leak scan
gitleaks:
    gitleaks detect --no-banner --redact

# Verify the justfile itself is formatted and valid
just-check:
    just --fmt --check
    just --list >/dev/null

# Fast, deterministic checks (runs on every commit via pre-commit)
check: test ruff mypy yamllint markdownlint prettier typos just-check

# Full lint + security suite (runs in CI, slower)
lint: check bandit semgrep gitleaks

# Apply auto-fixers (run before committing)
format:
    uv run --extra dev ruff check --fix .
    uv run --extra dev ruff format .
    bunx prettier --plugin=prettier-plugin-toml --write README.md pyproject.toml
```

## Pre-commit Hook Standards

Every project should have `.pre-commit-config.yaml` with these hooks. The
Python tools use `uv run --extra dev` when uv is the package manager or a
direct entry point for system-level Python.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.21
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run --extra dev mypy src tests
        language: system
        pass_filenames: false
        files: '\.py$'

  - repo: https://github.com/crate-ci/typos
    rev: v1.48.0
    hooks:
      - id: typos

  - repo: local
    hooks:
      - id: prettier
        name: prettier
        entry: bunx prettier --plugin=prettier-plugin-toml --check
        language: system
        files: '\.(md|toml)$'

      - id: markdownlint
        name: markdownlint
        entry: bunx markdownlint --config .markdownlint.json
        language: system
        files: '\.md$'

  - repo: https://github.com/adrienverge/yamllint
    rev: v1.35.1
    hooks:
      - id: yamllint
        args: [-c, .yamllint]

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ["-ll"]
        exclude: "^tests/"

  - repo: local
    hooks:
      - id: semgrep
        name: semgrep
        entry: semgrep scan --config auto --quiet --error --exclude .github
        language: system
        pass_filenames: false

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
```

### Project-specific additions

The above is the **core** toolchain. Projects add domain-specific hooks:

| Hook                      | Used when                 | stayturgid example         |
| ------------------------- | ------------------------- | -------------------------- |
| shellcheck + shfmt        | Shell scripts present     | device/termux scripts      |
| biome                     | TypeScript / JS present   | device/autojs6, just/tools |
| html-validate + stylelint | HTML / CSS present        | control/static             |
| ansible-lint              | Ansible playbooks present | ansible/                   |
| caddy-fmt                 | Caddyfile present         | control/caddy              |
| dotenv-linter             | .env files present        | .env.example               |
| pyinilint                 | .ini files present        | device termux configs      |

## Exporting to a New Project

1. Copy these files verbatim from stayturgid:
   - `.markdownlint.json`
   - `.yamllint`
   - `.pre-commit-config.yaml` (remove project-specific hooks)
   - `.typos.toml` (if the project has false positives; otherwise omit)

2. Add to `pyproject.toml`:
   - `[project.optional-dependencies] dev = [...]` with ruff, mypy, pytest, bandit, yamllint
   - `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`
   - `[tool.mypy]`
   - `[tool.pytest.ini_options]` (if using pytest)

3. Add to `package.json`:
   - `devDependencies`: markdownlint-cli, prettier, prettier-plugin-toml

4. Create `justfile` from the recipe standards above, adjusting:
   - Python paths (`src`, `tests`, etc.)
   - Target version in mypy/ruff (`py311` vs `py312`)
   - Any additional tool targets

5. Run once:
   ```bash
   uv sync --extra dev          # or pip install -e ".[dev]"
   bun install                   # Node lint tools
   pre-commit install            # Activate git hooks
   just check                    # Verify everything passes
   ```

## CI Integration

GitHub Actions workflow entry (from `.github/workflows/test.yml`):

```yaml
- name: Full lint + security
  run: just lint
```

`just lint` runs `check` (test + all fast checks) then `bandit semgrep gitleaks`.
The fast checks run first so security tools don't waste time on broken code.

## Bumping Versions

When updating tool versions, change these in lockstep:

| If bumping             | Update                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| ruff                   | `.pre-commit-config.yaml` rev + `pyproject.toml` dev dep + `justfile` (if direct uvx call) |
| mypy                   | `pyproject.toml` dev dep                                                                   |
| typos                  | `.pre-commit-config.yaml` rev                                                              |
| yamllint               | `.pre-commit-config.yaml` rev + `pyproject.toml` dev dep                                   |
| bandit                 | `.pre-commit-config.yaml` rev + `pyproject.toml` dev dep                                   |
| gitleaks               | `.pre-commit-config.yaml` rev                                                              |
| prettier, markdownlint | `package.json` devDependencies                                                             |
| semgrep                | system package manager (brew/pip) — pin in CI image                                        |

After bumping, run `just check && just lint` to verify nothing broke.
