# Session 2026-07-23 — docs consolidation, GitHub tracking migration

**Status: COMPLETE.** All planned steps finished, committed, and pushed
(final commit `07d8e62`). Kept as a historical record of the consolidation —
read `docs/STATUS.md` for current state, not this file.

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

## Remaining steps — all done

- [x] `7863b86` **STATUS.md + handoff.md + options.md rewrite + GitHub-issues
      policy** — `docs/STATUS.md` added as the single entry point;
      `docs/handoff.md` rewritten to point at it; `docs/options.md` slimmed
      from 523 to ~250 lines (closed bodies moved to
      `docs/archive/options-closed-2026-07-23.md`, T2's cross-link fixed, ID
      collisions documented, 43/44/54 rescope notes added);
      `docs/rules/github-issues.md` added; AGENTS.md + coding-rules.md
      updated (reading order, `~/stayturgid` path fix, AutoJs6→native-agent
      wording, GitHub-issues option in the error/warning policy);
      docs/README.md index refreshed.
- [x] `cb4a958` **Code-side pointer fixes** — `check_fleet_health.py`'s stale
      "see docs/handoff.md"/AutoJs6 hint; `fleet_health_monitor.py`'s
      "dual-run" docstrings (AutoJs6 path relabeled legacy fallback,
      native-agent path relabeled current mechanism); `healing_registry.json`
      AGENT-FRESH description; `autojs6.md` header marked retired/reference
      only. Verified via `git stash` that the pre-existing `pytest`
      failures in `test_fleet_health.py` (`WATCHDOG_HEAL_AFTER`
      AttributeError) and the `just check` healing-coverage gap
      (native_agent mechanism missing `@heals` annotations) both predate this
      session — not introduced by these edits.
- [x] `07d8e62` **GitHub migration** — labels `k1-native-agent`,
      `f1-mcp-bridge`, `observability`, `operator-action` created; issues
      [#43](https://github.com/djbclark/stayturgid/issues/43) (K1 fleet-state
      verification), [#44](https://github.com/djbclark/stayturgid/issues/44)
      (OpenObserve↔Vector 401), [#45](https://github.com/djbclark/stayturgid/issues/45)
      (K1 residuals), [#46](https://github.com/djbclark/stayturgid/issues/46)
      (F1 MCP bridge, consent-surface question included),
      [#47](https://github.com/djbclark/stayturgid/issues/47) (T5 follow-ons)
      filed — all hygiene-compliant (device aliases only, no real
      IPs/serials/contacts). Cross-linked #16 ↔ #41. Backfilled issue links
      into `docs/STATUS.md` and the corresponding `docs/options.md` entries.
- [x] **Push + verify** — all commits through `07d8e62` pushed to
      `origin/master`; `lychee --offline` across all docs: 0 errors;
      `just check` run (same pre-existing healing-coverage gap as baseline,
      not a regression).

**Where I stopped:** nowhere — session complete. Working tree clean, in sync
with origin at `07d8e62`.

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
  is `${OPS_ROOT:-~/ops}/stayturgid`; removal needs sudo — operator); `just firerpa-health`
  exits 1 silently by design (read ~/.config/stayturgid/logs/firerpa-health.log);
  pre-commit hook chain is strict (prettier/markdownlint MD060 table
  alignment — run `prettier --write` on touched .md before committing);
  device/native-agent/agent-release.jks must never be tracked;
  site-djbclark has one uncommitted operator file (human/F2-BREW-SERVICES-DECISIONS.md) — leave it alone.
- **Operator-action queue:** OO credentials + Vector restart; p7a/hd8
  physical check; F1 consent phasing decision (recommended: v1 osascript,
  elicitation later); stray ~/stayturgid removal; site repo dirty file.
