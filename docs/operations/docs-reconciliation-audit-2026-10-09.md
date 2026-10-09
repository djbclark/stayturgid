# Documentation reconciliation audit, 2026-10-09 (issue #137)

Audit of the documentation of the three ops repositories against their source
and against each other, for
[#137](https://github.com/djbclark/stayturgid/issues/137). Nothing was changed
in any repository except this file. Each finding below was checked against
source, a dry run, the other document, or the GitHub issue it cites. A finding
that could not be checked says "unverified".

## Scope and method

| Repository    | Commit    | Tracked `.md` | Visibility                   |
| ------------- | --------- | ------------- | ---------------------------- |
| stayturgid    | `0c6047b` | 188           | public                       |
| site-djbclark | `596e333` | 126           | public (the API returns 200) |
| site-private  | `c06c367` | 543           | private                      |

The work was split into five read-only passes: stayturgid top-level docs,
rules, notes and architecture (findings `A*`); stayturgid operations,
collection docs and component READMEs (`B*`); site-djbclark (`C*`); GitHub
issues and PRs of both public repositories against the docs (`E*`); and
site-private, which is summarized in section 6 only. Every `just` invocation in
the docs was compared with `just --list` and, where the form looked odd, with
`just --dry-run`. Paths were checked with `git ls-files`; relative links with a
link checker.

Not covered:

1. PR discussion threads and issue comment threads (only issue bodies and
   states were read).
2. The content of `docs/operations/sessions/**` and `docs/archive/**`, which is
   historical by design. Current docs that treat those files as current
   guidance are reported.
3. The detail of site-private findings, which stays private.
4. The issue's paid external-model pass. It needs operator approval (comment
   on #137); this audit was done without it.

## 1. Priority actions

1. **Single-host targeting is documented wrongly and can deploy to the whole
   fleet.** `just --set hosts <h> deploy` (and the same form for
   `deploy-check`, `verify`, `verify-drift`, `verify-heal`, `firerpa-heal`,
   `termux-pkg-upgrade`) is the documented way to target one host. The public
   recipe calls a nested `just _deploy_impl`, which never sees the `--set`
   value, so the deploy runs with no host argument. Reproduced on `0c6047b`:
   `just --dry-run --set hosts x deploy` prints `just _deploy_impl` with an
   empty argument, while `just --dry-run deploy x` prints `just _deploy_impl x`.
   The `HOSTS=` and `deploy hosts=<h>` spellings in other docs are also wrong.
   Working forms are `just deploy <host>` and `hosts=<host> just deploy`.
   Findings A1, A2, A3, B19. Consider also making the recipes reject or honour
   `--set`; that is a code change.
2. **The retired release regime is still prescribed as current.** The always-on
   rule `docs/rules/normal-deploy-convergence.md` requires a versioned ops
   release for every pin bump (A4). STATUS.md, the AGENTS.md quick start, and
   site-djbclark's relay protocol, research exception and handoff spec say the
   same (A5, A9, C1.2, C1.4, C1.5 and related).
3. **Agent entry points list closed work as active.** stayturgid `AGENTS.md`
   and `docs/STATUS.md` keep closed #44 and #46 as an active blocker and an
   operator-queue item, describe the forced K1 soak as "not run" although it ran
   and failed on 2026-08-01, and never cite #188, the issue that tracks that
   failure (A10, A12, A13, E1, E3, E20, E36).
4. **Docs for deleted components.** Module reference pages, the adoption guide
   and a lessons-learned rule still describe the deleted `stayturgid.fdroid` and
   `stayturgid.obtainium` collections; lessons-learned tells agents to reinstall
   apps through Obtainium "every time, proactively" (A7, A16, B1, B2).
5. **Example consumers pin tags that do not exist or predate K1** (B11, B13),
   so the documented generic install fails or installs a pre-cutover fleet.
6. **Shizuku fork drift.** `docs/hacking.md` says the fleet must use the
   thedjchi fork; the fleet is pinned to ShizukuTendCF (A6). The
   `shizuku_grant` module doc lists parameters the module rejects (B31).
7. **Current docs send agents to archived or frozen material as current
   guidance**: `docs/handoff.md`'s "latest baton", hacking.md's "current
   execution order", coding-rules.md's migration plan, and a research synthesis
   headed "Authoritative architecture" (A8, A20, A23, B36, and the sessions note
   in B).
8. **Where handoffs live is stated three different ways.** stayturgid says
   `docs/operations/sessions/` every session; that tree is frozen since
   2026-08-03 and the operator's tooling now writes handoffs elsewhere (A30).
9. **site-djbclark is public now.** stayturgid `AGENTS.md` and ADR 005 still
   call it private (known item 7a), and site-djbclark calls itself private in
   places (C1.3). Its `registry/ports.yml` and `docs/relay/PROTOCOL.md`
   contain IP addresses written while it was private (paths only; nothing
   copied). Several issue bodies in both public
   repositories contain tailnet addresses or `ts.net` hostnames, which
   stayturgid's own `docs/rules/github-issues.md` forbids; site-djbclark has no
   equivalent rule (E39). The operator decides whether to redact.
10. **Cross-repository policy drift in the three AGENTS.md slices.** Gemini is
    listed as an active TUI although it is deprecated (A36); the `CLAUDE.md`
    symlink the global rules require is missing in all three repositories, and
    stayturgid's symlink policy text would forbid it (known item 7b, A32);
    site-private's `AGENTS.md` still prescribes bare `pbcopy` and a
    `just ops-memory-sync` recipe that does not exist there (C1.1, section 6).
11. **Issues that look done but are open**: stayturgid #312, #310 and #253,
    site-djbclark #217 and #218; #45 is mostly done; #43, #45 and #188 track
    one failure (E16-E24). The operator decides; nothing was closed.
12. **CI is described but gone.** hacking.md and toolchain.md say CI runs
    `just test` from `.github/workflows/test.yml`, which was removed (A15).

## 2. Status of the issue #139 starting points

| #139 item                                          | Status on 2026-10-09                                                                              |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Site-contract spec header says "unimplemented"     | Fixed: `docs/architecture/site-contract.md` says "Shipped (Phase C+D)".                           |
| `docs/hacking.md` describes AutoJs6 as active      | Fixed for AutoJs6; hacking.md has other stale content (A3, A6, A8, A15, A16, A28).                |
| `control.md` hardcodes grok-4.5                    | Fixed: no model is pinned in `docs/architecture/components/control.md`.                           |
| `docs/STATUS.md` operator queue has resolved items | Still present (A10, A11, A13).                                                                    |
| `ansible/README.md` wrong cross-reference          | Fixed there; the same bug class remains in `ansible_collections/stayturgid/fleet/README.md` (B7). |

### Known structural items (7a, 7b)

1. **7a:** stayturgid `AGENTS.md` ("private repo; expect 404") and
   `docs/architecture/adr/005-two-repo-topology.md` call site-djbclark private.
   It is public. ADR 005 also says there are exactly two repository kinds,
   while `multi-site-topology.md` §4.10 and `AGENTS.md` describe a third,
   site-private (A33).
2. **7b:** none of the three repositories has `CLAUDE.md` as a symlink to
   `AGENTS.md`, which the operator's global rules require. site-djbclark's
   nested `tools/s-farm/AGENTS.md` has no sibling `CLAUDE.md` either.

## 3. stayturgid

### 3.1 Top-level docs, rules, notes and architecture (A)

#### CRITICAL

A1. CRITICAL: stayturgid/docs/commands.md:12-16,20 (also docs/coding-rules.md:192-193, docs/architecture/components/control.md:40-41, docs/architecture/platform-architecture.md:555-557, docs/architecture/components/termux.md:100, justfile:12). These document `just --set hosts <h> deploy|deploy-check|verify|verify-drift|verify-heal|firerpa-heal|termux-pkg-upgrade` as the way to target one host, but it does not limit anything. Every public recipe re-invokes a nested `just _<x>_impl`, and `--set` overrides do not reach the child process: there is no `set export`, and `hosts` is read with `env_var_or_default("hosts", "")` at justfile:20/24. The result is a full-fleet deploy, check or verify.

- Evidence: `just --dry-run --set hosts x deploy` prints `just _deploy_impl ` (empty host). `just --evaluate deploy_args` prints `""` unless the env var `hosts` is set. `firerpa-heal` dry-runs as `hosts="" just _firerpa_heal_impl`. `verify device=""` (just/fleet.just:193-194) drops its argument entirely.
- Fix: document the forms that work, the positional `just deploy oneui-device` or the env form `hosts=oneui-device just deploy`. Or fix the recipes, which is code outside this slice; file an issue. control.md:40 also labels the `--set hosts oneui-device` line "whole fleet (recommended)", which contradicts itself.
  A2. CRITICAL: stayturgid/docs/just_standards.md:10,17-28,33-43. The doc describes an interface the code does not have:
- wrappers `deploy +host?: +scope?:` calling `just --set hosts … deploy-legacy`;
- `-legacy` shims that "preserve" the `--set hosts` form;
- uppercase env overrides (`DEPLOY_ARGS`, `MAC_SITE`, `VENV`, `COLLECTIONS`, `HOSTS=oneui-device just deploy`);
- `collections` default "android_common termux obtainium fdroid play".

Evidence:

- The real recipe is `deploy host="": @just _deploy_impl {{ host }}` (just/fleet.just:17-18).
- The env names are lowercase (justfile:20-27); `mac_site`, `venv` and `collections` are constants (justfile:29-31; collections = "android_common termux play").
- `just --dry-run HOSTS=x deploy` gives "variable `HOSTS` overridden on the command line but not present in justfile". An exported `HOSTS=` env var is silently ignored, so you get a whole-fleet deploy.

Fix: rewrite it to match just/fleet.just, or delete it. It is also orphaned: nothing in AGENTS.md, README.md or docs/README.md links to it.
A3. CRITICAL: stayturgid/docs/hacking.md:744-746 (`just deploy SCOPE=fdroid HOSTS=…`, `just deploy [HOSTS=…]`), hacking.md:366, 490, 547 (`just deploy HOSTS=oneui-device`, `just verify-drift [HOSTS=…]`, `just verify HOSTS=oneui-device`), docs/architecture/multi-site-topology.md:70, 75, 123, 619-620 (`just bootstrap-ssh HOSTS=<alias>`, `just deploy hosts=<alias>`). After the recipe name these strings are bound to the positional `host` parameter. Evidence:

- `just --dry-run deploy hosts=x` gives `just _deploy_impl hosts=x`, so the literal `hosts=x` is handed to deploy_fleet.py as a host.
- `just --dry-run deploy SCOPE=play HOSTS=x` fails with "justfile does not contain recipe `HOSTS=x`".

Fix: `just deploy <host>`, and `scope=play hosts=<h> just deploy` for scope.
A4. CRITICAL: stayturgid/docs/rules/normal-deploy-convergence.md:17-19, 32-36. "Release discipline: Artifact pins advance only in a versioned ops release … cut the next coordinated ops release" is an always-on rule that every agent reads (coding-rules.md:14), and it orders a retired process. Evidence: AGENTS.md:62-69 says "Retired 2026-08-23 … releases still work but are optional"; site-djbclark/docs/OPS-RELEASES.md:3 says "OPTIONAL since 2026-08-23"; the last ops-release.json bump is 4105606 (2026-08-23, ops-v1.4.5). Fix: replace it with "artifact pins advance by a commit that updates the lock and passes a normal deploy". Keep the exact-tag/checksum lock requirement and drop the `ops-v*` wording.
A5. CRITICAL: stayturgid/docs/STATUS.md:8-9, 27-30 says "Coordinated ops releases … Deploy checkouts advance only through the release gate owned by site-djbclark; the current deployed release is ops-v1.0.2". That contradicts AGENTS.md:62-69 (retired 2026-08-23), and the last release was ops-v1.4.5 in any case. Fix: delete the bullet and point to AGENTS.md "Versioned deploy releases — retired".
A6. CRITICAL: stayturgid/docs/hacking.md:14, 27, 73-83, 125-126 tell a new-device installer that Shizuku must be "thedjchi fork (CRITICAL: must be this fork)", version 13.6.0.r1349-thedjchi-beta, from github.com/thedjchi/Shizuku. Evidence: STATUS.md:115-118 says the fleet is pinned to ShizukuTendCF Drop-In r2851; README.md:51 and 235 say ShizukuTendCF (frdminc fork); android_common/roles/bootstrap_apks/defaults/main.yml:114-119 has the ShizukuTendCF Drop-In flavor. Fix: point to the ShizukuTendCF pin in bootstrap_apks and say `just deploy` installs it. Same drift: multi-site-topology.md:65 ("Shizuku (thedjchi fork)") and ADR 004:4 ("operator/Shizuku").
A7. CRITICAL: stayturgid/docs/notes/lessons-learned.md:41-66 "Obtainium over Play Store / F-Droid" tells agents to "re-install it via Obtainium without asking — every time, proactively" and to "always add the app to Obtainium afterward". Obtainium was dropped as a fleet dependency (issue #119, PR #143 fbec068, 2026-07-30); installs now come from the checksummed bootstrap_apks lock. Fix: mark it historical, or rewrite it as "GitHub-signed builds via the bootstrap_apks lock". Keep the sharedUserId signature-mismatch lesson, which is still true.
A8. CRITICAL: stayturgid/docs/hacking.md:416-424 (and 778-783, "Current maintenance plans (2026-07-13)") tell maintainers that `archive/plans/outstanding-fix-priorities-2026-07-13.md` "contains the current execution order, acceptance gates … and a copy-paste junior-agent prompt". That contradicts AGENTS.md:191 and coding-rules.md:21 ("docs/archive/ … never treat as current"). Fix: replace it with STATUS.md + GitHub issues + options.md, as README.md:71-79 already does.

#### STALE

A9. STALE: stayturgid/AGENTS.md:57. The Quick start's first command is `cd ~/ops/site-djbclark && just ops-release-status`, the gate that AGENTS.md:62-69 retires. Fix: drop that line.
A10. STALE: stayturgid/AGENTS.md:40-43 and 48 (also STATUS.md:52 and 114): - "OpenObserve↔Vector auth fixed 2026-07-25, pending 24h clean-log verification" is still listed as an active blocker, but #44 was closed 2026-07-28. - Operator queue item 2, "Decide the F1 consent-surface phasing question (#46)", remains, but #46 was closed 2026-07-29.

    Fix: remove both items.

A11. STALE: stayturgid/AGENTS.md:49 and STATUS.md:91-93 and 120 still have "Remove the stray `~/stayturgid` file" (STATUS also lists it as a known gotcha). `ls ~/stayturgid` → No such file or directory. Fix: delete it from the queue and the gotchas.
A12. STALE: stayturgid/AGENTS.md:35-37 says "the forced CLOSED_NO_SHELL soak still hasn't run". STATUS.md:50 and options.md:255-268 say it ran on 2026-08-01 and failed: hd8's Shizuku never started. Open follow-up #188 tracks that. options.md:252-253 ("Still open: the forced soak has not run", the 07-31 paragraph) contradicts the 08-01 paragraph directly below it. Fix: "soak ran 2026-08-01 and failed (Shizuku never starts on hd8 after reboot) — #43/#188".
A13. STALE: stayturgid/docs/STATUS.md, "Last verified 2026-07-26" header (line 8), which is older than its own 2026-10-03 fleet-health section. Rows in the workstream table (lines 48-54) are resolved: - "Normal fleet-deploy convergence … awaiting paired PR merge": #72 merged 2026-07-26 (also Repo bullet 24-26). - "Peer-start … only the STARTED E2E remains": #61 closed 2026-07-28. - "OpenObserve <-> Vector auth … pending 24h": #44 closed. - "F1 — FIRERPA MCP bridge: Planned, not implemented": #46 "implement FIRERPA MCP bridge" closed 2026-07-29; `just firerpa-mcp` / `firerpa-mcp-stdio` exist; open #253 is about how it runs.

    Operator queue item 1 (line 112) calls the #50 audit "private", but #50 is a public open issue. Item 4 (line 119, "Retest p7a only after firerpa/lamda#147 publishes") is resolved by STATUS's own fleet-health text: p7a is on v10.9, verified 2026-10-03. Fix: refresh the header date and remove or close these rows.

A14. STALE: stayturgid/docs/STATUS.md:102-104. The "intentionally dirty nested api submodule" gotcha names `~/src/Shizuku`, which no longer exists (`ls` → No such file); only `~/src/ShizukuTendCF` exists. Fix: name only ShizukuTendCF.
A15. STALE: stayturgid/docs/hacking.md:494 ("CI runs `just test` on every push (`.github/workflows/test.yml`)") and docs/toolchain.md:15, 19, 309-314 ("CI … Runs the same just recipes"; "from .github/workflows/test.yml: run: just lint"). test.yml was removed in 2e3a6ef ("drop PR-gating CI"). The only workflows are collection-build.yml (runs `just ansible-test`) and termux-x11-stable-release-check.yml. Fix: say tests are local and pre-commit only, and drop the CI layer from the N+1 table.
A16. STALE: stayturgid/docs/README.md:28 and docs/architecture/core-architecture.md:11 ("`catalogs/` — Obtainium JSON catalogs"), and hacking.md:735-740 (`catalogs/obtainium/app-stores-optional.json`; "Obtainium catalog import is headless and belongs to the main fleet pass"). `catalogs/` was deleted in fbec068 (#143). Fix: remove these. core-architecture's tree also omits the live `just/`, `packaging/` and `examples/`.
A17. STALE: stayturgid/README.md:194-196, docs/architecture/components/control.md:135 and docs/hacking.md:362 say fleet-health and adb-reconnect post a macOS notification. The code sends to Hermes only: control/bin/fleet_health_monitor.py:112-114 ("Hermes only (no macOS notification)"), and control/lib/hermes_notify.py:1-4 is used by adb_reconnect, access_monitor and four other monitors. This also matches the home-agents.md rule "Operator notices from scripts go to Hermes too, not macOS notifications". Fix: change the wording to "sends a Hermes notice".
A18. STALE: stayturgid/docs/rules/screen-control-hold.md:25-28 and 37-38 say that at `__exit__` the session restores the prior foreground activity, and that "restore is the default". The code has it disabled: control/lib/screen_control.py:480 ("DISABLED 2026-07-14 (H9): foreground save/restore is unreliable"), and options.md:357-361 (H9) says so too. Fix: say restore is off and that the agent must leave the screen as it found it by hand (or say nothing about restore).
A19. STALE: stayturgid/docs/architecture/adr/001-ansible-boundary.md:9-10, 31-33, 52, 56-57 still names AutoJs6 as a runtime layer ("Python / AutoJs6 / shell", "AutoJs6 `main.js` watchdog", "Obtainium / Aurora / AutoJs6 drawer UI"), plus `android_ui` (deleted in #162, per ADR 002:3-6) and `make verify` (the Makefile is gone). Its non-goal "rebuilding logic in Tasker" now conflicts with the shipped Tasker sshd recovery (README.md:107-206, options 44). It is the only ADR without the K1/#162 retirement addendum that ADR 002, 003 and 004 carry. Fix: add the same addendum and correct `make verify` → `just verify`.
A20. STALE: stayturgid/docs/handoff.md:6-9 says the "latest complete baton" is handoff-2026-07-26-ops-separation-shelved.md. Newer handoffs exist (latest handoff-2026-08-01-ops-status.md), and the in-repo session log stopped 2026-08-15. Fix: drop the "latest baton" pointer; see finding A30 for where handoffs go now.
A21. STALE: stayturgid/docs/README.md:32 calls operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md the "Active F1 … implementation plan". F1 is implemented (#46 closed 2026-07-29; options.md:395 lists F1 as Closed). Fix: label it the shipped design. options.md:58-59 ("F1 denotes … open: MCP bridge") also contradicts options.md:395.
A22. STALE: stayturgid/docs/architecture/components/autojs6.md:8-10 says "AutoJs6 uninstall on some devices is unconfirmed". STATUS.md:50 and options.md:238-240 say it was confirmed absent on all three devices on 2026-07-31. termux.md:139 still lists autojs6.md as the "watchdog layer". Fix: update both.
A23. STALE: stayturgid/docs/coding-rules.md:102-103 ("Follow the [`just` migration plan](archive/plans/just-migration-plan.md)") gives an archived plan as a standing instruction. Fix: point to the justfile / docs/commands.md.
A24. STALE: stayturgid/docs/options.md:375-383 (Track F) says "fireos-device blocked by Fire OS SELinux (peer-bootstrap covers it; no plan to fix)" and "fireos-device remains unsupported". STATUS.md:54 and 79-84 say hd8 FIRERPA 10.0 works through control-node ADB and converges on the next plain `just deploy` (#311 closed 2026-10-03). Fix: update Track F's known limitations.

#### GAP

A25. GAP: stayturgid/README.md:24 (the SSH CA module's README is "docs/handoff.md § Major changes") and README.md:234 ("see docs/handoff.md for fireos-device quirks"). docs/handoff.md is an 18-line pointer with no such section and no Fire OS content. Fix: point SSH CA at ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml (or `just ca-status`), and Fire OS at docs/research/fire-os-local-adb.md. README.md:22 also uses autojs6.md (retired) as the Native agent's README, though device/native-agent/README.md exists.
A26. GAP: these commands named in docs are not recipes: - stayturgid/docs/commands.md:11: `just dotenv-lint` isn't a recipe; dotenv-linter runs inside another recipe (just/tests.just:299-302) and pre-commit. - docs/toolchain.md:12: `just format` doesn't exist. - docs/adding-a-launchd-service.md:115: `just landing-page-status` doesn't exist; the real one is `landing-status`. - commands.md:24: `just cf-run [HOSTS=…]` should be lowercase `hosts=`, per the recipe comment `just cf-run [hosts="p7a s24"]`. - commands.md:26: "Hermes worktree status" — the recipe is "Quick gateway status".

    Fix: correct each row.

A27. GAP: these paths named in docs do not exist: - stayturgid/AGENTS.md:128: `control/lib/logging.py` → `control/lib/site_logging.py`. - ADR 002:47: `control/bin/a11y_services.py` → `control/lib/a11y_services.py`. - control.md:174: "see HANDOFF § Mac fleet health" (no such section anywhere). - platform-architecture.md:172: `control/tools/obtainium/*.py` is still listed as an active violation (the directory is empty and untracked). - screen-control-lease.md:104: `make lease-status` in a sibling repo (unverified).

    Fix: correct or delete each.

A28. GAP: stayturgid/docs/hacking.md:26 gives the agent package as `com.stayturgid.agent`. The real applicationId is `org.stayturgid.agent` (device/native-agent/app/build.gradle.kts:16; README.md:91). Fix: correct it.
A29. GAP: stayturgid/docs/README.md (the "full documentation index") does not list commands.md, toolchain.md, just_standards.md, adding-a-launchd-service.md, notes/landing-health.md, architecture/site-contract.md, platform-architecture.md, components/cfengine-server.md, or ADR 003-006. It also labels research/experiments/ as "incubator/" and research/evaluations/ as "history/" (lines 61-75), which are old directory names. Fix: add the missing rows and use the real paths.

#### INCONSISTENT

A30. INCONSISTENT: stayturgid/AGENTS.md:190 ("docs/operations/sessions/ — Session-by-session history and handoffs — Every session"), docs/rules/github-issues.md:41-44 ("Session handoffs … still belong in docs/operations/sessions/"), and docs/notes/lessons-learned.md:236-243 ("Session wrap-up protocol"). The newest file in docs/operations/sessions is 2026-08-15. home-agents.md now sends handoffs elsewhere: a Tier 1 pointer under `~/.local/state/handoffs/` (session-handoff skill) and Tier 2 via the `handoff` skill, which "lands in site-private/memory/handoffs/ for the ops-djbclark suite". Fix: state the current home in all three places. The product doc can just say "handoffs are kept outside this repo by the operator's tooling".
A31. INCONSISTENT: stayturgid/AGENTS.md:200-202 ("Before any edit in a source task worktree: fetch && pull --ff-only … Always commit and push when done") and docs/coding-rules.md:32 ("source task worktree only; never a deploy checkout"). Worktrees and deploy checkouts went away with the release retirement (AGENTS.md:64-66: "Work directly in ~/ops"). home-agents.md "Where work happens" says edit in place in ~/ops and push at opportune moments. When another agent has unstaged edits: never stash, add or reset their files, never `commit -a`; if only ahead, plain push; if behind, wait or ask. As written, coding-rules.md:32 can be read as forbidding a pull in ~/ops, the only checkout. Fix: drop "worktree"/"deploy checkout" and adopt the home-agents wording, or link to it.
A32. INCONSISTENT: stayturgid/AGENTS.md:164-169 ("Symlinks (filesystem) are reserved for root-level ~ agent/vendor files … tool memory dirs … .mysite") enumerates allowed symlinks and leaves out the in-repo `CLAUDE.md -> AGENTS.md` symlink that home-agents.md "CLAUDE.md is always a symlink to AGENTS.md" requires in every repo. (Known item 7b is that the symlink is missing; this is the policy text that would block adding it.) Fix: add `CLAUDE.md → AGENTS.md` (same directory) to the allowed list.
A33. INCONSISTENT: stayturgid/docs/architecture/adr/005-two-repo-topology.md:10-25 says "Exactly two repo kinds … There is no third 'glue' repo". docs/architecture/multi-site-topology.md:377-387 (§4.10, "The third repo: site-private … three sibling checkouts, not two") and AGENTS.md:136-138 say otherwise. ADR 005 has no amendment. Fix: add a dated addendum to ADR 005 recognising site-private as a private, non-overlay companion. Known item 7a (it calls site-djbclark private) is in the same file.
A34. INCONSISTENT: stayturgid/docs/architecture/platform-architecture.md:3-8 says "Status: Draft — replaces … multi-site-topology.md … Once approved, those three documents become historical". It is still Draft, and multi-site-topology.md remains the doc cited as authoritative by AGENTS.md:23 and 172, handoff.md:18 and rules/github-issues.md:33. Readers can't tell which one is canonical. Fix: either mark platform-architecture "Accepted" and demote multi-site-topology, or change the header to "Draft proposal; multi-site-topology.md remains canonical".
A35. INCONSISTENT: stayturgid/docs/commands.md:24 says `just cf-run` "replaces cf-runagent". docs/architecture/components/cfengine-server.md:5-8 and 48 and the code (control/bin/fleet_health_monitor.py:814 `_try_cf_runagent_repair`) keep cf-runagent as the automatic Tier 3a path. cf-run (control/bin/cf_run.py) is a manual SSH-based alternative, not a replacement. Fix: "SSH-based manual CFEngine repair (cf-runagent remains the automatic Tier 3a)".
A36. INCONSISTENT: stayturgid/AGENTS.md:13 lists "Gemini" among the TUIs here. home-agents.md:264 says "gemini is deprecated and not installed". Fix: drop it (or list "Hermes" etc. by reference to home-agents.md).
A37. INCONSISTENT (low): stayturgid/docs/coding-rules.md:186-194 and AGENTS.md:82 run `just test` / `just pytest` bare. home-agents.md "Heavy builds and tests: run them through bg" requires `~/ops/site-private/bin/bg` for tests (machine-wide test slots, BG_CPUS=3). The Claude hook site-djbclark/claude/hooks/bg_test_gate.py only catches a literal pytest/tox/nox word, so `just test` slips past the cap. This is a site rule, so the public product doc should not hard-code it. Fix: add one line to the site overlay (or AGENTS.md "Environment") saying that on this machine tests run as `~/ops/site-private/bin/bg just test`.

### 3.2 Operations, collection docs and component READMEs (B)

B1. CRITICAL: stayturgid/docs/ansible/collections/modules/{fdroid_apps,fdroid_install,fdroid_repo_push,fdroid_repos,obtainium_app}.md — reference pages for modules in `stayturgid.fdroid` / `stayturgid.obtainium`, collections deleted 2026-07-30 (#119) — evidence: `git ls-files ansible_collections/stayturgid/obtainium ansible_collections/stayturgid/fdroid` is empty; ansible_collections/stayturgid/fleet/CHANGELOG.md:5-6; docs/operations/sessions/handoff-2026-07-30-drop-obtainium-119.md:13 — fix: move the five pages to docs/archive/ (or delete). (Note: the untracked directories still exist on disk in ~/ops/stayturgid, so `ls` there misleads; trust `git ls-files`.)

B2. CRITICAL: stayturgid/docs/ansible/collections/adoption.md:48-91 — tells consumers to `brew install fdroidcl` and call `stayturgid.fdroid.fdroid_repos`; role table lists `stayturgid.obtainium.obtainium_apps` and `stayturgid.fdroid.fdroid_repos`; §"Obtainium (on-device over SSH)" points at `control/tools/obtainium/import_catalog.py`; line 78 says play_store does "Aurora Shizuku grant" — all removed (#119 Obtainium/F-Droid; #145 Aurora, docs/operations/sessions/handoff-2026-07-30-drop-aurora.md) — evidence: no such collections/paths in `git ls-files`; play_store role has no Aurora tasks — fix: delete the F-Droid and Obtainium sections and rows, describe play_store as "optional apkeep/gplaycli sideload (gated by stayturgid_app_stores_enabled)", add rows for `android_common.bootstrap_apks`, `ensure_apps`, `app_privileges`, `fleet.shizuku_config`, `firerpa.firerpa`.

B3. STALE: stayturgid/docs/ansible/collections/std_modules_audit.md:15-17,25-26,51 — "Role" column cites fdroid roles, custom-module table lists `obtainium_app` and the four fdroid modules — evidence: as B1 — fix: drop those rows; add the modules that exist but are missing (`native_agent_config`, `shizuku_start`, `android_app_privileges`, `stayturgid_verify`).

B4. GAP: stayturgid/docs/ansible/collections/modules/ — no page for three shipped modules: `android_common.native_agent_config`, `android_common.shizuku_start`, `fleet.stayturgid_verify` — evidence: `git ls-files ansible_collections | rg plugins/modules/` — fix: add stub pages (or autogenerate from DOCUMENTATION blocks). Related: `fdroid_client.md` documents the `android_common.fdroid_client` lookup, which still exists in code but has no caller outside its own test (`rg -l fdroid_client` = the plugin, android_packages.py, tests/python/test_fdroid_client_lookup.py); mark it legacy or remove plugin+doc together.

B5. STALE: stayturgid/ansible_collections/README.md:36,38 — "examples/ — consumer site templates (termux, fdroid, full-fleet)": there is no fdroid example (`git ls-files examples` = consumer-full-fleet, consumer-termux-only, firerpa-nonroot); line 38 links `../human/HANDOFF-HUMAN.md`, deleted 2026-07-18 in 5e087e7 "Move operator docs to private site" — fix: "(termux-only, full-fleet, firerpa-nonroot)"; drop the HANDOFF-HUMAN item or point at docs/STATUS.md operator queue. Table line 10-13 also omits `firerpa` collection and the android_common roles `bootstrap_apks`, `ensure_apps`, `app_privileges`.

B6. GAP (dead link): stayturgid/docs/ansible/collections/modules/fdroid_repo_push.md:15 — `../../../../human/HANDOFF-HUMAN.md` §4.2 does not exist (same deletion as B5) — fix: resolved by B1 archiving. Cross-slice evidence for slice A: the same dead link is in README.md:41, docs/README.md:76, docs/options.md:37; docs/architecture/platform-architecture.md:823 lists the file in a layout tree.

B7. INCONSISTENT (wrong link, same class as #139 item 5): stayturgid/ansible_collections/stayturgid/fleet/README.md:3 — "Start at [../README.md](../../../control/lib/README.md)": text names the collections README, href goes to control/lib/README.md — evidence: file line 3 — fix: href `../../README.md` (= ansible_collections/README.md). #139 item 5 itself (ansible/README.md:120) is FIXED: href is now `../ansible_collections/README.md`.

B8. STALE: stayturgid/ansible_collections/stayturgid/android_common/README.md:4,14,20 — "installed as a dependency of ... `stayturgid.fdroid`"; lists `fdroid_client` lookup as current; `ensure_apps` described as "Unified play/fdroid/apk/obtainium dispatch" — evidence: ensure_apps/tasks/main.yml dispatches only play and apk sources (lines 11-50) — fix: "play/apk dispatch"; drop fdroid; add `bootstrap_apks`, `app_privileges` roles and `android_apk`, `android_app_privileges`, `native_agent_config`, `shizuku_start` modules to the table.

B9. STALE: stayturgid/ansible_collections/stayturgid/android_common/roles/tailscale_vpn/README.md:10 — "Included in `fleet.yml` after `obtainium_apps`" — evidence: ansible/playbooks/fleet/fleet.yml:17-19 runs termux_userland → shizuku_config → tailscale_vpn; no obtainium role — fix: "Included in fleet.yml after shizuku_config".

B10. STALE: stayturgid/ansible_collections/stayturgid/android_common/CHANGELOG.md:3-6 — newest entry (1.5.0) adds `autojs6_project_deploy`; no entry records its removal (#162, 2026-07-31) or the later `native_agent_config`, `shizuku_start`, `android_app_privileges` modules and `bootstrap_apks`/`app_privileges` roles; galaxy.yml still says 1.5.0 — fix: add an "Unreleased"/1.6.0 entry. Also android_common/CHANGELOG.md:15 "unified play/fdroid/apk/obtainium dispatch" is fine as history.

B11. CRITICAL: stayturgid/examples/consumer-termux-only/README.md:39-47 (and examples/consumer-termux-only/requirements.yml) — pins `version: stayturgid.termux-1.8.0`; that tag does not exist (local and `git ls-remote --tags origin` top out at `stayturgid.termux-1.5.0`), so `ansible-galaxy collection install -r requirements.yml` fails for a consumer following the doc — fix: push the missing collection tags (termux-1.8.0, android_common-1.5.0, fleet-1.6.1, play at its version, firerpa-0.1.0) or pin to an existing tag. B13 is the same problem for fleet.

B12. STALE: stayturgid/examples/consumer-full-fleet/README.md:5,15,19,21-30 — requires "AutoJs6 project" in the checkout (deleted #162); chain "fleet → post-ui → app-stores re-pass → validate" (site.yml has no re-pass; it is ensure-bootstrap-apks → verify-bootstrap-apks → ensure-shizuku → preflight → bootstrap → fleet → firerpa → post-ui → validate → control_node, ansible/playbooks/site.yml); "App stores (Neo / Aurora)" with `stayturgid_ensure_neo_store` / `stayturgid_ensure_aurora_store` (no code reads either var: `rg ensure_neo_store` hits only examples/consumer-full-fleet/inventory/hosts.yml.example) — fix: rewrite those sections; drop the two vars from the example inventory.

B13. CRITICAL: stayturgid/examples/consumer-full-fleet/README.md:19 (+ requirements.yml) — pins `stayturgid.fleet-1.5.0`, a tag whose galaxy.yml depends on the deleted obtainium/fdroid collections and the removed autojs6_watchdog role (fleet/CHANGELOG.md:5,15), so the "pinned" install is a pre-K1 fleet that no longer matches the site.yml it imports from the checkout — fix: tag fleet-1.6.1 (current galaxy.yml) and pin it.

B14. STALE: stayturgid/ansible/README.md:3,28 — "No AutoJs6, Obtainium, or Shizuku automation in this playbook" / "Out of scope: Shizuku pairing, AutoJs6 install, Obtainium bootstrap" frame retired components as things to configure separately — fix: drop AutoJs6/Obtainium from both lists.

B15. STALE: stayturgid/ansible/README.md:77-80 — `site.yml chains: preflight → bootstrap → fleet → optional post-ui → validate` — evidence: ansible/playbooks/site.yml starts with ensure-bootstrap-apks, verify-bootstrap-apks, ensure-shizuku, and includes firerpa and control_node/site.yml — fix: list the actual import order.

B16. STALE: stayturgid/ansible/README.md:116-123 — "domain collections ... (`termux`, `obtainium`, `fdroid`, `play`, `android_common`)" — evidence: tracked collections are android_common, firerpa, fleet, play, termux (justfile:31 `collections := "android_common termux play"`) — fix: correct list. Line 144 "headless Obtainium catalog import" in the full-deploy description is also gone.

B17. STALE: stayturgid/ansible/README.md:154-160 — "Routine updates after deploying a coordinated version with the sibling site-djbclark `just ops-release-deploy` recipe" — versioned ops releases were retired 2026-08-23 — fix: replace with the current routine (pull master in ~/ops, `just deploy`). Verified: site-djbclark/justfile has no `ops-release-deploy` recipe (only `ops-release-claim-*` at :89-100), so the documented command does not exist. stayturgid still tracks `ops-release.json` at repo root (code, outside this slice).

B18. GAP: stayturgid/ansible/README.md:14,106,133 — "copy `inventory/hosts.yml` pattern", "Both hosts are defined in `inventory/hosts.yml`" (table lists three), layout shows `inventory/hosts.yml` — evidence: only `ansible/inventory/hosts.yml.example` and `example-standalone.yml` are tracked; real inventory lives in the site overlay — fix: point at hosts.yml.example and the site overlay; "All three hosts". Line 114 "see `docs/handoff.md` tooling rules": docs/handoff.md is now a 15-line pointer to STATUS.md with no tooling rules.

B19. CRITICAL: stayturgid/ansible_collections/stayturgid/firerpa/README.md:20,26 and stayturgid/ansible_collections/stayturgid/play/roles/play_store/README.md:13-14 — `just firerpa-deploy HOSTS=oneui-device`, `just firerpa-remove HOSTS=...`, `just deploy HOSTS=oneui-device`, `just deploy SCOPE=play HOSTS=...` — evidence: `just --dry-run firerpa-deploy HOSTS=oneui-device` → "error: justfile does not contain recipe `HOSTS=oneui-device`"; `just --dry-run deploy HOSTS=oneui-device` → `just _deploy_impl HOSTS=oneui-device` (the literal string becomes the host). The justfile variables are lowercase `hosts`/`scope` and must precede the recipe (justfile:4-12, 20-21) — fix: `just hosts=oneui-device firerpa-deploy`, `just deploy oneui-device`, `just scope=play deploy oneui-device`.

B20. STALE: stayturgid/ansible_collections/stayturgid/play/roles/play_store/README.md:7-8,17 — "Mac: apkeep" bullet duplicated; "See docs/handoff.md for fleet status" (now a pointer to docs/STATUS.md) — fix: dedupe; link docs/STATUS.md.

B21. STALE: stayturgid/docs/ansible/collections/roles/validate.md:16-36 and stayturgid/ansible_collections/stayturgid/fleet/README.md:15 — document an "A11y profile drift" check that fails on drift and a `stayturgid_validate_a11y_merge` variable that merge-restores — evidence: validate/defaults/main.yml has only `stayturgid_validate_a11y_profile`; tasks/main.yml:60-90 only probe/warn and only when AutoJs6 is still installed (legacy K1 leftover); `rg a11y_merge` finds nothing in code — fix: describe it as "warn-only legacy AutoJs6 a11y probe" and delete the merge variable/example.

B22. STALE: stayturgid/ansible_collections/stayturgid/fleet/README.md:14 — `post_ui (post-deploy screen-control)`; adoption.md:80 says the `android_ui` module was deleted (#162) and post_ui is now only the screen-unlock gate — fix: align wording.

B23. STALE: stayturgid/tests/README.md:14-18,23,36 — Tier (b) "the AutoJs6 log parser under node with a files{} mock" (no node test remains: `rg '\bnode\b' tests/test-unit.sh` hits only the header comment at :4, itself stale); "regression tests for CODE-REVIEW.md findings" (file is now docs/research/evaluations/code-review.md); "that's `control/bin/tests/run.sh device --heal`" (no such dir; it is `tests/run.sh device --heal` = `just verify-heal`) — fix: correct the three references.

B24. STALE: stayturgid/packaging/homebrew/README.md:21-24 — "`just deploy-mac` ... is currently blocked by stayturgid#85 — until that is fixed, apply it manually" — evidence: issue #85 closed 2026-07-27 (GitHub issues API) — fix: drop the blocked caveat.

B25. INCONSISTENT: stayturgid/device/termux/cfengine/README.md:21-25 — "CFEngine Core ... is supplied by Homebrew: `brew install cfengine`" — contradicts packaging/homebrew/README.md:11-36 (pin `cfengine@3.27.1`, uninstall plain `cfengine`; `just cfengine-pin` does exactly that, just/cfengine.just:5-17) — fix: `just cfengine-pin` (or `just deploy-mac --tags prereqs`).

B26. GAP: stayturgid/control/site_contract/README.md:1-28 and stayturgid/SITE-CONTRACT.md:30-38 — describe only site-init/site-sync as "Phase C"; `serverapps.py` / `olivetin_projection.py` and `just site-serverapps` (just/site.just:6,67) and `just serverapps-upgrade` are undocumented here; README:53-54 "no adapter behavior or inject-mode writes occur in C4" and :81 "Never writes outside generated/stayturgid/ in Phase C3" read as current limits — fix: add a site-serverapps section and phase status (shipped), or mark the phase notes as historical.

B27. STALE: stayturgid/device/native-agent/README.md:67 — "Live fleet status: docs/archive/plans/native-agent-status-2026-07-22.md" presents an archived July snapshot as live; :15 "Checkpoint:" links a 2026-07-22 session log as the current checkpoint; :3 "OPTIONS K1 replaces AutoJs6" (K1 is done) — fix: link docs/STATUS.md for live status; label :14-15 "History".

B28. INCONSISTENT: stayturgid/device/native-agent/README.md:97 — Architecture list says "Composite build: dev.rikka.shizuku:api / :provider from local fork", but :41-48 (and settings.gradle.kts:30-38) say Maven Central is the default and the composite is opt-in since 2026-09-29 — fix: "Optional composite build (-Pshizuku.composite=true)".

B29. GAP: stayturgid/control/tools/native-agent/README.md:3-7 — table omits `provision_peer.py` and `reingest_soft_health.py` (both tracked in that dir); :18-21 "Fleet release17 APK ... track under K1 remaining work" is a K1-era note with no issue link — fix: add the two scripts; link the issue or drop. (Serial-number hygiene: see B40.)

B30. GAP: stayturgid/TEST_GUARD_SCRATCH.md — one line "throwaway, safe to delete", committed 2026-08-01 (d362c26, #204) and still tracked at repo root — fix: `git rm`.

B31. CRITICAL: stayturgid/docs/ansible/collections/modules/shizuku_grant.md:15-16 — documents parameters `shizuku_json` and `staging_path`; the module's argument_spec has only `device`, `package`, `connect` (ansible_collections/stayturgid/android_common/plugins/modules/shizuku_grant.py:80-84), and its DOCUMENTATION says it "no longer touches that file at all". A playbook following the doc fails with Ansible "Unsupported parameters" — fix: delete the two rows and say the module only does `pm grant` plus a conditional Shizuku restart.

B32. STALE: stayturgid/docs/ansible/collections/modules/shizuku_grant.md:5,23,29-30 — "(Neo Store, Aurora Store, etc.)", example package `com.machiav3lli.fdroid`, and "`stayturgid.fdroid.fdroid_repos` and `stayturgid.play.play_store` call this module" — evidence: the only caller is `android_common/roles/bootstrap_apks` (defaults/main.yml, tasks/install_apk.yml); Neo/Aurora automation removed (#119, #145) — fix: "called by bootstrap_apks"; use a current fleet package in the example. Same for docs/ansible/collections/modules/android_intent.md:25-29 (Neo Store fdroidrepos example) and android_packages.md:14,20 ("fdroid and play roles").

B33. STALE: stayturgid/docs/operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md:5-7 — "Status: ... Implementation is ready to begin" — evidence: F1 shipped: control/bin/firerpa_mcp.py, ansible/roles/control_node/templates/firerpa-mcp.plist.j2, tests/test_firerpa_mcp.py, `just firerpa-mcp` / `firerpa-mcp-stdio` (just/services.just:167-172), docs/operations/sessions/session-2026-07-23-firerpa-mcp-f1.md — fix: mark "Implemented (2026-07-23)" and move to docs/archive/plans/; its :9 priority link already points into archive.

B34. STALE: stayturgid/docs/operations/deep-dives/firerpa-ssh-investigation.md:100-106 — "Operator Commands" use `make firerpa-deploy HOSTS=...`, `make firerpa-heal`, `make firerpa-health`; there is no Makefile (`git ls-files Makefile` empty; migrated to just) — fix: `just hosts=oneui-device,stock-android-device firerpa-deploy`, `just firerpa-heal <host>`, `just firerpa-health` (see B19 for the `hosts=` placement).

B35. INCONSISTENT: stayturgid/docs/operations/secretspec-boundary-lifecycle.md:28-30 — "`add` ... mirror the declaration into the tracked `site-private/secretspec.toml.example` from a task worktree, then release it"; also :32-34 describes `template-check` against "the tracked declaration template" — contradicts docs/operations/secretspec-secrets-management.md:52 ("No tracked schema"), :170-172 ("no tracked file to mirror ... no release step required") and :180-182 (tracked-declarations file retired 2026-08-16); "release it" also assumes versioned ops releases (retired 2026-08-23) — fix: rewrite the `add` paragraph to the current no-tracked-schema flow; confirm whether `template-check` still exists (unverified: it is a sudo-secretspec subcommand outside this repo).

B36. CRITICAL: stayturgid/docs/research/unified-architecture-synthesis.md:5-6,12-14 — headed "Status: Authoritative architecture for stayturgid. Audience: ... autonomous agents"; links docs/archive/plans/agent-ovgo-implementation.md as "Specific instructions for autonomous agents deploying this architecture" and docs/handoff.md as "Current session context and state" — evidence: docs/architecture/platform-architecture.md:3-8 says it replaces this file, which then "become[s] historical"; the linked plan is archived; docs/handoff.md is a pointer stub; its §1.1 says `secretspec.toml` defines requirements (tracked schema retired, see B35) — fix: replace the status line with a visible "Historical research (2026-07); superseded by docs/architecture/platform-architecture.md" banner and drop the "instructions for agents" framing. docs/research/ovgo-stack-architecture.md and mobile_first_observability_stack.md ("Current Implementation Details") need the same visible banner.

B37. GAP: stayturgid/docs/research/** (29 of 37 tracked .md files) — the "historical" label is an HTML comment on line 1 (`<!-- historical: production hostnames/IPs ... -->`), invisible when rendered on GitHub, and it speaks to hostnames, not to whether the content is current; there is no docs/research/README.md stating "research and evaluations; not current behaviour" — fix: add docs/research/README.md with that rule plus an index, and a one-line visible status banner on docs still read as guidance (B36; mac-android-ui-automation.md, which docs/README.md:51 and docs/architecture/components/control.md:183 link as the live "Mac→Android UI playbook", is fine to stay current but its :26 "works with AutoJs6 a11y" is stale). Dated evaluation docs (evaluations/*, _-2026-07-_.md) are adequately labelled by their Date/Status headers.

B38. GAP (dead links): stayturgid/docs/research/site-identity-source-of-truth-2026-07-14.md:18,59 → `../../ansible/inventory/hosts.yml` and :67 → `../../secretspec.toml`; neither is tracked (inventory moved to the site overlay; only ansible/inventory/hosts.yml.example exists; the tracked secretspec schema was retired) — fix: point at hosts.yml.example and control/site_contract/templates/secretspec.toml.j2, or unlink. These are the only dead relative links in this slice besides B5/B6 (scripted check of every `](path)` in the 92 files).

B39. INCONSISTENT: stayturgid/examples/firerpa-nonroot/README.md:166-170,270 (and its justfile:40 `UPSTREAM_RELEASE`) download FIRERPA v10.9 from upstream `firerpa/lamda` releases, while ansible_collections/stayturgid/firerpa/README.md:79-82 says "upstream deletes releases (both v10.0 and v10.2 are gone), so the fork mirror is the dependable source" and the role uses djbclark/lamda (roles/firerpa/defaults/main.yml:32) — evidence: upstream v10.9 assets still return HTTP 200 today, so not broken yet — fix: note the fork as fallback in the example, or switch it to the fork URL.

B40. GAP (public-repo hygiene): a real device USB serial number appears in stayturgid/control/tools/native-agent/README.md:12 and stayturgid/docs/research/fire-os-local-adb.md:3 (value deliberately not copied here) — fix: replace with `<serial>`; the research doc's historical comment does not cover serials.

#### Sessions check (docs/operations/sessions/**)

docs/operations/sessions/README.md declares the tree a "Frozen archive as of 2026-08-03" (new handoffs live in site-private). Current docs that still treat a session file as current guidance:

1. CRITICAL (slice A file, reported here as evidence): docs/handoff.md:5-9 — "The latest complete baton is handoff-2026-07-26-ops-separation-shelved.md ... the next AI must prompt the operator with its loose ends before starting new implementation" — the tree has later handoffs (e.g. handoff-2026-08-01-ops-status.md) and is frozen; an agent following this would replay August-1-or-older loose ends.
2. device/native-agent/README.md:15 — B27.
3. docs/STATUS.md:11 links the 2026-07-26 release handoff as context (slice A; versioned releases retired 2026-08-23).
   Other links into sessions (docs/options.md:231,233; docs/notes/lessons-learned.md:338; docs/architecture/components/autojs6.md:11; docs/research/experiments/on-device-llm.md:64) cite them as history and are fine.

#### Archive check (docs/archive/**)

Current docs linking archive content as if current: device/native-agent/README.md:67 (B27, "Live fleet status"), docs/research/unified-architecture-synthesis.md:12 (B36, "instructions for autonomous agents"), docs/operations/plans/firerpa-mcp-bridge-plan-2026-07-22.md:9 (B33, cites an archived priority list as its live priority). ansible_collections/stayturgid/firerpa/README.md:90 lists the archived integration plan under "Related docs" — acceptable, but label it "(archived)".

#### Further notes

Bx1. Dead `human/HANDOFF-HUMAN.md` links (deleted 5e087e7, 2026-07-18): README.md:41, docs/README.md:76, docs/options.md:37; docs/architecture/platform-architecture.md:823 lists it in a layout tree.
Bx2. justfile:5 documents `scope=full | fdroid | play | app-stores`, and control/bin/deploy_fleet.py:21,209-213,392 still carries an F-Droid scope after F-Droid's removal (code, not docs).
Bx3. ansible/inventory/hosts.yml is referenced as tracked by several docs; only hosts.yml.example is tracked.

## 4. site-djbclark (C)

### C1. AGENTS.md slices, home-agents.md, and the Cursor copy (priority 1)

C1.1. CRITICAL: site-private/AGENTS.md:116-119 — tells agents to "always copy [a prompt] to the clipboard with `pbcopy`" — contradicts home-agents.md:236-240 ("never bare `pbcopy`", use `~/ops/site-private/bin/clip`; agent shells are `LC_CTYPE=C` and mangle `—`) — replace the bullet with a pointer to the home-agents Clipboard rule (`clip`, unasked, for prompts). Same stale advice in site-djbclark docs/relay/PROTOCOL.md:54-56 (`pbcopy < docs/relay/NEXT-PROMPT.md`).

C1.2. CRITICAL: site-djbclark/AGENTS.md:130-139 (research/ exception) — says research is exempt "from the branch/PR/worktree/release flow … everything else in this repo still uses the release flow", and to run `just ops-memory-sync` first — contradicts the same file's :104-111 (release regime retired 2026-08-23, ops-memory-sync "no longer required") and home-agents.md:27-41 (all of `~/ops` is edited in place on master). An agent reading :139 would refuse or route ordinary edits through a retired flow. Same text in research/README.md:4-6 and :18-19 ("code or config changes anywhere else still use the worktree/PR/release flow") and in the `DATA_DIRS` comment in bin/deploy_ops_release.py:26-28 — rewrite the subsection as "research/ is data: one research-only commit, push at once", drop "everything else still uses the release flow".

C1.3. STALE: site-djbclark/AGENTS.md:16 and README.md:7 — open with "Private **site repo**" — contradicts AGENTS.md:141 and :183 ("This repo is public") and the GitHub API (200) — say "Public site repo (no secrets; private material lives in site-private)". (Same defect class as known 7a, but in this repo's own entry files.)

C1.4. CRITICAL: site-djbclark/AGENTS.md:5-6, :64, :86-87 and README.md:19 — send agents to `docs/relay/NEXT-PROMPT.md` as "continuation state for the ongoing segmentation/AI-stack work" / "**Start here to continue the work**" and say "follow the relay protocol … read the baton before re-planning" — NEXT-PROMPT.md:1-4 says the chain is **CHAIN-COMPLETE** (closed 2026-07-20, last touched 2026-07-26), and its "current state" block (NEXT-PROMPT.md:13-40, headed "supersedes the dated snapshot below") says all development happens under `~/src/ops-worktrees/` and `~/ops` is a "deploy-only checkout … no branching/editing/direct master pulls" — the opposite of today's rule (home-agents.md:27-31). An agent obeying the AGENTS.md pointer gets the retired workflow as "current". Fix: drop the "start here"/"ongoing" wording from AGENTS.md/README (mark the relay as a closed historical record), and put a one-line "historical; superseded 2026-08-23 by home-agents 'Where work happens'" banner at the top of NEXT-PROMPT.md.

C1.5. CRITICAL: site-djbclark docs/relay/PROTOCOL.md:46-53 — "A deploy happens only after … a coordinated stable `ops-vMAJOR.MINOR.PATCH` release … never pull arbitrary `master` commits into `~/ops`" — retired 2026-08-23 (AGENTS.md:104-111, docs/OPS-RELEASES.md:3-12). AGENTS.md:86 tells agents to follow this protocol. Also PROTOCOL.md:106-128 routes AI choice through `docs/reference/available-ai-models.md` and `cswap` accounts rather than `aiuse`/`model-routing` (home-agents.md:109-118, :257-277). Fix: header banner "closed relay; rules 4-5 and 'Recommending an AI' superseded".

C1.6. INCONSISTENT: `just ops-memory-sync` is described three different ways — site-private/AGENTS.md:108-110 "does the same across **all three** repos"; research/README.md:10 "fetch+rebase all three repos"; site-djbclark README.md:33-34 "plain fetch-and-rebase of the repos"; justfile:123-124 (the recipe's own comment) "Sync site-private's live memory only when all remote post-release changes are confined to memory/" — the code (bin/deploy_ops_release.py:725-741 `memory_sync`) iterates `DATA_DIRS` only, i.e. **site-private and site-djbclark, not stayturgid**, and first calls `require_clean_master` (fails if any other agent has unstaged edits, which home-agents.md:38-40 says to work around with `git fetch`/plain push, never stash). Fix: one sentence everywhere: "fetch + rebase of site-private and site-djbclark; refuses on a dirty tree"; update the justfile comment.

C1.7. INCONSISTENT: "Multi-Agent Protocol" — site-djbclark/AGENTS.md:164-171 and stayturgid/AGENTS.md:198-205 — both still say "Before any edit in a **source task worktree**: `git fetch … && git pull --ff-only origin master`. Always commit and push when done" — vocabulary from the retired worktree regime; home-agents.md:27-41 says edit `~/ops` in place, "push at opportune moments", `git pull --rebase`, and never stash/add/reset another agent's unstaged files. The two copies also differ from each other (stayturgid: "Leave no uncommitted changes."; site-djbclark: "Leave no uncommitted changes you didn't create." — which reads as the opposite rule). Fix: replace both with a pointer to home-agents "Where work happens" plus the dirty-checkout rule.

C1.8. STALE: "Trust between agents" blockquote — site-djbclark/AGENTS.md:10, stayturgid/AGENTS.md:13, site-private/AGENTS.md:8 — lists "Gemini" among "all TUIs here" — home-agents.md:264 "**gemini is deprecated and not installed**"; `command -v gemini` → not found. Fix: drop "Gemini" (Antigravity is already listed); consider dropping the TUI list entirely and saying "every agent CLI on this machine".

C1.9. STALE: site-djbclark/AGENTS.md:224-227 and site-private/AGENTS.md:157-162 — "`bin/book-kb` and `bin/clip` are byte-identical to the site-private copies … verify with `cmp`" — `site-private/bin/book-kb` and `site-private/bin/clip` are now symlinks to `../../site-djbclark/tools/book-to-kb/bin/{book-kb,clip}` (`ls -la site-private/bin`); there is one file, nothing to keep in sync. Fix: replace with "one copy, in tools/book-to-kb/bin; site-private/bin links to it".

C1.10. INCONSISTENT: private-path list — site-djbclark/AGENTS.md:185 ("What stayed private: `memory/`, `web/`, `docs/books/`, …") and site-private/AGENTS.md:27-30 (also lists `bin/fleet-watch`) — the enforcing file `site-private/.githooks/private-paths` lists neither `docs/books/` nor `bin/fleet-watch`; `site-private/docs/books` does not exist; `site-private/bin/fleet-watch` is a symlink → site-djbclark/bin/fleet-watch → `~/src/djbclark-ade/bin/fleet-watch`. Consequently site-private/AGENTS.md:146-147 ("the source EPUB is tracked here at `docs/books/learning-cfengine.epub`") and site-djbclark docs/book-kb-vs-book-to-skill.md:3 and docs/docling-pre-bug/README.md:5 cite a file that is not in any repo. Fix: make the two AGENTS.md lists match private-paths, and say where the EPUB actually lives (or that it is untracked).

C1.11. GAP: site-djbclark/AGENTS.md:58-82 ("Where documentation goes") — omits the files this repo now owns that matter most to agents: `home-agents.md` (the live `~/CLAUDE.md`/`~/AGENTS.md`, reached via `~ → site-private/home-agents.md → site-djbclark/home-agents.md`), `cursor/home-agents.mdc`, `skills/`, `claude/` (agents, hooks, commands), `tools/` (book-to-kb, s-farm, herdr), `research/`, `docs/tooling-policy.md`, `docs/OPS-RELEASES.md`. Meanwhile :48-50 says the `~` symlinks "are documented in site-private / stayturgid — not duplicated here", although the target now lives here. And site-private/AGENTS.md:95-97 still maps `home-agents.md`, `shell/`, `skills/` as site-private content (they are symlinks into site-djbclark since 2026-10-06, per its own :20-25). Fix: add the rows to site-djbclark's table; in site-private's table mark those three "symlink → site-djbclark".

C1.12. GAP: site-private/AGENTS.md:121-124 — "Modern CLI tool replacements … policy lives in site-djbclark/AGENTS.md … See that file's Conventions section" — that section has no such content; it moved to site-djbclark docs/tooling-policy.md on 2026-08-24 (site-djbclark/AGENTS.md:146-151). Fix: point at docs/tooling-policy.md (and home-agents.md:212-224 "Tools and habits").

C1.13. INCONSISTENT: Book-KB instructions differ by slice — site-private/AGENTS.md:126-153 teaches `just book-query/book-toc/book-outline/book-add` (site-private justfile recipes); home-agents.md:244-250, site-djbclark/AGENTS.md:229-248 and stayturgid/AGENTS.md:207-226 teach the `book-kb` CLI (`toc --deep`, verified present in tools/book-to-kb/bin/book-kb:733-737). Both work, but site-djbclark/AGENTS.md:247-248 and stayturgid/AGENTS.md:225-226 send public readers to "site-private/AGENTS.md ('Book knowledge base')" for "full detail", which is a private repo (404 for others). Fix: point "full detail" at the public tools/book-to-kb/README.md; keep the `just book-*` variant only as a site-private convenience note.

C1.14. STALE (cross-slice, for slice A): stayturgid/AGENTS.md:57 — Quick start's first command is `cd …/site-djbclark && just ops-release-status` (release tooling optional/retired since 2026-08-23). stayturgid/AGENTS.md:49 operator-queue item 3 ("Remove a stray `~/stayturgid` file") is resolved: `ls ~/stayturgid` → No such file or directory.

C1.15. INCONSISTENT: site-djbclark codex/README.md:3-6, :18-19 (file moved here from site-private 2026-10-06) — "each entry [in `~/.codex`] is a symlink into **this repository** or its ignored `.codex-runtime/`" and "Codex memory live in this repository" — `.codex-runtime/` is in site-private (`ls -d site-djbclark/.codex-runtime` → missing; site-private/.codex-runtime exists), Codex memory is `site-private/memory/codex/`, and 27 of 62 top-level `~/.codex` entries are real files/dirs, not symlinks (`find ~/.codex -maxdepth 1 -mindepth 1 ! -type l | wc -l` → 27; e.g. `agents/`, `hooks/`, `packages/`, `.codex-global-state.json`). site-private/AGENTS.md:59-61 makes the same "every top-level entry … is a symlink" claim. Fix: say "site-private" explicitly, and "most entries" or list the exceptions.

C1.16. INCONSISTENT (policy vs config, intent unverified): home-agents.md:275-277 — "The grok vendor (SuperGrok: `grok` TUI, `acp-run grok`, LiteLLM `grok-sub`) is excluded for now (2026-10-06)" — roles/litellm/templates/litellm-config.yaml.j2:124-131 still renders `grok-sub` in the fallback chain whenever `litellm_xai_bridge_enabled` (Darwin), and `launchctl list` shows `com.djbclark.xai-oauth-bridge` and `com.djbclark.litellm` running; home-agents.md:301 itself lists `xai-oauth-bridge` as a running service. Either the exclusion means "agents don't route to it directly" (then say so) or the role should drop it. roles/litellm/README.md never mentions grok-sub, the xAI bridge, or `PYDANTIC_DISABLE_PLUGINS` (set in templates/litellm.plist.j2 and litellm.service.j2; home-agents.md:303 relies on it).

#### C1.17 cursor/home-agents.mdc vs home-agents.md (in-step check required by home-agents.md:85-87)

The .mdc was last changed in the same commit as home-agents.md (`9dc2c32`, 2026-10-09 00:05), so recent edits were mirrored, but it has drifted in these places:

a. INCONSISTENT: cursor/home-agents.mdc:2 and :12 — "canonical copy at `~/ops/site-private/home-agents.md`" — home-agents.md:3-4 says the file lives in site-djbclark and site-private only links to it (`site-private/home-agents.md -> ../site-djbclark/home-agents.md`). Fix: name site-djbclark/home-agents.md as canonical.
b. INCONSISTENT: cursor/home-agents.mdc:166-167 — "No working ACP route: muse (zcode via `acp-run zcode` …; grok TUI works via `grok agent stdio`; agy works via `acp-run agy`)" — garbled list that reads as if zcode/grok/agy had no ACP route, and advertises the grok TUI route that home-agents.md:275 excludes. home-agents.md:264-266: "No ACP: muse; every other agent speaks it". Fix: copy the home-agents sentence.
c. STALE: cursor/home-agents.mdc:198-200 — "`/orc`, `/orc-meta`: commands in `site-private/claude/commands/`" — they are symlinks into `~/src/djbclark-ade/claude/commands/` (site-djbclark/AGENTS.md:191-199; `readlink site-djbclark/claude/commands/orc.md`), and the same .mdc says so at :183-185. Fix: drop the stale clause.
d. STALE: cursor/home-agents.mdc:356-357 — Session-log "Spec: `site-private/docs/session-handoff-compaction-spec.md`" — that spec (site-djbclark docs/session-handoff-compaction-spec.md:22-25, :53-58) still asserts "`~/ops` stays deploy-only, pinned to tagged releases" (see 2.3); home-agents.md:307-311 points at the `session-handoff` skill instead. Fix: point at the skill.
e. INCONSISTENT: size/omissions — the .mdc calls itself a "deliberate **subset**" because "every section costs context on every Cursor turn" (:22-24), yet it is 21,792 bytes vs home-agents.md's 19,877. Its declared omissions (backup, LLM gateway, agent teams) do not mention that "Start slow commands in the background" and the pipe/exit-status rule's section are folded elsewhere or absent. Fix: trim to an actual subset (e.g. drop the Claude-Code-only `run_in_background` and Agent-tool sentences at :76-80) and list every omitted section.
f. Minor: cursor/home-agents.mdc:170 hardcodes `~/ops/site-private/bin/acp-run` while home-agents.md:268-270 says plain `acp-run` (on PATH from djbclark-ade); both resolve today (`site-private/bin/acp-run -> site-djbclark/tools/acp-run -> ~/src/djbclark-ade/tools/acp-run`), but the long path is a two-hop symlink chain that silently breaks if either hop moves.

### C2. Other site-djbclark docs (priority 2)

C2.1. STALE: claude/README.md:3-6 — "Live copies under `~/.claude/hooks/` and `~/.claude/skills/` are canonical — this directory only versions them" — `~/.claude/skills/handoff` and `session-handoff` resolve (via site-private/skills → site-djbclark/skills) to `~/src/djbclark-ade/skills/…`, and the tracked mirrors `claude/skills/{handoff,resume,session-handoff}/SKILL.md` **differ** from those live copies (`diff -q` → differ for all three); `resume` was folded into `baton` on 2026-10-08 (AGENTS.md:200-202) and has no `~/.claude/skills/resume`. claude/README.md:44-47 — "`claude/commands/{orc,orc-meta}.md` … are the canonical copies" — they are symlinks into djbclark-ade. Fix: delete `claude/skills/` mirrors (or label them historical) and update both README paragraphs to name djbclark-ade.

C2.2. STALE: claude/skills/session-handoff/SKILL.md:19 (tracked, diverged mirror) and docs/session-handoff-implementation-plan.md:21 — "tracked edits happen in task worktrees under `~/src/ops-worktrees/`" / "ops-djbclark suite (cwd under `~/src/ops-worktrees/` or `~/ops/`)" — worktree regime retired 2026-08-23. The implementation plan is marked "approved for implementation" (:3), not historical. Fix: mark both historical, or delete the mirror (2.1).

C2.3. STALE: docs/session-handoff-compaction-spec.md:1-3, :22-25, :53-58 — header "Status: v0.1–v0.3 built and in use; v0.4 built 2026-08-04" (presents as current) while asserting "`~/ops` stays deploy-only, pinned to tagged releases; `~/src/ops-worktrees/` stays where code moves … confirmed still correct and explicitly not being merged" — retired 2026-08-23 (AGENTS.md:104-111). This doc is the "Spec" cited by cursor/home-agents.mdc:357 and claude/README.md:5. Fix: add a dated note that the deploy-only split was retired and the spec now lives with the skill in djbclark-ade.

C2.4. STALE: docs/handoff.md (whole file; "stayturgid — AI Handoff Document … Read it fully before doing anything else … the current state") — a July-2026 stayturgid handoff copied into this repo; describes AutoJs6 as a live heal layer (:41, :85, :122-124, :150-154; AutoJs6 retired 2026-07-22, per this audit's common rules) and links to stayturgid paths that no longer exist (`docs/operations/plans/outstanding-fix-priorities-2026-07-13.md`, `.cursor/rules/` — both missing in `~/ops/stayturgid`). It is linked as current "Agent context" from human/HANDOFF-HUMAN.md:7 and human/README.md:8 ("§ Agent conventions"). Fix: move to an archive/historical location with a banner, and repoint the two human/ links at stayturgid AGENTS.md / docs/STATUS.md.

C2.5. STALE: human/HANDOFF-HUMAN.md:10 "Last updated: **2026-07-20**" and human/README.md — present as the live operator checklist; human/CHECKPOINT-p7a-autojs6.md (CLOSED 2026-07-09, AutoJs6 workflow, `./control/tools/autojs6/…`) sits beside it unlabelled in human/README.md's file table. Fix: label the checkpoint as closed/historical in the README table and re-date or trim HANDOFF-HUMAN.md.

C2.6. STALE: docs/reference/available-ai-models.md:1-11 — "**Authoritative** catalog … Verified as of mid-July 2026" (last commit 2026-07-20); AGENTS.md:68 says "quote full rows when recommending". It lists Grok TUI rows (:109-112) without the 2026-10-06 grok-vendor exclusion (home-agents.md:275), and lacks zcode, Hermes, copilot, cline, qwen, devin that home-agents.md and bin/skill-everywhere.md treat as current. Fix: banner "historical snapshot (July 2026); current routing: `aiuse --available` + the model-routing skill", and change the AGENTS.md:68 row description.

C2.7. INCONSISTENT: roles/litellm/README.md:3 — "This role renders the current Auto Router v2 configuration" — the same README :264-265 says "The former `smart-router` Auto Router v2 alias … [was] removed". Fix: rewrite the intro to describe the current ClinePass-first chain (plus grok-sub, see 1.16).

C2.8. GAP (portability rule broken): tools/book-to-kb/docs/book-kb-vs-book-to-skill.md:13, :23-26, :58 — uses `just book-add`, `just book-query`, `just book-toc`, `just book-skill-env` — AGENTS.md:221-223 requires the published package to name `book-kb …`, "never `just book-...`"; those recipes exist only in site-private's justfile, so an outside installer cannot run them. (The twin docs/book-kb-vs-book-to-skill.md and docs/docling-pre-bug/README.md also differ from their tools/book-to-kb/docs/ copies — `cmp`/`diff -q` → differ — two drifting copies of the same doc.) Fix: replace with `book-kb add/query/toc`, and keep one copy (link the other).

C2.9. GAP: docs/tooling-policy.md:13-14 — dead relative links `brew/fragments/agent-cli-tools.yml` and `generated/Merged-Brewfile` (resolve to `docs/brew/…`, `docs/generated/…`; targets exist at repo root) — fix: `../brew/fragments/agent-cli-tools.yml`, `../generated/Merged-Brewfile`. These were the only dead relative links found by the checker apart from 2.10.

C2.10. GAP (public repo): docs/clinepass-upstream-pr-reviews-2026-10-03.md:40-64 — nine links are absolute local paths (`/Users/…/src/litellm-clinepass-upstream/…:LINE`) — they resolve on this Mac (dir exists) but are dead on GitHub. Fix: use upstream GitHub permalinks.

C2.11. STALE: docs/reference/herdr-workstation.md:82 — `alt+g` → `grok` keybinding listed as a working agent launcher, and :161, :179 describe Grok as a live Herdr agent — grok vendor excluded 2026-10-06 (home-agents.md:275); `grok` is not on PATH in a login shell (`bash -lc 'command -v grok'` → nothing; `~/.grok/` config dir remains — unverified whether uninstalled). Fix: note the exclusion beside the binding. (bin/skill-everywhere.md:6, its TUI table and `~/.grok` instructions have the same issue; linking skills there is harmless, so low priority.)

C2.12. GAP: research/README.md:25-31 ("Packages" table) lists 4 packages; 3 tracked packages are missing: `research/acp-trial/`, `research/orca-vs-herdr/`, `research/src-navigation-view/`. Fix: add rows.

C2.13. STALE: docs/plans/agent-skill-library-strategy-v1.md ("Status: Implementation plan — **in progress**", evidence 2026-08-06) and docs/plans/ai-agent-reuse-first-implementation-plan-v1.md ("Implementation plan in progress", 2026-08-06) — untouched for two months, the first still references `~/src/ops-worktrees`; docs/plans/unattended-ai-coding-stack-plan-v1.md "not yet executed" (2026-08-17). Six other plans carry no status line at all (collie-caddy, kill-bluehost, open-webui-buzz, phase-d-funding, step0, step2). AGENTS.md:67 describes docs/plans/ as "this site's segmentation work", which no longer covers what is there. Fix: add a `Status:` line (done / abandoned / active, with date) to each, and widen the AGENTS.md row.

C2.14. STALE: docs/OPS-RELEASES.md:202-216 — bootstrap/migration commands `cd ~/src/ops-worktrees/main/site-djbclark` — the file's header (:3-12) marks the whole procedure optional, but these one-time-migration blocks read as live steps. Low priority: fold under a "historical (2026-07/08 migration)" heading.

### C3. research/** labelling (priority 3)

All seven packages are dated in their first lines and framed as research/verdicts (autonomy: dated 2026-08-16 plan; cfengine-community-review-coverage: "idea stage, not started"; apply-dev-toolchain: dated drop-in prompt; mac-tcc-boot-race: dated, "Status: diagnosed and worked around"; acp-trial 2026-10-03 verdict; orca-vs-herdr 2026-10-08 verdict; src-navigation-view 2026-10-06). None is presented as current operating policy. Only issue: the README index gap (2.12) and the release-flow wording in research/README.md (1.2).

## 5. GitHub issues versus the docs (E)

### E1. Issue citations in the six docs versus the issues' actual state

The README.md files of both repos cite no issues. Citations of the form
`#410` (`multi-site-topology.md#410-...` anchors), `firerpa/lamda#147`, and
`#17` in STATUS:25 (described as "private site PR #17") were checked as what they are.

E1. STALE (CRITICAL for agents): stayturgid/AGENTS.md:40-43. It lists "OpenObserve↔Vector auth fixed 2026-07-25, pending 24h clean-log verification before closing. Tracked in #44" under **Active blockers**. Evidence: #44 was closed as completed on 2026-07-28, and docs/options.md:323 says "following the fix for #44". Suggested fix: remove it from Active blockers.
E2. STALE: stayturgid/AGENTS.md:35-39. It says the forced `CLOSED_NO_SHELL` soak "still hasn't run". Evidence: docs/options.md:255-266 and STATUS.md:50 record that it ran on hd8 on 2026-08-01 and **failed**. The live blocker is #188 (open, "hd8: shizuku_server never starts after reboot"), and AGENTS.md does not cite it. Suggested fix: say the soak ran and failed, and cite #188 alongside #43.
E3. STALE (CRITICAL): stayturgid/AGENTS.md:48 and docs/STATUS.md:114 both keep "Decide the F1 consent-surface phasing question (#46)" in the operator queue. Evidence:

- #46 was closed as completed on 2026-07-29.
- The bridge shipped in PR #135 (commit 9bdbb62, `control/bin/firerpa_mcp.py`, `control/lib/firerpa_consent.py`). Lines 73-85 of the consent module implement the MCP-elicitation path that the open question was about.
- `launchctl list` shows `com.stayturgid.firerpa-mcp` loaded and running from `~/ops/stayturgid`.

Suggested fix: drop the item from both queues.
E4. STALE: stayturgid/docs/STATUS.md:53. The "F1 — FIRERPA MCP bridge" row says "Planned, not implemented … Tracked in #46, including the open consent-surface question". The evidence is the same as item E3. Suggested fix: mark the row shipped (2026-07-29, #135/#46) or move it out of the current workstreams table.
E5. STALE: stayturgid/docs/STATUS.md:52. The "OpenObserve <-> Vector auth" row says "Fixed 2026-07-25, pending 24h clean-log verification". Evidence: #44 closed as completed on 2026-07-28. Suggested fix: mark it verified and closed.
E6. STALE: stayturgid/docs/STATUS.md:56. The T5 row says "Evaluated, not started … Follow-ons tracked in #47, blocked on #44". Evidence: #47 closed on 2026-07-29 and #44 closed on 2026-07-28. docs/options.md:323-324 says "Implemented (2026-07-29) … #47 is now closed". Suggested fix: mark T5 done.
E7. STALE: stayturgid/docs/STATUS.md:51. The #61 row says "only the Shizuku-down STARTED E2E remains". Evidence: #61 was closed as completed on 2026-07-28. Suggested fix: record what closed it, or reopen or file the remaining E2E as its own issue.
E8. STALE: stayturgid/docs/STATUS.md:24-26 and :48. They say "Normal-deploy convergence is open in #72, paired with private site PR #17" and "awaiting paired PR merge". Evidence: stayturgid PR #72 was merged 2026-07-26T18:05Z, and site-djbclark PR #17 was merged 2026-07-26T18:06Z. site-djbclark is also no longer private (known item 7a). Suggested fix: mark it merged.
E9. STALE: stayturgid/docs/STATUS.md:48 says the normal fleet wrapper owns "headless Obtainium catalog import". Evidence: #119 ("Investigate dropping Obtainium") closed 2026-07-30, and PR #143 "Drop Obtainium fleet dependency" merged 2026-07-30. ansible/playbooks/fleet/termux-userland.yml:3 now says "NOT … Obtainium". #150's premise also says Obtainium automation was dropped. Suggested fix: remove the Obtainium clause.
E10. STALE (known item 7c, still present): stayturgid/docs/STATUS.md:111-121. The operator queue still holds resolved items: - Item 2 (#46, line 114) is closed; see item E3 above. - Item 4 (line 119), "Retest p7a only after firerpa/lamda#147 publishes a compatible runtime", is resolved by the same file's own fleet-health section (STATUS.md:85-89: v10.9 fixed it and p7a was verified on 2026-10-03). - Item 3 is struck through but kept.

    Suggested fix: delete items E2-4.

E11. INCONSISTENT: stayturgid/docs/STATUS.md:112 says "the seven ownership questions in the **private** #50 audit", but STATUS.md:55 says "The public issue records the inventory". #50 is in the public stayturgid repo (open, last updated 2026-08-08). stayturgid/AGENTS.md's condensed operator queue (lines 46-49) omits #50 entirely. Suggested fix: say "public", and add #50 to AGENTS.md's queue or note that it is intentionally STATUS-only.
E12. STALE: stayturgid/docs/STATUS.md:8-14, 27-30. "Last verified: 2026-07-26" and "coordinated `ops-v1.0.2` currently deployed … advance only through the release gate". Evidence: versioned releases were retired on 2026-08-23 (stayturgid/AGENTS.md:62-66; site-djbclark/AGENTS.md:104-111). Suggested fix: rewrite the Repo section for the plain-git `~/ops` workflow.
E13. STALE: stayturgid/AGENTS.md:57. The Quick start still begins `just ops-release-status`, although lines 62-66 of the same file say releases are optional and retired. Suggested fix: drop the line or label it optional.
E14. INCONSISTENT: stayturgid/docs/STATUS.md:117 has "rish fixed (#28)". In stayturgid, #28 is the PR "M1-Q: Phase D code-quality remediation" (closed 2026-07-19), so the bare `#28` points at the wrong thing. It presumably means a ShizukuTendCF issue (unverified). Suggested fix: write it as `frdminc/ShizukuTendCF#28` with a link.
E15. Verified consistent (no action): STATUS.md:49 #48 (closed 2026-07-24); STATUS.md:57 #16 open, #41 closed as a duplicate, #42 closed, PRs #136/#140 merged; options.md:250 #158 closed; options.md:304 #162 closed; site-djbclark/AGENTS.md:71 #36 (closed; "trial, not standing infra" matches #139's disposition); site-djbclark/AGENTS.md:72 #105 (closed, implemented).

### E2. Open issues that look already done, partly done, or duplicated (with evidence)

E16. DONE-BUT-OPEN: stayturgid#312 (conftest never adds the repo root). Evidence: tests/python/conftest.py:21-24 now appends `REPO` to `sys.path`, with a comment matching the issue. The fix is commit d470b0b (2026-10-06, "test: put the repo root on sys.path so one test file runs on its own"), which does not reference #312. Suggested fix: close it, referencing d470b0b.
E17. DONE-BUT-OPEN: stayturgid#310 (the nightly pkg upgrade has no error telemetry). Evidence: commit 5efe761 (2026-10-03), "Make the nightly Termux pkg upgrade's failures reach OpenObserve", has the body "Closes stayturgid#310". `stayturgid#310` is not a valid GitHub closing reference (it needs `#310` or `djbclark/stayturgid#310`), so it never auto-closed. Suggested fix: close it. Also add a line to the commit-message rules: closing keywords must use `#N` or `owner/repo#N`.
E18. DONE-BUT-OPEN: stayturgid#253 (firerpa-mcp runs on the tailnet from a worktree, outside the release contract). Evidence: - `launchctl list` shows `com.stayturgid.firerpa-mcp` loaded, and its process (started 2026-10-05) runs from `~/ops/stayturgid`, not a worktree. - ansible/roles/control_node/templates/firerpa-mcp.plist.j2:10 launches from `stayturgid_repo_root`, and agents_ensure.yml:93-100 manages the job. - The "release contract" premise was retired on 2026-08-23.

    Suggested fix: close it.

E19. MOSTLY-DONE: stayturgid#45 (K1 residuals: release APK, forced soak, official Shizuku packaging). Two of its three bullets are done: - The release APK ships: bootstrap_apks/defaults/main.yml:44-56 pins `org.stayturgid.agent` `agent-v0.9.15` `app-release.apk`, `resign: false`, removing `.debug`. - Shizuku is a properly signed release: lines 114-135 pin `frdminc/ShizukuTendCF` `13.7.0.r2851`, release-key signed, `resign: false`.

    The remaining bullet (the forced soak) is the same thing #43 and #188 track. Its "Obtainium catalog filter pattern" sub-point is stale (Obtainium was dropped, #119/#143). Suggested fix: close #45 and point it at #188.

E20. DUPLICATE CHAIN: stayturgid#43, #45 (soak bullet) and #188 all track the single remaining K1 acceptance item: hd8's Shizuku not starting after reboot, so `CLOSED_NO_SHELL` cannot be repaired. docs/options.md:263-266 says #43 "stays open for this Fire-OS boot-path failure", which is #188's exact subject. #188 is cited nowhere in AGENTS.md, STATUS.md or options.md (`rg '#188'` returns nothing). #43's title still leads with "AutoJs6 removal", which was verified done on 2026-07-31 (options.md:238-241). Suggested fix: make #188 the single open blocker, close #43 with a pointer to it (or retitle it), and cite #188 in AGENTS.md, STATUS.md:50 and options.md K1. Unverified: whether ShizukuTendCF r2851 ("restores its own ADB TCP port after a reboot through wireless debugging", STATUS.md:117) already fixes #188. hd8 is Tailscale-unreachable, so it cannot be retested now.
E21. PARTLY-DONE: stayturgid#151 (track untracked Termux companion APKs). `com.termux.tasker` (defaults/main.yml:81) and `com.termux.x11` (:92) are now pinned. styling, window and widget are still not pinned, and nor are the two third-party packages. Suggested fix: update the issue body to list only what remains.
E22. PARTLY-DONE: site-djbclark#83 (Grafana admin/admin; LiteLLM has no master key and is reachable beyond loopback): - The LiteLLM half is resolved: site-djbclark roles/litellm/defaults/main.yml:13 sets `litellm_bind: "127.0.0.1"`, and :236/:278 set a master key with the DB enabled. - The Grafana half is still true: stayturgid ansible/roles/serverapp_grafana/defaults/main.yml:29-30 is still `admin`/`admin`, with no override in site-djbclark (`rg serverapp_grafana_admin` finds nothing).

    Suggested fix: rescope it to Grafana only.

E23. DONE-BUT-OPEN (bot issues): site-djbclark#217 (collie 1.17.0) and #218 (collie 1.17.2). The live launchd job `herdr.collie` runs `~/.collie/versions/v1.17.2/bin/collie`, so both updates are applied or superseded. #219 (1.18.0) is the only real pending update. Every one of these bot issues says "changed from 1.16.2", so the watcher's baseline is not advancing after an update. Suggested fix: close #217 and #218, and check that the collie update workflow records the installed version.
E24. DUPLICATE/SUPERSEDED: site-djbclark#101, #99 and #37 are explicitly folded into #139 by #139's own body ("Continue, but reframe" / "Continue later, after the baseline"). #139's acceptance list says "Any implementation issue that duplicates this plan is closed or linked as a child task". Separately, #99's goal (a Git-backed canonical skill library reaching every agent) has largely been met by a different design: `site-djbclark/bin/skill-everywhere`, `site-djbclark/skills/`, and the djbclark-ade repo, as home-agents.md "Multi-agent toolkit" describes. All of #99's phase checkboxes are still unchecked. Suggested fix: the operator decides whether to close #99 or link it as a child of #139.
E25. OVERLAP: stayturgid#195 (Tasker Send Intent re-triggers the agent directly) and the docs/options.md:130-166 track "44 — Tasker kicker". Track 44 has partly landed a Tasker dispatcher (`recover.d/`) and says "The remaining legs of this item (agent and Shizuku kickers) become new `recover.d/` files". That is #195's goal, but neither the issue nor the track cites the other. Suggested fix: cross-link them, and record in #195 that the recovery now routes through the Tasker dispatcher, or close #195 into track 44.
E26. Watch issue: site-djbclark#205 is a machine-read dedupe record for the `monitor-thaw-next-access-request` workflow, and its own state line says upstream is `state=CLOSED`. It is open by design, but the watched request has ended. Suggested fix: the operator decides whether to retire the watch (low priority).
E27. Open draft PR: stayturgid#274 ("docs: stayturgid 2.0 architecture research"), draft, last updated 2026-08-13, tracker in another repo. No doc mentions it. Suggested fix: the operator decides whether to merge or close it (low priority).

### E3. Open issues whose premise is stale (retired components)

E28. STALE PREMISE: stayturgid#195 says "`com.termux.tasker` is being removed from `bootstrap_apks` (see #151)". It is now pinned in bootstrap_apks (defaults/main.yml:81-84), and options.md:132-135 says Tasker holds `RUN_COMMAND` on all three phones. Suggested fix: update or close; see item E25.
E29. STALE PREMISE: site-djbclark#92 ("Deploy Hindsight locally …") and #129 ("Hindsight retention pilot: current state", which says the service is "deployed and healthy on loopback"). Evidence: - Nothing listens on 127.0.0.1:8888 (curl gets no connection). - No Hindsight launchd job exists, and `~/.hindsight` is absent. - home-agents.md (`~/CLAUDE.md`) "Basic Memory — shared pool" names Basic Memory as the one shared memory server.

    Suggested fix: close both as superseded by Basic Memory, and update #139's references to them.

E30. (Covered above) #253's "release contract" premise was retired on 2026-08-23 (item E18). #224 cites `ops-v1.2.3`. Its restart gap may be partly addressed by 919ace1 (the shared `serverapp_launchd` role with `config_changed`), c6552a5 (restart on binary change) and aaa708d (restart the boot loop on env change). Whether a Caddy fragment change or a landing-code change now triggers a restart is **unverified**, so #224 is left as open-with-a-stale-example. #45's Obtainium sub-point is stale (item E19).
E31. No open issue still treats AutoJs6 as live. The only AutoJs6 mention is #43's title, which is done (item E20).

### E4. docs/options.md track IDs versus issues

E32. INCONSISTENT: docs/options.md:56 says "`F1` denotes two different items (open: MCP bridge; …)". The same file's track table (:74) lists only F3 as open for F, and :395 says "Closed: F1, F2, F4". The MCP bridge has shipped (#46 closed; #135). Suggested fix: change the collision note to "F1 (MCP bridge, shipped 2026-07-29)".
E33. STALE: docs/options.md:76 and :319. T5 is still in the "Open IDs" column and its heading says "Deferred", but the body (:323-324) says it was implemented on 2026-07-29 with #47 closed. Suggested fix: move T5 to the Shipped list (:291).
E34. INCONSISTENT (ID collision with issue numbers): Track D's open IDs are the bare numbers `44` and `45` (:72, :130, :168), and :126 says "Prefer health trail before 43–45". In the same file, the K1 section (:234-235, :323) uses `#44` and `#45` for the GitHub issues, which are different things: #44 is OpenObserve auth (closed) and #45 is K1 residuals (open). A reader cannot tell options item E44 (the Tasker kicker) from issue #44. Suggested fix: rename the numeric option IDs (for example D44 and D45, matching B63/B64), or state the convention in the "ID collisions" note at :52-58.
E35. INCONSISTENT: docs/options.md:371, "AutoJs6 debug APK (#553)". stayturgid has no issue #553 (the highest is #312). `553` is a legacy option ID (archive/options-closed-2026-07-23.md:157 "Closed (2026-07-08): … #553"), but the `#` makes it read as an issue link. Suggested fix: drop the `#` or write "option 553".
E36. GAP: the K1 track (docs/options.md:174-266) cites #43, #45 and #158, but not #188, which is the actual remaining failure (item E20). B64 "Full cold-device end-to-end" (:94-100) does not cite the open #290 (Termux first launch is an unmodelled cold-device precondition), which is directly on B64's path. Suggested fix: add both links.
E37. STALE: docs/options.md:304 says AutoJs6 "code deleted entirely (#162)". #162 is closed, but AutoJs6 constants and tests remain: `tests/python/test_enable_autojs6_a11y.py` (tests `a11y_services.AUTOJS6_A11Y`), `control/lib/a11y_services.py`, the `pm path org.autojs.autojs6` check at control/lib/fleet_health.py:318-324, and tests/lib.sh:82,106-109. Some of this is intentional (an absence check). Suggested fix: say "code retired; only absence checks and a11y constants remain", or remove the dead a11y test.
E38. No open GitHub issue backs the open options tracks H1, H3, H5/38, B63, B64, E54, F3, T2, T4 or T6 (title search: `rg -i 'semaphore|galaxy|mitm|frida|ansible-pull|shell-gpt|fireos'`). This fits the docs' own split (STATUS.md:36-39: options holds strategic/deferred tracks, issues hold discrete bugs), so it is not a defect. Noted only so the reader knows there is no issue/track mismatch beyond items E32-37.

### E5. Public-repo issue hygiene versus docs/rules/github-issues.md

E39. INCONSISTENT (policy versus practice): stayturgid docs/rules/github-issues.md:29-32 forbids "real Tailscale IPs, device serials, or hostnames" in issues. A body scan found tailnet-range addresses or `*.ts.net` hostnames in about ten stayturgid issues (open and closed) and five site-djbclark issues, which became public with that repository. The issue numbers are in the operator's private report, not here. Suggested fix: the operator decides whether to redact those bodies, and site-djbclark gets an equivalent issues rule.

## 6. site-private (summary only)

site-private is private, so its findings are summarized here by kind. The
operator has the full list. Most of its non-memory files are now symlinks into
site-djbclark, so several of its findings also apply there.

| Kind         | Count | Examples (generic)                                                                                                                                                                                                                                                                |
| ------------ | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CRITICAL     | 4     | `AGENTS.md` prescribes bare `pbcopy` against the global clipboard rule; `AGENTS.md` prescribes a `just ops-memory-sync` recipe that lives in another repo; a detail note contradicts the global rules on ACP support; a note sends handoffs to stayturgid's frozen sessions tree. |
| STALE        | 5     | A private-path list that no longer matches `.githooks/private-paths` (also copied in site-djbclark `AGENTS.md`); a "keep two copies byte-identical" rule for files that are now one symlink (also in site-djbclark `AGENTS.md`); Gemini listed as active.                         |
| GAP          | 8     | One dead link in the memory index, 20 notes missing from the index, 18 notes without a type, 13 dead wikilink targets, a dead path to a book source file.                                                                                                                         |
| INCONSISTENT | 4     | The symlink policy in both site-private's and stayturgid's `AGENTS.md` forbids the in-repo symlinks the 2026-10-06 private-only migration created; two detail notes disagree with the global rules on minor points.                                                               |

Cross-pointers between the three `AGENTS.md` files are complete: each points at
the other two.

## 7. Recommended order of work

1. **Fix the single-host targeting docs now** (priority 1). It is the only
   finding where following the docs changes the blast radius of a deploy. A
   documentation fix is small; a recipe fix that honours or rejects `--set`
   needs its own issue.
2. **Remove the release-regime instructions** from the always-on rule, STATUS.md,
   the AGENTS.md quick start and site-djbclark's relay and research docs in one
   pass, so no doc still requires `ops-v*` releases.
3. **Refresh the agent entry points**: the "Current state" block of stayturgid
   `AGENTS.md`, the STATUS.md header, workstream table and operator queue, and
   the K1 section of `options.md` (cite #188).
4. **Delete or mark historical** the F-Droid and Obtainium docs, fix the
   example consumers' tag pins, and update the Shizuku fork references.
5. **Settle where handoffs live** and say it once in each `AGENTS.md`.
6. **Bring the three `AGENTS.md` slices into line** with the global rules:
   Gemini, the `CLAUDE.md` symlink and the symlink policy, `clip`, tests through
   `bg`, and site-djbclark's public status.
7. **Operator decisions**: redact or keep the issue bodies that contain tailnet
   addresses; close or keep the done-but-open issues in section 5.
8. **Then the long tail**: STALE, GAP and INCONSISTENT items in sections 3 to 5
   in file order.

Ownership questions (which repository a document belongs in) are covered by
[ADR 007](../architecture/adr/007-core-site-ownership-boundary.md) and issue
[#50](https://github.com/djbclark/stayturgid/issues/50), not repeated here.
