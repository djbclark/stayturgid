# stayturgid 2.0 tooling-assumptions review — OpenAI v1

**Date:** 2026-08-08
**Scope:** authoritative 2.0 architecture, red-team report, live ~/ops suite,
and worktree protocol. This is a review, not an adoption plan. A tool is not a
security boundary merely because it emits a plan, signature, or green check.

## Executive decision

Keep the layered stack. Make authorities explicit before adding machinery:
Ansible remains the intent-to-service adapter; CFEngine remains the narrowly
scoped last-mile repair path; just remains the human command surface; mise
remains toolchain SSOT and the Ubuntu host-baseline renderer. Do not migrate
the command surface to mise now, and do not run two task runners for the same
pipelines.

The changes needed are security and ownership changes, not substitutions:
Tailscale ACLs/grants, capability-scoped SecretSpec delivery, a restricted
CFEngine policy/transport, immutable Android provenance, declared
observability placement, and a signed-update protocol with a
capability-enforcing executor. No reviewed tool supplies those prerequisites
for pull converge or consent.

## Verdict register

| Tool                               | Role it plays                                  | Verdict               | Reasoning                                                                                                                                |
| ---------------------------------- | ---------------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Ansible                            | Site Model adapters; fleet/service convergence | **KEEP-WITH-CHANGES** | Portable service owner required by D1/D3; check mode is evidence, not authority. Render from Site Model and constrain signed operations. |
| CFEngine                           | On-device continuous repair/recovery           | **KEEP-WITH-CHANGES** | Independent Termux recovery tier is valuable, but remote policy execution is a standing privileged channel.                              |
| just                               | Human verbs and local orchestration            | **KEEP**              | Existing modular expressive command surface; its small dependency graph does not justify churn.                                          |
| mise                               | Toolchain SSOT; Ubuntu baseline exit           | **KEEP-WITH-CHANGES** | Correct D3 role. Its DAG is real, but it must not become a second deploy runner.                                                         |
| Gradle                             | Android APK build                              | **KEEP-WITH-CHANGES** | Android-native authority; add locks, SBOM, reproducibility, and certificate lineage before consent.                                      |
| Termux (+api, +x11)                | Android userland, device APIs, UI              | **KEEP-WITH-CHANGES** | Zero-root R4 foundation; split pinned bootstrap artifacts from mutable pkg state.                                                        |
| Shizuku fork                       | User-mediated privileged broker                | **KEEP-WITH-CHANGES** | Required non-root capability, but a high-value upstream/artifact boundary.                                                               |
| FIRERPA/lamda                      | Independent gRPC repair channel                | **KEEP-WITH-CHANGES** | Preserve the fourth tier; authenticate, authorize, rate-limit it as privileged execution.                                                |
| ADB-over-Tailscale                 | Recovery/management transport                  | **KEEP-WITH-CHANGES** | Preserve distinct recovery path; limit 5555 reachability and rotate/pin ADB material.                                                    |
| Tailscale                          | Encrypted mesh transport                       | **KEEP-WITH-CHANGES** | Transport is not fleet authorization. Model ACLs/grants/device tags and review them as release data.                                     |
| SSH CA                             | Short-lived SSH identity                       | **KEEP-WITH-CHANGES** | Good role-identity fit if principals, issuance, revocation and CA custody are explicit.                                                  |
| SecretSpec (+ providers)           | Sole secret declaration schema                 | **KEEP-WITH-CHANGES** | Correct one schema; subprocess injection alone is not per-service authorization.                                                         |
| Vector                             | Edge telemetry transport                       | **KEEP-WITH-CHANGES** | Lightweight fit; make sink credentials, buffering and backpressure fail safely.                                                          |
| OpenObserve                        | Log analysis                                   | **KEEP-WITH-CHANGES** | Keep current O-V-G-O separation; role placement, auth and retention must be declared.                                                    |
| VictoriaMetrics                    | Metrics store/query                            | **KEEP-WITH-CHANGES** | Good low-footprint store; add role placement, auth and backup/restore evidence.                                                          |
| otelcol-contrib                    | Telemetry relay/translation                    | **KEEP-WITH-CHANGES** | Useful interoperability boundary; pin components and deny unreviewed receivers/exporters.                                                |
| Grafana                            | Dashboards/alerts                              | **KEEP-WITH-CHANGES** | Keep provisioned dashboards; isolate admin auth, alert routing and datasource credentials.                                               |
| Caddy                              | TLS ingress/reverse proxy                      | **KEEP-WITH-CHANGES** | Suitable ingress; declare every listener/upstream and treat config as deploy capability.                                                 |
| blackbox_exporter                  | External reachability probes                   | **KEEP**              | Narrow independent observation point; derive targets from facts.                                                                         |
| OliveTin                           | Operator action UI                             | **KEEP-WITH-CHANGES** | Helpful human surface, not authorization; actions need least privilege, auth and audit.                                                  |
| Beads                              | Work ledger                                    | **KEEP-WITH-CHANGES** | Retain provenance, but a task record must never authorize source/release/deploy effects.                                                 |
| Ralph TUI                          | Batch-agent orchestration                      | **KEEP-WITH-CHANGES** | Useful controller; fence worktrees and disable automatic integration for trust-boundary work.                                            |
| Herdr                              | Interactive agent multiplexing                 | **KEEP-WITH-CHANGES** | Good visibility, not isolation; give every agent an owned worktree and mutation scope.                                                   |
| Bare-store task worktrees          | Multi-repo isolation                           | **KEEP-WITH-CHANGES** | Right basic pattern; double-merge proves ownership claims and provenance gates are mandatory.                                            |
| Entangle/Entangled                 | Narrow literate tangle                         | **KEEP-WITH-CHANGES** | Keep only D5 scaffold/tutorial use, with parity CI and a stitch ownership lock.                                                          |
| git + GitHub Releases + gh + ops-v | Versioned source/release train                 | **KEEP-WITH-CHANGES** | Good immutable distribution; a tag/release is not secure-update metadata or authorization.                                               |
| flock/claim files                  | Local contention avoidance                     | **KEEP-WITH-CHANGES** | Useful local serialization, insufficient for distributed leases or release authority.                                                    |
| Python + uv                        | Control tooling/runtime                        | **KEEP-WITH-CHANGES** | Strong dependency workflow; lock and attest release environments.                                                                        |
| Bun                                | JS tooling/runtime                             | **KEEP-WITH-CHANGES** | Fits web/lint tooling; pin lockfiles and do not make it fleet substrate.                                                                 |
| Homebrew                           | Current macOS package source                   | **KEEP-WITH-CHANGES** | Keep under per-package single-writer registry through substrate migration.                                                               |
| apt                                | Ubuntu/Termux bootstrap packages               | **KEEP-WITH-CHANGES** | Required exit primitive; pin sources and minimize installed base.                                                                        |
| Termux pkg                         | Android userland packages                      | **KEEP-WITH-CHANGES** | Keep, explicitly non-reproducible; move sensitive artifacts to verified releases.                                                        |
| minisign/signify                   | Offline Ed25519 verification                   | **KEEP-WITH-CHANGES** | Adopt minisign as small signature primitive, wrapped in threshold/root/freshness metadata.                                               |
| deploy-rs                          | Nix-host activation                            | **KEEP-WITH-CHANGES** | Phase-4 Nix-host tool only, behind signed-plan gate; never owner of non-Nix services.                                                    |
| harmonia/attic                     | Future Nix binary cache                        | **RE-EVALUATE LATER** | Cache-key compromise substitutes executables. Decide after NAR verification and key segregation exist.                                   |
| nixos-anywhere                     | First NixOS bootstrap                          | **KEEP-WITH-CHANGES** | Bounded Phase-4 VPS bootstrap, only after rehearsed out-of-band recovery.                                                                |
| comin                              | Git-pull NixOS converger                       | **REPLACE**           | Rejection is right: generic Git-pull activation lacks signed update protocol and typed executor.                                         |

