# Stayturgid Coding and Work Rules

This is the durable implementation checklist for developers and coding agents. It
supplements, but does not replace, root [`AGENTS.md`](../AGENTS.md) and the always-on
[`docs/rules/`](rules/). If instructions conflict, follow the latest
operator instruction, then `AGENTS.md` and `docs/rules`, then this document, then
task-specific plans.

## Required reading order

Before changing the project, read:

1. [`AGENTS.md`](../AGENTS.md)
2. Every file in [`docs/rules/`](rules/)
3. [`docs/STATUS.md`](STATUS.md) — current fleet/workstream state, known gotchas
4. [`docs/options.md`](options.md) — strategic/deferred work with stable IDs,
   plus [GitHub issues](https://github.com/djbclark/stayturgid/issues) for
   discrete bugs and ops follow-ups
5. The relevant module, ADR, research, or task-plan documents

`docs/archive/` holds superseded plans and old sessions — read for historical
context only, never as current work order. STATUS.md and GitHub issues supply
current status; historical documents explain past decisions but do not
override current instructions.

## Session start

From `~/ops/stayturgid`:

```bash
git fetch origin --prune
git pull --ff-only origin master
just health
just firerpa-health
python3 control/bin/screen_lease.py status
git status --short --branch
```

- Report every active `WARNING` or `ERROR` with its host and `issues=` tags before
  proceeding. Distinguish a live failure from recovered history.
- If the pull cannot fast-forward or produces a conflict, stop and report it.
- Treat all existing worktree changes as belonging to the operator or another agent
  unless their origin is proven. Never reset or overwrite them.
- Landing discovery keeps static definitions in tracked
  `control/landing/services.json` and writes observations to
  `~/.config/stayturgid/landing/services.json`; do not reintroduce runtime fields
  into the committed catalog.

## Work selection and scope

- Start with the highest-priority open GitHub issue or `docs/options.md` entry
  unless the operator names a different item. Check `docs/STATUS.md` first for
  anything time-sensitive (e.g. an ongoing incident) that should come first.
- Work on one item at a time. Keep fixes, tests, documentation, and deployment
  evidence for that item together.
- Optional Galaxy, LLM, FIRERPA MCP/WebRTC/MITM, Tasker, `sshd -D`, or tooling work
  must not displace an ordered reliability fix.
- Do not expand into supporting repositories under `~/src/*` without a task-specific
  reason. Read their own instructions before changing them and keep commits in the
  correct repository.
- If required hardware, human consent, credentials, or a safety decision blocks an
  item, record exact evidence in a GitHub issue (or `docs/options.md` for a
  strategic/deferred track), leave the item open, and proceed only to the next
  independent safe item.

## Language and architecture boundaries

### Python is the default

Use Python for substantial new logic, including orchestration, parsing, validation,
retries, state transitions, structured output, and error classification.

- Prefer existing project libraries before adding another implementation.
- Use `pathlib`, explicit encodings, bounded timeouts, and argument-list subprocess
  calls where practical.
- Return meaningful nonzero exit codes and actionable error messages.
- Use the shared logging facilities for monitors and long-running processes.
- Add tests at the same time as behavior changes.

### Exceptions require a concrete reason

- **AutoJs6 JavaScript:** the AutoJs6 watchdog runtime was retired fleet-wide
  by the K1 native-agent cutover (2026-07-22 — see `docs/STATUS.md`).
  `device/autojs6/` is kept as reference code; do not add new fleet-facing
  AutoJs6 automation. Code executed inside AutoJs6 for other purposes should
  still keep platform calls narrow and cover portable logic with
  Node-compatible tests where possible.
- **Ansible:** use for declared fleet/control-node desired state and idempotent
  deployment within the boundaries in [ADR 001](architecture/adr/001-ansible-boundary.md).
- **Shell:** acceptable for a small, clearer wrapper or direct pipeline. Do not put
  complex control flow, parsing, retries, or duplicated Python behavior into shell.
- **`just`:** command runners must remain thin entry points. Substantive behavior
  belongs in Python or Ansible. Follow the [`just` migration plan](archive/plans/just-migration-plan.md).

When touching an existing substantial shell implementation, consider migrating it to
Python as part of the scoped task. Do not inflate a small fix into an unrelated rewrite.

## Error and warning policy

Every new `WARNING`, `ERROR`, failing check, or suspicious health condition encountered
during work must have one of these outcomes before handoff:

1. Fixed and covered by a regression test where feasible.
2. Demonstrated to be recovered history or expected state, with the evidence stated.
3. Filed as a GitHub issue (discrete bug/follow-up — see
   [`docs/rules/github-issues.md`](rules/github-issues.md) for hygiene rules)
   or added to `docs/options.md` with a stable ID (strategic/deferred track),
   with impact, evidence, risk, and next action either way.

Do not hide a warning, force a zero exit code, weaken a test, or broadly catch an
exception merely to make output green. Default summaries may group historical errors,
but raw diagnostic detail must remain available.

## Path and character set (ASCII-only for on-device paths)

- **On-device filesystem paths must be ASCII-only** (English letters, digits, `/`,
  `_`, `-`, `.`). No CJK or other non-ASCII code points in path segments we create
  or deploy to.
- Canonical AutoJs6 project path: **`/sdcard/stayturgid/autojs6`** (also reachable
  as `/storage/emulated/0/stayturgid/autojs6`). Do **not** install or leave a
  project under AutoJs6’s locale sample folders:
  - English: `/sdcard/Scripts/stayturgid`
  - Chinese UI: `/sdcard/脚本/stayturgid` (U+811A U+672C “Scripts”)
- AutoJs6 Chinese builds open **脚本** as the default sample directory. A stale
  copy there was the p7a `SyntaxError: Invalid quantifier` failure when running
  an old `main.js` under a non-ASCII path (2026-07-19). Always open/run
  `file:///sdcard/stayturgid/autojs6/main.js`.
- Repo-relative paths and identifiers used as paths in code (`device/autojs6/…`,
  inventory targets, deploy destinations) must also stay ASCII. Prose docs may
  use Unicode punctuation (em dash, etc.); path **literals** must not.
- After AutoJs6 project deploy, remove known stale mirrors (see
  `STALE_PROJECT_MIRRORS` in `autojs6_deploy_util.py`).

## Device safety

- Use `oneui-device` for the first live test unless the task explicitly depends on
  `stock-android-device` or `fireos-device` behavior (§4.1 names; your site inventory
  maps them to real hosts).
- Before interaction, announce the host, reason, and expected duration using the
  project device-warning convention.
- Acquire and retain `ScreenControlSession` for multi-step on-glass work. Fail closed
  if the lease is unavailable.
- Have a tested recovery channel before disrupting ADB, SSH, Shizuku, Tailscale,
  accessibility, or networking. Use USB when the plan requires it.
- Prefer read-only validation before mutation, a host-limited change before fleet-wide
  deployment, and dry-run/check mode before apply.
- Recheck live health after changes and inspect fresh logs rather than relying only on
  command exit status.

### Human-gated Android state

- Accessibility is detection-only. Never automatically write
  `enabled_accessibility_services`, restore a stored whole list, or use a toggle that
  replaces the list. Ask the user to enable missing services in Android Settings.
- Shizuku authorization may require the user to select **Allow all the time**. Success
  requires the documented UID-2000 probe; opening an application is not proof.
- An unlocked screen may be required for UI automation. State that requirement instead
  of waiting silently or attempting to bypass the lock screen.
- Do not weaken Android consent, Play Protect, device security, or network protections
  to make automation easier.

## Self-heal and deployment completeness

A manual repair is not a complete reliability fix. When a health issue is cleared,
update the appropriate durable recovery layers so the same condition can recover
without the one-shot intervention:

- Termux supervisor/repair
- Native agent heartbeat/repair (`device/native-agent/`) — replaces the
  retired AutoJs6 watchdog/co-monitor as of the K1 cutover (2026-07-22)
- Mac launchd health/heal
- Ansible deployment and validation
- Catastrophic recovery where applicable

Every new desired state must be represented in `tests/healing_registry.json` when the
coverage policy requires it. Follow the deployment/self-heal/catastrophic-recovery rule
in `docs/rules/`.

## Testing and validation

Run the smallest focused test during development, then the project gates appropriate
to the change:

```bash
just check                 # code syntax, lint, collection and parser checks
just test                  # device-free unit suites
just --set hosts oneui-device verify      # read-only live tier when device behavior changed
just --set hosts oneui-device deploy-check
```

- Add a regression test that would fail on the old defect.
- Test failure behavior, not only the happy path.
- Preserve established exit-code contracts used by CI and health monitoring.
- For live changes, validate `oneui-device` first and expand only when the task
  requires it.
- Record commands, results, warnings, and rollback evidence in the plan or OPTIONS.

## Git and documentation

- Before edits: fetch and fast-forward as required by `AGENTS.md`.
- Before commit: inspect `git status`, the complete scoped diff, and
  `git diff --check`.
- Stage explicit paths. Never include unrelated runtime or operator changes.
- Use a focused commit message, commit completed work, and push to `origin/master`.
- Update current documentation, OPTIONS state, and acceptance evidence in the same
  change. Do not rewrite historical session/research records to make the present look
  cleaner.
- Leave the branch synchronized with its upstream. If unrelated tracked changes remain,
  name them clearly in the handoff.

## Definition of done

An item is complete only when:

- its documented acceptance gate passes;
- tests and live validation proportional to risk pass;
- warnings/errors are fixed or tracked;
- self-heal/deployment coverage is updated where relevant;
- current docs and OPTIONS reflect reality;
- rollback is known;
- scoped work is committed and pushed; and
- untested or hardware-blocked behavior is not represented as complete.
