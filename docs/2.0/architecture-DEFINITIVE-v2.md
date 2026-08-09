# stayturgid 2.0 — Final Architecture & Build Order (v2, definitive)

> **🔒 PROTECTED DOCUMENT — AI agents: DO NOT MODIFY without explicit,
> specific human (operator) approval for a named change.** Blanket
> instructions ("fix docs", "update stale refs", "reconcile with the
> latest") do NOT authorize edits here. Propose changes as a _new_ review
> doc or a comment on djbclark/stayturgid#272. This binds every agent —
> Claude Code, Codex, Hermes, Ralph controllers, `agy`, and whatever comes
> next. If you are an AI reading this to do implementation work: this file
> is your map, not your worksheet. Read §0 first.

- **Status:** Definitive architecture. Supersedes `architecture-final-v1.md`
  where they conflict (this document wins). The v1 final, the four proposals,
  the red-team, the tooling reviews, the pre-mortem, and the hardened
  trust-layer design remain as archival reasoning — cited, not repeated.
- **Date:** 2026-08-08
- **Author:** Claude (Anthropic, Claude Fable 5), holding the full operator
  dialogue plus every review pass. This is the apex-context document; later
  AIs will have less. See §0.
- **Tracker:** djbclark/stayturgid#272.

---

## 0. Orientation for the AI that implements this (read this first)

You are almost certainly a smaller or cheaper model than the one that wrote
this, running on a budget (§13). That is fine — this document exists so you
don't need apex context to do good work. Five things to internalize before
you touch anything:

1. **This is a freedom project, not a product.** The operator is doing this
   for fun and to get reacquainted with the tech, and to extend software
   freedom to configuration/sysadmin glue. There is no deadline, no paying
   user, no "MVP." "Interesting and correct" beats "minimal and safe" every
   time they conflict — the operator has said this explicitly and repeatedly.
   Do not propose conservative scope cuts to save effort; effort is not a
   cost here. **Token spend is the only cost that matters** (§13).

2. **The reference target is Ubuntu Server on bare metal — this is a hard
   constraint, not a preference.** The operator will NOT run bare-metal Nix.
   The reason is _adoptability_: a stranger who wants to try this project
   should start from what they already have (a normal Linux box), and asking
   them to install duplicate packages is fine while asking them to replace
   their OS is not. Every design decision inherits this. Nix is still used
   heavily — but never as the thing a person installs on bare metal (§5).

3. **The trust/consent layer is the point, not a liability.** It is the most
   novel and most freedom-relevant part of the whole design. Its purpose is
   **user sovereignty**: any user — the operator's family, friends, or a
   stranger on the internet — should be able to understand a proposed config
   change in plain language, refuse it, and maintain their own divergent
   branch _without knowing what a branch is_, by telling their own AI agent
   what they want. Build it carefully (the security gates in §8 are real),
   but build it.

4. **The spine is data, not any one tool.** Facts live in the Site Model
   (§4). Every config tool — Ansible, mise, Nix-for-builds — is a replaceable
   consumer of that data. When in doubt about where something goes: facts and
   intent → Site Model; behavior → generic publishable code; never mix a
   hostname or secret into the generic layer.

5. **When you are unsure, stop and surface it — do not guess in code.** Some
   decisions in here are marked **[NEEDS FABLE-5 / MULTI-AI]** (§14). Those
   are places where a cheap model guessing wrong is expensive to unwind. If
   you hit one during implementation and it isn't resolved yet, write a
   question doc and stop; don't improvise a signing protocol or a capability
   schema.

Everything below is organized so you can implement front-to-back and the
system is in a coherent, describable state at every boundary (§12). That
property is not about "in case the operator quits" — it's just good design,
and the operator will often have several of these threads open at once.

---

## 1. The architecture in one screen

```
  ┌───────────────────────────────────────────────────────────────┐
  │                    SITE MODEL  (data, §4)                      │
  │  inventory · registries (ports/paths/services/roles) ·        │
  │  trust tiers · signing key ids · JSON-Schema'd, lint-gated    │
  │  → the ONLY home of facts; the thing that makes this portable │
  └───────────────┬───────────────────────────────────────────────┘
                  │  consumed by (never authored by) ↓
   ┌──────────────┼───────────────┬──────────────────┬────────────┐
   ▼              ▼               ▼                  ▼            ▼
 Ansible       mise           Nix (builds        Android       generic
 adapters      bootstrap      only, §5) —        stack         code =
 (services,    (host          NEVER bare-metal   (Termux,      "freeops"
 all           baseline,      OS; artifacts,     Shizuku,      publishable
 platforms)    toolchains)    dev shells,        agent,        layer (§11)
               THE Ubuntu     hermetic signed    CFEngine)
               reference      builds
               path
   └──────────────┴───────────────┴──────────────────┴────────────┘
                  │  every change ships as ↓
  ┌───────────────────────────────────────────────────────────────┐
  │        SIGNED RELEASE  =  manifest + typed ChangePlan (§7)     │
  │  TUF-subset root · Ed25519/minisign · monotonic · expiring    │
  │  consumed IDENTICALLY by push and pull; the executor          │
  │  mechanically refuses anything outside the plan (§8)          │
  └───────────────┬───────────────────────────────┬───────────────┘
        push ↓ (operator hosts)         pull ↓ (any host / consented device)
  ┌──────────────────────────┐   ┌────────────────────────────────────┐
  │ deploy from any host      │   │ user sovereignty: understand,      │
  │ holding a deploy role     │   │ refuse, or fork a change in plain  │
  │ (no permanent control     │   │ English via the user's own AI —    │
  │ node — roles are data)    │   │ this is the freedom feature (§9)   │
  └──────────────────────────┘   └────────────────────────────────────┘
        beneath both, unchanged: CFEngine self-heal + last-ditch recovery
```

The rest of this document specifies each block, in the order you'd build it.

---

## 2. Requirements (operator-stated, normative)

Carried from the dialogue; **bold** marks what changed or hardened in the
final round.

- **R1** Targets: macOS/Apple Silicon, Linux x86_64, Linux aarch64, Android.
  Intel Mac mini out of scope.
- **R2** No permanent control node; feature roles (main/backup/equal-peer)
  are data, assignable to any macOS/Linux box.
- **R3** Resource efficiency; minimal-to-no VMs; no fat containers.
- **R4** Android keeps Termux (+api,+x11), the built-in Terminal app, the
  Shizuku fork, stayturgid-agent, CFEngine. No nix-on-droid. Nix may build
  zero-on-device-footprint artifacts only.
- **R5 → HARD FACT:** **The operator will not run bare-metal Nix. Ubuntu
  Server is the reference Linux target.** Rationale is adoptability, not exit
  cost: the reference deployment must resemble what a stranger already runs.
  Nix lives at every level _except_ the installed base OS.
- **R6** Gradle stays for APKs; the suite orchestrates build + deploy; APK
  build does not drive architecture.
- **R7** Push AND pull. Pull evolves into **user-sovereignty**: plain-English
  understanding, refusal, and personal-branch maintenance driven by the
  _user's own_ AI agent — for family, friends, and strangers, none of whom
  need to know the underlying terms.
- **R8** Trust layer = specified interfaces + minimal safe implementations
  now; heavy machinery gated (§8), never deferred on "no user yet" grounds —
  the users are real (family/friends/public) and control over one's own
  computer is the entire point.
- **R9** Literate programming: **widen** it (§10). Token cost is no longer
  the limiting argument (asides are stripped from agent context anyway); the
  publishable, deeply-explained-with-asides version is wanted for humans and
  for Free Sysadmin. Only genuine agent-edit-accuracy costs constrain it.
- **R10** Free Sysadmin: the generic layer is publishable so anyone can run
  and fork it. Free-as-in-freedom and free-as-in-beer. **The sovereignty
  model (R7) is how R10 reaches non-technical people** — AI translates intent
  to config.
- **R11** Preserve: `~/src` + worktrees; `ops-v` release train; secretspec
  as sole secret authority; CFEngine; observability stack; Beads/Ralph/Herdr.
- **R12 (budget):** AI token spend ≤ ~$60/month for this project (≤$100 all
  projects). Design so routine work runs on cheap/subscription models; the
  architecture itself must keep agent token cost low (§13).

---

## 3. Verdict on the evaluated options (closed)

Unchanged and final: **none of the four is the spine.** `bgub/nix-macos-
starter` and `mrkuz/macos-config` are pattern donors (module layout,
brew/nix/mise triage) for the Mac only. Devbox and Devenv are optional
per-repo dev-shell tools, never system layers. The spine is the Site Model +
adapters (§4–5). Full detail lives in `architecture-proposal-v1.md` §3 and
the panel's convergence in `architecture-final-v1.md` §1–2; not re-argued.

The one option-level shift from R5-as-hard-fact: **Gemini's "no bare-metal
Nix" instinct is now correct by operator decree**, though its "drop Nix
entirely" conclusion is not — Nix stays for builds and dev shells (§5). Its
partial vindication is recorded so no later pass re-opens it.

---

## 4. The Site Model — the portable spine

**Principle: facts and intent in data; behavior in generic publishable code;
adapters translate.** This one mechanism satisfies R2 (roles are data), R5
(the Ubuntu path is just another adapter over the same data), R10 (the
generic layer is publishable because it holds nobody's facts), and R12 (agents
edit small data files, not a sprawling config tree — cheap to read).

### 4.1 Contents (extends what `site-djbclark` already does right)

- **`inventory/`** — hosts + taxonomy. Gains, per host: `arch`, `platform`,
  `adapter` (`ubuntu-mise` | `ansible` | `android` | `macos`), `trust_tier`
  (`operator` | `managed` | `consented`).
- **`registry/ports.yml`, `paths.yml`** — unchanged allocation authorities;
  adapters gain eval-time asserts against them.
- **`registry/services.yml`** (new) — one record per service: name, runs-as,
  command, `env` (secretspec key _names_ only), platform notes, role binding,
  `managed_by`. Every launchd plist / systemd unit / mise agent is a
  rendering of one such record.
- **`registry/roles.yml`** (new) — feature roles + assignment
  `role → {main, backups[], peers[]}`. **This file dissolves "control
  node"** into data (R2).
- **`registry/launchd-writers.yml`** (new, from the tooling review) — one
  writer per label prefix (`com.stayturgid.*`, `com.djbclark.*`, `dev.mise.*`,
  `org.nixos.*`), CI-enforced. Kills the two-writers hazard at the source.
- **Schema + lint** — JSON-Schema every file; enforce with the existing
  `registry_lint.py` pattern in CI and pre-commit.

### 4.2 Placement & consumption

Site Model lives in `site-<n>` (site data). Generic code lives fact-free
under `freeops/` (§11). Ubuntu/mise reads the model via a small generator;
Ansible reads it as vars it already understands; Nix (for builds only) reads
it via `builtins.fromJSON`. A stranger adopting the project fills in _their_
Site Model and runs the same generic code — that is the whole portability
story.

---

## 5. Platform layers (Nix everywhere except bare metal)

### 5.1 Linux — Ubuntu Server is the reference (R5 hard fact)

- **Base OS:** Ubuntu Server LTS, installed normally. No NixOS, no
  nixos-anywhere, no bare-metal Nix. A stranger clones the project onto their
  existing Ubuntu box and it works.
- **Host baseline** (packages, users, ssh, tailscale, firewall, systemd
  units for services): **mise `bootstrap` + Ansible adapters.** mise renders
  packages and host baseline from the Site Model; Ansible adapters render
  services (Vector/Caddy/etc.) — the already-debugged path. This was the
  "exit adapter" in v1; it is now the _main_ adapter. `comin` stays rejected
  (generic git-pull activation with no signed-update protocol — the trust
  layer §7 replaces it properly).
- **Nix on these boxes** is optional and _additive_: install multi-user Nix
  if you want it for building artifacts or dev shells, exactly as a stranger
  might `apt install` a tool. Never required for the runtime.

### 5.2 macOS (Apple Silicon) — the operator's own machine, a different case

The Mac is not a stranger's machine, so the adoptability constraint doesn't
bind it. **nix-darwin + home-manager MAY own the Mac substrate** (packages,
shell, dotfiles, defaults, declarative Homebrew) because generations and
rollback genuinely help on the one machine you can't easily reimage, and
because it's interesting. **[NEEDS FABLE-5 / MULTI-AI — see §14.1]:** whether
to go nix-darwin on the Mac at all, given that keeping the Mac on the same
mise+Ansible path as Ubuntu maximizes code sharing and keeps _one_ mental
model. This is a real fork — the fun answer (nix-darwin, learn the tech) and
the coherence answer (mise everywhere) diverge, and the operator said go the
interesting route, so the default is **nix-darwin on the Mac** unless a
review pass shows it fractures the Site Model. Services on the Mac stay
Ansible-owned regardless (§6).

### 5.3 Services — Ansible owns them, everywhere, permanently (D1, upheld)

Production services (`com.stayturgid.*`, `com.djbclark.*` and their systemd
twins) are rendered by Ansible adapters from `services.yml`, on every
platform. This is the panel's D1 decision and it survives the Ubuntu pivot
_more_ strongly: with Ubuntu as reference, services must render on a
vanilla-distro path anyway, so Ansible-owns-services is now the only
sensible answer, not a compromise. nix-darwin (if adopted) owns Mac
_substrate_, never services. The `launchd-writers.yml` lint enforces the
boundary.

### 5.4 Android — unchanged stack, plus the artifact lane (R4/R6)

Termux, Shizuku fork, stayturgid-agent, CFEngine, FIRERPA, SSH CA, Tailscale
— all unchanged. Two additions:

- **Artifact lane:** Nix cross-builds static aarch64/Termux-target binaries
  on a builder; they deploy as ordinary files via Ansible, content-addressed,
  hash recorded in the manifest. Zero on-device Nix. Use selectively (pin a
  fussy tool fleet-wide; ship what Termux `pkg` lacks — and note `pkg` is not
  reproducible, which is the actual justification).
- **stayturgid-agent 2.0** grows the **consent/sovereignty surface** (§9) and
  **peer-display** (device-from-device screen use — the parked
  `tablet-control-phone` experiment becomes the `peer-display` role, unblocked
  as data).

### 5.5 Future device classes (extension points, no build-out)

Routers → OpenWrt uci rendered from the Site Model (same adapter contract; no
bare-metal Nix there either, consistent with R5's spirit). iPhone / wearables
/ glasses → `trust_tier: consented` endpoints; consume services + artifacts,
never converge-managed. Microcontrollers → firmware as a Nix-built artifact,
flashing as a task. All are Site Model inventory entries + artifacts, not new
architecture.

---

## 6. Build & distribution topology (no VMs — R3)

- **Ubuntu closures/artifacts:** built natively on a Linux box, or
  substituted. Since the base OS is Ubuntu (not NixOS), there is _no system
  closure to build_ — Nix only builds the artifacts and dev shells you opt
  into, which mostly substitute from cache.nixos.org. This makes R3 almost
  free: the resource-heavy "build a whole system closure" problem the v1
  design worried about **no longer exists** on the reference path.
- **Cross-built artifacts (Android/firmware/pinned tools):** a `builder`
  role on real Linux hardware (ARM + x86 cover both arches natively). Declared
  in `roles.yml`. No VM on the Mac; the nix-darwin `linux-builder` VM stays
  rejected.
- **Cache:** only when a `builder` exists and produces non-substitutable
  artifacts. `harmonia` first (simplest, read-only serve). **Cache trust is
  total and is a real hazard (red-team RT-05):** a trusted cache key can
  substitute any store path. So the cache role is `trust_tier: operator` only,
  keys are separated from release keys, and NAR digests are pinned in the
  manifest and verified before activation. This is **CLOSE-BY-SCOPE** for the
  first 90 days of work — don't build a private cache until an artifact
  actually can't be substituted.
- **Explicitly rejected:** `nix.linux-builder` VM; Docker as build/run
  substrate; emulation builds in the deploy path.

---

## 7. Releases, manifests, and the typed ChangePlan (the core of the trust layer)

This section is the heart of the design and the part most changed by the
red-team + defensive passes. The full buildable spec lives in
`trust-layer-hardened-design-grok-v1.md`; this is the authoritative summary
and the decisions.

### 7.1 The release train (unchanged contract, richer payload)

`ops-vMAJOR.MINOR.PATCH` stays the only path to deploy checkouts. Each release
additionally publishes a **signed manifest + per-host typed ChangePlan**.

### 7.2 Signing: a TUF _subset_ sized for a solo operator (answers RT-01/02)

Do **not** ship one minisign key as fleet-root. Minisign stays the Ed25519
_signature primitive_ (offline-verifiable on Termux); it is not the update
system. Take this TUF subset, leave the rest:

- **root** — 2-of-3, offline. Three Ed25519 keys; two signatures change root
  or any other role. Shares on physically separate devices (laptop keyfile /
  phone or second machine / cold USB or paper), each password-sealed, not
  co-backed-up. Survives theft of the laptop _or_ any one share.
- **targets (release)** — 1-of-1 or 1-of-2, offline laptop ceremony (~15 min).
- **snapshot** — binds the exact metadata set (anti mix-and-match).
- **emergency** — 2-of-3, offline: security downgrade, key revocation,
  "do not apply releases signed by K."
- **timestamp** — **deferred while push-only**; required before pull timers.
- **Leave out:** delegations, mirrors role, online snapshot, path-hash
  delegation.

Every client that _applies_ a signed artifact (push targets included) keeps a
durable **high-water mark** (monotonic version + hash) and rejects
regressions, expired metadata, wrong channel, or wrong target — closing
replay/freeze/downgrade (RT-02). Root ships **out-of-band with the OS/agent
image** (no first-contact mirror trust — TOFU handled at install).

### 7.3 The typed ChangePlan operation IR (answers RT-03/04 — highest-value artifact)

A signed plan must _constrain execution_, not merely describe it. This is the
single most important thing to build correctly, and the one place a cheap
model must not improvise. **[NEEDS FABLE-5 / MULTI-AI — §14.2].**

The plan is a list of **typed operations**, each declaring: `capability`
(from a closed vocabulary), `resources` (exact ports/paths/packages/units it
may touch — checked against the registries), `target` (bound to the host's
public key), `rollback`, `expiry`, `nonce`. The **executor on each platform
mechanically refuses any effect outside the declared set**:

- **Ansible/Ubuntu+macOS:** a wrapper that maps declared capabilities to an
  allowlist of modules/paths; a task touching an undeclared port/path/unit
  fails closed. (Not "run the playbook because its hash is signed" — that is
  RT-03.)
- **Android agent:** operations map to a closed set of agent verbs; anything
  outside is refused; Shizuku actions are individually enumerated, never
  "run this APK."
- **Nix-built artifacts:** addressed by content hash; the manifest is the
  only name→hash binding.

The two-layer plan (from the ideas dump, adopted): a **verifiable layer**
(the exact operation IR + closure/artifact digests — ground truth) and a
**semantic layer** (generated, cached, LLM-legible: "this bumps openssl
across a CVE and restarts the public proxy"). The semantic layer briefs the
user and their advisor AI; it never authorizes — only the verifiable layer,
checked by the executor, authorizes.

### 7.4 Push and pull (both first-class)

- **Push:** from any host holding a `deploy-origin` role (plural — R2), via
  Ansible entry points and (on any Nix-artifact steps) content-addressed
  fetch. This is the **v1 path** and it is safe with §7.2–7.3 alone.
- **Pull:** a small converge agent (systemd/launchd timer) — **CLOSE-BY-SCOPE
  until the full §7.2 client protocol + resource quotas exist** (red-team
  RT-07 DoS). A fleet where every host pulls and none pushes _is_ the
  no-control-node end state, reached by editing `roles.yml`. Build it, gated.
- **CFEngine** stays beneath both. **But its remote-exec channel is both the
  recovery path and an attack surface** (tooling review): authenticate,
  authorize, and rate-limit `cf-runagent`; prefer SSH-mediated `just cf-run`
  over an open channel.

---

## 8. Security gates (what must hold before each capability opens)

These are correctness constraints, not budget or effort ones. They are the
distilled "blockers" from the red-team, dispositioned by the defensive pass.
Do not open a capability before its gate.

| Capability                                      | Gate (all must hold)                                                                                                                                                                                               |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Signed push to operator hosts** (v1 baseline) | TUF-subset root + targets/snapshot + high-water marks + typed ChangePlan executor enforcing on Ansible + source-to-signing hygiene (§8.1)                                                                          |
| **Autonomous pull (timers)**                    | above + timestamp role + converge resource quotas/backoff/kill-switch + hostile-mirror tests                                                                                                                       |
| **Consented devices**                           | above + device-key-bound, single-use, expiring consent grants + capability-enforcing agent executor + **Android artifact provenance** (dep locks, SBOM, signing-cert pin; independent rebuild for privileged APKs) |
| **Private cache / builder scale-out**           | separated build/upload/serve/release authorities + NAR-digest verification before activation + revocable-without-fleet-reinstall                                                                                   |
| **Autonomous role failover**                    | a real lease/fencing/quorum design + partition tests. **Until then: single designated owner + operator-signed plan for every single-writer mutation.** No YAML-ordering pseudo-HA.                                 |
| **local-fix → upstream-heal**                   | **never automated.** Advisory only; human (threshold) approval for any override; deterministic patch-equivalence, never "version claims to contain fix" (RT-09).                                                   |

### 8.1 Source-to-signing hygiene (answers RT-03 precondition + the 2026-08-06 incident)

The 2026-08-06 double-merge (an agent committed into another's worktree,
another merged 231 unreviewed lines) is **in-scope threat evidence**, not
trivia. Therefore, from day one: signing happens only from a clean, isolated,
reviewed checkout — **never a task worktree**; and the worktree
ownership/provenance rules become **automated deterministic checks** (a
`git log`/`git diff` range gate that fails closed under YOLO), not prose. This
is also the correct home for the **OpenHands technique** (§8.2).

### 8.2 OpenHands security — adopt the technique for agents, never as the fleet gate

Two surfaces, two verdicts (both reviewers concurred):

- **Surface A — the AI coding agents that build/deploy the fleet:** adopt the
  _deterministic-analyzer pattern_ (Pattern + PolicyRail + Ensemble
  max-severity), **vendored, not the SDK** — wired into shell/`git`/`gh`
  wrappers and Ralph step gates, because it doesn't depend on possibly-
  manipulated model judgment. This directly mitigates RT-03 and the
  double-merge class. Do not embed the full OpenHands `Conversation` harness.
- **Surface B — the fleet trust layer:** OpenHands analyzers _classify,
  don't hard-deny_, and `execute_tool()` bypasses them. They have **no role
  as an authorization gate** (that's the typed executor, §7.3). At most a
  future non-authorizing advisor input (§9), layered above the deterministic
  gate, never able to approve and never required to deny.

### 8.3 SecretSpec reference monitor (answers RT-06)

secretspec stays the sole declaration authority (R11). Add a deny-by-default
resolver: a signed policy maps `(service identity, host role, capability)` →
allowed handle; everything else is refused with a non-secret audit event.
Secrets delivered as per-service non-inherited runtime files, not ambient
env. Bootstrap material (SSH-CA key, cache key) is a minimal separate root,
not mixed with normal site secrets.

---

## 9. User sovereignty — the freedom feature (R7/R10, the interesting part)

This is what the trust layer is _for_, and it is where this project is
genuinely novel. Frame everything here as giving a person control over their
own computer, not as protecting the fleet from them.

**The interaction the whole design serves:** a user — the operator's parent,
a friend, a stranger who cloned the repo — receives a proposed config change.
Their _own_ AI agent reads the semantic layer of the ChangePlan (§7.3) and
explains, in plain language, what it does and why they might or might not want
it. If they don't want it, they say so in plain English; their agent
maintains a **personal branch** that diverges from upstream — and they never
need to know the words "branch," "merge," or "systemd." When upstream changes
again, their agent re-evaluates against their stated preferences and keeps
their divergence coherent.

Concretely, staged:

- **Consent surface v1 (agent 2.0):** `offer(manifest, plan) → accept |
reject | timeout(deny)`; device-key-bound, single-use nonce, expiring;
  protected local receipt. Gated per §8. The _interface_ is specified now so
  later phases can't regress it.
- **Advisor (T2):** the user's chosen model reads the semantic layer and
  advises. Never authorizes (RT-09). **The two-agent pattern (ideas dump,
  adopted as a first-class control):** the _proposing_ side and the
  _consenting_ side run different models; disagreement escalates to the
  human. This is vendor-diversity-as-a-safety-mechanism — exactly what this
  whole review process did by hand, formalized into the product.
- **Personal branch maintenance (T4, reframed):** the red-team correctly
  called "local-fix auto-merge" an injection vector _under the fleet-safety
  framing_. Under the sovereignty framing it is the product — but the
  security requirement is unchanged: the user's branch is _theirs_, applied
  under _their_ consent; it never auto-merges into anyone else's trust domain,
  and upstream-heal is a suggestion their agent evaluates, never an automatic
  authority. **[NEEDS FABLE-5 / MULTI-AI — §14.3]:** the branch-maintenance +
  advisor loop is the subtlest and most novel machinery in the project and
  deserves a dedicated design pass, including a red-team of the AI-in-the-loop
  attack surface (prompt injection into the advisor, poisoned model in the
  two-agent loop, the semantic layer as an injection vector).
- **Web of trust (T5):** graded trust ("anyone two members of set S vouch for
  at level X, with safeguards Y"), TUF-style thresholds evaluated against an
  attestation log, human-ritual attestations (the phone-call vouch) as
  first-class entries. Roadmap; interfaces shaped by §7 so it attaches
  cleanly.

The transparency-log (T1, Rekor-style, not a blockchain) and reproducible-
artifact provenance (T6/SLSA-style) remain roadmap, gated per §8, never
authorizing on their own.

---

## 10. Literate programming (R9 — widened)

The v1 policy kept entangle narrow, partly on token cost. Token cost is no
longer the governing argument (asides are stripped from agent context;
budget is managed by model routing, §13). So **widen literate coverage** to
everything where the explanation is genuinely part of the artifact —
especially the freedom-relevant glue that Free Sysadmin will publish:

1. **Two prose classes, mechanically separated** (unchanged, load-bearing):
   _rationale_ (intent/invariants/interdependencies) sits with code and is
   agent-visible; _narrative_ (the deep explanations, humor, historical
   asides the operator wants) lives in blocks the agent-facing tangle strips
   and the human/publish weave keeps. Full richness for people; agents don't
   pay for it.
2. **Widened scope:** the Site Model schema, the CFEngine failsafe policies,
   the SSH-CA flows, the ChangePlan IR + executor, the consent/sovereignty
   machinery, the converge agent — all literate. The subtle, freedom-relevant,
   publishable glue is exactly what benefits.
3. **`stitch`** lets agents edit tangled plain files cheaply; the literate
   source absorbs changes. **[stitch under parallel YOLO agents needs an
   ownership lock]** (ideas dump) — extend the worktree ownership rules to
   "who may stitch this doc now."
4. **Structure:** file-aligned chunks, minimal noweb indirection, CI tangle-
   parity gate, plus source-map comments in generated output (Gemini's idea)
   so errors trace to the literate source.
5. The remaining constraint is only agent-edit-accuracy: if a literate file
   measurably degrades agent edits, narrow _that file_. Otherwise, go rich.

---

## 11. Free Sysadmin publishing (R10)

- **Quarantine from day one:** everything under `freeops/` is written fact-
  free, reviewed as if public. Site facts enter only via Site Model
  instantiation. Because the reference target is plain Ubuntu (R5), the
  published artifact is _directly runnable by a stranger_ — the adoptability
  constraint and the publishing goal are the same constraint. Extraction to a
  standalone public repo when it has real consumers (in-tree until then).
- **Licensing:** generic code **GPL-3.0-or-later** (copyleft is the point —
  the freedom being extended is the glue itself); literate docs
  **CC-BY-SA-4.0**; interop _schemas_ (ChangePlan, registry JSON-Schema)
  permissive/**CC0** so the sovereignty ecosystem can interoperate; networked
  trust services **AGPL-3.0**. Audit current LICENSE files before any change
  — direction, never silent relicense.
- **The story this enables:** a person clones the generic layer + Site Model
  schema, fills in their own facts, and runs it on their own Ubuntu box —
  with their own AI helping them understand and diverge from upstream config
  they don't want (§9). That is "Free Configuration Management," and it is the
  same mechanism as the adoptability constraint and the sovereignty feature.
  Three goals, one design.

---

## 12. Build order (coherent state at every boundary)

Ordered so each step delivers standalone value and leaves the system
describable. Not a schedule (effort/time are not costs here) — a _dependency
and coherence_ order. The one correction kept from the pre-mortem on purely
logical grounds: **prove the Ubuntu path before investing in Mac Nix**,
because it de-risks the reference target that everything else depends on.

- **Step 0 — Site Model + fences (pure data, no runtime change).** Schemas
  for `services.yml`/`roles.yml`/`launchd-writers.yml`; transcribe current
  reality; lint in CI + pre-commit; automate the worktree provenance gate
  (§8.1). Coherent stop: same system, now with a truthful data spine and a
  provenance gate. _Also the cheapest possible agent work — good first task
  under the budget._
- **Step 1 — Ubuntu reference path.** mise `bootstrap` + Ansible adapters
  render a real Ubuntu host from the Site Model. This is the adoptability
  keystone; do it early even before you own a VPS, by rendering + dry-running
  against a throwaway box or container-like target. Coherent stop: the
  reference deployment provably works on vanilla Ubuntu.
- **Step 2 — First real Linux host.** Provision a VPS (Hetzner) as Ubuntu;
  give it backup/shadow roles (observability mirror, backup) — **not**
  obs-main yet. Proves R2 (flip a role's main to it and back) and gives the
  role mesh a second real node. Coherent stop: a genuine second host; destroy
  it and the Mac/fleet are unchanged.
- **Step 3 — Signed releases (push-only) + typed executor.** TUF-subset root
  ceremony; manifest + ChangePlan generation in `ops-release-*`; the
  capability-enforcing executor on Ansible (§7.3, §8). Push-only, operator
  hosts. Coherent stop: every deploy is a signed, execution-constrained plan;
  no autonomous anything yet.
- **Step 4 — Mac substrate (the interesting, optional Nix step).** If §14.1
  resolves toward nix-darwin: bring the Mac substrate under nix-darwin +
  home-manager, services still Ansible. Fully reversible (`darwin-rebuild
--rollback`). Coherent stop: Mac substrate is declarative; nothing depends
  on it that couldn't run on the mise path.
- **Step 5 — Pull convergence.** Converge agent with the full §7.2 client
  protocol + §8 quotas. Any host with the role self-updates. Coherent stop:
  the no-control-node end state exists as data.
- **Step 6 — Consent/sovereignty v1 (agent 2.0).** The consent surface on one
  fleet device, then the advisor and personal-branch loop (§9), each behind
  its §8 gate. This is the payoff — the freedom feature — built on everything
  below it.
- **Step 7+ — demand-driven.** builder/cache (when a non-substitutable
  artifact appears), reproducible-APK provenance (before any consented device
  runs privileged APKs), WoT/transparency-log, freeops extraction (when a
  second person runs it).

Every step's rollback is its own coherent stop above it.

---

## 13. Token budget as an architectural constraint (R12)

$60/month for this project is real and the architecture must respect it —
this is the one cost that counts. Design and workflow implications, to be
followed by every implementing agent:

- **The Site Model spine is itself a cost control:** agents edit small
  schema'd data files instead of reading a sprawling config tree; the
  literate strip-asides mechanism keeps agent-facing context lean. A big
  reason the data-spine design wins is that it makes routine agent work cheap.
- **Model routing (use `aiuse` to enforce):** routine implementation on
  cheap/subscription seats (Sonnet-class, DeepSeek v4 Pro, the subscription-
  covered Codex/Grok/Gemini seats), **not** metered Fable-5-xhigh. Reserve
  Fable 5 / high-effort / multi-vendor for the marked decisions (§14) and
  security-critical review only.
- **This architecture session was a deliberate one-time spend** (five agent
  passes, three vendors). That is not the operating mode. Steady-state
  implementation should be near-free against the budget if routed as above.
- **A plan step that clearly implies heavy recurring model spend is a
  smell** — prefer designs where the expensive thinking is done once and
  captured in a document (like this one) that cheap models then execute.

---

## 14. Points that would benefit from Fable 5 and/or multiple AIs

Everywhere else, a cheap model executing this document is fine. These are the
exceptions — places where a wrong guess is expensive to unwind, flagged per
the operator's request. Spend the premium budget here, nowhere else.

- **§14.1 — nix-darwin on the Mac, yes or no.** The fun/coherence fork (§5.2).
  Multi-AI, low security stakes; a Nix-idiom specialist pass would help. Not
  urgent — resolvable at Step 4.
- **§14.2 — the typed ChangePlan operation IR + executor enforcement (§7.3).**
  The highest-value and highest-risk artifact in the whole project. A cheap
  model must not improvise a capability vocabulary or an enforcement boundary.
  **Fable 5 for the design + an independent adversarial review** (different
  vendor) before it's built. This is the thing to spend premium tokens on.
- **§14.3 — the sovereignty/advisor/personal-branch loop + its AI-specific
  red-team (§9).** The most novel machinery; the attack surface (prompt
  injection into the advisor, poisoned model in the two-agent consent loop,
  the semantic layer as an injection vector) is genuinely new territory and
  under-reviewed. Fable 5 design + a dedicated AI-in-the-loop red-team, ideally
  a vendor not yet used adversarially here.
- **§14.4 — the solo-operator TUF-subset key ceremony + recovery runbook
  (§7.2).** Security-critical and easy to get subtly wrong. One careful Fable
  5 pass + one independent review; verify every protocol claim against current
  TUF/minisign docs, never training memory.

Everything not in this list: a cheap model following this document is
expected to do well. When such a model hits one of these four and it's
unresolved, it should write a question doc and stop, not improvise.

---

## 15. Decision register (operator sign-off)

| #         | Decision                 | Resolution                                                                                                                                                                                         |
| --------- | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1        | Production service owner | **Ansible, permanently, all platforms.** Strengthened by R5.                                                                                                                                       |
| D2        | Site Model formality     | Schemas at Step 0; generation gradual; writer-lint immediate.                                                                                                                                      |
| D3        | Ubuntu reference path    | **mise baseline + Ansible services is the PRIMARY Linux path** (promoted from "exit").                                                                                                             |
| D5        | Literate scope           | **Widened** (§10); token cost no longer the limiter.                                                                                                                                               |
| D6        | Nix on bare metal        | **NO — hard fact.** Nix for builds/dev-shells/Mac-substrate only.                                                                                                                                  |
| D8 (new)  | Trust layer disposition  | **Build it, gated (§8).** The "defer indefinitely" option is rejected — sovereignty is the point.                                                                                                  |
| D9 (new)  | OpenHands                | Vendor the analyzer _technique_ for coding agents (§8.2 Surface A); no role as fleet gate (Surface B).                                                                                             |
| D10 (new) | Task runner              | **Keep `just`** as the human verb surface; start using its dependency support; mise stays scoped to toolchains/baseline. Both reviewers concurred; a real DAG need is the only trigger to revisit. |
| D11 (new) | Trust-layer scope cuts   | Per the defensive pass: FIX-IN-V1 the root/executor/high-water/secret-monitor; CLOSE-BY-SCOPE consent/cache/failover/APK-provenance behind §8 gates; never automate local-fix.                     |

Silence = proceed from Step 0. Objections amend this register, not the
archived documents.

---

## 16. Document map (for the next AI)

- **This file** — authoritative architecture + build order. Start here.
- `architecture-final-v1.md` — prior synthesis; superseded where they differ.
- `architecture-proposal-v1.md` — Claude's detailed §7–8/§12 (manifest/consent
  detail still useful).
- `architecture-proposal-{openai,gemini,grok}-v1.md` — the independent panel;
  archival positions, do not edit.
- `redteam-trust-layer-openai-v1.md` — the nine findings; §8 here is their
  disposition.
- `trust-layer-hardened-design-grok-v1.md` — the _buildable_ trust-layer
  spec; §7–8 here summarize and decide, that doc implements.
- `tooling-assumptions-review-{openai,grok}-v1.md` — per-tool verdicts;
  source for D9/D10 and the CFEngine/Tailscale-ACL hardening notes.
- `premortem-scope-realism-openai-v1.md` — read with the correction in mind:
  its effort estimates assume a commercial objective function that does not
  apply; its _logical_ points (exit-before-Mac-Nix, coherent stops, two-
  writers, no-consent-UI-before-executor) are kept and live in §8/§12.
- `ideas-dump-claude.md` — unprotected; the two-agent-consent control, the
  semantic/verifiable plan split, the role-mesh-is-consensus flag, and the
  model/vendor notes all graduated into this document.

_Filed under djbclark/stayturgid#272. Amend via this register; treat the
archived reviews as immutable record._
