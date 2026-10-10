# stayturgid 2.0 — Loose Ideas Dump (low-effort, unpolished)

> **Not a proposal. Not protected.** This is a deliberately low-effort brain
> dump captured because the 2026-08-08 architecture session is the most
> concentrated context on this system's design that's likely to exist for a
> while. Half-formed on purpose. Cherry-pick; delete freely. Author: Claude
> (Fable 5). Nothing here is a decision or a recommendation with the weight
> of the reviewed docs — treat every bullet as "worth a thought," not "do."

## On the tools nobody analyzed

- **`just` is an unexamined keep.** Every proposal preserved it as the command
  surface without asking whether it should change. The one real question: once
  the Site Model is the source of truth, should justfiles be _generated from
  it_ (new role → its `just` targets appear automatically, guaranteed
  consistent across hosts) or stay hand-written (readable, greppable, no
  build step)? Leaning generated-for-role-boilerplate + hand-written-for-
  everything-else, but it's genuinely unclear and nobody looked. Also: `just`
  has no dependency graph across recipes the way make does; if the deploy
  choreography gets complex, that limitation will bite — watch for it.
- **direnv** never came up but probably should exist in the mise/devenv story
  for per-repo env activation; low stakes, just noting the gap.
- **Beads/Ralph/Herdr** were treated as untouchable R11 furniture. Fine, but
  the _release manifest + change plan_ artifact (§7) and Beads tasks are
  conceptually the same shape (a signed, described unit of intended change).
  Someday the deploy plan and the task graph might want to share a schema.
  Not now.

## Architecture roads not taken (worth remembering)

- **SPIFFE/SPIRE for workload identity.** The role-mesh + CA-signed-builders
  design is reinventing a slice of what SPIFFE does (short-lived, attested
  workload identity). Probably too heavy for a personal fleet, but if the
  mesh ever grows past ~a dozen hosts or gets multi-operator, SPIFFE is the
  grown-up version of the SSH-CA-principal scheme and worth a look before
  hand-rolling more.
- **The role mesh is a consensus system in disguise.** "main/backup/equal
  peer, any box can hold any role, no control node" is — the moment two
  peers can both believe they're `main` for a single-writer role — a
  distributed-consensus problem. The final doc's lease/fencing language
  papers over it. If the mesh ever does automatic failover for a
  _stateful_ single-writer role (not just healing), you will need real
  leader election (Raft-lite, or lean on an existing store's lease: e.g. a
  Tailscale-reachable etcd/consul, or even a Postgres advisory lock on the
  obs DB). Don't build this until a role actually needs it, but know the
  cliff is there. Today every single-writer mutation requires an
  operator-signed plan precisely to dodge this — that's the right v1 move.
- **CRDTs for the Site Model overlay merge.** When consented devices opt into
  feature sets and those persist in a per-device overlay that merges with
  upstream config (T3), you have a distributed-merge problem. If it stays
  "upstream wins, overlay is additive and non-conflicting" it's trivial; the
  moment overlays can conflict with upstream you'll want CRDT-ish merge
  semantics or a defined conflict-resolution order. Design the overlay to be
  _structurally_ non-conflicting (additive-only, namespaced) to avoid this
  entirely — cheaper than solving it.
- **Content-addressed everything.** Nix already gives you this for closures;
  the artifact lane (APKs, cross-built binaries, firmware) should adopt the
  same discipline — address artifacts by hash, let the manifest be the only
  name→hash binding. Makes the transparency log and rollback trivially
  correct. Probably already implied but worth stating as a principle.
- **NixOS on Android via a chroot/proot** exists (people run it) — explicitly
  NOT recommending it (violates the whole R4 analysis) but noting it was
  considered and rejected so nobody re-litigates.

## The AI-workflow angle (this is your actual differentiator)

- The single most novel thing in this whole design isn't the Nix or the mesh —
  it's that **the config system and the AI-agent-orchestration system are
  converging**. The consent artifact, the change plan, the advisor API, the
  local-fix-until-upstream-heals loop: these are the same primitives as your
  Beads/Ralph/Herdr agent stack. Nobody's really built "config management
  where the deploy plan is legible to and negotiated by AI agents on both
  ends." That's the interesting research territory, and it's undersold in the
  proposals because I kept it scoped to v1 interfaces.
- **The change plan should be designed as an LLM-legible artifact from the
  start**, not just machine-parseable. `nix store diff-closures` output is
  precise but not semantically rich; an advisor AI wants "this bumps openssl
  across a CVE boundary and restarts your public-facing proxy," not a package
  delta. Consider a plan format with a _semantic_ layer (generated, cached)
  over the _verifiable_ layer (the closure diff). The verifiable layer is
  ground truth; the semantic layer is the advisor's briefing.
- **Two-agent consent is the safety pattern.** Your vision has a user-side AI
  advisor evaluating a plan. The robust version: the _proposing_ side and the
  _consenting_ side run different models (different vendors ideally), and
  disagreement between them is a signal to escalate to the human. This is
  exactly what we just did manually with the multi-vendor panel — formalize
  it into the consent loop. Vendor diversity as a security control.
