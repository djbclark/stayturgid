# Handoff: overnight orchestration session, 2026-07-31 → 2026-08-01

Written mid-session as insurance against context loss (operator noticed heavy
conversation compaction and asked whether a fresh instance should take over;
this file is the practical answer — anyone/anything can pick up cold from
here). Not a sign anything is currently broken.

## Standing authorizations (operator gave these explicitly, still active)

- Full latitude as primary orchestrator for this session — direct work or
  delegation, best judgment, only hard constraint is never running out of
  tokens in an active window. Full text: `feedback_primary_orchestrator_role`
  memory (`~/.claude/projects/-Users-djbclark/memory/`).
- Full fleet deploy tonight to bring p7a current: **yes, go ahead**.
- Review + use judgment on the 4 pre-existing Shizuku PRs (#2-5): **yes,
  review and use your judgment** — merge what's solid, fix what's fixable,
  leave open + explain what's genuinely risky/unclear.
- Device reboot policy overnight: **reboots are fine, just let stuck devices
  wait** (not the no-reboot-at-all option).
- "During development you are allowed to ignore [the OPS-RELEASES.md
  operator-confirmation-before-merge] rule, as long as it's done at the tail
  loose ends step" — i.e. skip pausing for confirmation on the release-cut
  PRs described below.
- Operator is asleep; asked to front-load likely questions (done, answered
  above) and keep working autonomously on anything not requiring their input.

## In-flight: ops-v1.2.0 coordinated release cut

Deploy checkouts (`~/ops/{stayturgid,site-djbclark,site-private}`) were
discovered stuck on `ops-v1.1.0` — merging PRs to `master` does NOT
auto-deploy; only a coordinated `ops-vX.Y.Z` release (see
`~/ops/site-djbclark/docs/OPS-RELEASES.md`) does. A claim was taken
(`just ops-release-claim-begin 1.2.0 cut`, holder=djbclark pid=59026 host=mac,
started 2026-08-01T02:53:28Z) — **if this file is being read by a fresh
session/instance, first check `just ops-release-claim-status` from
`~/ops/site-djbclark` to see if the claim is still held or has gone stale.**

State as of this writing:
- 3 task worktrees created, each on branch `release-1.2.0`:
  `~/src/ops-worktrees/release-1.2.0-{stayturgid,site-djbclark,site-private}`.
- Each repo's `ops-release.json` bumped `1.1.0` → `1.2.0`, committed, pushed.
- 3 PRs open: `djbclark/stayturgid#180`, `djbclark/site-djbclark#55`,
  `djbclark/site-private#20` (all "chore: bump ops-release.json to 1.2.0").
- A persistent Monitor was polling all three PRs' CI checks (stayturgid was
  first waiting on CI + CodeRabbit).

**Remaining steps (from `docs/OPS-RELEASES.md`, "Cutting a release" section)
once those 3 PRs are green:**
```
gh pr merge 180 --repo djbclark/stayturgid --squash --delete-branch
gh pr merge 55  --repo djbclark/site-djbclark --squash --delete-branch
gh pr merge 20  --repo djbclark/site-private --squash --delete-branch
# in each repo:
git tag -a ops-v1.2.0 -m "djbclark ops 1.2.0" && git push origin ops-v1.2.0
gh release create ops-v1.2.0 --verify-tag --title "djbclark ops 1.2.0" --repo djbclark/<repo>
# from ~/ops/site-djbclark:
just ops-release-check 1.2.0
just ops-release-deploy 1.2.0     # fast-forward only, refuses non-FF
just ops-release-status
just ops-release-claim-end --version 1.2.0
```
**After that**, the release is only in the deploy checkouts — still need to
apply it to the running stack:
- `just deploy` — Android fleet, fleet-wide including p7a (pre-authorized).
- `just deploy-mac` — Mac control node/launchd (needed: central-logging PR
  #178 touched Mac-side `control/bin/fleet_health_monitor.py`).
- Check whether `just site-serverapps` is needed — central-logging was
  designed for "zero Vector config changes" so probably not, but confirm
  nothing else in tonight's merges needs it before skipping.

## Tonight's merged work (all already on `origin/master`, just not deployed yet)

dialog-dismiss-automation race (PR #173), HeartbeatWriter MediaStore
exhaustion cleanup (#34, no code fix needed), Shizuku `BootRetryWorker`
permanent-give-up bug — root cause of issue #43's whole soak (Shizuku PR #7),
native-agent logcat buffer resize + resource leak (PR #174, v0.9.1→v0.9.2),
stale `automation_mode=autojs6` (site-djbclark PR #53), Shizuku `.gitignore`
gap (Shizuku PR #8), Termux ResultReturner-toast root cause (stayturgid PR
#176), Shizuku Build-App workflow re-tag idempotency (Shizuku PR #9), guided
setup screen + 2 real bugs found in review (stayturgid PR #177, v0.9.3→0.9.4),
central-logging pipeline for device failure signals (stayturgid PR #178),
hd8's Tailscale false-negative repair failures (stayturgid PR #179).

## Parallel work started, may still be running

A background `general-purpose` agent was dispatched to review + merge the 4
pre-existing Shizuku PRs (#2 Fire OS notification/native lib fix, #3
HANDOFF.md/OPTIONS.md docs, #4 signing-cert trust allowlist, #5 CI signing
secrets — #4/#5 look related to open issue `stayturgid#158` "Patch
djbclark/Shizuku fork to permanently grant org.stayturgid.agent"). Check
`gh pr list --repo djbclark/Shizuku --state all` for the outcome if this
wasn't yet reported back.

## CodeRabbit feeder (self-pacing background automation)

`~/.config/coderabbit-feeder/` — `feeder.py` runs via launchd
(`com.djbclark.coderabbit-feeder.plist`, `StartInterval=300`) against a
dedicated worktree set at
`~/src/ops-worktrees/coderabbit-feeder-workspace/{stayturgid,site-djbclark,site-private,Shizuku}`
(NOT the shared `main/*` checkouts — that was a bug, fixed mid-session).
Queue (`queue.jsonl`) has 24 batches across the 4 repos; feeder auto-paces
against CodeRabbit's rolling rate limit using the exact "Next review
available in: N minutes" text from CodeRabbit's own PR comments. Trial Pro+
expires Aug 3 — goal is to keep it saturated until then. No action needed
unless the queue empties (it's built to text via `hermes send` if so) or
launchd stops firing (`launchctl list | grep coderabbit-feeder` to check).

## Not yet started

- "Look closely at the various .md files we use" (operator's explicit ask,
  mid-turn, not yet acted on) — likely means README.md/AGENTS.md/docs/*.md
  across stayturgid/site-djbclark/site-private/Shizuku for staleness given
  tonight's volume of changes, and specifically the HANDOFF.md/OPTIONS.md
  that Shizuku PR #3 adds.
- Broader open-issue backlog (stayturgid): #166, #158, #155, #152, #151,
  #150, #137, #114, #86, #63, #62, #50, #45, #43 (should be closable once
  ops-v1.2.0 actually deploys and hd8 is observed stable), #41, #18, #16.

## Token/account pacing

Two `cswap`-managed accounts (`djbclark@mit.edu`, `djbclark@gmail.com`).
Check `cswap status` / `aiuse --json` (the latter can take ~1 min, that's
normal) before deciding how aggressive to be — become more aggressive if
10%+ behind pace on either account's current window, per the standing
orchestrator-role memory.