## Priority 1 — task runner

### Ground truth and correction

The brief’s measured baseline is substantial. The live checkout is larger:
six imported just fragments, 1,668 physical lines across root/imports, and
144 names in just --summary, including compatibility aliases. It uses the
brief’s interpolation, environment, conditional-assignment, shebang,
parameter/default, bash-shell and justfile-directory features. This is an
operator/API interface, not a handful of scripts.

The ideas dump’s “just has no dependency graph” claim is wrong. Just runs
dependencies before dependents, detects cycles, and executes a same-argument
dependency once per invocation. It is deliberately a command runner, not an
incremental build system, so it lacks source/output invalidation and a parallel
scheduler. Only about nine current recipes use dependencies; that missing
capability is not currently a production pain point.

### Does mise cover it?

Yes for task mechanics. Current mise builds a validated DAG; prerequisites
finish before dependents, independent work can run in parallel, and it supports
depends, depends_post, wait_for, sources/outputs, usage arguments,
environment, directory, shell/shebang scripts and task templates. This is a
real DAG, not alias expansion.

It is not a drop-in rewrite. By default mise has four jobs and independent
nodes run concurrently. Naively splitting deploy, secret staging, service
restart and verification would break choreography. Mutable pipelines need
explicit ordered edges/serial arrays or -j 1.

