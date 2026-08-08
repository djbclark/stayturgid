# stayturgid 2.0 — Declarative Ops Architecture Proposal & Migration Plan (v1)

> **🔒 PROTECTED DOCUMENT — AI agents: DO NOT MODIFY this file without
> explicit, specific human (operator) approval given for a named change.**
> Blanket instructions like "fix docs" or "update stale references" do NOT
> authorize edits here. Propose changes as a separate review document or a
> GitHub issue instead. This rule binds all agents (Claude Code, Hermes,
> Codex, Ralph controllers, `agy`, and any future agent).

- **Status:** Proposal v1 — awaiting operator review
- **Date:** 2026-08-08
- **Author:** Claude (Anthropic, Claude Fable 5), via interactive dialogue
  with the operator (djbclark). Decisions attributed to the operator in
  §2/Appendix A were stated by him; everything else is recommendation.
- **Scope:** Successor architecture for the `~/ops` suite (stayturgid,
  site-djbclark, site-private + ops-djbclark control plane) across macOS
  (Apple Silicon), Linux (x86_64 + aarch64), and Android — with designed
  extension points for IoT, iPhone, microcontrollers, smartglasses,
  smartwatches, and routers.
- **Competing proposals:** This document will be compared against proposals
  from other AI agents. It is self-contained.

---

## 1. Executive summary

**Verdict on the four evaluated options:** none of them is the spine.

| Option | Category | Verdict |
| --- | --- | --- |
| `bgub/nix-macos-starter` | Single-host macOS starter (nix-darwin + home-manager + mise + brew) | **Pattern donor only.** Validates the mise-inside-home-manager and declarative-Homebrew patterns. No Linux, no fleet, no multi-host story. |
| `mrkuz/macos-config` | Personal modular nix-darwin flake | **Structure donor.** Steal the host/user/module decomposition with declared options, and the remote-Linux-builder posture. Not a framework; his NixOS side is unmaintained. |
| Devbox (Jetify) | Per-project dev environments (JSON over Nix) | **Rejected for the spine; optional per-repo tool.** Answers "what is in this project's shell," not "what state should this machine converge to." |
| Devenv.sh | Per-project dev environments (Nix language, processes, hooks) | **Adopted narrowly**: candidate replacement for per-repo toolchain/services setup inside `~/src` repos where useful. Never a system layer. |

**The recommended architecture** is a fifth thing the option list implied
but did not contain — and it is shaped by three operator constraints that
rule out every off-the-shelf answer: (1) NixOS is acceptable **only with a
cheap exit** to a conventional distro; (2) Android **cannot** run Nix
on-device; (3) the end-state has **no control node** — any macOS/Linux box
holds an arbitrary set of feature roles as main/backup/equal peer.

The only design that satisfies all three is one where **the source of
truth is a tool-neutral data model, and every config system is a thin,
replaceable adapter over it**:

1. **The Site Model** (§4) — machine-readable YAML/JSON: hosts, taxonomy,
   feature roles, role assignments (main/backup/peer), service definitions,
   and the existing port/path registries. It generalizes what
   `site-djbclark` already does right (`inventory/hosts.yml` as the only
   home of site facts; `registry/*.yml` as allocation authorities). All
   logic elsewhere is generic; all facts live here.
2. **Adapters** (§5) — consumers of the Site Model, one per platform
   paradigm: **nix-darwin + home-manager** on the Mac; **NixOS** on the
   greenfield Linux boxes; **mise bootstrap** held as the certified
   non-Nix exit adapter (its `[bootstrap.linux.systemd.units]` /
   `[bootstrap.macos.launchd.agents]` surface consumes the same service
   registry on an Ubuntu box); **Ansible + CFEngine + stayturgid-agent**
   unchanged as the Android adapter. Leaving NixOS later means swapping an
   adapter, not rewriting the world.
3. **No VMs anywhere** (§6). Linux closures come from public-cache
   substitution + build-on-target at first, growing into a declared
   `builder` feature role on real Linux hardware plus a Tailscale-internal
   signed binary cache. The nix-darwin `linux-builder` VM is explicitly
   rejected.
4. **Every deploy — push or pull — flows through a signed release manifest
   plus a machine-readable change plan** (§7). This is the v1 seed of the
   consent/trust/"config app store" vision: the same artifact a `just`
   push consumes today is what a consent prompt, a user-side AI advisor,
   and a web-of-trust policy consume later. Interfaces are specified now
   (§12); heavy machinery is roadmap.
