# Handoff: ~/ops routine-maintenance status (2026-08-01)

**Why this exists:** the operator is about to start a larger reorg — a new,
improved multi-agent orchestration system — and won't be returning to this
specific thread of routine `~/ops` maintenance work for a while. This
document captures exactly where things stand so nothing gets silently
dropped or re-discovered from scratch. Tracked by issue #210.

**Scope:** this covers the fleet (stayturgid/site-djbclark/site-private)
deploy state, currently open PRs across those three repos, and one explicit
pending decision. It does NOT cover the separate `djbclark/aiuse` audit —
that has its own fully self-contained handoff at
`~/src/aiuse/docs/quota-algorithm-audit-2026-08-01.md` (issue #23 there),
unrelated to the new orchestration reorg.

## Coordinated release state

`ops-v1.2.1` was cut and deployed earlier the same day — all three
`~/ops/{stayturgid,site-djbclark,site-private}` deploy checkouts are on it,
confirmed via `just ops-release-status`. Nothing pending on the release
process itself.

## Fleet state (as of this writing)

All three devices reachable and current:

- **s24** — clean, current, tested live (not just dry-run) against the
  `gnu-rsync-control-node` branch described below.
- **p7a** — clean, current (FIRERPA on this device remains
  `firerpa_runtime_status: pending-incompatible-runtime` — its v10 server
  binary predates Android 17/API 37 support; see the `djbclark/aiuse`-adjacent
  research below, and `firerpa/lamda` upstream issues #145/#147 for the
  vendor-side status. Not an urgent fix — the device just runs without
  FIRERPA's failsafe layer for now).
- **hd8** — clean, current — **but only just.** Its wireless ADB
  (`adb_wifi_enabled`) is still down (known Fire OS 8 limitation — clears at
  boot, no safe non-root remote fix exists, see
  `memory/project_fireos8_adb_wireless_debugging.md` if that's ever synced
  into this repo, or ask the operator). It's connected via **USB**
  (`GN43T503430603PS`) and via **Tailscale SSH on port 8022** — the
  `termux_userland` role's file/config sync uses SSH, not ADB, so the real
  deploy went through cleanly over that path despite ADB wireless being
  down. ADB-dependent sub-tasks (APK version checks, permission grants)
  would still need wireless ADB restored — either a physical Wireless
  Debugging toggle in Developer Options, or another USB session.
  **If hd8 goes offline again and only USB is available**, target it
  directly: `hosts=hd8 just deploy` still works over Tailscale SSH; ADB
  itself isn't required for the bulk of what this role does.

## Open PRs across the three repos

### Ready to merge, no action needed
- **`djbclark/site-djbclark` #59** — `feat: declare DISCORD_* secrets in
  secretspec manifest`. Zero CodeRabbit findings, CI green. Just merge
  whenever convenient.

### Fixed, but CodeRabbit hasn't actually re-reviewed the fix yet — read this before merging
- **`djbclark/stayturgid` #208** + **`djbclark/site-djbclark` #62** — a
  paired PR making the Mac control node use Homebrew's GNU rsync (3.4.4)
  instead of macOS's ancient system rsync (2.6.9) for `termux_userland`'s
  file-sync tasks. Real story, worth reading in full before merging:

  1. First attempt set `_local_rsync_path` as an `ansible.posix.synchronize`
     **module parameter**. CodeRabbit correctly found (by fetching the
     actual `ansible.posix` 2.2.2 source) that this parameter is silently
     overwritten by the action plugin, which always rebuilds it from
     `task_vars.get('ansible_rsync_path')` (defaulting to bare `'rsync'`).
     My own earlier "verified against a live device" claim had been
     accidentally passing because `/opt/homebrew/bin/rsync` happened to be
     first in `PATH` on this Mac — not because the parameter was respected.
  2. Second attempt set `ansible_rsync_path` via a task-level `vars:` block.
     This failed differently and more subtly: the action plugin reads
     `task_vars.get('ansible_rsync_path')` **with no templating call**
     (unlike `ansible_user`/`ansible_password` a few lines below it in the
     same plugin, which explicitly call `self._templar.template(...)`). A
     plain `key: "{{ expr }}"` value — task-level `vars:` or group_vars,
     both tested — stays an **unevaluated template reference** in Ansible's
     internal representation until something explicitly requests templated
     evaluation, which this code path never does. Real device run failed
     with a literal `Failed to find required executable "{{
     stayturgid_local_rsync_path }}"` error.
  3. **Working fix**: `ansible.builtin.set_fact: ansible_rsync_path: "{{
     stayturgid_local_rsync_path }}"` as the very first task in
     `termux_userland`'s `tasks/main.yml`. `set_fact` evaluates eagerly and
     stores a concrete resolved string (no residual Jinja markup) as a
     hostvar, which the action plugin's raw `task_vars.get()` then reads
     correctly. **Verified for real this time**: `ANSIBLE_VERBOSITY=3`
     against a live device (s24) shows the actual invoked binary is
     `/opt/homebrew/opt/rsync/bin/rsync` (the configured Homebrew path) —
     not `/opt/homebrew/bin/rsync` (what the old PATH-fallback bug would
     also have produced) — proof this is the mechanism working, not
     environmental coincidence.
  4. Also fixed per CodeRabbit on the site-djbclark side: `brew --prefix
     rsync` returns a path even for a formula that **isn't installed**
     (just where it would go); switched to `brew --prefix --installed
     rsync`, which fails loudly instead. Verified both the success and
     failure cases directly in a shell.

  **What's NOT done**: `@coderabbitai review` was re-triggered on both PRs
  after pushing the real fixes above, and both show "Review completed" —
  but checking `gh api repos/<repo>/pulls/<n>/reviews`, the recorded review
  is still tied to the **pre-fix commit** on both PRs (`7dd024a` for #208,
  `a79b838` for #62), not the actual fix commits (`385d250`, `ebd907e`).
  This is the same "`@coderabbitai review` doesn't re-review an
  already-reviewed PR" quirk documented in
  `memory/reference_coderabbit_manual_review_trigger.md` — only
  `@coderabbitai full review` forces a fresh pass, and that command risks
  hitting the shared rate limit (see
  `memory/reference_coderabbit_rate_limit_tracking.md`). **Before merging
  these two, either run `@coderabbitai full review` on both and read the
  result, or accept the manual verification above as sufficient** (it's
  solid — both fixes were proven against real device runs, not just
  reasoned about) and merge on that basis. Either is a reasonable call; it
  wasn't made in this session because the operator asked to wrap up and
  hand off rather than keep iterating.

- Both branches are named `gnu-rsync-control-node` (same branch name,
  separate repos — normal for this kind of companion-PR pattern in this
  project). Full task worktrees still exist at
  `~/src/ops-worktrees/gnu-rsync-control-node/{stayturgid,site-djbclark}` —
  not yet cleaned up (intentionally, in case more fixup commits are needed
  before merge).

### Needs an explicit decision — not started
- **`djbclark/stayturgid` #206** — `fix: gateway uses git-install venv
  (Python 3.14 breakage)`. **This PR is not this session's own work** — it
  came from an unrelated Hermes-gateway-repair conversation that happened
  to run in a herdr pane earlier the same day. CodeRabbit found a real gap:
  `stayturgid_hermes_bin` (in `ansible/roles/control_node/defaults/main.yml`)
  documents a Homebrew-install override mode, but the role's actual
  dependency-install task only ever targets the git/uv virtual environment
  — the Homebrew path is never actually installed if selected, and
  `failed_when: false` on the install task masks the resulting failure
  silently. CodeRabbit's own suggested fix is to remove the unsupported
  Homebrew override entirely (3 affected line ranges — see the PR's review
  comment for exact locations) rather than try to actually implement
  Homebrew support. **Decision needed**: fix this now (it's a
  well-scoped, CodeRabbit-guided cleanup — probably a 30-60 minute job for
  whoever picks it up), or leave it for whoever actually owns/continues the
  Hermes gateway work, since this session didn't originate it and doesn't
  have full context on why `stayturgid_hermes_bin` exists as a
  configurable override in the first place.

### Self-managing, no action needed
- **`djbclark/stayturgid` #203** — `chore: coderabbit audit —
  stayturgid-batch-0001`. Part of the `~/.config/coderabbit-feeder`
  pipeline's own review-queue-draining mechanism — its own description says
  it'll close itself once CodeRabbit's review lands (currently rate-limited,
  same shared-budget issue as above). Nothing to do here; it's designed to
  resolve on its own.

## Loose ends explicitly checked and ruled out

- **"Another agent doing a deploy"** — the operator flagged a possible
  concurrent deploy in the `pi` herdr pane as a live test of this project's
  defense-in-depth against simultaneous deploys. Checked: that pane's most
  recent completed activity was unrelated Herdr-keymap-documentation work
  (already merged as `site-djbclark` #61), not a deploy. No evidence of an
  actual concurrent deploy was found anywhere this session looked. If this
  comes up again, the deploy tooling's own defenses are documented in
  `docs/OPS-RELEASES.md` (exclusive flock + version claim for *release*
  operations specifically — ordinary `just deploy` fleet pushes aren't
  release-flock-gated, so if two agents really did run `just deploy`
  concurrently against the same device, Ansible/SSH-level connection
  handling is the only real protection, not an explicit lock. Worth
  keeping in mind for the orchestration reorg this hands off into.)
- **hd8 recovery options** — FIRERPA and CFEngine were both checked as
  possible remote-recovery channels for hd8's dead wireless ADB and ruled
  out: FIRERPA isn't currently running on the device at all (port 65000
  refused), and CFEngine's `cf-serverd` runs inside Termux's own
  unprivileged app sandbox (confirmed via a live SSH session — same
  `INTERACT_ACROSS_USERS` permission wall as plain Termux shell), so it
  can't touch `adb_wifi_enabled` either. No remote path exists; physical
  access (USB or the Settings toggle) is genuinely required.

## Suggested next steps whenever this thread resumes

1. Decide and act on #206 (see above).
2. Either run `@coderabbitai full review` on #208/#62 and read the result,
   or merge on the manual verification already done.
3. Merge #59 (trivial, no blockers).
4. Clean up the two `gnu-rsync-control-node` task worktrees once #208/#62
   are merged (`git worktree remove` + delete the remote branches — they're
   currently left in place deliberately).
5. If hd8's wireless ADB is still down when this resumes, physical
   USB/Settings-toggle access is still the only fix — nothing changed
   about that since it was last investigated.
