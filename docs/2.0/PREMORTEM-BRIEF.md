# PRE-MORTEM / SCOPE-REALISM BRIEF — stayturgid 2.0

## Why this exists

Every document in `docs/2.0/` is architecture. Not one asks the two questions
that actually determine whether this happens:

1. **It is six months from now and this migration failed. What went wrong?**
2. **How much work is this really, for ONE person, and what should be cut?**

Your job is that lens. You are not an architect here — you are the sceptical
engineering manager who has watched ambitious migrations die.

## The reality to hold onto

- **One operator.** Not a team. With AI coding agents (Claude Code, Codex,
  Ralph controllers, Herdr) doing much of the implementation.
- **Live fleet today:** one M1 MacBook Air (a _laptop_, which sleeps, and is
  currently the sole control node running the entire observability stack),
  three Android devices (Galaxy S24, Pixel 7a, Kindle Fire HD8) over
  Tailscale. `vps-primary` and the Intel mini are `offline_unprovisioned` —
  **the entire Linux half of this architecture is hypothetical hardware.**
- **The system already works.** This is a migration of a functioning
  production setup that the operator depends on, not a greenfield build.
- **In-flight work already exists** (per repo docs): secretspec value
  migration, a Fire OS soak, OpenObserve clean-log acceptance, LiteLLM
  multi-host rollout, Beads/Ralph orchestration, plus the operator's other
  projects (aiuse, Hermes, twilio relay, site work).
- **The current plan:** 8 architecture phases + a signing-key ceremony +
  threshold-root protocol + typed operation IR + capability-enforcing
  executors on three platforms + reproducible APK provenance + consent UI +
  exit drill. Plus tooling changes. Plus a Free Sysadmin extraction.

## Deliverable

ONE file: `docs/2.0/premortem-scope-realism-<slug>-v1.md` (slug in your
launch prompt).

## Required contents

### 1. Pre-mortem

Assume it is 2027-02 and the migration is dead, abandoned, or worse — a
half-migrated mess that is harder to operate than what it replaced. Write the
autopsy. Be specific and concrete, not generic ("scope creep" is not a
finding; _"Phase 3 stalled with 6 of 14 services flipped and two writers
fighting over the vector plist"_ is). Rank causes by probability.

Cover at minimum: half-migrated states and their operational cost; the
laptop-is-the-control-node problem during migration; the never-provisioned
VPS blocking three phases; the exit drill that never actually gets run; the
trust layer eating months and delivering nothing user-visible; AI agents
producing plausible-but-wrong infra changes at scale; the operator losing
interest once the interesting design work is done; a macOS upgrade breaking
nix-darwin mid-migration; a security incident _caused by_ the new machinery.

### 2. Effort reality check

Go phase by phase (final doc §5) and the trust-layer work, and give honest
ranges in operator-days/weeks _with_ AI assistance. Call out anything that is
a multi-week project written as a bullet point. Flag anything that cannot be
meaningfully delegated to an AI agent and therefore consumes scarce human
attention.

### 3. What to cut

The aggressive version: **what is the smallest subset that delivers most of
the value?** Be specific about what to drop or defer indefinitely. Consider
seriously: is the whole Nix layer worth it for a fleet of this size? Is the
role mesh solving a problem the operator actually has _today_? Should the
trust/consent layer simply not be built until there is a real second user?
Argue your answers; do not just ask the questions.

### 4. Sequencing for motivation and reversibility

Reorder the work so that (a) each step delivers standalone value even if
everything after it is abandoned, and (b) nothing leaves the system worse
than it started if the operator stops mid-way. Name the specific _stopping
points_ where the system is in a coherent state.

### 5. Kill criteria and leading indicators

What observable conditions should make the operator stop, roll back, or
re-scope? What early signals predict failure (e.g. "Phase 0 schemas not
written within N weeks means the data-model spine won't happen")? What
should be checked at each phase boundary?

## Rules

- Read: `docs/2.0/architecture-final-v1.md` (esp. §5 migration plan),
  `redteam-trust-layer-openai-v1.md` §5 (blockers — these add substantial
  unbudgeted work), `tooling-assumptions-review-*-v1.md`,
  `ideas-dump-claude.md`. Ground truth in `~/ops` (READMEs, STATUS docs,
  inventory, justfiles, docs/OPS-RELEASES.md) and
  `~/src/ops-worktrees/README.md` — including the 2026-08-06 double-merge
  incident, which is direct evidence about how AI-agent-driven work fails
  here.
- Look at the repos' actual in-flight work (open GitHub issues via `gh` if
  available, docs/STATUS.md, handoff docs) to gauge existing load.
- Create ONLY your own file. Never modify any file you did not create;
  nothing under `~/ops`. No git commits/pushes.
- **Be blunt.** Flattery is worthless here. If the plan is 3x too big, say
  so and say which third to keep. If a piece is genuinely low-risk and
  high-value, say that too — this is a realism pass, not a demolition.