5. **Selective literate programming** (§10): entangle for high-subtlety
   glue with agent-facing rationale kept and human-facing asides stripped
   from agent context; plain code elsewhere; `stitch` as the mechanism
   that lets agents edit cheap tangled files while the literate source
   absorbs changes.
6. **Free Sysadmin publishing** (§11): the generic layer is quarantined
   for extraction into a public repo (working name `freeops`) so the FSF —
   or anyone — can publish glue without publishing facts.

---

## 2. Requirements & constraints (operator-stated)

Normative inputs from the dialogue. R-numbers are referenced throughout.

- **R1 Targets:** macOS/Apple Silicon, Linux/x86_64, Linux/aarch64,
  Android. Intel Mac mini is out of scope.
- **R2 Roles, not control node:** control node switchable macOS↔Linux now;
  end-state is per-feature main/backup/equal-peer assignment on any
  macOS/Linux box.
- **R3 Resource efficiency:** do not solve problems with resources. VM use
  minimal to none; no fat container images.
- **R4 Android reality:** Termux (+ `termux:api`, `termux:x11`), the
  built-in Android Terminal app, Shizuku fork, and stayturgid-agent stay.
  No nix-on-droid (storage + memory + process contention). Nix may serve
  Android only as a zero-footprint artifact builder.
- **R5 NixOS with exit:** NixOS acceptable first on greenfield Linux, but
  moving to e.g. Ubuntu Server later must be "pretty easy."
- **R6 APK builds:** Shizuku + stayturgid-agent keep Gradle; the suite
  orchestrates invocation and deployment; APK builds must not drive
  architecture.
- **R7 Push AND pull deploys**, evolving toward consent-based deploys for
  untrusted devices: contractually valid change descriptions, user-side AI
  advisor, opt-in feature sets, local-fix-until-upstream-heals, graded
  web-of-trust with durable attestations.
- **R8 Trust layer scope for v1:** specified interfaces + minimal
  implementations; WoT/advisor phases as architecture-sketched roadmap.
- **R9 Literate programming:** depth calibrated to what Sonnet-5 /
  DeepSeek-v4-Pro-class agents handle well; token cost and code quality
  govern; rich human narrative desired where it does not tax agents.
- **R10 Free Sysadmin:** architecture must let the FSF (and others)
  publish generic sysadmin glue safely — free software extended to the
  glue between programs.
- **R11 Existing invariants preserved:** `~/src` as definitive source +
  worktree discipline; `ops-vX.Y.Z` coordinated release train; secretspec
  as the single secrets authority; CFEngine as on-device self-heal and
  last-ditch remote fallback; observability stack (Vector, OpenObserve,
  VictoriaMetrics, otelcol-contrib); Beads/Ralph agent orchestration.

---

## 3. Evaluation detail

### 3.1 bgub/nix-macos-starter
A clean, current expression of nix-darwin + home-manager + declarative
Homebrew (`nix-homebrew`) + mise-for-runtimes on one Mac. Its value here:
(a) confirms mise and home-manager coexist without fighting when mise owns
per-project runtimes and Nix owns global packages; (b) its
`darwin/ | home/ | hosts/` split is a sane minimal layout. Its limits: one
host, one OS, no services story beyond defaults, no secrets, no fleet.
**Use as reference, adopt nothing wholesale.**

### 3.2 mrkuz/macos-config
The most architecturally instructive of the four: hosts and VMs as
expressions, per-user Home Manager trees, feature modules with declared
options, pragmatic install-source policy (App Store via `mas` for Apple
software, Homebrew for proprietary/DMG, Nix for the rest), flake-compat
shim, and a documented remote-Linux-builder requirement for building Linux
packages from macOS. **Adopt:** module-with-options decomposition; the
install-source policy nearly verbatim; the remote-builder posture (on real
hardware, §6 — not his VM tooling, per R3). **Ignore:** the VM/QEMU
machinery, single-person hardcoding.

### 3.3 Devbox
JSON-config Nix wrapper, per-project shells and services, exports to CI.
Good tool, wrong layer: nothing in it addresses system convergence, hosts,
or fleets, and its abstraction (hide the Nix language) removes exactly the
expressive power the adapters need. **No role in the architecture.**
Individual `~/src` repos may still use it privately if convenient.

