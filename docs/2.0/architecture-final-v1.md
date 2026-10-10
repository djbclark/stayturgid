# stayturgid 2.0 — Final Architecture (v1)

> **🔒 PROTECTED DOCUMENT — AI agents: DO NOT MODIFY this file without
> explicit, specific human (operator) approval given for a named change.**
> Blanket instructions like "fix docs" or "update stale references" do NOT
> authorize edits here. Propose changes as a review document or GitHub issue
> (tracker: djbclark/stayturgid#272). This rule binds all agents.

- **Status:** Final synthesis v1 — awaiting operator sign-off on the
  Decision Register (§6)
- **Date:** 2026-08-08
- **Synthesized by:** Claude (Anthropic, Claude Fable 5)
- **Inputs:** interactive operator dialogue (decisions in
  `architecture-proposal-v1.md` Appendix A); four independent proposals in
  this directory — Claude (`-v1`), OpenAI Codex/GPT-5 (`-openai-v1`),
  Gemini (`-gemini-v1`), Grok 4.5 (`-grok-v1`, incl. its critique of
  Claude); shared brief (`SECOND-OPINIONS-BRIEF.md`). DeepSeek v4 Pro seat
  was quota-blocked and dropped.
- **How to read this:** §1 is the verdict. §2 is what the whole panel
  agrees on (treat as settled). §3 resolves the contested decisions —
  including two places where the panel changed Claude's original position.
  §4 is the final architecture, §5 the final migration plan, §6 the
  operator sign-off register, §7 credit and dissent.

---

## 1. Verdict

**On the four evaluated options — unanimous across all four AIs:** none is
the architecture. `bgub/nix-macos-starter` and `mrkuz/macos-config` are
pattern donors (layout, module decomposition, brew/nix/mise triage rule,
remote-builder posture). Devbox and Devenv.sh are per-project dev-shell
tools; either may be adopted per-repo, neither may own machine services or
fleet state. Gemini alone would also drop nix-darwin/NixOS entirely
(mise + Ansible only); that thesis is rejected in D6 below, but its exit
argument sharpened the design.

**The architecture** is a layered mesh — the panel converged on the same
family independently, which is strong evidence the requirements force it:

> **Facts and intent live in a tool-neutral Site Model (inventory,
> registries, roles, service intent). The three-repo ops-v suite, Ansible,
> CFEngine, and the Android product remain the durable system of record for
> fleet behavior. A thin, dual-exit host layer (nix-darwin on the Mac,
> NixOS on greenfield Linux, Ubuntu+mise as a continuously-proven exit)
> gives any macOS/Linux box arbitrary feature roles with no permanent
> control node. Every deploy — push or pull — flows through a signed
> release manifest plus machine-readable change plan, the v1 seed of the
> consent/trust/Free-Sysadmin future.**

## 2. Settled by convergence (all or 3-of-4 proposals agree)

1. **Role mesh, not control node** (R2). Roles
   (`host-os, android-peer, obs-main/backup, ai-proxy, apk-build, release,
agent-orch, builder, cache, deploy-origin, pull-converge, …`) are
   inventory data; any host holds zero or more; "control node" dissolves
   into role assignments. First movements: obs-main to the VPS when it
   exists, because the M1 Air is a laptop that sleeps.
2. **Source-of-truth placement** (R2/R5/R10): site facts only in
   `site-*/inventory` + `registry/*`; product behavior in public
   stayturgid; secret _declarations_ only in secretspec (values in
   providers, never git); host substrate in a small flake; coordinated
   deploy version in the preserved `ops-v` train. No monorepo flake that
   swallows the product.
3. **No VMs** (R3): no always-on `nix.linux-builder` on the Air; no
   Docker build/run substrate. Linux closures: public-cache substitution +
   build-on-target first; a remote-builder + signed-cache **role** on real
   Linux hardware later, demand-driven.
4. **Android unchanged** (R4): Termux(+api,+x11), Terminal app, Shizuku
   fork, stayturgid-agent, CFEngine layers, FIRERPA, SSH CA, Tailscale.
   nix-on-droid rejected. Nix may cross-build zero-footprint artifacts
   deployed as ordinary files by Ansible. Gradle stays for APKs (R6);
   builds are invoked and their artifacts hashed/deployed by the suite.
5. **Signed manifests + change plans** (R7/R8): every release publishes a
   canonical signed manifest (release id, per-host closure/playbook +
   artifact digests, key id) and per-host change plans (closure diffs on
   Nix hosts; `--check --diff` + artifact deltas elsewhere). Offline
   Ed25519/minisign verification — a handset must be able to verify with
   no network dependency (OpenAI's hardening, adopted). Consent surface v1
   in stayturgid-agent: verify → show plan → accept/reject/defer → durable
   local receipt. Advisor/WoT/catalog remain roadmap interfaces (T0–T6
   table in Claude v1 §12, adopted by Grok).
6. **secretspec stays sole declaration authority** (R11). No agenix/sops
   as a second schema; at most a bounded host-bootstrap exception
   (Claude v1 §8) or a provider backend under the one schema (Grok §8).
   No secret values at Nix eval time; nothing secret in any store.
7. **Push AND pull**: push via existing just/Ansible entry points (plus
   deploy-rs for Nix hosts); pull via a small auditable converge agent
   fetching signed `ops-v` tags. CFEngine unchanged beneath both.
8. **Free Sysadmin** (R10): generic layer written fact-free from day one;
   published under copyleft (GPL-3.0-or-later code, CC-BY-SA-4.0 docs;
   permissive/CC0 for interop _schemas_ — Grok's refinement, adopted);
   identity-scrub CI before anything ships. Feature-bundle model
   (OpenAI §8): a published bundle declares capabilities, ports/paths,
   privileges, rollback, SBOM/provenance — it cannot self-register
   undeclared daemons. **License changes require an audit of current
   LICENSE files first — direction, not silent relicense (Grok).**
9. **Literate programming stays narrow for now** (R9) — see D5.

## 3. Contested decisions, resolved

### D1 — Who owns production launchd/systemd? **RESOLVED: Ansible remains the production service owner; Nix owns the substrate.** _(Claude's original position amended by the panel.)_

The fork Grok named precisely: are `com.stayturgid.*`/`com.djbclark.*`
services a _Nix generation_ problem (Claude v1: migrate all to
home-manager, "Ansible manages no launchd on the Mac" as Phase 3 exit
criterion) or an _Ansible role_ problem on a Nix-managed host (OpenAI +
Grok)? The panel's arguments carry:

- These services are **fleet-coupled** (inventory peers, secretspec
  injection, registry ports); rendering them from Nix still requires the
  Site Model _plus_ a second apply path — complexity moved, not deleted.
- The **R5 exit** must re-render the same services without generations
  anyway; making Nix the only production renderer weakens the exit.
- **R10 consumers** must be able to adopt the Android+Ansible product
  without installing nix-darwin; Ansible-owned services keep the
  publishable product self-sufficient.
- Flip risk lands on the **live observability laptop**.

**Final ownership matrix** (merging Grok §3.2 + OpenAI §2 + Claude's
`managed_by` fact):

| State                                          | Sole writer                    | Namespace                            |
| ---------------------------------------------- | ------------------------------ | ------------------------------------ |
| Production fleet/site services (all platforms) | **Ansible adapters**           | `com.stayturgid.*`, `com.djbclark.*` |
| Nix daemon, macOS defaults, Touch ID sudo, GC  | nix-darwin                     | `org.nixos.*` / system               |
| Cross-platform user packages, dotfiles, shell  | home-manager                   | HM-managed paths                     |
| Language runtimes, per-project tools           | mise                           | shims, `.mise.toml`                  |
| Optional personal utility agents               | mise bootstrap                 | `dev.mise.*` **only**                |
| Homebrew formula services / GUI apps           | brew (existing site mechanism) | `homebrew.mxcl.*`, casks             |

Enforced by a new `registry/launchd-writers.yml` + lint from **day one**
(Grok), independent of Site Model maturity: one writer per label prefix,
CI-failed on violation. `services.yml` keeps a `managed_by` field
(Claude) so _individual low-coupling utilities_ may flip to HM by ADR —
but "no Ansible launchd" is **not** a success criterion, and no
production label moves before a live launchd census prices each flip
(Grok). What Nix's generations still protect: the substrate (packages,
env, defaults) — which is where macOS-upgrade breakage actually lands.

### D2 — Site Model formality on day one. **RESOLVED: schemas early, generation gradual, lint immediate.**

Adopt Claude's `roles.yml` + `services.yml` schemas in Phase 0 as the
**inventory of intent** (they are what R5's exit generator, R7's plans,
and R10's bundles all consume) — but transcription is descriptive first:
no live plist must be _generated_ from the model before its family
migrates deliberately. Grok's `host_roles:` inventory extension and
writer lint land first, cheapest. (Grok critique #2, OpenAI Phase 0,
Claude §4 — merged.)

### D3 — mise's weight and the exit's renderer. **RESOLVED: mise = toolchain SSOT + host-baseline exit; Ansible adapters = service exit.**

mise owns language runtimes everywhere now (Grok Phase 2). The
Ubuntu-exit drill (Claude's standing CI job — adopted by Grok) renders
**packages + host baseline** via `mise bootstrap` from the Site Model;
**services** on an exited host come from the already-debugged Ansible
adapters, not a second mise-unit rendering (Grok critique #3 — avoids
implementing Vector/Caddy ownership twice). The exit runbook is written
once and drilled on a throwaway host (Grok Phase 6 / OpenAI §3.2): the
success criterion is that an engineer or agent completes it **without
reading Nix**.

### D4 — freeops extraction timing. **RESOLVED: in-tree until stable.**

Destination unchanged (public generic layer, working name `freeops`),
but it lives under stayturgid/site trees and is extracted only when it
has real consumers — never a fourth repo in the ops-v ceremony
prematurely (Grok critique #7, OpenAI's "only once it has two
consumers"; Claude's front-loading dropped).

### D5 — Literate programming scope. **RESOLVED: keep the current narrow calibration; adopt Claude's mechanics inside it.**

The suite's existing choice (only `SITE-CONTRACT.md` is Entangled, with
byte-parity CI) is validated by all panelists and by the research record
(context/boundary docs measurably help agents; interleaved prose in
hot-path code taxes them). Expansion rule (Grok §10.2): a new literate
source only where it (a) generates a product↔site scaffold boundary or
(b) is a Free Sysadmin tutorial that emits starter files — candidates:
the consent machinery, ChangePlan schema, exit runbook. Where literate
sources exist, use Claude's mechanics: rationale adjacent to chunks
(agent-visible), human asides in stripped blocks, file-aligned chunks,
`stitch` so agents edit tangled files cheaply, tangle-parity CI, plus
Gemini's source-map comments in generated outputs so errors trace back.
Require a short decision record before any new literate source (OpenAI).

### D6 — Gemini's no-Nix thesis. **RESOLVED: rejected, with two ideas retained.**

Dropping nix-darwin/NixOS entirely forfeits: atomic generations on the
substrate (the recovery story for OS-upgrade breakage), verifiable
closure diffs (the strongest possible "what will change" artifact for
R7 consent — a diff you can _prove_, not narrate), and hermetic builds
for the artifact/firmware lanes. Its honest accounting of the rollback
trade-off is retained as the exit path's documented cost (git-revert +
re-apply + CFEngine + filesystem snapshots), and its source-map idea
lands in D5. Its deeper value was as pressure-test: the final design's
Nix surface is _thinner_ than Claude v1 because Gemini and Grok pushed
on it.

## 4. Final architecture (amended Claude v1)

`architecture-proposal-v1.md` remains the detailed reference for
everything §2 marks settled: the Site Model contents (§4), build/cache
topology (§6), manifest/plan formats and consent surface (§7), secrets
(§8), observability placement-as-data (§9), Free Sysadmin publishing
(§11), trust roadmap T0–T6 (§12), and risks (§14). It is amended as
follows; where this section conflicts with it, **this document wins**:

1. §5.1(2) launchd end-state and Phase 3 exit criterion → replaced by
   D1's ownership matrix and census-priced, ADR-gated flips.
2. §5.1(3) → mise bootstrap additionally owns optional `dev.mise.*`
   personal agents now (not only the dormant exit generator).
3. §4.1 registries → add `registry/launchd-writers.yml` (+ lint) to the
   Site Model, effective Phase 0.
4. §5.3 exit adapter → per D3, exit services render via Ansible
   adapters; mise renders host baseline only.
5. §4.2/§11 freeops placement → per D4, in-tree until two consumers.
6. §10 literate policy → per D5, expansion gated on the scaffold/
   tutorial rule + decision records.
7. Add (from Grok §1.2/OpenAI §1.1): role assignment carries
   primary/backup/peer ordering with lease/fencing semantics — a backup
   claims a role only after the plan's timeout and a recorded handoff;
   externally-visible single-writer mutations (publish a release, rotate
   a secret) always require an operator-signed plan. High availability
   for healing, never accidental split-brain administration.
8. Add (from Grok §4.3): near-term R2 work is parameterizing every
   "the Mac" assumption into `stayturgid_control_peers`/role lists, with
   systemd twins (or explicit `darwin_only` marks) for each
   `com.stayturgid.*` agent template.

## 5. Final migration plan

Gates are evidence-based (OpenAI's discipline: a green build is not a
live-device verification; publish evidence + gaps in STATUS docs per
phase). Do not interleave with the outstanding Fire OS soak or
OpenObserve clean-log acceptance (OpenAI).

| Phase                                                      | Contents                                                                                                                                                                                                                                                                     | Rollback                                           |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| **0 — Map & fence** (days)                                 | Site Model schemas (`roles.yml`, `services.yml` descriptive, `host_roles` in inventory); `launchd-writers.yml` + lint; live launchd census; ownership matrix in docs. No runtime change.                                                                                     | delete files                                       |
| **1 — Toolchains & flake skeleton** (days)                 | mise pins as toolchain SSOT (`mise doctor` clean, `just test` green); flake with `darwinConfigurations.m1-air` that **builds** (no switch) on the existing Determinate install.                                                                                              | ignore flake; brew unchanged                       |
| **2 — Mac substrate switch**                               | nix-darwin/HM own packages, shell, dotfiles, defaults. **Services untouched.** Brew: per-package single-owner decision recorded in registry (no bulk nix-homebrew migration — OpenAI).                                                                                       | `darwin-rebuild --rollback`                        |
| **3 — Role parameterization** (pre-Linux)                  | Kill "the Mac" assumptions: peer lists, systemd twins/`darwin_only` marks, `just deploy-host`. Dry-run against a mock `vps-primary`.                                                                                                                                         | `legacy_single_control: true` flag                 |
| **4 — First NixOS host**                                   | Hetzner `vps-primary` (ARM) via nixos-anywhere: thin NixOS base; services via the same Ansible adapters → systemd; backup roles first; obs-main migrates after a 7-day clean soak (Mac sleep must not drop fleet telemetry — Grok). Build-on-target; exit-drill CI turns on. | NixOS generations; or destroy VPS, roles fall back |
| **5 — Release/plan v1**                                    | Manifest + ChangePlan schemas, signing ceremony, preflight verification; converge (pull) agent on operator hosts; deploy telemetry events; one device verifies a no-op signed plan end-to-end, fail-closed tests (bad sig/expiry/target/digest).                             | feature flag off; push-only                        |
| **6 — Consent v1**                                         | stayturgid-agent consent surface + local receipts on one opted-in fleet device; then one bounded peer-help op with proven rollback.                                                                                                                                          | revoke feature; recorded rollback                  |
| **7 — Exit drill**                                         | Throwaway Ubuntu host; run the §D3 runbook; written proof R5 holds. Mandatory gate before any deeper Nix investment (Grok).                                                                                                                                                  | n/a (drill)                                        |
| **8 — Builder/cache + freeops extraction** (demand-driven) | On second Linux box or first non-substitutable artifact: `builder`+`cache` roles (harmonia first), CA-bound trust, Android artifact lane. freeops extraction when two consumers exist.                                                                                       | remove roles/substituter                           |

Explicit non-goals for the first 90 days (Grok, panel-endorsed):
wholesale Ansible→Nix service rewrite; nix-on-droid; replacing CFEngine;
moving production labels to mise or nix-darwin; always-on linux-builder;
consent marketplace.

## 6. Decision Register — operator sign-off

| #   | Decision                 | Resolution                                                   | Revisit trigger                                         |
| --- | ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------- |
| D1  | Production service owner | Ansible permanent; Nix = substrate; per-label ADR flips only | An ADR shows a concrete win for a specific label family |
| D2  | Site Model formality     | Schemas Phase 0, generation gradual, writer lint day one     | —                                                       |
| D3  | Exit renderer            | mise = host baseline; Ansible adapters = services            | Exit drill (Phase 7) findings                           |
| D4  | freeops timing           | In-tree until two consumers                                  | Second consumer appears                                 |
| D5  | Literate scope           | Narrow + scaffold/tutorial gate + Claude mechanics           | Free Sysadmin tutorial work begins                      |
| D6  | Gemini no-Nix thesis     | Rejected; snapshot-fallback + source-maps retained           | Exit drill proves Nix layer net-negative (unlikely)     |
| D7  | Third-vendor gap         | DeepSeek seat dropped (quota); panel = OpenAI/Gemini/Grok    | Operator may commission a DeepSeek pass later           |

Silence = consent to proceed with Phase 0; objections amend this
register, not the archived proposals.

## 7. Credit and dissent

- **OpenAI:** Ansible-permanence argument (with Grok); feature-bundle
  capability model; offline-verifiable signatures; evidence-gated
  phases; no-bulk-Homebrew-migration; "don't interleave with live
  soaks"; three-state secrets reporting (declared/published/consumed).
- **Grok:** the D1 fork named cleanly; writer-namespace lint; launchd
  census as migration unit-of-account; Ops Mesh role table + lease/
  fencing framing; exit-drill-as-mandatory-gate; freeops timing;
  schema-license split (CC0/Apache for interop schemas); license-audit-
  before-relicense caution.
- **Gemini (dissent preserved):** the no-Nix mise-first architecture
  remains on file as the documented alternative if the exit drill ever
  proves the Nix layer net-negative; source-map comments and honest
  rollback accounting adopted.
- **Claude v1:** Site Model spine; adapters concept; manifest/plan/
  consent seed; T0–T6 trust roadmap; no-VM build topology; literate
  mechanics; Free Sysadmin publishing architecture — all surviving,
  with the D1 end-state conceded to the panel.

_Filed under djbclark/stayturgid#272. The four source proposals are
archival records of independent positions — do not edit them; amend via
this document's Decision Register._
