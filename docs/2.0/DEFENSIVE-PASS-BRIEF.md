# DEFENSIVE COUNTER-PASS BRIEF — hardened trust-layer v1

## Why this exists

The trust/deploy/consent layer has been **attacked once and defended zero
times**. `docs/2.0/redteam-trust-layer-openai-v1.md` (OpenAI/GPT-5) returned
nine findings — three Critical — and the verdict: *"do not ship v1 pull
deployment or consent on the proposed one-key/one-manifest design."* Nobody
has answered it. That asymmetry is the single biggest weakness in the corpus:
the most security-critical part of the architecture is also the least
reviewed-in-both-directions.

**Your job is the defense.** Not a rebuttal — the findings are largely
correct. Design the actual v1 that closes the blockers, and be equally clear
about which findings should be closed by **cutting scope** rather than
building machinery.

You are deliberately NOT the attacker (OpenAI wrote the red-team) and NOT the
synthesizer (Claude holds the operator dialogue). Keep that separation:
critique both freely.

## Deliverable

ONE file: `docs/2.0/trust-layer-hardened-design-<slug>-v1.md` (slug in your
launch prompt).

## Required contents

### 1. Disposition of every red-team finding
Table covering RT-01…RT-09 plus each systemic gap. For each:
`ID | agree/partially/disagree (justify disagreement) | disposition`
where disposition is one of:
- **FIX-IN-V1** — build it now; you must then specify it in §2
- **CLOSE-BY-SCOPE** — the vulnerable surface is not built in v1; state the
  exact scope cut and the gate that must be passed before it opens
- **ACCEPT-RISK** — with explicit rationale, blast radius, and detection
- **DEFER-WITH-TRIGGER** — the named condition that forces it

### 2. The hardened v1 design (this is the core deliverable)
Concrete, buildable specifications — not principles. At minimum:

- **Key/root model:** answer RT-01. What is the minimum viable threshold-root
  scheme for a **solo operator** (this matters: a 2-of-3 ceremony with
  hardware tokens is very different for one person than for an org)? Where do
  shares live? What is the recovery runbook when the laptop is lost or the
  key is stolen? Full TUF is likely overkill — say what subset is not.
- **Update protocol:** answer RT-02. Concrete metadata fields: version
  monotonicity, expiry, channel binding, snapshot/target binding, persisted
  highest-seen state, clock strategy. Write the client verification algorithm
  as ordered, testable steps.
- **The typed operation IR:** answer RT-03/RT-04 — the highest-value single
  artifact. Specify the ChangePlan operation schema: what an operation
  declares (capabilities, resources, target binding, rollback, expiry,
  nonce), and **how the executor mechanically refuses anything outside it**
  on each of the three platforms (Nix host, Ansible/Linux+macOS, Android
  agent). Concrete: show the schema and a worked example.
- **Consent v1:** the `offer()` interface with device-key binding, single-use
  nonce, expiry, timeout-is-deny, capability vector, protected receipts.
- **Builder/cache containment:** answer RT-05 with separated authorities.
- **SecretSpec reference monitor:** answer RT-06 — deny-by-default policy
  mapping (service identity, host role, capability) → handle.
- **Role mesh safety:** answer RT-07 — you may simply forbid autonomous
  failover in v1; if so, say exactly what replaces it.

### 3. Scope-cut proposal (be aggressive here)
The operator is **one person** with a laptop, three Android devices, and a
VPS that does not exist yet. Propose the smallest v1 that is genuinely safe.
Explicitly evaluate: *"v1 is push-only from operator hosts; no autonomous
pull; no consented devices; no autonomous role failover"* — how many blockers
does that close for free? What is the minimum useful thing that still ships?

### 4. Revised phase gates
Rewrite the final architecture's Phase 4/5/6 gates with the security
prerequisites embedded as entry criteria, with rollback for each.

### 5. Build order and effort
Rough effort per item (days/weeks for one operator with AI agents), and what
to build first. Flag anything that is a multi-week project masquerading as a
bullet point.

## Rules

- Read first: `docs/2.0/redteam-trust-layer-openai-v1.md` (the thing you are
  answering), `architecture-final-v1.md` (authoritative architecture),
  `architecture-proposal-v1.md` §7–8/§12 (detailed manifest/consent design),
  `tooling-assumptions-review-*-v1.md` (tool verdicts — esp. minisign,
  deploy-rs, cache, OpenHands Surface A/B split), `ideas-dump-claude.md`.
  Ground truth: `~/ops/site-private/secretspec.toml`,
  `~/ops/site-djbclark/inventory/hosts.yml`, `~/ops/site-djbclark/registry/`,
  `~/ops/stayturgid/`, `~/src/ops-worktrees/README.md`.
- **Verify current facts on the web** (TUF, minisign, sigstore/Rekor, Nix
  cache trust, deploy-rs, Android signing/provenance). Do not trust training
  memory for tool/protocol capabilities.
- You MAY clone/download into `~/src/vendor/` and search the web.
- Create ONLY your own file (+ optional `questions-<slug>.md`). Never modify
  any file you did not create; nothing under `~/ops`. No git commits/pushes.
- Bias to **buildable by one operator**. A design that is correct but will
  never be implemented is a failed design. Where the secure option is too
  expensive, say so and propose the cheap safe subset instead.