### 3.4 Devenv.sh
Real Nix, per-project processes/services/git-hooks, container export.
Same category limit as Devbox, but because it is plain Nix it composes
with the suite flake. **Optional per-repo adoption** where a repo wants
declarative dev services (e.g. a repo needing a local Postgres); never
required, never system-level. Note: devenv's maintainer also builds
`secretspec` — the ecosystems already interoperate deliberately.

### 3.5 Alternatives scanned and not chosen as spine
- `dustinlyons/nixos-config`, `nixologist/macnix-config`: better
  dual-OS starters than the two evaluated, still single-operator
  workstation configs, not fleet spines. Reference material for
  darwin+NixOS flake wiring and agenix bootstrap flows.
- Pure Ansible-everywhere (status quo extended): satisfies R5's exit
  trivially but forfeits reproducibility, rollback generations, closure
  diffs (needed by R7's change plans), and the Nix ecosystem; rejected.
- Guix: philosophically closest to R10, but no macOS host management,
  much smaller ecosystem, and would strand the Nix investment; noted for
  the Free Sysadmin narrative, rejected for the stack.

---

## 4. The Site Model (the spine)

**Principle:** *facts and intent in data; behavior in generic, publishable
code; adapters translate.* This is R2, R5, and R10 satisfied by one
mechanism — role assignment is data (so "who is main for feature X" is an
edit, not a re-architecture), exit from NixOS is an adapter swap, and the
generic layer is publishable because it contains nobody's facts.

### 4.1 Contents
Extends what already exists rather than inventing a parallel scheme:

- **`inventory/`** (exists) — hosts + taxonomy groups. Gains non-Android
  hosts as first-class entries and, per host, `arch`, `platform`,
  `adapter` (`nix-darwin` | `nixos` | `mise` | `android`), and
  `trust_tier` (`operator` | `managed` | `consented` — R7's future
  untrusted devices enter here, not via a new system).
- **`registry/ports.yml`, `registry/paths.yml`** (exist) — unchanged as
  allocation authorities; the Nix adapters gain eval-time asserts against
  them (a NixOS service declaring a port not in the registry fails the
  build — the registry lint becomes unskippable).
- **`registry/services.yml`** (new) — service definitions: name, runs-as,
  command, env (secretspec key *names* only), platform notes, role
  binding. The current launchd plists / systemd units / mise agents are
  all renderings of one such record.
- **`registry/roles.yml`** (new) — feature roles (`litellm`, `hermes`,
  `observability-sink`, `builder`, `cache`, `deploy-origin`,
  `adb-reconnect`, …) and per-role assignment:
  `role → {main: host, backups: [host…], peers: [host…]}`. **This file is
  the no-control-node mechanism**: "control node" dissolves into a set of
  role assignments; switching Mac↔Linux for any function is a one-line
  change (R2).
- **Schema + lint** — JSON Schema for all of the above, enforced by the
  existing `registry_lint.py` pattern in CI and pre-commit.

### 4.2 Placement
Site Model lives in **`site-djbclark`** (it is site data; that repo is
already the allocation authority). Generic adapter code starts under a
quarantined `freeops/` subtree there (or in stayturgid where
Android-generic), written from day one as if public: no operator facts, no
hostnames, no secrets — extraction to a standalone public repo is then
`git filter-repo`, not surgery (§11).

### 4.3 Consumption
Nix reads it natively (`builtins.fromJSON` / `fromTOML`; YAML via a
committed generated JSON twin, produced by the same lint step, to keep
eval pure). Ansible reads it as vars files it already understands. mise
bootstrap TOML for an exit-hatch host is *generated* from
`services.yml` + `roles.yml` by a small script — the exit is mechanical.

---

## 5. Platform adapters

### 5.1 macOS (Apple Silicon) — nix-darwin + home-manager
- **Flake** at `site-djbclark/flake.nix` exposes
  `darwinConfigurations.<host>` (and the NixOS outputs of §5.2), importing
  generic modules from `freeops/` and instantiating them with Site Model
  data.
- **Layer ownership (the decision the dialogue left to me):**
  1. *Packages, shell, dotfiles, macOS defaults, declarative Homebrew:*
     **nix-darwin + home-manager**, replacing ad-hoc brew state. mrkuz's
     install-source policy applies (mas for Apple, brew for
     proprietary/DMG, Nix otherwise).
  2. *User services (launchd agents):* **end state is home-manager**
     (generated from `services.yml`), because generations + rollback of
     the whole service layer is the strongest recovery story and closure
     diffs feed §7's change plans. **Transitional state is Ansible**, which
     owns them today. Migration is per-service behind a single boolean in
     `services.yml` (`managed_by: ansible | nix`), and the Ansible role
     learns to *remove* its plist when a service flips — the two-writers
     hazard is resolved by making ownership a Site Model fact, never a
     race.
  3. *mise:* retained for per-project runtimes in `~/src` (unchanged), and
     its **bootstrap surface is deliberately kept warm as the exit
     adapter** (§5.3) — we do not use `[bootstrap.macos.launchd.agents]`
     on the Mac while nix-darwin is in play (three writers is worse than
     two), but the generator that emits mise TOML from `services.yml` is
     built and CI-tested against a throwaway host entry, so the exit path
     is continuously proven, not aspirational.
  4. *Dev toolchains inside repos:* mise (status quo) or devenv per repo
     preference; invisible to the system layer.
- **Never moved to Nix:** anything Apple-signed/entitlement-bound (per
  install-source policy), and the live agent stack's runtime state.

### 5.2 Linux (greenfield VPSs + any future physical boxes) — NixOS
- `nixosConfigurations.<host>` from the same flake; same generic modules;
  host facts from the Site Model. First target: `vps-primary` (Hetzner;
  aarch64 recommended for price/perf — an x86_64 sibling follows when a
  second box is justified, conveniently covering both Linux arches for the
  builder role).
- **Exit design (R5), concretely:** (a) all service semantics live in
  `services.yml`, so the NixOS module layer contains no knowledge that
  isn't regenerable; (b) no NixOS-only primitives in service *contracts* —
  services are plain systemd units + files + packages, the three things
  every distro has; (c) the mise-adapter generator (§5.3) is the tested
  translation; (d) an "exit drill" is a standing CI job: render
  `vps-primary` as mise-on-Ubuntu output and shellcheck/dry-run it. Exit
  cost ≈ provision Ubuntu, run generated bootstrap, restore state — the
  same class of task as the panel-app reimplementations the operator
  already budgets for AI.
- **State discipline:** declarative config never contains state; app state
  lives under registered paths (`registry/paths.yml`) with restic/borg
  backup as a `services.yml` entry — this is what makes both NixOS
  rebuilds *and* the exit cheap.

### 5.3 Exit adapter — mise bootstrap (certified, dormant)
mise's bootstrap surface (declarative packages across brew/apt/dnf,
dotfiles, `[bootstrap.linux.systemd.units]`,
`[bootstrap.macos.launchd.agents]`, `dev.mise.*`-prefixed ownership
fencing, `status --missing` for convergence checking) is the designated
non-Nix implementation of the adapter contract. It is forward-only (no
generations) — acceptable for an exit or for future low-priority boxes,
with git-revert + re-apply + CFEngine as its recovery story. A
`freeops/gen/mise-adapter` script renders any Site Model host into
`mise.toml`; kept green by CI (§5.2). This is also the natural adapter for
future "guest" machines too small or too foreign for Nix.