The 152 brace interpolations and 17 just-language conditional assignments do
not mechanically become mise configuration. Mise has Tera for template context,
but its Tera argument functions are deprecated for removal in 2027; supported
arguments are usage environment variables. Most logic should become tested
bash/Python, which is a semantic rewrite. Mise discovers/merges configuration
and offers task files/templates, but it has no exact import equivalent
preserving just’s single namespace and override behavior. Replacing imports
means a new task-directory/config hierarchy with changed names and resolution.

| Option                                     | Assessment                                                                                                       | Decision                     |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| Keep just                                  | Readable verb surface, imports, expressions, arbitrary-language scripts and compatibility; present DAG adequate. | **Recommended**              |
| Move all tasks to mise                     | Gains scheduler/incremental metadata, but converts 144 exposed names and composition semantics.                  | Reject now                   |
| just verbs + mise toolchains/host baseline | Matches D3 and preserves one deploy surface.                                                                     | **Adopt**                    |
| mise DAG + just front end                  | Two graphs and two contracts for a tiny current dependency set.                                                  | Reject                       |
| Task (go-task)                             | Credible YAML DAG/sources; parallel fan-out and template migration without unique benefit.                       | Reject                       |
| make                                       | Ubiquitous DAG, but target/file semantics and portability reintroduce complexity just avoided.                   | Reject                       |
| mask                                       | Markdown command/doc unity helps R9 tutorials, but is not the needed DAG replacement.                            | Re-evaluate for one tutorial |
| moon/turbo                                 | Monorepo build schedulers; this is heterogeneous fleet orchestration.                                            | Reject                       |
| dagger                                     | Container runtime is central, contrary to the no-Docker substrate decision.                                      | Reject                       |
| cargo-make / xc                            | Extra ecosystems, weaker fit than installed cross-platform tools.                                                | Reject                       |

The “mise re-couples D3’s Ubuntu exit” claim is **wrong** if it renders only
toolchains/baseline: mise runs on Ubuntu and supports Linux bootstrap. It becomes
partly real only if moving deploy verbs into mise duplicates Ansible services.
The boundary above avoids that.

