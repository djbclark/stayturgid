# Session 2026-07-23 — memory/site-docs policy follow-up plan

**Status: COMPLETE (2026-07-23).** Executed with one intentional design change
vs the original “move canonical policy into stayturgid” proposal: policy is
**distributed** across the three siblings’ `AGENTS.md` files (each owns its
slice and points at the other two). The then-deferred site-discovery work was
subsequently implemented under
[stayturgid#48](https://github.com/djbclark/stayturgid/issues/48): `.mysite`,
private-companion exclusion/bootstrap, and selected-path announcements.

**Builds on:** `session-2026-07-23-memory-policy-migration.md` (this same
directory).

## What was executed

1. **Distributed policy** into each repo’s `AGENTS.md` (stayturgid product
   slice; `site-djbclark` site slice; `site-private` private/generic slice),
   with mutual path + absolute GitHub URL pointers. `README.md` ↔ `AGENTS.md`
   links in each repo.
2. **Removed** the obsolete “pending move to stayturgid” banner from
   `site-private/README.md`; replaced with the distributed-policy overview.
3. **Updated** `multi-site-topology.md` §4.8 / §4.10 to describe the discovery
   change later completed by #48, and to stop calling `site-private` the sole
   canonical policy home.
4. **Reconciled** loose `~/ops/StayTurgid TODO.md` as a stale duplicate of
   `site-djbclark/docs/relay/NEXT-PROMPT.md` and removed it.
5. **Independent project `~/src/ai`:** kept Claude memory symlink →
   `docs/memory/`; deduped duplicate memory essays into `AGENTS.md`; documented
   links to `site-private` memory (path + https); parked cswap investigation
   as #1 next-work for that repo.
6. **Opened** [#48](https://github.com/djbclark/stayturgid/issues/48) for
   discovery/`.mysite`/`site-private` special-case implementation.

## Original survey / research

Retained below for history. Do not re-derive; treat the **Status** line and
“What was executed” as authoritative for what landed.

---

## What prompted this (historical)

After the migration session finished, the operator asked (verbatim, lightly
compressed across several messages):

1. Move the canonical memory/site-docs policy out of `~/ops/site-private`
   (private) into `~/ops/stayturgid` (public) — later **superseded** by the
   distributed three-`AGENTS.md` model.
2. Soften framing so `site-private` is not a forced convention for every
   reader — retained as optional private extras.
3. Handle `site-<name>` being per-operator-variable — absolute GitHub URLs +
   placeholders; `.mysite` for local discovery (#48).
4. Top-level `~` agent-config files and loose `~/ops` content — covered in
   policy text; `StayTurgid TODO.md` removed as stale duplicate.
5. Cross-repo link format — absolute https URLs (done).
6. `.mysite` research — deferred to code in #48; docs describe intent.

## Open decision (resolved)

Original “where does canonical policy live in stayturgid?” → **neither a new
`docs/policies/` file nor expanding §4.10 as the sole home.** Each of the three
repos keeps its slice in `AGENTS.md`; §4.10 is a short pointer.

## Explicitly out of scope / do not touch (still true)

- `~/ops/stayturgid-device-backups/` — secrets + binary, never goes in git.
- Tool runtime logs (`.aider.chat.history.md`, `~/.claude/history.jsonl`).
- `human/F2-BREW-SERVICES-DECISIONS.md` in `site-djbclark` — leave uncommitted.
- `~/.claude/projects/-Users-djbclark-upmon-handoff/memory` — no git repo yet.
- Implementing #48 discovery code — next session/issue, not this completion.