### 5.4 Android — unchanged stack, new lanes
- **Unchanged (R4):** Termux runtime, Ansible collections, Shizuku fork,
  stayturgid-agent, CFEngine self-heal + remote fallback, FIRERPA backup
  channel, SSH CA, Tailscale.
- **New lane 1 — Nix-built artifacts, zero on-device footprint:** the
  `builder` role can cross-build static (musl / Termux-target) aarch64
  binaries; they deploy as ordinary files via the existing Ansible roles,
  content-addressed (store hash recorded in the deploy manifest). Use
  selectively: pinning a fussy tool fleet-wide, shipping what Termux's
  repos lack. Never a `pkg` replacement.
- **New lane 2 — APK orchestration (R6):** Gradle builds stay as-is,
  invoked by `just` targets the suite flake wraps (`nix run
  .#build-agent` → same Gradle, pinned JDK from Nix on the invoking host
  only). Outputs are hashed, recorded in the release manifest, deployed by
  the existing `just agent-rollout` path. Reproducible-APK work is
  roadmap (§12), valuable for R7's trust story, not required now.
- **stayturgid-agent 2.0 scope:** grows two suite-facing interfaces —
  the **consent surface** (§7.4) and **peer control** (device-from-device
  screen use; the parked `tablet-control-phone` experiment becomes the
  role `peer-display` in `roles.yml`, unblocking it as data rather than a
  fork of the architecture).

