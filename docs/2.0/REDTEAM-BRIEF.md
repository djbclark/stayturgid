# RED-TEAM BRIEF — stayturgid 2.0 trust/deploy/consent layer

You are an adversarial security reviewer. Your ONLY job is to break the
security design of the stayturgid 2.0 architecture — specifically the
deploy, release-signing, consent, builder-trust, pull-converge, and
web-of-trust machinery. Assume a capable, motivated attacker. Do not be
polite; do not propose the architecture's virtues. Find the holes.

## Deliverable

Write ONE file: `docs/2.0/redteam-trust-layer-openai-v1.md`.

Structure it as a threat report:
1. **Assets & trust boundaries** — what must not be violated, and where the
   boundaries actually are (correct the docs if they draw them wrong).
2. **Attacker models** — enumerate concrete adversaries (compromised
   builder, stolen release key, malicious feature-bundle author, hostile
   consented device, network MITM on Tailscale, malicious/compromised AI
   coding agent with worktree write access, insider, supply-chain via
   nixpkgs/cache, a compromised upstream Shizuku/dependency).
3. **Findings** — each with: ID, title, severity (Crit/High/Med/Low),
   preconditions, attack walkthrough, what breaks, and a concrete fix or
   mitigation. Be specific to THIS design (minisign/Ed25519 manifests,
   `nix store diff-closures` plans, CA-signed builders, harmonia/attic
   cache, ~50-line pull-converge agent, offline verification requirement,
   consent `offer()` interface, secretspec injection, `trust_tier`
   consented devices, TUF-roadmap, transparency-log/attestation ideas).
4. **Systemic gaps** — things the design does not address at all
   (revocation, key rotation under compromise, rollback/downgrade attacks,
   time/replay, metadata privacy for consented devices, quorum/split-brain
   abuse of the no-control-node role mesh, denial of service on the
   converge agent, trust bootstrapping / TOFU, the "local-fix-until-
   upstream-heals" auto-merge path as an injection vector).
5. **Prioritized fix list** — what to change before v1 ships vs. what's
   acceptable as roadmap.

## Rules

- Read the design docs FIRST: `docs/2.0/architecture-final-v1.md` is
  authoritative; `docs/2.0/architecture-proposal-v1.md` §7/§8/§11/§12 has
  the detailed manifest/consent/trust design; the other `-*-v1.md`
  proposals have alternative takes on the same machinery. Also read the
  real ground truth: `~/ops/site-private/secretspec.toml`,
  `~/ops/site-djbclark/inventory/hosts.yml`, `~/ops/site-djbclark/registry/`,
  `~/src/ops-worktrees/README.md` (the cross-agent rules are themselves a
  trust-boundary artifact — the 2026-08-06 double-merge incident described
  there is a real in-scope threat).
- You MAY read/clone code into `~/src/` and search the web (verify current
  facts about minisign, TUF, sigstore/Rekor, Nix cache trust, deploy-rs,
  comin, Tailscale ACLs — do not trust training memory).
- Create ONLY `docs/2.0/redteam-trust-layer-openai-v1.md` (and optionally
  `docs/2.0/redteam-questions-openai.md`). Never modify any file you did
  not create — especially not the protected proposal docs or anything
  under `~/ops`.
- No git commits/pushes. No changes under `~/ops`.
- Be decisive about severity. A finding without a concrete attack
  walkthrough is not a finding. Prefer 8 sharp findings over 30 vague ones.