**Recommendation, cost, rollback.** Keep just as sole human/CI verb surface
through Phase 4. In Phase 1 add a small tested mise config for pinned runtimes
and mise bootstrap host baseline; neither runner calls the other for deploy.
At the Phase-7 Ubuntu drill, measure one build-only pipeline with at least
three independent expensive nodes. If it earns a DAG, prototype it behind one
new just target, with mise run -j 1 for mutable work. Keep the original just
recipe until matching output, failure and dry-run tests pass. Rollback is
deleting the isolated mise task/config and retaining the existing just target;
the experiment makes no fleet mutation.

## Priority 2 — OpenHands SDK security

Current OpenHands documentation draws the required line:
AlwaysConfirm, ConfirmRisky and NeverConfirm decide whether to ask;
pattern/policy-rail analyzers classify risk; an ensemble returns maximum
severity. They do not hard-deny, and conversation.execute_tool bypasses both
analyzer and confirmation loop.

### Surface A — coding/deploy agents

**Verdict: KEEP-WITH-CHANGES, adopt the technique, not the SDK.** OpenHands
would cover only agents inside its conversation/tool loop; it does not mediate
native CLIs, Herdr/Ralph, gh, git hooks, or direct shells. It would add a
framework while failing closed nowhere important.

Vendor a small deterministic preflight pattern instead: normalize a proposed
command/effect record; match deny/confirm rails (destructive paths,
history/merge/push, secrets, network-to-shell and privilege escalation);
default unknown high-impact effects to stop; then require owned-worktree claim
and existing pre-merge provenance checks. Run it in launch wrappers, not
prompts. It would have made the 2026-08-06 incident harder by checking
ownership/provenance, but cannot prove a benign-looking diff safe. Cost:
policy schema, wrapper integrations and adversarial tests; it is not a sandbox.

### Surface B — fleet trust/consent

**Verdict: REPLACE: no OpenHands component belongs in authorization.** An LLM
or regex analyzer may produce a T2 advisory explanation, never a grant.
RT-03/RT-04 require independently verified typed-operation IR and an executor
that hard-denies undeclared file, process, network, secret, package, service
and Shizuku effects. Borrow maximum-severity composition only for
non-authoritative analysis. The real replacement cost—IR, signed grants,
local reference monitor, monotonic state, negative tests and recovery—is a
Phase-5/6 blocker.

## Required changes to kept tools

### Config, recovery, Android and network

- **Ansible:** render descriptors from Site Model with writer-namespace lint;
  retain check/diff only as plan evidence. Before pull, map every play to typed
  operations or restrict v1 to executor-owned operations. Cost is role-by-role
  descriptor/plan work; rollback is current push-only adapters.
- **CFEngine:** retain a signed, size-bounded policy and least-privileged repair
  allowlist. Limit targets, rotate credentials, rate-limit runs, add restart
  circuit-breaker and audit. Cost is policy audit plus live-device soak;
  rollback is explicit operator recovery to current policy.
- **Termux, Shizuku, FIRERPA and ADB:** preserve independent paths, but add
  caller/endpoint allowlists, version/digest policy and revoke/kill procedure.
  Gradle privileged APKs need locks, SBOM, isolated reproducible comparison,
  certificate policy, and permission/exported/Shizuku/network deltas before
  consent. This is RT-08 cost, not a tool swap.
- **Tailscale and SSH CA:** add a network-policy registry covering tags,
  ACL/grant subject-destination-port rules, SSH principals and issuance. CI
  compares it to services/ports; only operator release changes it. Tailscale
  encryption does not replace application authorization. Use short SSH certs,
  constrained principals, audited issuance and threshold CA rotation.
- **SecretSpec:** retain one declaration schema, add a signed
  service-identity/host-role/capability/release-sequence-to-handle resolver.
  Deliver per-service credential files/OS credentials, not inherited
  environment. Cost is provider-wrapper/service-contract work, not moving
  secret values.

### Observability and human actions

