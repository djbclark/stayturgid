# Tooling assumptions review — Grok (v1)

- **Date:** 2026-08-08
- **Slug:** `grok`
- **Brief:** `docs/2.0/TOOLING-REVIEW-BRIEF.md`
- **Ground truth read:** `architecture-final-v1.md`, `redteam-trust-layer-openai-v1.md`,
  `ideas-dump-claude.md`, `~/src/ops-worktrees/README.md` (2026-08-06 double-merge
  incident), on-disk justfiles / Ansible serverapps / secretspec / CFEngine /
  site-djbclark ops-release docs under `~/ops`.
- **Web verification:** mise task docs (jdx.dev, crawled 2026-08), OpenHands SDK
  security guide, go-task docs, Tailscale ACL/grants docs, minisign/signify,
  deploy-rs/comin context. Training memory is not used as feature evidence.

This review systematically challenges every load-bearing tool treated as an
unexamined R11 keep by the 2.0 architecture panel. Verdicts aim for reasoned
keeps, not churn. Where the 2.0 design (role mesh, Site Model, signed
manifests, consent, Free Sysadmin, cheap-exit) changes the original calculus,
that is called out explicitly.

---

## Verdict table (all tools)

| Tool | Role it plays | Verdict | Reasoning |
| --- | --- | --- | --- |
| **just** | Human-facing verb surface + modular recipe packs (~147 stayturgid + ~36 site-djbclark recipes) | **KEEP-WITH-CHANGES** | Excellent CLI UX; already modular; deps under-used relative to operator's new "DAG is important" requirement. Expand native recipe deps for pipeline recipes; do not rewrite to another runner yet. |
| **mise (toolchains)** | Language runtime / tool pin SSOT; exit host-baseline renderer (D3) | **KEEP** | Architecture final already assigned this role correctly. Installs identically on macOS and Ubuntu. |
| **mise tasks** | Candidate task runner / DAG | **RE-EVALUATE LATER** | Real DAG (`depends` / `depends_post` / `wait_for`), parallel-by-default, Tera, includes, sources/outputs. Trigger: deploy/release choreography needs a real multi-stage DAG *and* just deps prove insufficient. Not a Phase 0–2 move. |
| **Ansible** | Production service owner; fleet/device deploy adapters | **KEEP** | Final architecture D1: permanent production service owner. Role mesh + R5 exit + R10 publishability all require Ansible permanence. |
| **CFEngine** | On-device self-heal + last-ditch remote repair | **KEEP-WITH-CHANGES** | Unchanged product path (R4/R11), but treat the remote-exec channel as an attack surface (ideas-dump + red-team spirit): inventory ACLs, authz on `cfruncommand`, prefer SSH-mediated `just cf-run` over open cf-runagent. |
| **Gradle** | APK / native-agent builds | **KEEP** | R6 + architecture: Nix may hash/deploy artifacts; Gradle remains the Android build system. |
| **Termux (+api, +x11)** | Android userland for agent/SSH/CFEngine | **KEEP** | R4 settled: Android product surface. Non-reproducible `pkg` is accepted; artifact lane is the reproducibility fix, not Termux replacement. |
| **Shizuku fork** | Privileged Android broker for stayturgid | **KEEP** | Product dependency; separate release cadence from ops-v. Supply-chain risk is real (RT-08) — pin, SBOM, and sign the APK path; do not replace the broker. |
| **FIRERPA / lamda** | gRPC backup heal channel | **KEEP** | Operationally load-bearing backup path when SSH/ADB are sick. Keep as secondary channel; do not elevate it above signed converge. |
| **ADB-over-Tailscale** | Device control / deploy transport | **KEEP** | Core fleet connectivity. Pair with explicit Tailscale grants (see below); ADB itself stays. |
| **Tailscale** | Encrypted mesh transport + identity adjacency | **KEEP-WITH-CHANGES** | Keep transport. **Stop treating "on the tailnet" as authorization.** Specify tags + grants in Phase 0/3 (red-team + ideas-dump gap). |
| **SSH CA** | Host/user cert authentication for fleet SSH | **KEEP** | Authenticates peers; does not authorize releases or cache content (red-team table). Still correct for what it does. |
| **secretspec** | Sole secret *declaration* schema | **KEEP** | D1/R11: no second schema (agenix/sops). Values in providers only. |
| **Vector** | Log shipper (serverapp) | **KEEP** | Working adapter path; migrate placement with obs-main role, not tool churn. |
| **OpenObserve** | Log/UI sink | **KEEP** | Live stack; auth fix 2026-07-25 pending soak. Replacement only if product fails soak, not for architecture fashion. |
| **VictoriaMetrics** | Metrics store | **KEEP** | Fits role-mesh obs placement; no 2.0 pressure to replace. |
| **otelcol-contrib** | OTel collection on devices/hosts | **KEEP** | Standard collector; Termux role already ships it. |
| **Grafana** | Dashboards | **KEEP** | Operator UI; low coupling to trust layer. |
| **Caddy** | Local reverse proxy / TLS front | **KEEP** | Simple, Ansible-owned; exit-compatible. |
| **blackbox_exporter** | Probe exporter | **KEEP** | Small, purpose-fit. |
| **OliveTin** | Clickable ops actions UI | **KEEP** | Convenience surface; not in the TCB. Ensure actions call the same signed/just entry points, not bespoke privilege. |
| **Beads** | Cross-repo task graph DB | **KEEP** | Agent orchestration SSOT for work units. Conceptual kinship with ChangePlan is future schema work, not a merge now. |
| **Ralph TUI** | Parallel agent controller | **KEEP-WITH-CHANGES** | Keep controller model; enforce provenance gates and isolated ralph workspaces (already documented post-incident). Do not run with write access to shared `main/`. |
| **Herdr** | Multi-agent terminal mux / orchestration | **KEEP** | Operator harness; orthogonal to fleet trust. |
| **Worktree bare-store pattern** | Multi-repo task isolation | **KEEP-WITH-CHANGES** | Pattern is correct; 2026-08-06 failure was procedural. Codify ownership + provenance as *automated* checks where possible (hooks/scripts), not only prose. |
| **entangle / Entangled** | Literate tangle for SITE-CONTRACT | **KEEP** | D5: narrow calibration validated. Expansion only under scaffold/tutorial rule + ADR. |
| **git + GitHub Releases + `gh` + ops-v train** | Coordinated three-repo release | **KEEP** | R7 seed; pull agent consumes signed tags. Harden with manifest/signing (Phase 5), not a different VCS. |
| **flock / claim files** | Exclusive ops-release lock + multi-step claim | **KEEP** | Small, correct single-writer guard for release ceremony. Extend same pattern to any single-writer role mutation. |
| **Python + uv** | Control-plane language + packaging | **KEEP** | Dominant control code; uv is the right installer story. |
| **Bun** | JS tooling (tsc/biome wrappers, ocr) | **KEEP** | Narrow surface; fine under mise pin. |
| **Homebrew** | macOS packages / some pinned formulae (e.g. cfengine) | **KEEP-WITH-CHANGES** | Final arch: per-package single-owner registry, no bulk nix-homebrew migration. Census + one writer per formula. |
| **apt** | Ubuntu/Debian packages (exit hosts, future VPS non-Nix paths) | **KEEP** | Required by R5 exit drill and any non-Nix Linux. |
| **Termux `pkg`** | On-device packages | **KEEP** | Non-reproducible (accepted). Prefer hashed artifacts for critical binaries. |
| **minisign / signify** (proposed) | Offline Ed25519 release signatures | **KEEP** (adopt) | Correct floor for handset-offline verify. Prefer **minisign** for trusted comments + portable tooling; signify-compatible verification is a plus. Not a full TUF root — pair with RT-01 threshold/root metadata before pull ships. |
| **deploy-rs** (proposed) | Nix host push with rollback-on-failure | **KEEP** (adopt at Phase 4) | Fits NixOS hosts; macOS/Android stay on just/Ansible. Scope-limited adoption is right. |
| **harmonia** (proposed) | Simple binary cache role | **RE-EVALUATE LATER** | Prefer harmonia first when `cache` role exists (read-only serve of local store). Trigger: second Linux box or non-substitutable artifact. Cache key = total trust (RT-05). |
| **attic** (proposed) | Multi-uploader cache | **RE-EVALUATE LATER** | Heavier; only if multi-builder upload is proven necessary. Same RT-05 constraints. |
| **nixos-anywhere** (proposed) | Greenfield NixOS install | **KEEP** (adopt at Phase 4) | Right bootstrap for Hetzner `vps-primary`. One-shot installer, not ongoing converge. |
| **comin** (rejected) | GitOps auto-pull NixOS | **KEEP rejection** | Rejection was correct: NixOS-only, less transparent than a small auditable converge agent that also targets macOS/Termux. Revisit only if NixOS fleet ≫ other surfaces *and* pull agent is abandoned (unlikely). |
| **OpenHands SDK security** | Agent action confirmation + risk classification | **Surface A: KEEP-WITH-CHANGES (technique, not SDK)** · **Surface B: REPLACE with "no role as gate"** | See Priority Question 2. |
| **make** | Classic DAG | **REJECT for this suite** | Ubiquitous but worse DX; would be a downgrade from just. |
| **go-task (Task)** | YAML task runner with deps + sources/generates | **RE-EVALUATE LATER** | Strong alternative if just is ever abandoned wholesale. Not worth a third system now. |
| **mask** | Markdown-defined tasks | **REJECT for primary surface** | Cute R9 angle, but weaker modularity/DAG than just or mise; dual maintenance with existing justfiles not justified. `just --justfile foo.md` already covers lite literate recipes if wanted. |
| **moon / turbo / dagger** | Monorepo / CI graph / container pipelines | **REJECT** | Overkill for a three-repo ops suite; wrong shape for device fleet. |
| **cargo-make / xc** | Niche runners | **REJECT** | No Rust-workspace-primary or Swift-primary surface that needs them. |

