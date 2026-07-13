# Stayturgid Coding and Work Rules

This is the durable implementation checklist for developers and coding agents. It
supplements, but does not replace, root [`AGENTS.md`](../AGENTS.md) and the always-on
[`.cursor/rules/`](../.cursor/rules/). If instructions conflict, follow the latest
operator instruction, then `AGENTS.md` and `.cursor/rules`, then this document, then
task-specific plans.

## Required reading order

Before changing the project, read:

1. [`AGENTS.md`](../AGENTS.md)
2. Every file in [`.cursor/rules/`](../.cursor/rules/)
3. [`docs/handoff.md`](handoff.md), especially Cold-start and Known issues
4. [`docs/options.md`](options.md) for live open/closed status
5. [Outstanding Fix Priorities](plans/outstanding-fix-priorities-2026-07-13.md)
6. The relevant module, ADR, research, or task-plan documents

The priority plan supplies work order and acceptance gates. OPTIONS supplies current
status. Historical documents explain past decisions but do not override current
instructions.

## Session start

From `~/stayturgid`:

```bash
git fetch origin --prune
git pull --ff-only origin master
make health
make firerpa-health
python3 control/bin/screen_lease.py status
git status --short --branch
```

- Report every active `WARNING` or `ERROR` with its host and `issues=` tags before
  proceeding. Distinguish a live failure from recovered history.
- If the pull cannot fast-forward or produces a conflict, stop and report it.
- Treat all existing worktree changes as belonging to the operator or another agent
  unless their origin is proven. Never reset or overwrite them.
- Until OPTIONS H11 is complete, hourly landing discovery modifies the tracked
  `control/landing/services.json`. Preserve it and do not stage it incidentally.

## Work selection and scope

- Start with the first incomplete item in the ordered priority plan unless the
  operator names a different item.
- Work on one numbered priority at a time. Keep fixes, tests, documentation, and
  deployment evidence for that item together.
- Optional Galaxy, LLM, FIRERPA MCP/WebRTC/MITM, Tasker, `sshd -D`, or tooling work
  must not displace an ordered reliability fix.
- Do not expand into supporting repositories under `~/src/*` without a task-specific
  reason. Read their own instructions before changing them and keep commits in the
  correct repository.
- If required hardware, human consent, credentials, or a safety decision blocks an
  item, record exact evidence in `docs/options.md`, leave the item open, and proceed
  only to the next independent safe item.

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

- **AutoJs6 JavaScript:** required for code executed inside AutoJs6. Keep platform
  calls narrow and cover portable logic with Node-compatible tests where possible.
- **Ansible:** use for declared fleet/control-node desired state and idempotent
  deployment within the boundaries in [ADR 001](adr/001-ansible-boundary.md).
- **Shell:** acceptable for a small, clearer wrapper or direct pipeline. Do not put
  complex control flow, parsing, retries, or duplicated Python behavior into shell.
- **`just`/Make:** command runners must remain thin entry points. Substantive behavior
  belongs in Python or Ansible. Follow the [`just` migration plan](plans/just-migration-plan.md).

When touching an existing substantial shell implementation, consider migrating it to
Python as part of the scoped task. Do not inflate a small fix into an unrelated rewrite.

## Error and warning policy

Every new `WARNING`, `ERROR`, failing check, or suspicious health condition encountered
during work must have one of these outcomes before handoff:

1. Fixed and covered by a regression test where feasible.
2. Demonstrated to be recovered history or expected state, with the evidence stated.
3. Added to `docs/options.md` with a stable ID, impact, evidence, risk, and next action.

Do not hide a warning, force a zero exit code, weaken a test, or broadly catch an
exception merely to make output green. Default summaries may group historical errors,
but raw diagnostic detail must remain available.

## Device safety

- Use S24 for the first live test unless the task explicitly depends on P7A or HD8
  behavior.
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
- AutoJs6 watchdog/co-monitor
- Mac launchd health/heal
- Ansible deployment and validation
- Catastrophic recovery where applicable

Every new desired state must be represented in `tests/healing_registry.json` when the
coverage policy requires it. Follow the deployment/self-heal/catastrophic-recovery rule
in `.cursor/rules/`.

## Testing and validation

Run the smallest focused test during development, then the project gates appropriate
to the change:

```bash
make check                 # code syntax, lint, collection and parser checks
make test                  # device-free unit suites
make verify HOSTS=s24      # read-only live tier when device behavior changed
make deploy-check HOSTS=s24
```

- Add a regression test that would fail on the old defect.
- Test failure behavior, not only the happy path.
- Preserve established exit-code contracts used by CI and health monitoring.
- For live changes, validate S24 first and expand only when the task requires it.
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
