# Python Tooling: uv, ty, and Ruff for stayturgid

**Date:** 2026-07-13
**Purpose:** Evaluate adopting the Astral toolchain (uv, ty, ruff) for dependency management, static analysis, and linting/formatting of the stayturgid Python codebase.

---

## Current State

The project has ~70+ hand-written Python files across five locations:

```
control/lib/          — shared libraries (logging, fleet_health, adb_cli, etc.)
control/bin/          — Mac-side CLI tools (dashboard, monitors, deploy, heal)
control/tools/        — one-shot scripts (autojs6, fdroid, obtainium, play)
device/termux/py/     — scripts deployed to Android Termux (start_adb, repair, bridges)
tests/python/         — pytest twin tests for device scripts + libs
ansible_collections/  — Ansible module_utils + modules with their own unit tests
```

Key observations:

| Dimension          | Current                                                                                 |
| ------------------ | --------------------------------------------------------------------------------------- |
| Python version     | 3.14.6 (Mac), 3.12.x (Ansible CI), 3.9.x (Termux device)                                |
| Package management | None — no pyproject.toml, no requirements.txt (except test deps)                        |
| Virtualenv         | `.venv-test` created by `make test-venv`, deps in `tests/python/requirements.txt`       |
| Test framework     | pytest 9.1.1 + pytest-mock + pytest-xdist                                               |
| Linting            | None for Python (ansible-lint + yamllint + shellcheck exist for other layers)           |
| Type checking      | None                                                                                    |
| Formatting         | None                                                                                    |
| CI                 | GitHub Actions: `make test` runs pytest + ansible-test, `make check` runs syntax checks |

The codebase predates modern Python packaging conventions. It uses a flat layout with `sys.path.insert(0, ...)` in test conftest.py and some scripts to find sibling modules. The Ansible module_utils pattern (used by collections) is the only structured packaging.

---

## Tool-by-Tool Assessment

### uv — Package and project manager

**What it is:** Rust-based replacement for pip + pip-tools + pipx + poetry + pyenv + virtualenv. From Astral (same team as Ruff/ty). Supports project mode (`uv init`, `uv add`, `uv lock`, `uv sync`) and pip-compat mode (`uv pip install`).

**Why it matters for stayturgid:**

- **Reproducible environments.** A `uv.lock` pins every transitive dependency with hashes, so the Mac controller, CI runner, and any future dev workstation resolve identically.
- **Single tool.** Replaces `python3 -m venv`, `pip install`, `pip freeze`, `pip-compile`, `pipx`.
- **Speed.** 10-100x faster than pip. `uv sync` on a warm cache takes milliseconds.
- **Python version management.** `uv python install 3.12` downloads CPython; `uv python pin 3.12` locks a project to a version. This would let CI and the Mac host agree on the Python minor version without Homebrew `python@3.x` management.
- **uvx for ephemeral tools.** `uvx ruff check` runs ruff without installing it. Useful for CI steps without permanent tool venvs.
- **PEP 723 script support.** `uv run script.py` reads inline `# /// script` metadata and creates an ephemeral environment. Several device scripts (`device/termux/py/*.py`) could declare deps this way.

**Caveats:**

- The project has no `pyproject.toml` today. Adopting uv's project mode requires creating one.
- Flat layout (no `src/`, no `__init__.py` in control/lib/) is not a standard PEP 621 project layout. uv can still manage it with a minimal `pyproject.toml` and `tool.uv.package = false`, but the primary use case here is _dependency management for the Mac controller + CI_, not publishing a package.
- Device-side scripts cannot use uv (Termux has no Rust toolchain, no uv binary). They must remain standalone or use the flat layout with `sys.path` injection.
- `uv pip` compatibility mode works with existing requirements files today with zero config — instant speedup for `make test-venv`.

### ty — Type checker

**What it is:** Rust-based Python type checker from Astral (beta, v0.0.59). 10-100x faster than mypy/pyright. Has a language server (LSP) with code actions, completions, inlay hints. Supports intersection types, advanced narrowing, gradual typing.

**Why it matters for stayturgid:**

