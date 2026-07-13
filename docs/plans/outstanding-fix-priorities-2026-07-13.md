# Outstanding Fix Priorities

**Created:** 2026-07-13

**Status:** Accepted execution order; open work remains tracked in
[`docs/options.md`](../options.md).

**Audience:** Maintainers and junior implementation agents resuming work on
Stayturgid.

## Goal

Fix the most consequential defects and operational gaps discovered during the
2026-07-13 Python migration, FIRERPA integration, reboot tests, and live S24/P7A
validation. Complete reliability and safety work before optional publishing,
LLM, MCP, WebRTC, or MITM enhancements.

## Current State

- S24 and P7A are currently healthy.
- HD8 is the only persistent aggregate health failure, with a documented stale
  watchdog/offline state while its Python deployment remains incomplete.
- FIRERPA secure SSH/gRPC works on S24 and P7A after persistent Termux Shizuku
  authorization.
- `control/landing/services.json` is Git-tracked but is modified hourly by service
  discovery, so the working tree does not stay clean.
- P7A produced a real AutoJs6 error because `files.getParent()` is unavailable;
  the calls remain in the source.
- Fleet health correctly recognizes recovered hosts but presents a large volume of
  historical errors alongside current state.

## Execution Rules

Work in the order below unless a step is blocked by required hardware or explicit
operator interaction. If blocked:

1. Record the exact blocker and evidence in `docs/options.md`.
2. Leave the item open.
3. Continue only with the next independent, lower-risk code item.
4. Do not claim the blocked item is complete.

For every item:

- Read and follow `AGENTS.md`, `.cursor/rules/`, `docs/handoff.md`, and the relevant
  module documentation before editing.
- Fetch and fast-forward from `origin/master` before edits.
- Run fleet health first and report active `WARNING`/`ERROR` conditions.
- Prefer Python for substantial logic. AutoJs6 runtime code is a justified JavaScript
  exception; keep JavaScript changes narrow and testable.
- Use S24 as the primary live test device. Use P7A or HD8 only when their different
  behavior is necessary.
- Announce device interaction and obey the screen-control lease.
- Never silently grant or rewrite Android accessibility services.
- Fix each new warning/error or add a stable OPTIONS item before finishing.
- Keep changes scoped, test them in proportion to risk, commit, and push.
- Do not stage, reset, or overwrite unrelated worktree changes.

## Priority 1 — Fix the AutoJs6 parent-path failure (H10)

### Problem

P7A logged:

```text
trigger file write failed: TypeError: Cannot find function getParent
```

The unsupported API remains in:

- `device/autojs6/lib/termux.js`
- `device/autojs6/lib/notify.js`

This is important because the failing branch is intended to recreate missing state
directories during self-heal.

### Work

1. Reproduce or unit-test the unavailable API behavior without changing a phone.
2. Introduce one small, AutoJs6-compatible parent-path helper or use an existing
   supported project helper.
3. Replace both calls; do not fix only the observed trigger-file site.
4. Add regression coverage for a missing parent directory.
5. Run code tests and deploy the narrow change to S24 first.
6. Exercise the trigger/notification writes on S24, then deploy to P7A.
7. Confirm fresh device and fleet logs contain no `getParent` error.

### Completion gate

- Missing parent directories are recreated successfully.
- Trigger and notification state writes succeed on S24 and P7A.
- Automated regression coverage fails with the old implementation and passes with
  the replacement.
- Live health remains clean.

## Priority 2 — Resolve HD8's permanently red health state (H1/H3)

### Problem

HD8's incomplete Python deployment leaves aggregate health nonzero. A permanently
red health command trains operators and agents to ignore later real failures.

### Work

Ask the operator to choose between these outcomes if the intent is not already clear:

1. **Active fleet member:** connect HD8 with USB recovery available, deploy the
   Python runtime, and validate its Fire OS-specific path.
2. **Intentional maintenance/offline state:** represent that state explicitly so
   health reports it as expected maintenance rather than an active failure.

Do not merely suppress HD8 globally. Maintenance state must be visible, explicit,
and reversible.

### Completion gate

- If active: HD8 passes its applicable deploy and health checks.
- If maintained offline: aggregate health distinguishes maintenance from failure,
  and the dashboard clearly shows the state.
- H1/H3 are consolidated or closed accurately rather than left contradictory.

## Priority 3 — Separate landing configuration from runtime state (H11)

### Problem

`control/landing/discover.py` writes timestamps, reachability, and HTTP status into
the tracked `control/landing/services.json` every hour. This keeps the repository
dirty and can accidentally mix transient network observations into code commits.