---

## Priority Question 1 — task runner: `just` vs `mise` tasks vs alternatives

### Ground truth: what `just` is here today

Measured 2026-08-08 on this worktree + `~/ops/site-djbclark/justfile`:

| Metric | stayturgid | site-djbclark | Notes |
| --- | --- | --- | --- |
| Lines | ~1244 across `justfile` + `just/*.just` | ~424 | Brief's "~510" under-counted; modular split grew. |
| Recipes | ~147 | ~36 | Thin wrappers over Python/bash are the norm. |
| `import` | 6 modules (fleet, kotlin, services, tests, cfengine, site) | — | Modular surface already exists. |
| `{{ }}` interpolations | ~161 | (not re-counted) | Brief's 152 is in the right band. |
| `env_var_or_default` | 11 | — | Hosts/scope/limit plumbing. |
| Conditional `if` in vars/recipes | Yes (deploy args, Java home, host limits) | — | Non-trivial expression surface. |
| Shebang multi-line recipes | ~17 | — | Bash/python blocks, not one-liners. |
| Recipes with dependencies | **~8–9** (`test`, `unit-and-pytest`, `lint`, `kt-check`, `cfbs-build`, `dryrun`, a few aliases) | few | **DAG is available but almost unused.** |

Patterns that matter for migration cost:

