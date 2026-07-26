# Session 2026-07-23 — AI memory policy migration to git (${OPS_ROOT:-~/ops}/site-private)

**Status: COMPLETE.** All work committed and pushed across all three repos.
This doc is a handoff/historical record — for current state read
`docs/STATUS.md` (this repo), and `${OPS_ROOT:-~/ops}/site-private/README.md` for the
memory/site-documentation policy this session established.

## What happened

Earlier the same day, a separate session (`session-2026-07-23-docs-consolidation.md`,
this same directory) restructured stayturgid's docs and moved open-work
tracking to GitHub issues. Partway through that session, the operator asked
to also get all AI memory content (until then living only under
`~/.claude/`, outside any git repo) into version control. This session did
that.

## Final state (verified this session, all repos synced with origin)

- **`${OPS_ROOT:-~/ops}/stayturgid`** (public) HEAD `e4b402c`. Added `docs/notes/lessons-learned.md`
  (11 stayturgid-specific memory topics rewritten as prose), a new
  `docs/architecture/multi-site-topology.md` §4.10 documenting the
  three-repo convention, and a "fix adjacent issues opportunistically"
  convention folded into `docs/coding-rules.md`.
- **`${OPS_ROOT:-~/ops}/site-djbclark`** (private) HEAD `f966ca2`. Got its first `AGENTS.md`
  (it had none) plus cross-links; no new memory-derived content needed since
  its existing `docs/relay/` and `docs/reference/available-ai-models.md`
  already fully covered the two site-djbclark-bound memory topics. One
  pre-existing uncommitted file remains there
  (`human/F2-BREW-SERVICES-DECISIONS.md`) — operator-authored, deliberately
  left untouched all session, not related to this work.
- **`${OPS_ROOT:-~/ops}/site-private`** (new, private) HEAD `1ec78cf`. Created fresh this
  session: canonical `README.md` (the memory/site-documentation policy — what
  goes where, how the live memory symlink works), `AGENTS.md` (entry point +
  a general "always `pbcopy` a requested prompt" behavior convention added at
  the very end), `home-agents.md` (backs the home-directory symlinks below),
  and `memory/` (8 genuinely generic memory topics + `MEMORY.md` index).

## Symlinks now in place (verified resolving correctly)

- `~/.claude/projects/-Users-djbclark/memory` → `${OPS_ROOT:-~/ops}/site-private/memory`
- `~/AGENTS.md` → `${OPS_ROOT:-~/ops}/site-private/home-agents.md`
- `~/CLAUDE.md` → `${OPS_ROOT:-~/ops}/site-private/home-agents.md` (points directly at the
  same target as `~/AGENTS.md`, not chained through it, so one broken link
  can't cascade)

## Retired (backed up first, then removed — content fully migrated)

- The original `~/.claude/projects/-Users-djbclark/memory/` contents (22
  files) → backed up to `~/.backups/memory.pre-symlink-backup-2026-07-23/`.
- `~/.claude/projects/-Users-djbclark-ops-stayturgid/memory/` (one
  stayturgid-scoped memory, migrated into `docs/coding-rules.md`) → backed up
  to `~/.backups/stayturgid-project-memory-pre-retire-2026-07-23/`, then the
  live directory removed (not symlinked — project-specific content now lives
  as a normal doc, not as Claude memory, per the policy in
  `${OPS_ROOT:-~/ops}/site-private/README.md`).

## Explicitly out of scope (operator confirmed, not touched)

- `~/.claude/projects/-Users-djbclark-upmon-handoff/memory/` — `~/upmon-handoff`
  isn't a git repo.
- `~/.claude/projects/-Users-djbclark-src-ai/memory/` — `~/src/ai` (GitHub
  `djbclark/ai`) is its own git repo; the operator will have that project's
  own agent do the equivalent migration. A ready-to-paste prompt for that was
  generated and copied to the clipboard at the end of this session (not
  saved to a file — if it's needed again, the pattern is documented in this
  session doc and in `${OPS_ROOT:-~/ops}/site-private/README.md`'s policy).

## If anything looks inconsistent, check these first

- All three repos' local HEAD should match `origin/master` — if not, a
  session was interrupted mid-push; `git status -sb` in each will show it.
- The three symlinks above should all resolve (`ls -la` each target). If one
  is missing/broken, the backups under `~/.backups/` have the pre-migration
  content to restore from.
- `${OPS_ROOT:-~/ops}/site-private` is private on GitHub (`djbclark/site-private`) — if it
  doesn't exist or is public, something went wrong with its creation.