- **Catches real bugs.** Type checking finds `None`-unsafe dereferences, mismatched argument types, missing return values — the exact class of bugs that have caused production issues (e.g., the `getParent()` TypeError on Android 16 AutoJs6, or `sys.path.insert` shadowing stdlib `logging`).
- **Gradual adoption.** ty has `--level` to start with only the most severe rules, and supports per-file overrides and `# type: ignore[code]` suppressions. It does not require full coverage from day one.
- **Designed for partially typed code.** The "gradual guarantee" means untyped code is tolerated; you get value where you have type annotations and silence elsewhere.
- **Language server.** Richer editor experience (VS Code, Neovim, PyCharm) via LSP — auto-imports, hover docs, rename refactoring. The doc mentions opencode-web editing; this would give better error surfacing there too.

**Caveats:**

- **Beta software.** `0.0.x` versioning, no stable API, breaking changes between releases. The project operates a fleet of phones; CI could break after a `uvx ty` upgrade.
- **Not all patterns supported.** `sys.path` hacks, dynamic imports, and `__import__`-style patterns confuse most type checkers. The flat-layout imports in this codebase may produce false positives.
- **Device-side Python 3.9 incompatibility.** ty supports checking code targeting 3.10+. Device scripts target 3.9 (Termux). Using `ty --python-version 3.9` may produce false negatives.
- **Annotation effort.** The codebase has almost zero type annotations today. A type checker will find hundreds of issues. The value comes incrementally — annotate hot paths first.

### Ruff — Linter and formatter

**What it is:** Rust-based Python linter (replaces flake8 + ~200 plugins) and formatter (replaces black). Single binary, no Python runtime needed. From Astral.

**Why it matters for stayturgid:**