### 5.5 Future device classes (extension points, no build-out now)
- **Routers:** NixOS-on-router where hardware allows; otherwise OpenWrt
  with uci config rendered from the Site Model (same adapter contract).
- **iPhone / smartglasses / smartwatches:** never converge-managed;
  modeled as `trust_tier: consented` endpoints reachable via
  companion-app/shortcut adapters; they consume services, appear in
  inventory, and receive artifacts only.
- **Microcontrollers:** firmware = Nix-built artifact (cross-compile is
  what nixpkgs is genuinely good at here); flashing is a `just` lane; the
  device is inventory + artifact, not a convergence target.

---

## 6. Build & distribution topology (no VMs — R3)

- **Darwin closures:** built on the Mac (native).
- **Linux closures, phase 1 (now → first VPS):** *build-on-target with
  public-cache substitution.* `nixos-rebuild switch --flake` on the box
  (or `deploy-rs` with `remoteBuild = true`); ≳95% of paths substitute
  from cache.nixos.org; the box evaluates and links. Cost ≈ zero; works
  from any deploy origin including the Mac.
- **Phase 2 (second Linux box / first non-substitutable artifacts):**
  declare `builder` as a feature role in `roles.yml` → rendered into
  `nix.buildMachines` on consumers and a builder profile on holders.
  Real hardware only; ARM + x86 boxes cover both Linux arches natively.
  Add role `cache`: **harmonia** (simplest; serves the holder's own store,
  read-only, negligible overhead — preferred under R3) or **attic**
  (multi-uploader, GC'd, better once several builders exist) over
  Tailscale, signed with a fleet Nix signing key; all hosts list it as a
  substituter. Build once, substitute everywhere.
- **Trust:** builders are fully trusted by consumers — bound to the
  existing SSH CA (builder SSH host keys CA-signed; dedicated
  `nix-builder` principal), and cache paths are signature-checked.
  Compromise of a builder is compromise of its consumers; therefore
  builders are `trust_tier: operator` hosts only, forever.
- **Failure mode:** offline/degraded ⇒ no *fresh* Linux builds; cached
  closures still deploy; CFEngine still heals. Accepted (R3 over
  availability of a local VM builder).
- **Explicitly rejected:** `nix.linux-builder` VM on the Mac; Docker as a
  build or run substrate; Rosetta/qemu-binfmt emulation builds (allowed
  ad hoc for one-off debugging, never in the deploy path).

---

## 7. Deployment, releases, and the consent seed

### 7.1 Release train (unchanged contract, extended payload)
`ops-vMAJOR.MINOR.PATCH` coordinated releases remain the only way code
reaches deploy checkouts (`just ops-release-*`; `ops-memory-sync` stays
the sole data exception). New: a release additionally publishes a
**release manifest**.

### 7.2 Release manifest + change plan (the R7 seed, R8-scoped)
Per release, per host, two artifacts, both signed:

- **`manifest.json`** — release id; per-host adapter + closure hash (Nix
  hosts) or playbook set + artifact hashes (Android); APK/Shizuku artifact
  hashes; signing identity. Signing: **minisign/signify** key now (small,
  boring, auditable), key id recorded in the Site Model; TUF-style role
  metadata is the roadmap upgrade path, not reinvented today.
- **`plan/<host>.txt|json`** — the machine-readable "what will change":
  Nix hosts: `nix store diff-closures` between current and proposed
  system (package/version/size deltas — *verifiable*, not narrated);
  Android: `ansible-playbook --check --diff` output + artifact hash
  deltas; mise hosts: `mise bootstrap status --missing` + dry-run.
- These artifacts are **consumed identically by push and pull**, and they
  are the contract the future consent prompt, AI advisor, and WoT policy
  evaluate (R7). Nothing about the trust roadmap requires changing this
  format later — only adding evaluators of it.

### 7.3 Push and pull (both first-class — R7)
- **Push:** `just deploy-host <host>` / `just deploy-fleet` from any host
  holding role `deploy-origin` (plural holders; R2). Implementation:
  `deploy-rs` for Nix hosts (rollback-on-failure, `--build-on-target`
  default), existing Ansible entry points for Android. Interactive dev
  pushes to a designated scratch host bypass the release train explicitly
  and are labeled as such in telemetry.
- **Pull:** a ~50-line converge agent (systemd/launchd timer; part of
  `freeops/`): fetch latest `ops-v*` tag → verify signature → if new,
  apply own host's closure/playbook → report. Any host with role
  `pull-converge` self-updates; a fleet with every host pulling and no
  `deploy-origin` assigned **is** the no-control-node end state — reached
  by editing `roles.yml`, not by new machinery. (comin was evaluated;
  rejected for now as NixOS-only and less transparent than owning 50
  auditable lines that also run on macOS and Termux.)
- **CFEngine:** unchanged beneath both — self-heal and the
  remotely-triggered last-ditch path. Its promises gain one addition:
  verify the converge agent itself is alive.

### 7.4 Consent surface (interface specified now, minimal impl)
stayturgid-agent 2.0 exposes, for `trust_tier: consented` devices:
`offer(manifest, plan) → {accept | reject | timeout(policy_default)}`,
rendered as an on-device prompt showing the human-readable plan; decision
+ manifest hash appended to an append-only local log, mirrored to the
suite's transparency log (§12). v1 implementation: the prompt, a
yes/no, the log. Advisor hooks, feature-set opt-in catalogs, and WoT
evaluation attach to this same interface later (R8).

---

## 8. Secrets

- **secretspec stays the single authority** (R11) — the unified
  `site-private/secretspec.toml` continues to declare what exists, where,
  and why. The trio-symlink consolidation and value-migration work in
  flight (site-private#37) proceeds unchanged.
- **Nix rule:** no secret values at eval time; nothing secret in any
  store. Units/agents get secrets at *activation/runtime* via
  `secretspec`-wrapped ExecStart / launchd wrappers (pattern already in
  use for LaunchAgent env injection — it generalizes).
- **agenix/sops-nix:** *not* adopted for the general case (a second
  authority violates the single-source rule). One narrow permitted use:
  host-bootstrap material that must exist before secretspec can run
  (machine SSH host keys for CA signing, the Nix cache signing key),
  encrypted to host keys, stored in site-private. Documented as the
  explicit, bounded exception.
- **Trust-tier rule:** `consented` devices never receive site secrets;
  the manifest schema structurally cannot reference secretspec keys for
  them (lint-enforced).

## 9. Observability

Stack unchanged (Vector, OpenObserve, VictoriaMetrics, otelcol-contrib;
R11); its *placement* becomes `roles.yml` data (`observability-sink`
main/backup — today the Mac, movable to a VPS by data edit, per R2) and
its units become `services.yml` entries rendered by adapters (the current
hand-tended vector plist becomes generated). Additions: the converge
agent, deploy-rs wrapper, and Ansible callback all emit deploy events
(release id, host, plan hash, outcome, duration) into the existing
pipeline — making the release train itself observable, which the trust
layer later requires anyway (an advisor that can't see deploy history
can't advise).

## 10. Literate programming policy (R9)

Grounded in the current research (agent context files measurably help and
agents follow them; comment *removal* improved long-context benchmark
performance for most models; agents spend ~⅔–¾ of tokens reading files;
selective commenting beats blanket commenting):

1. **Two prose classes, mechanically separated.** *Rationale* (intent,
   invariants, interdependencies) lives adjacent to code and IS agent
   context. *Narrative* (humor, history, essayistic asides — wanted for
   humans and for Free Sysadmin publishing) lives in marked blocks that
   the agent-facing tangle **strips** and the human-facing weave keeps.
   Full Knuthian richness for readers; zero per-agent-run token tax.
2. **Selective literacy.** Literate (entangle) sources for high-subtlety,
   high-explanation-value glue only: CFEngine failsafe policies, consent
   machinery, SSH CA flows, the Site Model schema itself, the converge
   agent. Ordinary config stays plain with terse comments.
3. **`stitch` is the cost-control mechanism.** Agents edit *tangled* plain
   files with normal tooling and cheap targeted reads; entangle stitches
   changes back into the literate doc. Full-document context is paid only
   for intent-level work.
4. **Structure rules:** chunks file-aligned (≈1 chunk : 1 file), minimal
   noweb indirection (indirection is simulation burden for models); CI
   gate asserting tangle(doc) == committed code so representations cannot
   drift.
5. **Boundary docs stay the primary documentation investment** (AGENTS.md
   files, per-role design docs, registries) — this is where the evidence
   says tokens buy the most correctness, and it is already house style.
6. **Tool commitment:** entangle-the-tool is used but not load-bearing —
   rule 4's CI gate means any tangle-compatible tool could replace it;
   the *practice* is the requirement.

## 11. Free Sysadmin publishing (R10)

- **Quarantine discipline from day one:** everything under `freeops/`
  (generic modules, adapter generators, converge agent, manifest tooling,
  schema) is written containing zero site facts — reviewed as if public,
  because it will be. Site facts enter only via Site Model instantiation.
  Extraction to a standalone public repo happens when it stabilizes
  (target: end of Phase 4) — the same product/site/private split
  stayturgid already proved, generalized.
- **Licensing recommendation:** code **GPLv3-or-later** (glue and modules
  are the freedom being extended; copyleft is the point of the exercise —
  Apache/MIT would invite proprietary re-enclosure of exactly the layer
  R10 aims to free); literate docs **CC BY-SA 4.0** (dual with GPLv3 for
  tangled chunks); the future networked trust services **AGPLv3**.
  Operator + FSF may of course decide otherwise; the architecture is
  license-neutral.
- **The FSF story this enables:** an org publishes its `freeops`-style
  generic layer + Site Model *schema* while its filled-in Site Model and
  secrets stay private; reproducible builds + signed manifests +
  transparency log let outsiders verify that published glue is what
  actually runs. "Free Configuration Management" = publishable glue +
  verifiable deployment.

## 12. Roadmap: trust / consent / WoT (R8 — interfaces now, machinery later)

| Phase | Deliverable | Builds on |
| --- | --- | --- |
| T0 (in §7) | Signed manifests, change plans, consent surface v1, deploy telemetry | Release train |
| T1 | Transparency log: append-only (Rekor-style; sigstore tooling evaluated first, blockchain explicitly not required) recording releases, consent decisions, attestations | T0 |
| T2 | Advisor API: `advise(manifest, plan, history) → risk assessment`, pluggable model, runs device-side or on a user-chosen host | T0, T1 |
| T3 | Feature-set catalog: opt-in roles for consented devices ("config app store"); opted-in features persist in the device's Site Model overlay and ride future releases | consent v1 |
| T4 | Local-fix / upstream-heal loop: local patch branch + auto-filed issue; converge agent prefers upstream once a release containing the fix is signed and advisor-cleared | T1, T2 |
| T5 | Web of trust: TUF-style role/threshold metadata; graded trust policies ("anyone trusted by 2 members of set S at level X, with safeguards Y") evaluated against T1's attestation log — including human-ritual attestations (the phone-call vouch) as first-class log entries | T1, T2 |
| T6 | Reproducible APK + artifact provenance (SLSA-style) so consented devices can verify, not just trust | T0 |

## 13. Migration plan

Each phase ends at a working system and a rollback point; the suite stays
deployable throughout. Phases ride the normal `ops-v` train.

- **Phase 0 — Foundations (no behavior change).** Site Model schema +
  lint; `services.yml`/`roles.yml` populated by *transcribing* current
  reality (Ansible stays the executor); registries gain the schema.
  CI: lint + schema + (later phases') adapters build. *Rollback: delete
  files.* Exit criterion: every currently-running service and role
  assignment is represented and lint-clean.
- **Phase 1 — Mac under nix-darwin (packages/env only).** Flake +
  `darwinConfigurations.m1-air`; nix-darwin owns packages, shell,
  dotfiles, defaults, declarative Homebrew; **services untouched
  (Ansible)**. Brew state reconciled into `homebrew.nix` before first
  switch. *Rollback: `darwin-rebuild --rollback`; brew unaffected.*
- **Phase 2 — First NixOS host.** Provision `vps-primary` (Hetzner ARM)
  via nixos-anywhere; roles per `roles.yml` (start: `litellm` backup +
  `observability-sink` backup); deploy-rs wired; build-on-target;
  exit-drill CI job (render + dry-run mise/Ubuntu twin) turns on.
  *Rollback: NixOS generations; or destroy VPS (roles fall back to
  main).* This phase also proves R2: flip one role's main to the VPS and
  back as an acceptance test.
- **Phase 3 — Service migration on the Mac.** Per-service
  `managed_by: ansible → nix` flips, low-risk first (vector → litellm →
  control-node daemons → Hermes last); Ansible removes what it loses;
  each flip is one commit, one release, individually revertible. Exit
  criterion: Ansible manages no launchd on the Mac (its macOS role
  retires; Android role untouched).
- **Phase 4 — Release manifests + pull converge.** Manifest/plan
  generation in `ops-release-*`; signing key ceremony; converge agent on
  all operator hosts (timer-driven pull as steady state, push retained);
  deploy telemetry flowing. `freeops/` extraction readiness review.
- **Phase 5 — Builder/cache roles (triggered, not scheduled).** When the
  second Linux box or first non-substitutable artifact arrives:
  `builder` + `cache` roles live (§6 phase 2), Android artifact lane
  available, CA-bound builder trust.
- **Phase 6 — Consent v1 (agent 2.0).** Consent surface + log in
  stayturgid-agent; first `trust_tier: consented` device is a test
  device already in the fleet; T1+ per §12 thereafter.

**Sequencing rationale:** 0–1 are risk-free and immediately useful; 2
front-loads the strategic unknown (NixOS fit + exit drill) while it is
cheap to abandon; 3 waits until Nix habits exist before touching live
services; 4 is prerequisite to everything in §12; 5–6 are demand-driven.

## 14. Risks & open items

- **Two-writer window in Phase 3** — mitigated by `managed_by` as the
  single ownership fact + Ansible's remove-on-flip, but the flip commits
  deserve extra review.
- **nix-darwin churn across macOS majors** — historically breaks briefly
  at OS releases; policy: pin flake inputs, upgrade inputs deliberately,
  never same-day with an OS update.
- **VPS resource ceilings for the builder role** (R3) — mitigated by
  substitution-first and zram; if a build ever needs a bigger box, rent
  hourly, build, destroy — never a standing VM.
- **Entangle bidirectional edge cases** (stitch conflicts under
  concurrent agent edits) — the CI tangle-gate catches drift; conflicts
  resolve doc-side by the workspace owner per existing cross-agent rules.
- **Open (parameters, not forks):** Hetzner instance sizing; which
  panel-apps land on `vps-primary` first; harmonia vs attic (defer to
  Phase 5 facts); minisign vs signify (either; pick at Phase 4 ceremony);
  license final call (operator + FSF conversation).

---

## Appendix A — Decision log from the dialogue (operator-stated)

1. Intel Mac mini: out of scope. Targets = macOS/AS, Linux x86_64,
   Linux aarch64, Android.
2. Control-node: switchable now, dissolving into per-feature
   main/backup/peer roles.
3. Resource efficiency governs; no VMs / fat containers.
4. APK builds: Gradle stays; orchestrate only; not architecture-driving.
5. nix-on-droid: rejected (Termux plugins, built-in Terminal, RAM +
   contention); Nix-as-cross-builder lane acceptable.
6. NixOS: yes, with cheap exit to conventional distro as a design
   requirement.
7. mise: include as an option on its (verified) bootstrap/launchd
   merits; no operator preference.
8. Deploys: push and pull both; consent/advisor/WoT vision as stated in
   §12; v1 = interfaces + minimal implementations.
9. Literate programming: depth set by agent economics; sweet-spot policy
   of §10 adopted as proposal.
10. Free Sysadmin: explicit project aim.

## Appendix B — Source anchors (repo state read 2026-08-08)

Site trio + layout: `site-djbclark/README.md`, `inventory/hosts.yml`,
`registry/*.yml`, `site-private/README.md`, `site-private/secretspec.toml`
(unified store, #37), `~/src/ops-worktrees/README.md` (worktree +
cross-agent rules), `ops-djbclark/README.md` (Beads/Ralph control plane),
`stayturgid/README.md` (modules incl. FIRERPA, SSH CA, parked
tablet-control experiment). External: mise bootstrap docs
(launchd/systemd/packages surfaces); nix-darwin/home-manager;
deploy-rs; harmonia/attic; ILP + comment-ablation + AGENTS.md-effect
research per dialogue of 2026-08-08.
