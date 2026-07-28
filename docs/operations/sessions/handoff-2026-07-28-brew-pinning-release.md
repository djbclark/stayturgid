# Handoff 2026-07-28 — brew-pinning + unified update monitor shipped as ops-v1.0.13

## Executive summary

Agent 1 of the human-relayed orchestration chain (`~/ai-orchestration-plan-2026-07-28.md`).
Finished and shipped the in-flight `brew-pinning` feature (stayturgid #97 /
site-djbclark #29) as coordinated release **ops-v1.0.13**, start to finish, as
one continuous actor. Suite baseline was ops-v1.0.12.

**Bottom line:** release cut, tagged, published, and deployed cleanly to all
three `~/ops` checkouts and to **s24 + hd8** (both fully converged, `failed=0`
across every attempt). **p7a is left in an inconsistent Ansible-convergence
state** — explicit operator call, not a release blocker — see §3. Three new
issues filed (#103, #104, #105) from problems found while shipping; none were
show-stoppers, all are follow-up work.

---

## 1. Release / fleet state

- **Suite:** `stayturgid` / `site-djbclark` / `site-private` all at
  **ops-v1.0.13**, tagged, released (stable, non-draft, non-prerelease), and
  deployed — `just ops-release-status` clean. Release claim held during the
  cut/deploy, ended cleanly after deploy (`ops-release-claim-end --version
1.0.13` succeeded; claim was already past its 2h stale threshold by the time
  I closed it out, having held it the whole session — harmless, no other agent
  was waiting on it).
- **s24, hd8:** confirmed on ops-v1.0.13, `failed=0` across every fleet-deploy
  attempt tonight (several were needed — see §3).
- **p7a:** **not fully converged** — left inconsistent by explicit operator
  instruction after repeated same-task Ansible failures (see §3). Whatever
  state it's actually in should be checked fresh at the start of whichever
  session picks this back up; don't assume anything from this document is
  still true for that one host.
- **Mac control node (`~/ops`):** all three checkouts fast-forwarded to
  ops-v1.0.13. `just deploy-mac` and `just site-serverapps` both run clean.
  Homebrew Tier-1 pins confirmed: `brew list --pinned` → `caddy`, `grafana`,
  `vector`, `victoriametrics`, `hermes-agent` (+ pre-existing
  `cfengine@3.27.1`), stable across two `site-serverapps` runs.

---

## 2. What shipped

Consolidated 5-pass pre-merge review comment on stayturgid #97 was the
must-fix list (see PR for full text). All items addressed and pushed to
`feature/brew-pinning` (commit `90b1a2d`) before merge:

- **`control/bin/update_monitor.py`**
  - Fixed `IndexError` on empty `installed_versions` (`(item.get(...) or
[""])[0]` instead of a default that only covers key-absence).
  - Replaced the inverted "heartbeat only when `not metrics`" hack with an
    **unconditional** `software_update_monitor_last_success_timestamp <epoch>`
    gauge, emitted every run.
  - Made the homebrew `software_update_available` series **resettable**: now
    iterates the known Tier-1 set (`caddy grafana vector victoriametrics
hermes-agent`) and emits explicit `0`/`1` every run, instead of only ever
    pushing `1` for currently-outdated formulae (which left stale `1` samples
    after an upgrade).
  - Escaped Prometheus label values (backslash/quote/newline).
  - Added optional `GITHUB_TOKEN`/`GH_TOKEN` auth for the GitHub releases
    check (lifts the 60/hr unauthenticated limit).
- **`rules.yaml.j2`** (Grafana alert): widened the software-update alert's
  `relativeTimeRange.from` 600s → 86400s (24h — 2× the monitor's 12h push
  cadence) so one fresh sample latches across a full cycle instead of the
  alert seeing data for only ~10min per cycle.
- **`termux-pkg-nightly.plist.j2`**: reverted `RunAtLoad` `true`→`false` (a
  full `pkg update && pkg upgrade` must not fire on every boot/deploy/wake;
  `StartCalendarInterval` already catches up a missed run).
- **Brew-pin tasks** (caddy/grafana/vector/victoriametrics/hermes-agent): added
  `failed_when` so an absent/edge-case formula degrades gracefully instead of
  aborting the play.

Merged **#97** then **#29** (squash). Re-ran the non-regression check on
merged `site-djbclark` master: `git grep -n 'src/ops-worktrees' --
generated/` → **empty**, confirming the earlier worktree-path blocker fix
(`ee73519`) held.

---

## 3. Problems hit while shipping (chronological, so the reasoning is legible)

### p7a: repeated Ansible failure on `otelcol-contrib` liveness verify

`just deploy` failed on p7a's `Verify otelcol-contrib is running` task across
**five separate attempts** tonight, for what turned out to be **two distinct
causes**:

1. **Real memory pressure** (confirmed via `logcat`): `lowmemorykiller` was
   actively reaping unrelated background processes (Photos' metadata service,
   Keychain, Play Store background) on p7a at the exact time otelcol-contrib
   died — genuine device-level memory contention, not a config bug. Checked
   Android's own exemption state directly: `com.termux` was **already fully
   exempted** from Doze/App Standby (`dumpsys deviceidle whitelist`,
   `RUN_ANY_IN_BACKGROUND: allow`, standby bucket `5` = `EXEMPTED` — the best
   possible bucket). There was no battery-optimization/autostart setting left
   to toggle; the earlier idea of a "check your settings" notification
   wouldn't have caught this specific case. Operator closed some background
   apps manually, which visibly stopped the LMK churn.
2. **A second, less clear failure** afterward, with the process confirmed
   alive via `adb` both immediately before and immediately after the exact
   ansible-run timestamp of the failure — looks like a transient SSH/exec
   race rather than the process actually being dead. Not fully diagnosed.

**Root cause class**: Ansible is push-once (converge-and-exit), not a
continuous supervisor — there's nothing like systemd's `Restart=on-failure`
for it to delegate to on Termux/Android, so a process Android kills five
minutes after a deploy finishes stays dead until the next deploy happens to
run. Filed **stayturgid#103** with the full investigation and a two-tier fix
recommendation (Ansible self-heal now vs. CFEngine `processes:` promise for
real continuous supervision), plus operator-directed follow-up ideas (a
low-memory notification prompting the user to close apps; native-agent
supervision instead of reimplementing otelcol-contrib/sshd, which are
external maintained binaries and a poor fit for that).

**Resolution for tonight**: operator explicitly said it's fine to leave p7a
in an inconsistent state and stop chasing it. Not resolved. Whoever picks
this up next should treat p7a's actual current state as unknown and re-check
rather than trust anything above.

### Tooling gaps surfaced by the p7a decision

Filed **stayturgid#104**: no existing convention for marking a fleet device
"offline" (researched — Ansible has no built-in for this; proposed a single
`stayturgid_fleet_status` field in `site-djbclark/inventory/hosts.yml`,
enforced first in `control/bin/deploy_fleet.py`; explicitly **not** reusing
`site_litellm`'s `site_host_status` field, unrelated group/concern). Also
surfaced that device targeting is **already fragmented** across three
mechanisms today — `deploy_fleet.py` (Ansible inventory), `just cf-run` (SSH
config aliases, different names entirely), and `agent-rollout`
(`rollout.py`) — so a flag added to inventory alone wouldn't be "one central
place" without further work on the other two. Also proposed a ~30min
wall-clock timeout on fleet rollouts (no existing cap; historical runs take
~13-15min).

No code changes landed for #104 — by design, `hosts.yml`/`deploy_fleet.py`
are tracked code that can only reach `~/ops` via the full worktree → PR →
coordinated-release pipeline, which can't complete same-night. It's scoped
follow-up work for whoever's up next.

### `update-monitor` launchd agent never loaded (found during STEP 5 verify)

Confirmed by code trace, not device flakiness: `com.stayturgid.update-monitor`
was rendered to disk correctly but never appeared in `launchctl list`. Root
cause: `agents.yml:341` adds it to `_mac_launchd_reload_labels` (the
"reload if changed" list) but it was **never added** to
`_mac_launchd_ensure_services` in `agents_ensure.yml` (`_core_launchd_agents`
there lists only `access-monitor`/`fleet-health`/`fire-help`). Every task in
`launchd_ensure.yml` (reload-when-changed, load-when-unloaded,
restart-on-abnormal-exit, HTTP health probe) loops over
`mac_launchd_ensure_services` — so an agent absent from that master list is
never touched by any of this automation, making the `_mac_launchd_reload_labels`
entry dead code. This meant the **entire point of tonight's release** (the
software-update monitoring) would have silently never run. Loaded it
manually (`launchctl load`) to get tonight's monitoring actually working;
filed **stayturgid#105** for the real fix (add it to
`_mac_launchd_ensure_services`).

### Brew-pin tasks for grafana/vector/victoriametrics don't run via `just deploy`

Also found during STEP 5: `grafana`/`vector`/`victoriametrics` weren't
pinned even after several successful `just deploy` / `just deploy-mac`
runs. Traced it to: those are `serverapp_*` roles that **only** run via
`just site-serverapps` (`control/site_contract/serverapps.py`, a separate
"own/inject/off adapter activation" tool for Mac-hosted serverapps) — not
part of the Android fleet deploy (`just deploy`) or even `just deploy-mac
--tags mac`. `caddy`/`hermes-agent`/`cfengine` were already pinned from
some earlier point, which masked the gap until I ran `just site-serverapps`
explicitly and all 5 Tier-1 formulae picked up their pins. Not a bug — just
a real gap in my own operational knowledge of this repo, documented as a
note (not a fix request) on #105 for the next person who hits it. Consider
adding a mention of `just site-serverapps` to OPS-RELEASES.md or the release
checklist if serverapp-role changes ship again.

### OliveTin `config.yaml` still has worktree-baked `cd` lines (known #100, confirmed live)

STEP 5's own checklist anticipated this: `provider.yaml` (tracked under
`generated/`) is correctly on the portable `${OPS_ROOT:-...}` form (the
`ee73519` fix holds), but the **live** `~/.config/djbclark/olivetin/config.yaml`
still has `cd /Users/djbclark/src/ops-worktrees/brew-pinning/stayturgid` in
all 9 action blocks. This file is a single-writer **projection**
(`control/site_contract/olivetin_projection.py`) that only `site-sync`
refreshes — and running `site-sync` is exactly what this whole ship was told
not to do (that's #100, already scoped as Agent 2's next task, which
specifically targets fixing `provider.yaml`'s path and "the 9 OliveTin cd
lines"). So this isn't a new problem — it's confirmation that #100 is real
and still live.

**Verified current functional state directly** (ran the exact shell block
from `stayturgid_fleet_health`'s action rather than fighting OliveTin's API
wire format): it works right now, because the brew-pinning worktree still
exists. **This is why the brew-pinning worktree has NOT been removed** as
part of this handoff, despite the original brief saying to remove it — doing
so before #100 lands would break all 9 live OliveTin actions on the control
node with no easy recovery (the projection can't be refreshed without
`site-sync`, which re-bakes worktree paths elsewhere until #100 is fixed).
**Whoever runs Agent 2 (#100) should re-run `site-serverapps`/`site-sync`
once site-sync itself is fixed, confirm the 9 `cd` lines become `~/ops`-based,
and only then is it safe to remove `~/src/ops-worktrees/brew-pinning/`.**

---

## 4. STEP 5 on-fleet verification results

- ✅ `com.stayturgid.update-monitor` launchd agent: was unloaded (bug, #105),
  now manually loaded, firing correctly (`RunAtLoad`, exit 0).
- ✅ `software_update_available` flowing in VictoriaMetrics: confirmed via
  `query_range` — all 5 Tier-1 homebrew formulae present with explicit `0`
  values (resettable series working), plus the 2 GitHub-release checks
  (openobserve/olivetin, both showing real pending updates, `1`).
- ✅ `software_update_monitor_last_success_timestamp` gauge: present,
  unconditional, fresh epoch value.
- ✅ `brew list --pinned` includes the full Tier-1 set; stable across two
  `just site-serverapps` runs (no regression on re-run).
- ⚠️ `machine_name` labels: **not present** on `software_update_available`
  (expected — that metric is control-node-only, no per-host ambiguity to
  resolve, and the alert template never references `$labels.machine_name`
  for this rule) nor on `probe_success`/blackbox targets (pre-existing state,
  not a regression — the alert template's `{{ if $labels.machine_name }}`
  gracefully falls back to `$labels.instance`; no site inventory target
  currently populates the optional dict-format `labels:` the scrape template
  supports). Not a bug introduced tonight.
- ⚠️ `provider.yaml`: portable path confirmed correct. OliveTin `cd` lines:
  confirmed still worktree-based — see #100 discussion above. Verified
  functionally working today only because the worktree still exists.

---

## 5. Cleanup

- **`~/src/ops-worktrees/ops-release-1.0.13/`** — removed (release fully
  cut, tagged, published, deployed; no further use for this workspace).
- **`~/src/ops-worktrees/brew-pinning/`** — **intentionally NOT removed**,
  per §3's OliveTin finding. Remove only after #100 lands and
  `site-sync`/`site-serverapps` has been re-run to re-project
  `config.yaml`'s `cd` lines onto `~/ops`.

---

## 6. Issues filed this session

- **stayturgid#103** — Fleet deploy has no automated recovery when Termux
  processes (sshd, otelcol-contrib) die. Two-tier fix (Ansible self-heal +
  CFEngine `processes:` promise) plus operator-directed notification ideas
  (low-memory prompt, settings-check — the latter confirmed not applicable
  to p7a specifically since it's already fully exempted).
- **stayturgid#104** — Standard for marking a fleet device offline (no
  Ansible built-in; proposed `hosts.yml` field, explicitly not touching
  `site_litellm`'s scheme) + device-targeting fragmentation across
  `deploy_fleet.py`/`cf-run`/`rollout.py` + ~30min rollout timeout cap.
- **stayturgid#105** — `update-monitor` launchd agent rendered but never
  loaded (confirmed code bug: missing from `_mac_launchd_ensure_services`),
  plus a documentation note that `grafana`/`vector`/`victoriametrics`
  brew-pin tasks only run via `just site-serverapps`, not `just deploy`(-mac).

None of these blocked tonight's ship. All are real, scoped follow-up work.

---

## 7. Addendum — overnight follow-up (post-ship, same session)

With Agent 1's unit done, ops-v1.0.13 shipped, and the handoff above already
committed, the operator asked me to keep working on well-scoped, low-risk
follow-up rather than idle until 5am — implement but do **not** merge, leave
for morning review. Six PRs opened across the two repos (four in stayturgid,
two in site-djbclark), all `just check`-clean and CI-green,
none merged:

| PR                                                                                                                              | Repo          | What                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Notes                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| [#107](https://github.com/djbclark/stayturgid/pull/107)                                                                         | stayturgid    | Fixes #105 — adds `com.stayturgid.update-monitor` to `_core_launchd_agents` so it actually gets loaded/restarted like the other core agents.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Small, mechanical.                                                                                                               |
| [#108](https://github.com/djbclark/stayturgid/pull/108) + [site-djbclark#32](https://github.com/djbclark/site-djbclark/pull/32) | both          | Implements #104's proposed standard: `stayturgid_fleet_status` inventory field + `deploy_fleet.py` enforcement (explicit-host override never filtered; all-hosts-offline case explicitly refused rather than silently falling back to `--limit all`) + a 30min wall-clock timeout per `ansible-playbook` invocation (`STAYTURGID_DEPLOY_TIMEOUT_SECONDS` override). site-djbclark#32 applies the flag to mark **p7a offline**, pending #103. **These two must merge together** — the flag has no effect until #108 lands.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | 7 new unit tests.                                                                                                                |
| [#109](https://github.com/djbclark/stayturgid/pull/109)                                                                         | stayturgid    | Tier-1 (deploy-time) self-heal for #103: `otelcol.yml` verify retries once via the existing restart-handler path before hard-failing; `preflight.yml` does a best-effort `am start` + pause on a Termux that looks backgrounded before SSH bootstrap, matching the exact technique already used in `firerpa_heal.py`'s `restart_sshd()`, plus `ignore_errors` so a bootstrap module failure doesn't pre-empt the existing (clearer) assert. **Correction made mid-investigation and posted to the #103 thread**: withdrew an earlier suggestion to add a CFEngine `processes:` promise for otelcol — `start_adb.py`'s boot-loop daemon already has this (`_monitor_otelcol()`, `@heals: OTELCOL-RUNNING`); the real gap when this bit tonight was the boot-loop supervisor's own reliability, which is #86's scope, not something to duplicate here. **Recommend testing against a live device before merging** (p7a is currently offline per #108/#32) — not verified end-to-end tonight, by design (did not re-touch p7a after the operator said to stop chasing it). | 2 new structural tests (repo's existing convention for this file — read task text, assert names/ordering, no live Termux in CI). |
| [#110](https://github.com/djbclark/stayturgid/pull/110)                                                                         | stayturgid    | Closes out the last deferred "low" item from the original #97 review: `update_monitor.py`'s version comparison was raw string inequality, false-positiving on e.g. `"1.2"` vs `"1.2.0"`. Dependency-free numeric compare (no `packaging.version` — this script deliberately has zero dependencies).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | 6 new unit tests; this file had none before.                                                                                     |
| [site-djbclark#33](https://github.com/djbclark/site-djbclark/pull/33)                                                           | site-djbclark | Docs-only: adds an "Applying the release to the running stack" section to `OPS-RELEASES.md` — it only covers the checkout-version-advance mechanism, never mentions `just deploy`/`deploy-mac`/`site-serverapps`, which is exactly the gap that caused §4's grafana/vector/victoriametrics pin miss above.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | —                                                                                                                                |

**Deliberately not touched**: the rest of the open issue backlog (issues 41
through 66, 82, 86, 100, etc.) — those are already assigned to specific
agents later in the `~/ai-orchestration-plan-2026-07-28.md` roster (different models, by design,
to spread load). Picking them up here would risk duplicate/conflicting work
when those agents start fresh. Also did not re-engage with p7a beyond what's
described above (no further adb/device interaction after the operator's
"stop chasing it, leave it inconsistent" call) — #109's self-heal fix is
untested against the actual failure it targets for that reason.

**Per operator instruction, the Agent 2 handoff prompt (self-perpetuation
protocol) is deliberately not generated yet** — holding until after 5am.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
