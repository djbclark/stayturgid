# TOOLING ASSUMPTIONS REVIEW BRIEF — stayturgid 2.0

## Why this exists

The 2026-08-08 architecture panel (4 AI proposals + 1 red-team, all in
`docs/2.0/`) evaluated the _config management_ layer thoroughly but treated a
large set of other tools as **unexamined keeps** — preserved under requirement
R11 ("preserve existing invariants") without anyone asking whether they are
still the right choice for the 2.0 architecture. The operator has explicitly
asked for that gap to be closed.

Your job: **systematically challenge every load-bearing tool in this stack.**
Not to churn — most will survive — but so that each one is a _reasoned keep_
rather than an inherited assumption, and so genuine mismatches surface now
rather than in Phase 4.

## Deliverable

ONE file: `docs/2.0/tooling-assumptions-review-<slug>-v1.md` (your slug is in
your launch prompt).

For EVERY tool below, produce a verdict row plus (where the verdict is not a
trivial keep) a short analysis section:

| Tool | Role it plays | Verdict | Reasoning |
Verdicts: **KEEP** (reasoned) · **KEEP-WITH-CHANGES** · **REPLACE** ·
**RE-EVALUATE LATER** (with the trigger that should force the decision).

Be decisive and specific. "It works fine" is not analysis. For every REPLACE
or KEEP-WITH-CHANGES, give the migration cost honestly.

## PRIORITY QUESTION 1 — task runner: `just` vs `mise` tasks vs alternatives

The operator has stated: **"having a DAG is important."** This is now a
requirement, not a preference. Analyze:

- What `just` actually provides today in this repo. Ground truth (measured
  2026-08-08 across `stayturgid/justfile`, `stayturgid/just/*.just`, and
  `site-djbclark/justfile` — ~510 lines total, ~60+ recipes):
  - 152 `{{ }}` interpolations; 18 `env_var_or_default()`; 17 conditional
    expressions in variable assignment (`if x == "" { } else { }`)
  - 11 `import` statements (modular justfiles: fleet/kotlin/services/tests/
    cfengine/site)
  - 24 shebang/script recipes (`#!/usr/bin/env` — multi-line bash/python)
  - parameterized recipes with defaults (`deploy host=""`, `ocr *args`)
  - `set shell := ["bash", "-uc"]`, `justfile_directory()`
  - **only ~9 recipes use dependencies at all** (`kt-check: kt-format-check
kt-detekt kt-test`, `test: unit-and-pytest`,
    `unit-and-pytest: _ensure-test-collections`, `cfbs-build: cfbs-validate`,
    `dryrun: deploy-check-legacy`, `lint: _ensure-test-collections`, …)
- Whether **mise's task runner** (`[tasks]` in mise.toml + file tasks) covers
  all of it: `depends`, `depends_post`, `wait_for`, `sources`/`outputs` for
  incremental runs, usage-spec arg parsing, env, dir, `mise run a ::: b`.
  **Investigate carefully and verify against current docs — do not trust
  training memory.** Specifically resolve:
  - Does mise give a real DAG with correct ordering + parallelism?
  - mise runs tasks in **parallel by default** — is that a footgun for
    sequential deploy choreography, and how is it controlled?
  - Can mise express the 17 conditional variable assignments and 152
    interpolations (tera templating?) without ugly workarounds?
  - Modular includes equivalent to `import`?
  - What is the honest rewrite cost of ~60 recipes?
