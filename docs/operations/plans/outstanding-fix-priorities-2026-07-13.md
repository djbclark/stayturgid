# Outstanding Fix Priorities

**Created:** 2026-07-13

**Status:** Accepted execution order; open work remains tracked in
[`docs/options.md`](../../options.md).

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

## Priority 1 — Fix the AutoJs6 parent-path failure (H10) — COMPLETE 2026-07-13

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

Completed with the shared `config.ensureParentDir()` helper, tests for both trigger
and notification parent paths, standalone deploy-tool import-path coverage, and
S24/P7A deployment. P7A's unrelated headless-Shizuku failures remain open as H12.

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

## Priority 3 — Separate landing configuration from runtime state (H11) — COMPLETE 2026-07-13

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

Completed with `control/landing/state.py`, static catalog cleanup, first-use migration,
atomic runtime writes, landing/discovery integration, and regression coverage. Two
live discovery runs left the tracked catalog unchanged.

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

H8 completed 2026-07-13. `control/bin/dashboard.py` adds the Shizuku launch and
UID-2000 `rish` verification endpoint; `_device_card.html` exposes it only for
the actionable `shizuku_down` state. Tests cover the UID requirement, launch
sequence, and unknown-host rejection. H9 remains open for foreground-screen cleanup.

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

## Priority 6 — Make fleet-health output emphasize current state (H12) — COMPLETE 2026-07-13

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

Implemented in `control/bin/check_fleet_health.py`: raw `errors.log` remains the
forensic source, while default output groups normalized repeated messages and
labels active, recovered, and historical host conditions. Counts and latest
timestamps are shown, and health exit status still depends only on current
actionable fleet/access state. Added unit coverage for grouping/classification and
recovered output; `make check` and `make test` pass.

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

The prompt is intentionally short. Project rules and work details live in the linked
files so they can be maintained without rewriting handoff prompts.

```text
Work as a junior developer on ~/stayturgid and, only when the task requires it, the
supporting repositories under ~/src/*. Before doing anything, read these completely
and follow them in order:

1. ~/stayturgid/AGENTS.md
2. ~/stayturgid/docs/coding-rules.md
3. every file under ~/stayturgid/.cursor/rules/
4. ~/stayturgid/docs/handoff.md
5. ~/stayturgid/docs/options.md
6. ~/stayturgid/docs/operations/plans/outstanding-fix-priorities-2026-07-13.md

Then run the session-start checks specified in those files, report active warnings or
errors, and begin only the first incomplete priority in the ordered plan. Read any
module, ADR, research, or task-plan documents that priority references before editing.
Do not rely on this prompt for implementation details; the repository documents are
authoritative. Stop and ask when those documents require operator approval or when a
material decision is not already specified.
```
