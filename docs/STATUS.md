# STATUS — stayturgid at a glance

> Entry point for AI agents: [../AGENTS.md](../AGENTS.md) (conventions,
> commands, and a condensed version of this file). Project overview:
> [../README.md](../README.md). See AGENTS.md's "Where documentation goes"
> table for what belongs in this file versus elsewhere.

**Last verified:** 2026-07-24 (site-discovery hardening completed; s24/hd8
native-agent and Tailscale state verified). Read this first; it links
everywhere else. If a
claim here looks stale, trust `git log`, `just health`, and the
[GitHub issues](https://github.com/djbclark/stayturgid/issues) over this file,
and update this file in the same commit.

## Repo

- `master` == `origin/master`. No open PRs, no long-lived branches.
- Session/handoff docs: [docs/operations/sessions/](operations/sessions/)
  (chronological, newest last-modified). Superseded plans and old sessions
  live in [docs/archive/](archive/) — read-only history, do not treat as
  current state.
- Open work: tracked as [GitHub issues](https://github.com/djbclark/stayturgid/issues)
  (bugs, ops follow-ups, soak verifications) plus
  [docs/options.md](options.md) (strategic/deferred tracks with stable IDs).
  See [docs/rules/github-issues.md](rules/github-issues.md) for the policy —
  **this is a public repo; no raw device dumps, IPs, serials, or operator
  contact info in issues.**

## Fleet workstreams (current)

| Workstream                                                                                                                                       | State                                                        | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Site discovery hardening** ([#48](https://github.com/djbclark/stayturgid/issues/48))                                                           | **Completed 2026-07-24**                                     | Shared resolver excludes `site-private`, honors `OPS_ROOT/.mysite`, announces the selected path/source, and safely creates the configurable private-companion directory when absent.                                                                                                                                                                                                                                                                               |
| **K1 — native agent** (AutoJs6 -> Kotlin/Shizuku UserService)                                                                                    | Cutover landed (195c5c7, 2026-07-22), **not fully verified** | hd8, p7a, and s24 are confirmed on v0.3.5 debug with one host and one Shizuku UserService each. [#43](https://github.com/djbclark/stayturgid/issues/43) still tracks AutoJs6 removal and the forced `CLOSED_NO_SHELL` soak; [#45](https://github.com/djbclark/stayturgid/issues/45) tracks release APK and official Shizuku packaging. See [operations/sessions/handoff-2026-07-23-native-agent-k1.md](operations/sessions/handoff-2026-07-23-native-agent-k1.md). |
| **OpenObserve <-> Vector auth**                                                                                                                  | **Broken, live**                                             | 401 Unauthorized on both OO sinks (latest seen 2026-07-23T12:21Z). Blocks K1 soak evidence and both T5 follow-ons. Tracked in [#44](https://github.com/djbclark/stayturgid/issues/44). `soft_health.jsonl` on the Mac is the source of truth until this is fixed.                                                                                                                                                                                                  |
| **F1 — FIRERPA MCP bridge**                                                                                                                      | Planned, not implemented                                     | Decisions D1-D3 finalized ([operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md](operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md)). Tracked in [#46](https://github.com/djbclark/stayturgid/issues/46), including the open consent-surface question. `mcp` 1.28.1 installed in `~/.venv-stayturgid-firerpa` (that venv has **no pip binary** — verify with `python -c "import importlib.metadata; ..."`, not `pip show`).                                |
| **T5 — observability/portal unification**                                                                                                        | Evaluated, not started                                       | Reject Homer/Glance ([research/evaluations/observability-portal-unification-evaluation-2026-07-23.md](research/evaluations/observability-portal-unification-evaluation-2026-07-23.md)). Follow-ons tracked in [#47](https://github.com/djbclark/stayturgid/issues/47), blocked on #44.                                                                                                                                                                             |
| **Settings-state corruption** ([#41](https://github.com/djbclark/stayturgid/issues/41), [#42](https://github.com/djbclark/stayturgid/issues/42)) | Investigation open                                           | Battery-percentage reset + portrait-lock flip on Android; hypothesis is settings-DB corruption around sleep/wake. [#16](https://github.com/djbclark/stayturgid/issues/16) describes an overlapping symptom and is now cross-linked.                                                                                                                                                                                                                                |

## Fleet health (as of last check)

- **s24** — online, healthy, direct Tailscale connection.
- **p7a** — offline (Tailscale unreachable). Check physically before assuming
  a software fault.
- **hd8** — offline (Tailscale unreachable). Also has a history of Shizuku
  service failures independent of the offline state.

Run `just health` for current state — do not trust the table above once it's
more than a day or two old.

## Known gotchas (read before you hit these)

- `~/stayturgid` is a stray, root-owned, 0-byte file — **not** the repo. The
  repo is `~/ops/stayturgid`. Removing the stray file needs sudo; ask the
  operator rather than working around it silently.
- `just firerpa-health` exits 1 with **no stdout** by design
  (`also_print=False`). That is not a crash — read
  `~/.config/stayturgid/logs/firerpa-health.log` for the actual result.
- The pre-commit hook chain is strict, including `markdownlint`'s MD060 table
  alignment rule. Run `prettier --write` on any Markdown you touch before
  committing, or the commit will fail on style, not content.
- `device/native-agent/agent-release.jks` (the release signing keystore) must
  never be tracked in git. Check `git status` before any broad `git add`.
- The sibling private repo `~/ops/site-djbclark` may have its own uncommitted
  operator-authored files (e.g. `human/F2-BREW-SERVICES-DECISIONS.md`) — leave
  those alone unless the operator asks you to touch them.

## Operator-action queue (things only a human can do)

1. Set OpenObserve credentials for the Vector LaunchAgent and restart it ([#44](https://github.com/djbclark/stayturgid/issues/44)).
2. Physically check p7a and hd8 (Tailscale unreachable).
3. Decide the F1 consent-surface phasing question ([#46](https://github.com/djbclark/stayturgid/issues/46)).
4. Remove (or authorize removal of) the stray `~/stayturgid` file.

## Where things are documented

| Need                                                      | Read                                                           |
| --------------------------------------------------------- | -------------------------------------------------------------- |
| Onboarding / dev environment setup                        | [docs/hacking.md](hacking.md)                                  |
| Coding rules, session-start checklist, definition of done | [docs/coding-rules.md](coding-rules.md)                        |
| Always-on agent rules (self-heal, screen-control)         | [docs/rules/](rules/)                                          |
| Strategic/deferred work menu (stable IDs)                 | [docs/options.md](options.md)                                  |
| Discrete bugs and ops follow-ups                          | [GitHub issues](https://github.com/djbclark/stayturgid/issues) |
| Session-by-session history                                | [docs/operations/sessions/](operations/sessions/)              |
| Superseded plans and old sessions                         | [docs/archive/](archive/)                                      |
| Repo/doc index                                            | [docs/README.md](README.md)                                    |
