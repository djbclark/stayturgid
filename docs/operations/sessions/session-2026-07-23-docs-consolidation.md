# Session 2026-07-23 — docs consolidation, GitHub tracking migration

**Status: IN PROGRESS — this file is the continuation checkpoint.** If this
session dies, a successor AI should read this file top-to-bottom, then continue
from the first unchecked item in "Remaining steps". Update checkboxes and the
"Where I stopped" line as you go, committing after each step.

## Operator decisions (locked — do not re-ask)

1. **Tracking = Hybrid.** GitHub issues become canonical for discrete work
   items (bugs, ops follow-ups, soak verifications), with workstream labels and
   a written public-repo hygiene policy. The repo keeps a compact
   `docs/STATUS.md` (single entry point) plus a slimmed `docs/options.md`
   (stable IDs, issue links).
2. **Restructure = Aggressive full re-org.** Archive superseded docs, merge
   handoffs into sessions, rename/merge top-level docs, rewrite
   coding-rules.md around the new layout, update code-side doc pointers.
3. **Session docs stay in this public repo** with hygiene rules codified: no
   operator contact info, no raw device dumps, no real IPs/serials. Sensitive
   artifacts go to the private site overlay.
4. **No docs/plans in vendor-specific out-of-git dirs** (`.cursor`, `.claude`,
   …). `.cursor/rules/` already migrated to `docs/rules/`.

## Done so far (commits on master, each one pushed or pushable)

- [x] `1dbfcc1` — restructure: `docs/archive/{plans,sessions}/` created;
      superseded plans (outstanding-fix-priorities-2026-07-13,
      native-agent-status, autojs6-to-native-apk, ongao/ovgo/agent-ovgo,
      just-migration, firerpa-integration, logging/) and old sessions
      (2026-07-12/13/14) archived; `operations/handoffs/` merged into
      `operations/sessions/` (07-23 K1 handoff is live there; 07-22 archived);
      `.cursor/rules/*.mdc` → `docs/rules/*.md` (content de-staled in the move:
      make→just, dead ADR links, AutoJs6 watchdog → native agent); all inbound
      references repo-wide updated.
- [x] `1f1ec63` — hygiene scrub of session-2026-07-23-handoff.md (no raw dumps
      to public issues; operator contact removed; healer note repointed at
      native agent post-K1).
- [x] `70953d4` — imported two stranded docs from `~/.claude/plans/` with
      identity genericization: `docs/archive/plans/blackbox-exporter-plan-2026-07-21.md`
      and `docs/research/active-passive-monitoring-evaluation-2026-07-21.md`.

## Remaining steps (in order)

- [ ] **STATUS.md** — write `docs/STATUS.md`: dated fleet/workstream snapshot
      (source: consolidated-state summary at the bottom of this file), operator
      actions needed, doc map. Keep ≤120 lines, weaker-AI-friendly.
- [ ] **handoff.md** — rewrite the 8-line stub to point at STATUS.md +
      sessions + private overlay (many inbound links expect this file; keep the
      filename).
- [ ] **options.md rewrite** — fix stale front-matter (fleet snapshot is
      2026-07-13; pick-a-track table lists T1/F2/F4 wrong; suggested order
      cites shipped/abandoned items; dead handoff.md anchors); fix T2's wrong
      cross-link (its body is JS-runtime supervision →
      `research/javascript-runtime-supervision-2026-07-13.md`, NOT the
      dashboard-framework prompt); note ID collisions (H5, H1/H3, F1 each mean
      two things); move closed-entry bodies to
      `docs/archive/options-closed-2026-07-23.md`, keep one-line ledger; add
      GitHub issue links once issues exist; add post-K1 rescope notes to
      43/44/54 (they presuppose live AutoJs6).
- [ ] **coding-rules.md + AGENTS.md updates** — reading order becomes
      AGENTS.md → docs/rules/ → docs/STATUS.md → docs/options.md + GitHub
      issues → task docs (outstanding-fix-priorities is archived; do NOT tell
      agents to read it); fix `~/stayturgid` → `~/ops/stayturgid` in
      coding-rules session-start; add GitHub-issues policy section (when to
      file, labels, hygiene: no raw dumps/contacts/IPs); note AutoJs6 runtime
      retired 2026-07-22 (K1) in the language-boundary section
      (device/autojs6/ is legacy reference code).
- [ ] **docs/README.md index refresh** — add STATUS.md, docs/rules/, archive
      rows; drop/relabel archived rows.
- [ ] **Code-side pointer fixes** (docstrings/messages only, then
      `just check` + `pytest tests/python/test_fleet_health.py`):
      `control/bin/check_fleet_health.py:267` (says "prefer fixing
      AutoJs6/a11y/repair before OPTIONS 43–45; see docs/handoff.md" — stale
      post-K1); `control/bin/fleet_health_monitor.py` lines ~9/13/61/166
      ("dual-run", AutoJs6-restart wording); `tests/healing_registry.json`
      AGENT-FRESH description says "dual-run OPTIONS K1";
      `docs/architecture/components/autojs6.md` header still says dual-run —
      mark retired-from-fleet 2026-07-22, code kept as reference (Rhino
      gotchas section stays).