- Heavy parameterization: `hosts=`, `scope=`, `devices_only=`, recipe args (`deploy host=""`).
- `set shell := ["bash", "-uc"]` and `justfile_directory()`.
- Real work lives in `control/bin/*.py` and Ansible; just is mostly a *discoverable CLI*, not the orchestration engine.
- Operators and agents are trained on `just deploy`, `just health`, `just test`.

### What mise tasks actually provide (verified against current docs)

From [mise task configuration](https://mise.jdx.dev/tasks/task-configuration.html) and [running tasks](https://mise.jdx.dev/tasks/running-tasks.html) (docs live as of 2026-08):

| Capability | mise | just (here) |
| --- | --- | --- |
| Real dependency graph | **Yes** — `depends`, `depends_post`, `wait_for` | Yes, but sparse use |
| Parallelism | **Parallel by default** (default max 4 jobs); order via depends | Sequential by default; deps run before recipe |
| Incremental / sources+outputs | **Yes** (mtime + experimental content cache) | No (always run) |
| Modular includes | `task_config.includes` (toml dirs, file tasks, experimental `git::`) | `import` / modules |
| Templating | **Tera** (`{{ }}`, vars, usage templates) | just expressions + `{{ }}` |
| Args | usage-spec (richer flags/completions) | recipe params + env vars |
| Confirm before run | `confirm` (does **not** block deps — footgun) | Manual / none |
| Human UX (`just --list` docs) | `mise tasks` / descriptions | Excellent, battle-tested here |

**Does mise give a real DAG with ordering + parallelism?** Yes. Independent deps run in parallel up to `--jobs`; `depends` forces order; `depends_post` runs after; `wait_for` synchronizes without adding nodes. That is a real DAG scheduler, stronger than just's "run these first" list for complex graphs.

**Is parallel-by-default a footgun for sequential deploy choreography?** **Yes.** A naive port of `deploy → verify → heal` without explicit `depends` edges (or `mise run --jobs 1`) can race. Mitigation is mechanical: model edges, or force serial jobs for production verbs. just's sequential default is safer for ops verbs; mise's default is better for CI fan-out. For this fleet, sequential-safe defaults matter more.

**Can mise express conditional vars and 150+ interpolations?** Mostly yes via Tera + `[vars]` (`default`, `required`, task-local vars) and `env`. The *style* changes (TOML + Tera vs just DSL). Ugly workarounds appear only for just-specific conveniences (`path_exists` chains for JAVA_HOME, `--set` ergonomics). Not a hard blocker; it is a rewrite tax.

**Modular includes equivalent to `import`?** Close enough: `task_config.includes` plus file tasks. Remote `git::` includes exist (experimental) — useful later for freeops shared tasks, not required now.

**Honest rewrite cost of the recipe surface:** for ~180 recipes that are mostly thin wrappers, a careful mechanical port is on the order of **3–8 engineer-days** for syntax, plus **1–2 weeks** of agent/operator muscle-memory, CI, docs, and site-djbclark parity — call it **~2–3 calendar weeks** to trust. The risk is not typing; it is subtle ordering bugs under parallel default and dual-path confusion during transition.

### Alternatives (serious short takes)

| Runner | Fit | Call |
| --- | --- | --- |
| **just (stay)** | Best human verb surface; already modular; deps under-used | Primary recommendation |
| **mise tasks** | Best DAG + sources/outputs *if* already all-in on mise | Secondary / later hybrid |
| **go-task** | YAML, deps (parallel), sources/generates, includes | Best "leave just" alternative; still a full rewrite |
| **make** | True classic DAG, ubiquitous | Worse DX; tabs/PHONY tax; no win over just+deps |
| **mask** | Markdown = docs+tasks (R9 rhyme) | Too weak for this surface; just can already read `.md` just blocks |
| **moon / turbo** | JS monorepo graphs | Wrong domain |
| **dagger** | Containerized pipelines | Violates "no Docker substrate" posture |
| **cargo-make / xc** | Ecosystem-specific | No |

### Correcting the "mise tasks re-couple D3 / hurt R5" claim

**The claim is wrong as stated.**

- D3 assigns: mise = toolchain SSOT + **host-baseline exit renderer**; Ansible adapters = **service** exit. That is about *what owns packages vs services*, not about *which binary runs `test` or `deploy`*.
- mise runs on Ubuntu the same as on macOS. Putting tasks in `mise.toml` does not force mise to own launchd/systemd, does not break the exit drill, and does not re-implement Vector/Caddy ownership.
- What *would* re-couple D3 is using mise **bootstrap services** (`dev.mise.*` only is already allowed for personal agents) to own production `com.stayturgid.*` units. **Task recipes ≠ service ownership.**

Partial truth nearby: collapsing *all* operator mental model into mise can blur the architecture diagram for newcomers ("mise does everything"). That is a documentation risk, not an R5 technical failure.

### Hybrid: two tools vs one

| Hybrid | Pros | Cons |
| --- | --- | --- |
| **just façade + mise DAG internals** | Keep UX; gain graph for heavy pipelines | Two systems; agents must know which owns what |
| **mise only** | One tool with toolchains+tasks | Large rewrite; parallel footguns; weaker list UX for ops |
| **just only + denser deps** | Zero new tool; uses existing skill | Weaker incremental builds; no sources/outputs |

**Two full surfaces is worse than one** for this operator+multi-agent environment. A *narrow* hybrid (mise tasks only for 3–5 internal CI-style graphs, never advertised as human verbs) is acceptable later. A dual public CLI (`just deploy` vs `mise run deploy`) is not.

### Recommendation (ONE path)

**Path: KEEP `just` as the only human-facing task runner; KEEP-WITH-CHANGES to actually use its DAG; keep mise for toolchains/bootstrap per D3; do not migrate the verb surface to mise tasks in Phases 0–4.**

#### Migration plan (small, reversible)

1. **Phase 0 (days):** Document recipe dependency policy in AGENTS/coding-rules: any multi-step pipeline (`lint`, `check`, `kt-check`, future `release-preflight`) **must** declare deps; no "run these three just lines" prose without edges.
2. **Phase 0–1:** Refactor the few real pipelines that already want order (`test`/`lint`/`kt-check`/`cfbs-*`/`web-health`) into explicit dep trees; add `release-preflight` / `converge-check` stubs as deps chains when Phase 5 schemas land.
3. **Do not** rewrite `deploy`/`heal`/`firerpa-*` into mise — those already delegate to Python with their own sequencing.
4. **Optional spike (½ day, disposable):** port `kt-check` + `unit-and-pytest` to mise tasks in a branch to validate ergonomics; delete if no clear win.
5. **Revisit trigger for full mise-task (or go-task) evaluation:** (a) more than ~15 recipes need cross-cutting ordered parallelism, or (b) sources/outputs caching becomes load-bearing for agent CI time, or (c) just cannot express a signed-release choreography cleanly.

#### Rollback

- Dep-only just changes: revert commits; recipes still runnable.
- Spike mise tasks: delete `[tasks]` / `mise-tasks/`; no production path depends on them.

---

## Priority Question 2 — OpenHands SDK security

Source: [OpenHands SDK Security & Action Confirmation](https://docs.openhands.dev/sdk/guides/security) (fetched 2026-08-08).

### What the SDK actually provides

- **Confirmation policies:** `AlwaysConfirm`, `NeverConfirm`, `ConfirmRisky` (thresholded on analyzer risk).
- **Analyzers:** `LLMSecurityAnalyzer`; deterministic `PatternSecurityAnalyzer`, `PolicyRailSecurityAnalyzer`; `EnsembleSecurityAnalyzer` (max concrete severity).
- **Risk levels:** LOW / MEDIUM / HIGH / UNKNOWN — **classify for policy, do not hard-deny.**
- **Documented bypass:** `conversation.execute_tool()` **skips** analyzer and confirmation.
- **Documented non-goals:** not a full shell AST, not a sandbox, not a complete prompt-injection solution; pair with isolation for stronger safety.

### Surface A — AI coding agents (Herdr / Ralph / Codex / Claude Code, worktree write)

**Relevant findings:** RT-03 (source-to-signing laundering), the real **2026-08-06** double-merge incident (`ops-worktrees/README.md`: foreign commits + merge without provenance).

| Question | Answer |
| --- | --- |
| Does OpenHands SDK adoption meaningfully mitigate a compromised/mistaken agent? | **Partially, and only as a soft pre-exec filter** inside an OpenHands-shaped conversation loop. Pattern/PolicyRail catch some `rm -rf`, `curl|sh`, sudo-class strings. They do not stop a determined agent writing a malicious Ansible task that looks like normal code, nor stop `gh pr merge` of foreign commits. |
| Integration cost with Herdr/Ralph/Beads? | **High for the SDK.** Those harnesses are not OpenHands `Conversation` objects. Wiring the full SDK means either wrapping every agent in OpenHands (non-starter) or building a side process that never sees tool calls. |
| Vendor *technique* vs *SDK*? | **Vendor the technique.** Implement a small deterministic action/command classifier (regex + policy rails + ensemble max-severity) at harness boundaries that *you* control: shell wrappers, `gh`/`git` hooks, Ralph step gates. Mirror OpenHands patterns without taking the dependency. |

**Verdict Surface A: KEEP-WITH-CHANGES — adopt the *pattern*, not the SDK.**

Concrete cheap wins aligned with the incident writeup:

1. Procedural provenance gate as a **script** (`git log` + `git diff` range checks) required before any merge helper; fail closed under YOLO.
2. Pattern rails on high-risk argv for agent-exposed shell (destructive git, force-push, secrets paths, production deploy).
3. Keep human/operator confirmation for release signing and production deploy — never `NeverConfirm` on those verbs.
4. Do **not** treat LLM risk labels as authorization (RT-09 / advisor-must-not-authorize).

Migration cost: days for hooks + classifier; weeks if someone tries full SDK embedding (don't).

### Surface B — fleet trust layer (signed manifests, consent, pull converge)

Red-team RT-04 / RT-09: capability-enforcing executor; AI advisor must never be an authorization oracle. OpenHands docs: **confirm, don't block**; analyzers return risk; `execute_tool()` bypasses.

| Proposed use | Verdict |
| --- | --- |
| Analyzer as hard gate on converge/consent | **No. Forbidden shape.** Classification ≠ enforcement; bypassable; non-deterministic if LLM involved. |
| Advisor input *above* a deterministic capability gate (T2-style briefing: "this plan looks HIGH risk because…") | **Optional later, non-authorizing.** Same role as any other LLM summary over a ChangePlan. Must not be able to approve, and must not be required for deny. |
| Replace signed capability IR / executor allowlist | **No.** |

**Verdict Surface B: no legitimate role as a control-plane gate. Optional non-authorizing advisor feature only after a deterministic executor exists.**

---

## Full-stack notes (by group)

### Orchestration / config

**Ansible — KEEP.**  
2.0 strengthens the case: role mesh still needs multi-OS config push; R5 exit re-renders services via Ansible adapters; R10 consumers must not need nix-darwin. Failure mode under-considered: playbooks are general-purpose code once signed (RT-03). Mitigation is typed operation IR + check-mode honesty, not replacing Ansible.

**CFEngine — KEEP-WITH-CHANGES.**  
Last-ditch heal is both *recovery* and *remote exec*. Ground truth: `cf-serverd` ACLs exist (Tailscale CGNAT range, wrapper path); `just cf-run` is preferred over classic cf-runagent. Under consent/trust: CFEngine should remain **break-glass**, logged, network-restricted, and not a silent bypass of signed converge for routine changes. Adding "converge agent alive" promise (proposal-v1) is fine; expanding remote-exec surface is not.

**Gradle — KEEP.** APK builds stay Gradle; suite hashes and deploys outputs.

### Android

**Termux stack — KEEP.** R4 settled. Reproducibility gap on `pkg` is real; answer is content-addressed artifact lane for critical binaries, not nix-on-droid.

**Shizuku fork — KEEP** with supply-chain hygiene (RT-08): pin upstream, own signing, SBOM in release manifests when Android artifacts enter ops-v.

**FIRERPA/lamda — KEEP** as backup heal. Compromise of FIRERPA key is high impact (`secretspec` already declares it); rotate like other fleet roots; never let FIRERPA install unsigned "emergency" code without the same gates as primary deploy.

**ADB-over-Tailscale — KEEP** transport; authorization must not equal "ADB reachable."

### Network / identity

**Tailscale — KEEP-WITH-CHANGES.**  
Encryption and peer identity are real. **ACLs/grants are not specified as fleet policy today** (ideas-dump + red-team). Tailscale now pushes **grants** as the preferred policy syntax (deny-by-default, tags, groups). Before consented / lower-trust devices share a tailnet:

- Tag roles: `tag:operator`, `tag:android-fleet`, `tag:android-consented`, `tag:obs`, `tag:builder`, …
- Grants: operator → fleet admin ports; consented ↛ builder SSH; obs scrape only metrics ports; deny lateral movement defaults.
- Store a **reviewed** policy template in site overlay docs (not necessarily auto-applied from public stayturgid).

**SSH CA — KEEP.** Proves host/user keys; does not prove release freshness or cache honesty. Do not overload it as a release authority.

### Secrets

**secretspec — KEEP.** Sole declaration authority is correct under R11 and Free Sysadmin (declarations public-safe; values never git). Ensure provider backends and bootstrap exceptions stay narrow (architecture § secrets).

### Observability

**Vector, OpenObserve, VictoriaMetrics, otelcol-contrib, Grafana, Caddy, blackbox_exporter, OliveTin — KEEP** as a set.

2.0 changes *placement* (obs-main off the sleeping M1 Air → VPS role), not *tool choice*. OliveTin must remain a thin button face over existing just/Ansible verbs so it does not become a second unsigned remote-exec path. OpenObserve clean-log soak remains an ops gate, not a redesign trigger.

### Agent orchestration

**Beads / Ralph / Herdr — KEEP** (Ralph KEEP-WITH-CHANGES).  
They are the control plane for *coding* work, not fleet converge. Long-term schema kinship with ChangePlan is interesting (ideas-dump); do not merge schemas in v1.

**Worktree bare-store — KEEP-WITH-CHANGES.**  
Architecture is sound (shared objects, task isolation). Failure was concurrent writers + merge without provenance. Automate: claim file or Beads ownership field for workspace path; pre-merge script; refuse commits if `git` detects foreign authors on branch without operator override flag.

### Literate

**Entangled — KEEP** at current narrow scope (SITE-CONTRACT + parity CI). stitch + parallel agents = corruption risk (ideas-dump); extend cross-agent ownership rules to literate sources before any expansion (D5).

### Release / VCS

**git + GitHub Releases + gh + ops-v — KEEP.**  
Mechanics in site-djbclark (`ops-release-check/deploy`, annotated tags, `ops-release.json`) are the right coordination spine. Phase 5 adds signed manifests *on top*, not a different train.

**flock + claim files — KEEP.**  
`ops-release.lock` + `ops-release.claim.json` are the right small single-writer primitive; reuse for other single-writer role mutations (architecture lease/fencing).

### Runtimes / packages

**Python+uv, Bun, Homebrew (with single-owner discipline), apt, Termux pkg — KEEP** as above. mise should pin the language tools; brew/apt remain OS package channels under the ownership matrix.

### Proposed-but-not-yet-adopted

| Tool | Verdict | Migration / cost note |
| --- | --- | --- |
| **minisign** | Adopt (Phase 5) | Small binary on Mac + Termux; ceremony docs; **not** sufficient alone (RT-01 threshold root still required before pull). |
| **signify** | Accept as verify-compatible cousin | Prefer minisign for trusted comments + packaging ergonomics. |
| **deploy-rs** | Adopt for NixOS push (Phase 4) | Days to wire flake profiles; rollback-on-failure is the feature earn. |
| **harmonia** | Later, demand-driven | Lowest-complexity cache role; still total trust on cache key (RT-05). |
| **attic** | Later only if multi-uploader needed | Higher ops cost. |
| **nixos-anywhere** | Adopt Phase 4 bootstrap | One-shot; then deploy-rs / rebuild. |
| **comin** | Rejection stands | NixOS-only auto-gitops fights transparent multi-OS converge agent. |

---

## Tools whose failure/compromise is under-considered

| Tool / channel | Why under-considered | What to do |
| --- | --- | --- |
| **CFEngine remote-exec** | Recovery path *is* remote code execution | Tailnet grants; authz on wrapper; audit logs; break-glass only |
| **Release signing key (future minisign)** | One key = fleet root (RT-01) | Threshold root metadata before pull; separate emergency key |
| **Nix cache key (harmonia/attic)** | Trusted cache ⇒ arbitrary store paths (RT-05) | Separate builder/cache/release authority; pin critical closures |
| **FIRERPA API key / cert** | Backup channel can heal/change devices | Rotate; scope; monitor |
| **SSH CA key** | Issues host/user trust | Offline/HSM ceremony; short host cert TTLs |
| **Tailscale policy (or lack)** | "On tailnet" used as authz | Explicit tags/grants before consented devices |
| **Agent worktree write + `gh` auth** | Already bit once (2026-08-06) | Provenance automation; no shared writable main |
| **OpenHands-style LLM analyzer if misused as gate** | Looks like security, is advice | Never in executor path |

---

## Does 2.0 change the original calculus?

| Tool | Original reason | 2.0 effect |
| --- | --- | --- |
| just | Nice CLI after Make migration | Still best verb surface; DAG requirement → use deps, don't churn tool |
| mise | Runtime pins | Elevated to toolchain SSOT + exit baseline (D3) — **stronger keep** for toolchains, not tasks |
| Ansible | Fleet config | Elevated to permanent service owner (D1) — **stronger keep** |
| CFEngine | Device self-heal | Unchanged product; **more** scrutiny on remote-exec under trust model |
| Nix-related (deploy-rs, harmonia, nixos-anywhere) | Not in stack | **New** scoped adopts; comin still out |
| Tailscale | Connectivity | Must add policy layer for consent/mesh |
| secretspec | Secret declarations | Confirmed sole schema |
| Agent stack | Coding velocity | Becomes threat model input (RT-03); pattern-level security, not SDK |

---

## Summary recommendations (operator-facing)

1. **Task runner:** stay on **just**; implement real recipe DAGs where pipelines exist; **do not** fold the public verb surface into mise tasks now. The "mise recouples D3" objection is **incorrect**; the right objection is rewrite cost + parallel footguns + two CLIs.
2. **OpenHands:** **do not** adopt the SDK into Herdr/Ralph/Codex. **Do** copy deterministic pattern/rail ensemble ideas into harness gates. **No** role as fleet authorization.
3. **Biggest unexamined policy gap:** **Tailscale grants/tags** — close in Phase 0/3 docs + live policy before consented devices.
4. **Biggest under-modeled attack surface among "keeps":** **CFEngine remote-exec** and **future single release key** — architecture already points at mitigations; implement them before pull converge.
5. **Proposed adopts:** minisign + deploy-rs + nixos-anywhere on the existing phase plan; harmonia/attic demand-driven; comin rejection upheld.

*End of tooling-assumptions-review-grok-v1.*