### Work

1. Identify the static fields that are source-controlled configuration and the
   dynamic fields produced by discovery.
2. Keep a committed seed/catalog file containing only intended static definitions.
3. Move generated runtime state to a path such as
   `~/.config/stayturgid/landing/services.json`.
4. Update the landing service, discovery command, launchd/Ansible provisioning,
   tests, and documentation to use the runtime path.
5. Provide a safe first-run migration/fallback from the committed seed.
6. Preserve the current modified file until its useful runtime data has been
   accounted for; do not discard it just to clean Git status.
7. Run discovery twice and prove the second run changes no tracked file.

### Completion gate

- Discovery and the landing page still work.
- Fresh installation creates runtime state automatically.
- Repeated discovery leaves `git status --short` unchanged.
- Static service definitions remain reviewable in Git.

## Priority 4 — Complete dashboard human-action workflows (H8, then H9)

### Problem

Persistent Termux access to Shizuku requires a human Android authorization. Reboots
and deployment UI work may also require an unlocked screen or accessibility toggle.
The current scheduled flow can leave the operator waiting without an immediate retry.

### Work

1. Show missing or nonpersistent Termux `rish` authorization as an actionable state.
2. Add an immediate request/open/test action where Android permits it.
3. Poll the canonical probe and require UID 2000:

   ```console
   ~/.stayturgid/bin/rish -c 'id -u'
   ```

4. Allow the dashboard to rerun the blocked probe or operation immediately after the
   user grants access.
5. Clearly say when Android still requires the user to tap **Allow all the time**.
6. Surface screen-unlock and accessibility-toggle requirements without attempting to
   bypass Android consent.
7. After H8 works, inventory foreground UI transitions and restore a predictable
   final screen under H9. Do not block core reliability on cosmetic cleanup.

### Completion gate

- A missing authorization is visible without reading logs.
- The operator can initiate and verify authorization without waiting for a scheduled
  supervisor cycle.
- Success is based on UID 2000, not merely on opening the Shizuku application.
- The dashboard never claims it can automate a consent action Android requires from
  the human.

## Priority 5 — Exercise untested recovery paths (B63/B64)

### B63: native Shizuku launch

Test the `shizuku_start` native fallback with Shizuku genuinely stopped. Use S24,
have USB recovery available, announce the disruption, and obtain explicit operator
approval before stopping a working Shizuku instance.

### B64: cold-device bootstrap

Run the complete bootstrap only on a virgin, factory-reset, or deliberately disposable
device. If no such device is available, leave B64 open with the hardware blocker; do
not approximate a virgin-device result on an already-managed phone.

### Completion gate

- B63 proves both stopped-to-running and already-running idempotent paths.
- B64 proves USB-debugging-only to managed-fleet state, or remains explicitly blocked
  on suitable hardware.
- Recovery instructions reflect what was actually observed.

## Priority 6 — Make fleet-health output emphasize current state (H12)

### Problem

`make health` can print dozens of historical P7A errors from the 24-hour window after
P7A has recovered. The current summary is technically accurate but makes active
problems harder to see.

### Work

1. Preserve the raw log and full diagnostic view.
2. In the default summary, group repeated messages by host and failure type.
3. Show count, first/last occurrence, and whether the host subsequently recovered.
4. Separate active failures, resolved recent failures, and historical diagnostics.
5. Keep exit status based on current actionable health, not historical log presence.
6. Add tests for active, recovered, repeated, and stale-scrape cases.

### Completion gate

- Active failures appear first and remain unmistakable.
- Recovered errors are summarized without losing access to details.
- Existing monitoring exit-code contracts remain stable.

## Priority 7 — Audit and constrain FIRERPA networking (F4)

### Problem

FIRERPA is a large closed-source server running with Android shell privileges. Secure
inbound gRPC/SSH works, but outbound behavior has not received the same validation.

### Work

1. Begin with a read-only listener and outbound-connection audit on S24.
2. Document which interfaces and destinations are necessary.
3. Design the least disruptive isolation available through Tailscale ACLs, interface
   binding, or host controls.
4. Obtain operator approval before applying network policy that could remove recovery
   access.
5. Validate SSH, gRPC health, localhost ADB recovery, and ordinary phone networking
   after any restriction.

Do this before optional FIRERPA MCP, WebRTC, or MITM expansion.

### Completion gate

- Required network behavior and observed outbound behavior are documented.
- A reviewed isolation decision is implemented or an evidence-backed limitation is
  recorded.