- [ ] **GitHub migration** — create labels `k1-native-agent`, `f1-mcp-bridge`,
      `observability`, `operator-action`; create issues (bodies must follow
      hygiene policy; device aliases s24/p7a/hd8 OK, no IPs/serials/contacts): 1. K1 post-cutover fleet verification (p7a+hd8 offline; AutoJs6
      uninstall unverified — uninstall task is `failed_when: false`; hd8
      maintenance flag; p7a FIRERPA UID-2000 bridge gap; battery
      verification). Source: operations/sessions/handoff-2026-07-23-native-agent-k1.md. 2. OpenObserve↔Vector 401 fleet-wide (operator: set
      OPENOBSERVE_ROOT_EMAIL/PASSWORD for the Vector LaunchAgent, restart,
      then `control/tools/native-agent/reingest_soft_health.py` dry-run →
      real). Blocks K1 soak evidence + both T5 threads. Still live as of
      2026-07-23T12:21Z (vector.log). 3. K1 residuals: fleet still on `.debug` APK → release APK + GitHub
      release asset matching Obtainium filter; forced CLOSED_NO_SHELL soak
      (never run); Fire Shizuku official STORED-libs packaging
      (~/src/Shizuku). 4. F1 FIRERPA MCP bridge implementation (plan
      operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md steps 2–10;
      step 1 done, mcp 1.28.1 installed; ⚑ consent-surface phasing awaits
      operator). 5. T5 follow-ons: OO→Grafana Prometheus datasource + run
      dashboard-framework research prompt (both blocked by issue 2).
      Cross-comment #16 ↔ #41 (overlapping battery-percentage symptom).
      Then backfill issue numbers into STATUS.md + options.md, commit.
- [ ] **Push** everything; verify `just check` green; update this checkpoint's
      checkboxes; final wrap-up.

**Where I stopped:** after commit `70953d4`. Checkpoint file committed; NOTHING pushed yet this session — push first. Continue at "STATUS.md" step.

## Consolidated current state (evidence-checked 2026-07-23, ~12:20Z)

Use this as the source for STATUS.md; every claim was verified this session.

- **Repo:** master == origin/master at start (938b018); no PRs, no branches.
  52 commits landed since the 2026-07-20 FINAL-REVIEW anchor (430560fa).
- **Fleet:** s24 online/healthy (direct Tailscale, clean soft-health every
  ~17 min). p7a offline since ~03:28Z, hd8 offline since ~05:36Z —
  `just health` exits 1 with SCRAPE_STALE for both; needs physical check.
- **K1 native agent:** cutover commit 195c5c7 (2026-07-22) deleted
  autojs6_watchdog role, switched health to agent_missing/agent_stale, added
  dashboard agent card + best-effort AutoJs6 uninstall (`failed_when: false`).
  BUT: only s24 verified post-cutover; the 07-22 handoff's soak preconditions
  (CLOSED_NO_SHELL pilot, 7-day OO evidence) never ran; fleet last seen on
  `.debug` APK; "Phase 4 complete" in options.md is intent, not verified state.
- **OO/Vector:** 401 Unauthorized ongoing (latest 12:21Z);
  soft_health.jsonl on the Mac is the SSOT until fixed.
- **F1 MCP bridge:** docs-only; D1–D3 resolved; mcp 1.28.1 in
  ~/.venv-stayturgid-firerpa (venv has NO pip binary — verify via
  importlib.metadata, not `pip show`); implementation gated on operator go +
  consent-surface phasing answer.
- **T5:** evaluation done (reject Homer/Glance); two follow-ons blocked on
  the 401.
- **Settings-state corruption:** issues #41/#42 open, human investigation
  pending; #16 overlaps #41.
- **Known gotchas:** stray root-owned 0-byte file at `~/stayturgid` (real repo
  is `~/ops/stayturgid`; removal needs sudo — operator); `just firerpa-health`
  exits 1 silently by design (read ~/.config/stayturgid/logs/firerpa-health.log);
  pre-commit hook chain is strict (prettier/markdownlint MD060 table
  alignment — run `prettier --write` on touched .md before committing);
  device/native-agent/agent-release.jks must never be tracked;
  site-djbclark has one uncommitted operator file (human/F2-BREW-SERVICES-DECISIONS.md) — leave it alone.
- **Operator-action queue:** OO credentials + Vector restart; p7a/hd8
  physical check; F1 consent phasing decision (recommended: v1 osascript,
  elicitation later); stray ~/stayturgid removal; site repo dirty file.