- **Zero-config linting.** `ruff check` with defaults catches unused imports, undefined names, bare `except:`, unused variables, `print()` in production code, etc. All are present in the current codebase.
- **Zero-config formatting.** `ruff format` is compatible with black but faster. Consistent style across 70+ files without debate.
- **Pre-commit support.** `ruff check --fix` and `ruff format` in pre-commit (or in CI's `make check`) prevents style drift.
- **Rule maturity.** Ruff is stable (v0.10+), widely adopted, and has a rich rule set (800+ rules). Low risk.
- **CI integration.** GitHub Actions `make check` already runs; adding `ruff check` and `ruff format --check` is a two-line addition.

**Caveats:**

- Formatting may produce large initial diffs. Best applied as a single "initial format" commit with `git blame`-ignore configured.
- Some rules (`PLC0415` — import at module level) may conflict with the project's conditional import patterns. Easy to suppress per-rule in `pyproject.toml`.

---

## Integration Strategy

### Phase 0 — Install tools (hours)

```bash
brew install uv ruff
uv tool install ty
```

Or, for CI: `uvx ruff`, `uvx ty`, `uvx ruff format --check`.

No changes to the project needed yet.

### Phase 1 — uv for build toolchain (half-day)

1. **Replace `pip install -r tests/python/requirements.txt` with `uv pip sync`**

   In `Makefile`:

   ```makefile
   test-venv:
   	uv venv --python 3.12 $(VENV)
   	uv pip sync tests/python/requirements.txt --python $(VENV)
   ```

   This is a drop-in replacement, no structural changes. Speed improvement alone is worth it.

2. **Optional: Create minimal pyproject.toml for tool config**

   Ruff and ty both read config from `pyproject.toml`. A minimal file:

   ```toml
   [project]
   name = "stayturgid"
   requires-python = ">=3.9"
   description = "Android fleet resilience tooling"
   
   [tool.ruff]
   target-version = "py39"
   line-length = 100
   
   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "UP"]
   
   [tool.ty]
   python-version = "3.9"
   ```

   This does not make the project a package — it's purely for tool configuration. The `requires-python` is informational; no build backend is declared.

### Phase 2 — Ruff for linting (day)

1. **Initial scan:**

   ```bash
   ruff check control/ device/ tests/ ansible_collections/
   ```

   Expect 200-600 findings. Many are auto-fixable (`ruff check --fix`).

2. **Suppress intentional violations** in `pyproject.toml`:

   ```toml
   [tool.ruff.lint.per-file-ignores]
   "tests/*" = ["S101"]            # allow assert
   "device/termux/py/*" = ["T201"] # allow print() in device scripts
   ```

3. **Add to CI:**

   ```makefile
   lint: ruff-check
   ruff-check:
   	uvx ruff check --output-format=github
   ```

4. **Add formatting check:**

   ```makefile
   ruff-format-check:
   	uvx ruff format --check
   ```

5. **Make a single initial-format commit** with `git blame --ignore-revs-file .git-blame-ignore-revs`.

### Phase 3 — ty for type checking (weeks)

1. **Initial run in warn-only mode:**

   ```bash
   uvx ty check control/lib/ --level=warn
   ```

   This produces warnings but exits 0. Gauge the noise level.

2. **Annotate control/lib/ first.** That is the most-reused code and has the highest bug surface.

3. **Add to CI as allowed-to-fail (soft gate):**

   ```makefile
   .PHONY: typecheck
   typecheck:
   	-uvx ty check --level=warn control/lib/ control/bin/
   ```

   The `-` prefix means the recipe does not fail the build. Only promote to hard gate when warning count is stable.

4. **Cover hot paths:**
   - `control/lib/fleet_health.py` — probe/evaluate logic used by two monitors
   - `control/lib/stayturgid_device.py` — device iteration, config parsing
   - `control/lib/logging.py` — custom logging layer
   - `control/lib/firerpa_auth.py` — certificate resolution (security-sensitive)
   - `control/bin/dashboard.py` — web app entry point

### Phase 4 — uv for project management (optional, future)

If the Mac controller grows enough to warrant a proper package layout:

```bash
uv init --app  # creates pyproject.toml in current dir
uv add flask markupsafe
uv lock        # creates uv.lock
```

This is a larger structural change. Defer until the flat layout becomes painful (e.g., import ambiguity, pip dependency resolver conflicts).

---

## Risk Analysis

| Risk                             | Likelihood | Impact             | Mitigation                                                             |
| -------------------------------- | ---------- | ------------------ | ---------------------------------------------------------------------- |
| ty beta instability              | Medium     | High (CI breakage) | Pin `ty` version in CI; run in warn-only mode initially                |
| Formatting changes mental model  | Medium     | Low                | Single-commit initial format; `git blame`-ignore                       |
| False positives from flat layout | High       | Medium             | Per-file `--ignore` in early phases; annotate incrementally            |
| Device-side Python 3.9 mismatch  | Low        | Low                | `ruff` targets `py39`; `ty` can skip device scripts                    |
| Team/agent tool adoption         | Medium     | Medium             | Add to AGENTS.md + Makefile; tool calls use `uvx` so no install needed |
| No `pyproject.toml` today        | Low        | Low                | Start with tool config only; no build backend required                 |

---

## Recommendation

**Proceed with Phase 1 and Phase 2 immediately.** The ROI is clear:

- `uv pip sync` is a zero-config speedup for every `make test-venv` and CI run.
- `ruff check` + `ruff format` catch real issues with minimal config and no architectural changes.

**Phase 3 (ty) should start as a soft gate** on `control/lib/` only, with explicit buy-in to fix one module per session. The beta risk is real — ty should not block deploys until the team is comfortable with its output.

**Phase 4 is optional.** The project's flat layout works for its deployment model (Ansible pushes files, imports via `sys.path` on the device). No urgency to restructure.

### Concrete Next Step

```bash
# 1. Install
brew install uv ruff
uv tool install ty

# 2. Speed up test venv immediately
# Edit tests/python/requirements.txt to add ruff (for CI convenience)
# Update Makefile: use uv pip sync in test-venv target

# 3. Run initial lint
cd ~/stayturgid
ruff check control/ device/ tests/ \
  --ignore E501 \
  --per-file-ignoires "tests/*=S101" \
  --fix

# 4. Run initial format
ruff format control/ device/ tests/

# 5. Add pyproject.toml with tool config (no build backend)
```

### Files to Modify

| File                                     | Change                                                                                               |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `pyproject.toml`                         | Create with `[tool.ruff]` and `[tool.ty]` config                                                     |
| `Makefile`                               | Replace `pip` with `uv pip` in test-venv; add `ruff-check`, `ruff-format-check`, `typecheck` targets |
| `.github/workflows/test.yml`             | Add `ruff check` and `ruff format --check` steps                                                     |
| `.github/workflows/collection-build.yml` | Ensure uv available                                                                                  |
| `AGENTS.md`                              | Document uv/ruff/ty commands                                                                         |
| `.git-blame-ignore-revs`                 | Add initial-format commit hash                                                                       |