- **The cross-agent worktree incident (2026-08-06) is a preview of the trust
  layer's hardest problem.** Two agents with no shared view of each other
  clobbered a branch. That's the _same_ problem as two consented devices, or
  two peers claiming a role, or an upstream fix racing a local patch. Whatever
  solves the worktree-ownership problem (explicit ownership, provenance gates,
  procedural-not-interactive checks) is a prototype of the fleet trust model.
  Study your own incident writeup as threat-model input — I flagged it to the
  red-teamer for exactly this reason.

## Model/vendor notes for future architecture work (capture while fresh)

- **Best harness on this machine today: Codex CLI (GPT-5).** It ran full
  agentic loops, dug up on-disk ground truth unprompted (found SITE-CONTRACT,
  the _secretspec wrapper), verified tool docs against the web, and self-
  validated output with markdownlint. Use it for the heavy independent passes.
- **Grok 4.5 (SuperGrok) punched above expectations** for structured
  comparative reasoning — its critique-of-Claude section was the most useful
  single artifact of the panel because it named the actual fork (D1) cleanly.
  Good "second architect who argues back" model.
- **Gemini underperformed but it was mostly harness, not model.** The CLI's
  `--print` mode did one shallow pass while others looped. If you want
  Google's real capability, use Antigravity agent-mode or Deep Think, not
  `gemini --print`. Don't judge Gemini 3 on the thin doc it produced here.
- **DeepSeek v4 Pro: couldn't test (quota/billing).** It's one of your two
  planned _implementation_ workhorses, so its ability to read+critique these
  docs is a capability probe worth doing later via direct API. $3.91 direct
  balance may cover a review pass.
- **For architecture specifically**, the pattern that worked: one model does
  the interactive requirements dialogue + first proposal (needs to hold a lot
  of context and ask good questions — that's the expensive seat), then
  independent one-shot proposals from _different vendors_ with a shared
  written brief, then synthesis by the dialogue-holder. The independence rule
  (don't read others' docs until yours is done) mattered — it's why the
  convergence is meaningful evidence rather than herding.
- **Untested but plausibly strong for this work, via OpenRouter/Zen:**
  Qwen3-Max and Kimi K2 (both good at long-context systems reasoning, cheap,
  and genuinely different training distributions = real diversity). A
  reasoning-heavy model like o3/o4 or DeepSeek-R-successor for the pure
  logic-of-the-trust-layer. Mistral Large for a European-infra perspective on
  the Free Sysadmin/licensing angle. None tested — just where I'd spend the
  next $5 of curiosity.
- **Diversity > raw capability for review passes.** The value of the panel was
  that OpenAI and Grok _independently_ landed on the Ansible-permanence
  argument against my position — two different models agreeing is worth more
  than one stronger model. For future reviews, optimize for training-distro
  diversity, not leaderboard rank.

## Small technical flags (don't lose these)

- **x86_64-darwin is dying in nixpkgs** — irrelevant now (Intel mini out of
  scope) but if any Intel Mac ever re-enters, it's a Linux-builder conversion,
  not a darwin host.
- **minisign vs signify vs sigstore:** the offline-verification requirement
  (handset verifies with no network) rules out naive sigstore/Rekor as the
  _only_ path (it wants a transparency-log lookup). Keep offline Ed25519 as
  the floor; sigstore is an _additional_ attestation, not the base. The
  red-team is checking this.
- **Nix cache trust is binary and total** — any substituter you trust can
  give you any path. The `builder = fully trusted` note in the proposal is
  correct and underscored; harmonia/attic don't change it. This is the
  softest part of the Nix story and the red-team should hammer it.
- **Tailscale ACLs are the real network trust boundary** and no proposal
  specified them. "Reachable over Tailscale" is doing a lot of unexamined
  work — the mesh's security assumes tailnet = trusted, which is a policy
  decision that should be explicit (esp. once consented/untrusted devices
  join the tailnet). Flagged to red-team.
- **Termux's `pkg` is not reproducible** and that's the actual argument for
  the Nix-cross-built-artifact lane — worth making explicit if the artifact
  lane ever needs justifying to a reviewer.
- **CFEngine as last-ditch is also a standing remote-exec capability** —
  i.e. an attack surface. It's your recovery path AND a way in. The red-team
  should look at whether the consent model applies to the CFEngine channel or
  bypasses it (I suspect it bypasses, which is both the point and the risk).
- **entangle stitch + parallel YOLO agents = corruption risk.** The tangle-
  parity CI catches drift but not a mid-stitch race. If literate sources
  expand, the cross-agent ownership rules must extend to "who may stitch this
  doc right now." Noted in the literate section but worth a real lock.

## Meta

- The final doc's Decision Register (§6) is the thing to actually maintain —
  it's the living state. Everything else is archival. If you revisit this in
  6 months, read the register first, then this dump, then only the section of
  the final doc whose decision you're reopening.
- If you commission the DeepSeek pass and/or a real Gemini-3 agent pass later,
  the interesting question isn't "do they agree" — it's "do they find a
  seventh contested decision the panel missed." Four models found six forks
  and converged on the rest; a fifth/sixth finding _nothing new_ is itself
  evidence the design is stable.
