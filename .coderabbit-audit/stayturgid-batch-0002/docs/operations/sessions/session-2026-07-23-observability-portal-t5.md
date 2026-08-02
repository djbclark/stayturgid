# Session checkpoint — observability/portal unification evaluation (2026-07-23)

**Purpose:** Recoverable handoff for whoever picks up OPTIONS T5.
**OPTIONS:** T5 (Track T — Tooling, deferred)
**Evaluation doc:** [observability-portal-unification-evaluation-2026-07-23.md](../../research/evaluations/observability-portal-unification-evaluation-2026-07-23.md)

## What happened this session

The operator pasted a third-party AI's proposal to (a) unify metrics/logs/health into
Grafana and (b) replace the landing page with Homer or Glance. Rather than acting on it
directly, this session researched the actual repo state, found the proposal's premises
didn't hold, wrote up the findings as a dated evaluation doc, and added OPTIONS T5. No
code, config, or running services were touched — this was documentation only.

## Decision recorded

- **Do not adopt Homer/Glance.** They'd duplicate the landing page's job worse than the
  landing page already does it, and the real open question — replacing/augmenting the
  Fleet Dashboard (`control/bin/dashboard.py`) — is already scoped in
  `docs/research/prompts/dashboard-framework-research.md` and hasn't been run yet.
- Two separable next steps identified, not started:
  1. Finish OpenObserve → Grafana metrics datasource wiring (Prometheus-compatible, not
     Elasticsearch — the fragment already anticipates this).
  2. Actually run the dashboard-framework-research.md prompt as its own research task.
- Both are blocked on the same thing: **OpenObserve auth for Vector is broken
  fleet-wide** (401s since at least 2026-07-22 — see
  [handoff-2026-07-22-native-agent-k1.md](../../archive/sessions/handoff-2026-07-22-native-agent-k1.md) §1,
  operator action required, `OPENOBSERVE_ROOT_PASSWORD` empty/wrong in the Vector
  LaunchAgent env). Check whether this has been fixed before starting either thread.

## Loose ends for the next agent/operator

1. **`docs/options.md` T2 has a stale cross-reference** — its heading and body cover
   JS-runtime-supervision tooling (PM2, Uptime Kuma, etc.), but it links
   `research/prompts/dashboard-framework-research.md`, which is actually about replacing
   the Flask fleet dashboard with an Ansible/ops framework — a different, larger
   question with no OPTIONS entry of its own tracking the prompt itself. Not fixed this
   session (out of scope); worth splitting next time Track T is touched.
2. **OpenObserve/Vector auth still broken** as of this session start — re-check status;
   don't assume the 2026-07-22 handoff's fix instructions have been applied.
3. **No `docs/research/dashboard-framework-evaluation-*.md` exists yet.** The prompt is
   ready to hand to a research agent as-is.
4. **Git housekeeping note, not a code issue:** this session's commit
   (`248de5f`) got bundled with unrelated K1-handoff doc updates
   (`docs/README.md`, `docs/operations/handoffs/handoff-2026-07-2{2,3}-native-agent-k1.md`)
   that were already staged in the working tree — apparently from a concurrent session —
   before this session ran `git commit`. A pre-commit hook auto-pushes on success, so by
   the time this was noticed the combined commit was already on `origin/master`. Nothing
   was lost or overwritten (verified via `git fetch` + reflog), and the pushed content is
   legitimate, just under a commit message that only describes the T5 half. Left as-is
   per this repo's git safety rules (no amending published commits). If working in this
   repo concurrently with another agent/session, check `git status` for pre-staged
   changes before committing — don't assume a clean stage is yours alone.

## Files touched this session

- `docs/research/evaluations/observability-portal-unification-evaluation-2026-07-23.md` (new)
- `docs/options.md` (added T5)
- This file (new)

No production dashboard code, Caddy, launchd, or persistent host software was modified.
