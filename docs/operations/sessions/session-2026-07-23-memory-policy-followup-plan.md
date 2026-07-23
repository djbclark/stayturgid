# Session 2026-07-23 — memory/site-docs policy follow-up plan

**Status: PLANNED, NOT YET EXECUTED.** This is a plan produced by a
different AI session (working primarily in `~/src/ai`, asked to survey and
extend the memory-policy migration below) — no reorg steps in this doc have
been applied yet. One open decision remains (see bottom); everything else is
ready to execute. See
[docs/STATUS.md](../STATUS.md) and [AGENTS.md](../../AGENTS.md) for how this
surfaces as current priority.

**Builds on:** `session-2026-07-23-memory-policy-migration.md` (this same
directory) — that session created `~/ops/site-private`, split memory content
three ways, and wired the home-directory symlinks. It marked itself
**COMPLETE**. This doc is the operator's follow-up ask on top of that
already-complete work, not a correction of it.

## What prompted this

After the migration session finished, the operator asked (verbatim, lightly
compressed across several messages):

1. Move the canonical memory/site-docs policy out of `~/ops/site-private`
   (private) into `~/ops/stayturgid` (public) — "the policy is in
   site-private, which is a mistake because it makes the policy unavailable
   to other [operators]."
2. Soften the policy's framing so it doesn't read as forcing `site-private`
   as a mandatory name/repo on every reader — "it should not reference
   site-private as a forced convention" — while keeping real links to this
   operator's actual `site-private` fine, since it's a legitimate concrete
   example.
3. Figure out how to handle `site-<name>` being per-operator-variable inside
   a policy doc meant for other operators too.
4. Extend the policy: any top-level `~` agent-config file (like
   `~/CLAUDE.md`) and anything loose directly under `~/ops` (not inside one
   of the three repos) should get the same distribute-and-symlink treatment
   as `~/.claude`.
5. Make cross-repo links in the policy doc work both opened locally and on
   github.com's web renderer.
6. Investigate whether there's a standard name for a symlink like
   `~/ops/.mysite -> site-djbclark` (the operator's own tentative idea,
   which they suspected — correctly — would break GitHub-rendered links).

Then, mid-planning, the operator clarified a scoping question before it was
even fully asked (see "Resolved" below), and asked for this plan to be
checked into git, surfaced as top priority, and for a resume prompt.

## Survey findings (as of this session)

Confirmed by direct inspection, not assumption:

- **`~/ops/stayturgid`** — public (`github.com/djbclark/stayturgid`), branch
  `master`, clean working tree except the pre-existing, deliberately-untouched
  operator file `human/F2-BREW-SERVICES-DECISIONS.md` note (that's in
  `site-djbclark`, not here — see below). `docs/architecture/multi-site-topology.md`
  §4.10 already documents the three-repo convention and defers to
  `site-private/README.md` as canonical — this is exactly the link direction
  item 1 above wants reversed.
- **`~/ops/site-djbclark`** — private (`github.com/djbclark/site-djbclark`),
  branch `master`. Its `AGENTS.md` already demonstrates the right
  cross-repo link _format_ for item 5: an absolute
  `https://github.com/djbclark/stayturgid/blob/master/...#anchor` URL, which
  renders correctly both locally and on github.com (relative links can't
  cross a repo boundary in GitHub's web renderer — only same-repo relative
  links work there). One pre-existing uncommitted change,
  `human/F2-BREW-SERVICES-DECISIONS.md`, is operator-authored and
  deliberately untouched (noted in the prior session's handoff too — not
  part of this plan).
- **`~/ops/site-private`** — private (`github.com/djbclark/site-private`),
  branch `master`, clean tree. Holds `README.md` (the canonical policy today),
  `AGENTS.md`, `home-agents.md` (backs `~/CLAUDE.md`/`~/AGENTS.md`), and
  `memory/` (8 generic memory topics + `MEMORY.md`).
- **Symlinks already in place and verified resolving:**
  `~/.claude/projects/-Users-djbclark/memory` → `~/ops/site-private/memory`;
  `~/CLAUDE.md` and `~/AGENTS.md` → `~/ops/site-private/home-agents.md`
  (independently, not chained).