- Existing recovery channels remain usable.

## Priority 8 — Migrate the command interface to `just` (T1)

After the operational defects above are stable, follow
[GNU Make to `just` Migration Plan](just-migration-plan.md). Make `just` primary,
move substantial shell logic to Python, and retain a small Make compatibility shim
through CI and live-fleet soak. Do not combine this migration with live reliability
fixes or delete Make in a flag day.

## Explicitly Lower Priority

Do not let these displace the ordered fixes above:

- Galaxy publication (H5/38)
- shell-gpt escalation (54)
- FIRERPA MCP, WebRTC, or MITM additions (F1-F3)
- Tasker or `sshd -D` experiments (44/45) without their triggering symptom
- AutoJs6 WorkManager work (43) before upstream support exists

## Junior Developer Resume Prompt

Copy the following prompt into a new AI session:

```text
You are resuming work as a junior developer responsible for the Stayturgid project
at ~/stayturgid and its supporting projects under ~/src/*. Work carefully and in
small, reviewable increments. The operator prefers Python for substantive logic;
JavaScript is acceptable only where the AutoJs6 runtime requires it.

Before editing anything:

1. Read ~/stayturgid/AGENTS.md completely and follow it.
2. Read ~/stayturgid/docs/handoff.md, ~/stayturgid/docs/options.md, and
   ~/stayturgid/docs/plans/outstanding-fix-priorities-2026-07-13.md completely.
3. Read the relevant module docs and .cursor/rules files before touching that area.
4. From ~/stayturgid run:
     git fetch origin --prune
     git pull --ff-only origin master
     make health
     make firerpa-health
5. Immediately report every active WARNING/ERROR and its host/issues tags. Historical
   P7A log errors may be resolved; distinguish live state from history.
6. Inspect git status. Do not reset, overwrite, or stage unrelated changes. In
   particular, control/landing/services.json is currently modified by runtime discovery;
   preserve it until Priority 3 deliberately migrates that state.

Execute the priorities in this exact order:

1. H10: fix the unsupported AutoJs6 files.getParent() calls in both termux.js and
   notify.js, add a regression test for missing parent directories, deploy narrowly
   to S24 then P7A, and verify fresh logs.
2. H1/H3: resolve HD8's permanently red health state. Use USB recovery if deploying.
   If the operator intends HD8 to stay offline, implement an explicit visible
   maintenance state rather than silently suppressing it.
3. H11: split the committed landing-page service catalog from generated runtime
   reachability/timestamp state. Prove two discovery runs leave Git clean.
4. H8 then H9: add dashboard detection plus immediate request/test/retry for Termux
   Shizuku authorization, requiring rish UID 2000. Surface unlock/accessibility human
   actions without bypassing Android consent. Treat foreground cleanup as secondary.
5. B63/B64: test native Shizuku stopped-to-running with S24 and USB recovery, but ask
   for explicit approval before stopping Shizuku. Run the cold bootstrap only on a
   virgin/disposable device; otherwise record the hardware blocker and leave it open.
6. H12: make default fleet-health output group repeated historical errors and clearly
   separate active, recovered, and historical conditions while preserving raw detail
   and current-state exit codes.
7. F4: perform a read-only FIRERPA listener/outbound audit, then propose least-disruptive
   isolation. Ask before applying ACL/network changes that could affect recovery.
8. T1: only after reliability work is stable, follow docs/plans/just-migration-plan.md.
   Keep a Make compatibility shim and move complex shell logic into Python.

Rules while working:

- Work on one numbered priority at a time and keep commits scoped.
- If hardware or a human action blocks an item, document the exact blocker in
  docs/options.md, leave the item open, and continue only with the next independent
  safe item. Never mark an untested path complete.
- Prefer S24 for live tests. Announce every device interaction with host, reason, and
  expected duration, and obey the screen-control lease.
- Never automatically rewrite enabled accessibility services.
- Fix every new WARNING/ERROR you encounter or add a stable OPTIONS item explaining
  its impact, evidence, and next action.
- Run focused tests plus make check; run broader tests when risk warrants it.
- Verify git diff and git status before committing. Commit and push completed work,
  but never include unrelated runtime/user changes.
- Update the plan and options with evidence, validation, and rollback information.

Start with Priority 1 only. First inspect the AutoJs6 runtime APIs and existing tests,
explain the smallest safe fix, implement it, test it locally, and then announce before
touching S24. Do not begin optional Galaxy, LLM, MCP, WebRTC, MITM, Tasker, or sshd-D
work while these priorities remain.
```