- Alternatives to evaluate seriously, at minimum: **mise tasks**, staying on
  **just**, **mask** (markdown-defined tasks — note the R9 literate-
  programming angle: task runner and publishable documentation could be the
  same artifact), **make** (the original DAG; ubiquity vs. syntax), **task
  (go-task)** (YAML, real DAG, sources/outputs), **moon**/**turbo** (probably
  overkill), **dagger** (probably overkill), **cargo-make**, **xc**.
  Add any others you find.
- **Correct a muddled claim from the dialogue:** it was suggested that folding
  the task surface into mise would "re-couple what D3 uncoupled" and hurt the
  R5 Ubuntu exit. Assess this honestly — mise runs identically on Ubuntu, so
  state clearly whether this concern is real, partly real, or wrong.
- Consider a **hybrid**: mise tasks for DAG/dependency-heavy pipelines,
  `just` retained as the human-facing verb surface (or vice versa). Is two
  tools worse than one here?

Recommend ONE path with a migration plan and rollback.

## PRIORITY QUESTION 2 — OpenHands SDK security as an adopted component

Read <https://docs.openhands.dev/sdk/guides/security>. It provides
confirmation policies (`AlwaysConfirm`/`ConfirmRisky`/`NeverConfirm`) and
security analyzers (`LLMSecurityAnalyzer`, plus deterministic
`PatternSecurityAnalyzer`, `PolicyRailSecurityAnalyzer`,
`EnsembleSecurityAnalyzer` with max-severity composition).

Assess adoption for TWO distinct surfaces — they are different problems:

- **Surface A — the AI coding agents that build/deploy this fleet**
  (Herdr/Ralph/Codex/Claude Code with worktree write access). Relevant to
  red-team finding **RT-03** and the real 2026-08-06 double-merge incident in
  `~/src/ops-worktrees/README.md`. Would adopting the OpenHands SDK (or
  reimplementing its deterministic analyzer pattern) meaningfully mitigate a
  compromised/mistaken agent? What is the integration cost given the existing
  Herdr/Ralph/Beads orchestration? Is vendoring the _technique_ better than
  adopting the _SDK_?
- **Surface B — the fleet trust layer** (signed manifests, consent, pull
  converge). Note that OpenHands analyzers **classify risk; they do not
  hard-deny**, and their docs say `execute_tool()` bypasses them. Red-team
  RT-04/RT-09 require a capability-enforcing executor and state that an AI
  advisor must never be an authorization oracle. Give a clear verdict on
  whether OpenHands has any legitimate role here (e.g. as a T2 advisor input
  layered _above_ a deterministic gate) or none.

## THE FULL TOOL LIST TO REVIEW

Every one of these is currently an unexamined or lightly-examined keep:

**Orchestration/config:** Ansible · CFEngine · just · mise · Gradle
**Android:** Termux (+termux:api, +termux:x11) · Shizuku fork · FIRERPA/lamda
· ADB-over-Tailscale
**Network/identity:** Tailscale · SSH CA · (are Tailscale ACLs specified
anywhere? the red-team flagged "tailnet = trusted" as an unexamined policy)
**Secrets:** secretspec (+ its provider backends)
**Observability:** Vector · OpenObserve · VictoriaMetrics · otelcol-contrib ·
Grafana · Caddy · blackbox_exporter · OliveTin
**Agent orchestration:** Beads · Ralph TUI · Herdr · the worktree bare-store
pattern itself
**Literate:** entangle/Entangled
**Release/VCS:** git + GitHub Releases + `gh` + the ops-v train mechanics ·
flock/claim files
**Runtimes/pkg:** Python+uv · Bun · Homebrew · apt · Termux `pkg`
**Proposed-but-not-yet-adopted (also review):** minisign/signify · deploy-rs ·
harmonia/attic · nixos-anywhere · comin (rejected — was that right?)

For each, ask: does the 2.0 architecture (role mesh, Site Model, signed
manifests, consent layer, Free Sysadmin publishing, cheap-exit constraint)
change the calculus that originally justified this tool? Flag any tool whose
_failure or compromise_ is under-considered (the red-team noted CFEngine's
remote-exec channel is both the recovery path and an attack surface).

## Rules

- Read first: `docs/2.0/architecture-final-v1.md` (authoritative),
  `redteam-trust-layer-openai-v1.md`, `ideas-dump-claude.md`, and the ground
  truth under `~/ops` and `~/src/ops-worktrees/README.md`.
- **Verify current tool capabilities on the web.** Several of these gained
  major features in 2025–2026 (mise's bootstrap surface is the known example).
  Training memory is not acceptable evidence for a feature claim.
- You MAY clone/download code into `~/src/vendor/` and search the web freely.
- Create ONLY your own review file (+ optional `questions-<slug>.md`).
  Never modify any file you did not create; nothing under `~/ops`.
- No git commits/pushes.
- Prefer honest "KEEP, and here's the actual reason" over inventing churn.
  But do not be reflexively conservative: if something genuinely no longer
  fits, say so with the migration cost.