- **Loose files directly under `~/ops`** (item 4's "ditto for `~/ops`"),
  neither symlinked nor distributed:
  - `~/ops/StayTurgid TODO.md` — an untracked relay-baton doc. Reads as a
    stale duplicate of the pattern already tracked properly in
    `site-djbclark/docs/relay/NEXT-PROMPT.md` / `LEDGER.md`. Recommend
    reconciling (confirm nothing here is missing from those tracked docs,
    then delete) rather than moving it anywhere — it looks like it predates
    the relay-doc convention rather than being additional information.
  - `~/ops/stayturgid-device-backups/` — a 416 MB device backup **containing
    a real `.ssh` directory** (actual key material). **Explicitly excluded
    from this policy, permanently** — this is backup data with live secrets,
    not memory/planning content, and must never enter any git repo (all
    three repos' existing policy already bans secrets; this is also just too
    large). Naming it here so a future broad "distribute everything under
    `~/ops`" pass doesn't sweep it in by accident.
- **Top-level `~` agent-config files beyond `CLAUDE.md`/`AGENTS.md`:**
  checked for `.cursorrules`, `.windsurfrules`, Copilot instructions, etc. —
  none exist. `~/.aider.chat.history.md` exists but is Aider's own transient
  run log from a session that never touched any project (ran from `$HOME`
  with no git repo, immediately quit) — that's tool _runtime_ state, the
  same category as Claude's `history.jsonl`, not curated memory. Recommend
  the policy explicitly distinguish "curated memory/planning content" (in
  scope) from "tool runtime logs/history" (out of scope), so this doesn't
  get over-applied later.
- **Independent (non-`~/ops`) project memories**, e.g. `~/src/ai`: see
  "Resolved" below — this is no longer an open question.

## Naming-convention research (item 6)

Web search (see sources) turned up no standard for a fixed-name symlink like
`~/ops/.mysite`. The closest real prior art for "shared framework + your own
named overlay" is an **environment-variable override with discovery**, not a
hardcoded symlink name — Doom Emacs's `DOOMDIR` and Spacemacs's
`SPACEMACSDIR` both work this way rather than assuming a fixed directory
name. This codebase already independently converged on exactly that pattern:
`multi-site-topology.md` §4.8 specifies `STAYTURGID_SITE_DIR` plus
discovery-scanning `OPS_ROOT` for `site-*` checkouts, explicitly stating
"there is no operator-specific default directory."

**Recommendation: don't invent anything new.** A `.mysite`-style symlink
would live loose on disk, in no repo, so no doc anywhere could ever resolve
it — confirming the operator's own suspicion. In **docs/prose**, keep using
the placeholder `~/ops/site-<name>` (already used by `site-djbclark/AGENTS.md`
and the topology doc). In **scripts**, keep using the existing
`STAYTURGID_SITE_DIR` / `OPS_ROOT`-discovery mechanism. `site-private`'s name
is fine to hardcode precisely because — unlike `site-<name>` — it's supposed
to be identical for every operator, by design.

Sources:
[Doom Emacs FAQ](https://docs.doomemacs.org/latest/faq),
[Doom Emacs documentation](https://docs.doomemacs.org/latest/),
[Using Multiple Emacs Configurations with Chemacs2](https://systemcrafters.net/emacs-tips/multiple-configurations-with-chemacs2/).

## Resolved: independent-project memory handling

Originally posed as an open question (retire third-party project memory
folders vs. always-symlink-into-site-private). The operator resolved it
directly: **any memory content that lives in _any_ git repo is fine.**
Projects under `~/src/*` (and similar independent repos) are expected to
have their own memory files, committed in their own tree — that's not a
policy violation, it's the intended shape for anything outside the three
`~/ops` repos. The `~/.claude`/`~/.cursor`/etc. **symlink-everything**
convention is being rolled out **project by project**, one at a time, by
telling each project's own agent session about the policy; eventually every
project's tool-memory directory will be a symlink into wherever that
project's own repo (or, for the three `~/ops` repos, the appropriate
site-split location) actually keeps the content — not necessarily into
`~/ops/site-private` specifically.

**Already done as of this session:** `~/src/ai` got this treatment directly
(by the other AI session working there, prompted by this same policy
rollout) — its Claude memory now lives at `~/src/ai/docs/memory/`, with
`~/.claude/projects/-Users-djbclark-src-ai/memory` converted to a real
symlink pointing there (old content backed up to
`~/.backups/memory.pre-symlink-backup-ai-2026-07-23` first). That project's
`AGENTS.md` and `README.md` were updated to describe the live symlink and
the earlier point-in-time snapshot file it replaces was removed. No further
action needed there.

**Still not converted** (found during survey, not yet actioned, lower
priority than the items below since none of them have their own repo to
symlink into yet):
`~/.claude/projects/-Users-djbclark-upmon-handoff/memory` (`~/upmon-handoff`
isn't a git repo — nothing to symlink to until/unless it becomes one).

## Proposed changes to execute (ready, pending the one open decision below)

1. **Move the canonical policy text** out of `~/ops/site-private/README.md`
   into `~/ops/stayturgid`, at the location decided by the open question
   below. Rewrite it per item 2/3: present the three-repo shape as a
   recommended pattern with djbclark's own setup as a labeled concrete
   example (mirroring how §4.1 already turns real device names into generic
   `oneui-device`-style placeholders for exactly this reason — same
   technique, same rationale, just applied to repo names instead of device
   names this time), not a requirement every reader must replicate exactly.
   Explicitly note that links to djbclark's own `site-private`/`site-djbclark`
   (private) will 404 for any other reader — expected, not a bug — rather
   than silently looking broken.
2. **`site-private/README.md` and `AGENTS.md`** shrink to short stubs
   pointing at the new stayturgid location via absolute GitHub URL (same
   format `site-djbclark/AGENTS.md` already uses successfully).
3. **`site-djbclark/AGENTS.md`**'s existing cross-link to
   `multi-site-topology.md#410-...` needs updating to point at wherever the
   policy actually ends up.
4. **Add the two extension clauses** (item 4): top-level `~` agent-config
   files (any tool, any name, present now or added later) get the same
   distribute-and-symlink treatment as `~/.claude`; anything loose directly
   under `~/ops` must land in one of the three repos or be an explicitly
   named exclusion (secrets/binaries — use `stayturgid-device-backups` as
   the standing example of what's excluded and why).
5. **Encode the link-format rule** explicitly in the policy: absolute
   `https://github.com/<owner>/<repo>/blob/master/...` URLs for anything
   cross-repo (works locally and on github.com); plain relative links only
   within the same repo. One-line caveat: pin links to stable
   files/section-anchors, since either format breaks the same way on a
   rename.
6. **Reconcile `~/ops/StayTurgid TODO.md`** against `site-djbclark`'s
   existing relay docs, then remove it (see survey note above).

## Open decision (the one thing this plan does NOT resolve)

**Where exactly should the canonical policy text live inside `stayturgid`?**

- **Recommended: new dedicated doc**, `docs/policies/ai-memory-and-docs.md`.
  Short, single-purpose, easy to link to and find on its own; §4.10 of
  `multi-site-topology.md` shrinks to a two-line pointer. The policy isn't
  inherently about Android fleet topology, and burying it in a 631-line
  topology doc makes it harder for an unrelated reader to find.
- **Alternative: expand in place**, keep it as the full text of §4.10 inside
  `multi-site-topology.md` instead of a pointer. Fewer files, but nested
  inside a much larger fleet-specific document.

This was asked of the operator via a clarifying-question prompt; the operator
redirected to "put the plan in the repo" before answering it, so it's carried
forward here as the one thing the next session should either ask again or
just decide (the recommended option above is a reasonable default to proceed
with if no reply is forthcoming — this is a low-stakes, easily-reversed
organizational choice, not an architectural commitment).

## Explicitly out of scope / do not touch

- `~/ops/stayturgid-device-backups/` — secrets + binary, never goes in git.
- `~/.aider.chat.history.md`, `~/.claude/history.jsonl`, and similar tool
  _runtime_ logs — not curated memory, not in scope for this policy.
- `human/F2-BREW-SERVICES-DECISIONS.md` in `site-djbclark` — pre-existing
  operator-authored uncommitted file, unrelated to this work, do not commit
  it as a side effect of an otherwise-unrelated commit in that repo.
- `~/.claude/projects/-Users-djbclark-upmon-handoff/memory` — no git repo to
  symlink into yet; leave as-is until that changes.

## If you are the next AI session picking this up

1. Read this doc plus the original
   `session-2026-07-23-memory-policy-migration.md` for full context — don't
   re-survey from scratch, everything above was verified directly this
   session.
2. Resolve or proceed with the default on the one open decision above.
3. Execute items 1–6 under "Proposed changes to execute."
4. Update this doc's status line to COMPLETE (or note what's still pending)
   and update `docs/STATUS.md` / `AGENTS.md`'s active-blockers section to
   remove the pointer to this doc once done.
5. Commit and push all three repos (`stayturgid`, `site-private`,
   `site-djbclark`) — standard wrap-up, per
   [docs/notes/lessons-learned.md](../notes/lessons-learned.md)'s session
   wrap-up protocol.