Keep O-V-G-O as separate roles, not a new platform. Vector/otelcol need export
allowlists, bounded queues, TLS/auth and redaction. OpenObserve/VictoriaMetrics
need retention, backup/restore and role-failover tests. Grafana needs
provisioned datasources and distinct admin credentials. Generate Caddy and
blackbox targets from registries. Make each OliveTin action a named,
server-authorized capability with audit—never a raw shell escape hatch. These
are configuration migrations; keep current services until declared-role
deployment survives soak.

### Agent, literate, release and packages

Beads/Ralph/Herdr and bare stores survive because they coordinate work, not
trust. Enforce one owner per worktree, durable claim, clean isolated release
checkout, and two-person review for executor/policy/secret/privilege changes.
flock coordinates local processes only; distributed single-writer roles need
fenced signed epochs or remain manual. Entangled stays D5-narrow with
tangle-parity CI and stitch ownership lock.

Keep GitHub Releases and ops-v as immutable distribution, but add TUF-like
threshold root/release metadata, expiry/channel/target binding, persisted
high-water marks, revocation and out-of-band recovery. Minisign is the offline
signature floor, not this update protocol. gh must not sign/publish from task
worktrees.

Keep uv/Bun for project tooling and Homebrew/apt/pkg for bootstrap, with
explicit package owner and locked/attested inputs. pkg is not reproducible;
security-sensitive Android artifacts must be verified release assets. Nix
eventually owns substrate packages only where generation rollback earns cost.

For Phase 4, nixos-anywhere suits the disposable VPS and deploy-rs may activate
Nix closures there; neither replaces Ansible services or signed-plan
authorization. Defer Harmonia-versus-Attic until a second Linux consumer exists.
Harmonia is the likely first experiment only after separate build/upload/serve/
release keys, independent critical rebuilds and signed NAR inventory checks.
Its cost is key custody, revocation drill and monitoring, not hosting. Comin
stays rejected: normal Git-pull activation is the generic converger the red
team says must not be trusted; build a small verified pull client instead.

## Decision gates

1. **Before Phase 1:** ownership, network and package registries; mise only
   for toolchain pins/host-baseline proof.
2. **Before Phase 4:** prove NixOS bootstrap/recovery and Ansible systemd
   adapters without moving a production service owner.
3. **Before Phase 5 pull:** threshold update metadata, replay/freeze defense,
   provenance, cache containment, SecretSpec reference monitor, bounded typed
   executor and hostile-mirror/resource tests.
4. **Before Phase 6 consent:** Android provenance plus expiring, target-key-
   bound, single-use grants enforced by that executor. No tool verdict relaxes
   these blockers.

## Capability sources checked

- [mise task architecture](https://mise.jdx.dev/tasks/architecture.html),
  [running tasks](https://mise.jdx.dev/tasks/running-tasks.html),
  [TOML tasks](https://mise.jdx.dev/tasks/toml-tasks.html),
  [templates](https://mise.jdx.dev/tasks/templates.html), and
  [configuration](https://mise.jdx.dev/configuration.html): DAG, default
  parallelism, serial mode, sources/outputs, templates and configuration.
- [just dependencies](https://just.systems/man/en/dependencies.html),
  [imports](https://just.systems/man/en/imports.html), and
  [manual overview](https://just.systems/man/en/): dependency/module semantics.
- [OpenHands Security & Action Confirmation](https://docs.openhands.dev/sdk/guides/security):
  analyzer/confirmation behavior and direct-call bypass.
- [Task dependencies](https://taskfile.dev/docs/guide),
  [mask README](https://github.com/jacobdeichert/mask), and
  [Dagger overview](https://docs.dagger.io/): alternative models.
- Local evidence: architecture-final-v1.md, redteam-trust-layer-openai-v1.md,
  ideas-dump-claude.md, live ~/ops justfiles/inventory/registries, and
  /Users/djbclark/src/ops-worktrees/README.md. No secret values were read.
