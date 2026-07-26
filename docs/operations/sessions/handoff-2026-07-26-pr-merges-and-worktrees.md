# Handoff — 2026-07-26 PR merges (Kotlin toolchain + OPS_ROOT) and worktrees-only workflow

Continuation of [handoff-2026-07-26-kotlin-tooling.md](handoff-2026-07-26-kotlin-tooling.md)
(read that first for the merge hazards it flagged). This session **merged the
three open PRs**, conformed our code to the new Kotlin toolchain, tore down the
`kotlin-tooling` worktree, and established the go-forward **worktrees-only /
`~/ops`-deploy-only** workflow. Cross-repo session (stayturgid + site-djbclark +
site-private); filed here because stayturgid #67 was the centerpiece.

## ✅ All three PRs merged, pushed, 0 open PRs

| Repo | PR | master HEAD |
|---|---|---|
| stayturgid | #67 Kotlin toolchain | `48249c2` |
| site-djbclark | #5 OPS_ROOT paths | `710306a` |
| site-private | #3 OPS_ROOT paths | `947bc53` |

`~/ops`, `~/src/ops-worktrees/main`, and `.store` are all at these HEADs; clean
trees; no stashes; only `master` branches remain.

### stayturgid #67 — the conflicted merge
The PR branch was cut before this repo's later functional work, so it was
resolved by **keeping master's logic and layering the PR's toolchain on top**
(not the reverse). What was preserved over the PR's older Kotlin:

- `AdbClient` unique-stream-id fix (`nextLocalId++`, `readForStream`,
  `AdbAuthPendingException` handshake) — the only real conflict, in
  `command()`; resolved to master's fix.
- `AgentSchedule` + per-device stagger wiring in `HostService`; `PeerStarter`
  `AUTH_PENDING`/`isSuccess`/target-reminder; `build.gradle.kts` version bump
  (`0.5.2-peerstart-ux`, versionCode 14), BouncyCastle dep + packaging excludes
  + proguard keeps; `INTERNET` perm + `PeerStartReceiver`.

Everything else auto-merged; verified the merge kept every functional marker
before committing.

### Task B — conformed our code to the new toolchain
- Migrated `AgentScheduleTest` JUnit4 → JUnit5 (the merged stack dropped JUnit4).
- Fixed detekt `MagicNumber` (extracted `FRACTION_RESOLUTION`), simplified
  `staggerFraction`.
- Ran `just kt-format` (spotlessApply) tree-wide; refreshed
  `config/detekt/baseline.xml` for the two remaining ktfmt-vs-ktlint conflicts.
- **Verified `just kt-check` green** (spotlessCheck + detekt + debug/release
  compile + unit tests). Pre-commit hooks also pass Spotless + detekt.

## Worktree teardown (C/D)
`kotlin-tooling` worktree had nothing unmerged (all 3 branches == PR heads, 0
commits not in `origin/master`). Removed the 3 worktrees + local + remote
`feature/kotlin-tooling` branches + the empty dir; fast-forwarded the `main/`
worktrees.

## 🆕 Go-forward workflow (the important change)
- **All coding happens under `~/src/ops-worktrees/`** (bare-store +
  task-workspace layout). `~/ops/` is now **deploy-only** — pull merged
  releases; no branching/editing/committing. Refuse dev work requested in
  `~/ops` and redirect to a worktree. (This handoff and the baton refresh below
  were both committed from the worktree, then pulled into `~/ops` — that's the
  pattern.)
- **Exception:** `site-private/memory/` (the live memory store, symlinked from
  `~/.claude/.../memory`) is committed **directly to master, in place** —
  one-fact-per-file, `pull --rebase` before writing, push immediately.
- Authoritative policy: `~/ops/site-private/home-agents.md` (loaded by all AIs
  via `~/CLAUDE.md` + `~/AGENTS.md`).

## Also this session
- **site-djbclark relay baton** (`docs/relay/NEXT-PROMPT.md`) refreshed to
  2026-07-26 state (`710306a`). Recovered content that had been mis-stashed
  into `human/F2-BREW-SERVICES-DECISIONS.md`; brew-services doc left intact; old
  stash dropped.
- **[site-private#4](https://github.com/djbclark/site-private/issues/4)** filed:
  asks Codex which process regenerates `memory/codex/{memory_summary,raw_memories}.md`
  (the whole-file rewrites — the real memory merge-conflict hazard). Name that
  process in `home-agents.md` once answered.

## Kotlin tooling notes for the next agent
- Builds work in this env (JDK 21 auto-detected, Android SDK present). Recipes
  (root justfile imports `just/kotlin.just`): `just kt-check` / `kt-format` /
  `kt-detekt` / `kt-test` / `kt-build-debug` / `kt-build-release`.
- ktfmt (Spotless) and detekt's ktlint rules **disagree** on import order and
  some trailing commas. The project's resolution is `config/detekt/baseline.xml`
  — for new ktfmt-canonical code, regenerate with `just kt-detekt-baseline`
  rather than hand-fighting it. Genuine smells (e.g. `MagicNumber`) still get
  fixed at the source, not baselined.

## Open items (none blocking)
- site-private#4 awaits Codex's answer.
- stayturgid has 21 pre-existing open issues (backlog, e.g. `#68` just-test
  healing gap) — untouched this session.
