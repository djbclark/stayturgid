# STATUS — stayturgid at a glance

> Entry point for AI agents: [../AGENTS.md](../AGENTS.md) (conventions,
> commands, and a condensed version of this file). Project overview:
> [../README.md](../README.md). See AGENTS.md's "Where documentation goes"
> table for what belongs in this file versus elsewhere.

**Last verified:** 2026-07-25 (OpenObserve<->Vector auth fixed, see below).
Read this first; it links
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

<!-- markdownlint-disable MD060 -->

| Workstream                                                                                                                                       | State                                                              | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Site discovery hardening** ([#48](https://github.com/djbclark/stayturgid/issues/48))                                                           | **Completed 2026-07-24**                                           | Shared resolver excludes `site-private`, honors `OPS_ROOT/.mysite`, announces the selected path/source, and safely creates the configurable private-companion directory when absent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **K1 — native agent** (AutoJs6 -> Kotlin/Shizuku UserService)                                                                                    | Cutover landed (195c5c7, 2026-07-22), **still not fully verified** | AutoJs6 was actually still installed fleet-wide despite the cutover's claim otherwise — now genuinely uninstalled (2026-07-25). A reboot-based `CLOSED_NO_SHELL` soak attempt on p7a surfaced a bigger open question: boot-triggered app startup may not reliably run the comonitor heartbeat loop the whole catastrophic-repair mechanism depends on. Full writeup, all commands run, and next steps: [operations/sessions/session-2026-07-25-k1-verification.md](operations/sessions/session-2026-07-25-k1-verification.md). Tracked in [#43](https://github.com/djbclark/stayturgid/issues/43); debug-vs-release gap in [#45](https://github.com/djbclark/stayturgid/issues/45).                                   |
| **OpenObserve <-> Vector auth**                                                                                                                  | **Fixed 2026-07-25, pending 24h clean-log verification**           | Root cause: OpenObserve's root-user password (in its own sqlite user store) didn't match Vector's or `.env`'s configured value — no dotfile/secretspec value was ever the live credential. Reset via `openobserve reset --component root`, which needed `ZO_DATA_DB_DIR` set explicitly (the CLI's default DB path resolution differs from the running server's — a real OpenObserve quirk/bug, not a config mistake here). New credentials written to Vector's plist and `.env`/secretspec consistently. `reingest_soft_health.py` re-run; all 801 backfilled records confirmed queryable. Tracked in [#44](https://github.com/djbclark/stayturgid/issues/44), left open pending the 24h clean-log acceptance check. |
| **F1 — FIRERPA MCP bridge**                                                                                                                      | Planned, not implemented                                           | Decisions D1-D3 finalized ([operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md](operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md)). Tracked in [#46](https://github.com/djbclark/stayturgid/issues/46), including the open consent-surface question. `mcp` 1.28.1 installed in `~/.venv-stayturgid-firerpa` (that venv has **no pip binary** — verify with `python -c "import importlib.metadata; ..."`, not `pip show`).                                                                                                                                                                                                                                                                                   |
| **FIRERPA / Fire OS recovery**                                                                                                                   | **Merged; transport limitation confirmed**                         | hd8 FIRERPA 10.0 works through control-node ADB; Fire OS clears classic TCP ADB and wireless-debugging state across reboot. The health monitor now allows a bounded five-minute hd8 settle window. p7a remains explicitly `pending-incompatible-runtime`; upstream rebuild request is [firerpa/lamda#147](https://github.com/firerpa/lamda/issues/147).                                                                                                                                                                                                                                                                                                                                                               |
| **Ownership audit** ([#50](https://github.com/djbclark/stayturgid/issues/50))                                                                    | **Inventory complete; operator decisions open**                    | The public issue records the inventory and seven ownership questions. Prompt the operator before opening migration issues.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **T5 — observability/portal unification**                                                                                                        | Evaluated, not started                                             | Reject Homer/Glance ([research/evaluations/observability-portal-unification-evaluation-2026-07-23.md](research/evaluations/observability-portal-unification-evaluation-2026-07-23.md)). Follow-ons tracked in [#47](https://github.com/djbclark/stayturgid/issues/47), blocked on #44.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Settings-state corruption** ([#41](https://github.com/djbclark/stayturgid/issues/41), [#42](https://github.com/djbclark/stayturgid/issues/42)) | Investigation open                                                 | Battery-percentage reset + portrait-lock flip on Android; hypothesis is settings-DB corruption around sleep/wake. [#16](https://github.com/djbclark/stayturgid/issues/16) describes an overlapping symptom and is now cross-linked.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

<!-- markdownlint-enable MD060 -->

## Fleet health (as of last check)

- **s24** — online; FIRERPA and Shizuku directly verified healthy.
- **p7a** — ADB and Shizuku reachable; FIRERPA intentionally down because the
  current closed runtime rejects API 37 with `unsupported sdk`.
- **hd8** — ADB, FIRERPA 10.0, FIRERPA SSH, and Shizuku directly verified
  healthy. Startup may span pre-login and post-login and take about five
  minutes to settle.

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
- `/Users/djbclark/src/Shizuku` has an intentionally dirty nested `api`
  submodule from pre-existing user work. Preserve it; inspect `git diff -- api`
  before any cleanup. Its fork `master` is ahead of upstream `origin/master`
  by design.
- The sibling private repo `~/ops/site-djbclark` may have its own uncommitted
  operator-authored files (e.g. `human/F2-BREW-SERVICES-DECISIONS.md`) — leave
  those alone unless the operator asks you to touch them.

## Operator-action queue (things only a human can do)

1. Answer the seven ownership questions in the private #50 audit before any
   repository moves.
2. Set OpenObserve credentials for the Vector LaunchAgent and restart it
   ([#44](https://github.com/djbclark/stayturgid/issues/44)).
3. Decide the F1 consent-surface phasing question ([#46](https://github.com/djbclark/stayturgid/issues/46)).
4. Decide whether to publish Shizuku release20 through the normal APK path.
5. Retest p7a only after firerpa/lamda#147 publishes a compatible runtime.
6. Remove (or authorize removal of) the stray `~/stayturgid` file.

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
