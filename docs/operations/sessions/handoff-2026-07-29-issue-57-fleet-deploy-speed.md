# Handoff: #57 fleet deploy speed (measure-first, per the issue's own order)

**Session:** Agent 11, human-relayed orchestration chain (see
`~/ai-orchestration-plan-2026-07-28.md`). **Worktree:**
`~/src/ops-worktrees/fleet-deploy-speed-57/stayturgid` (branch
`feature/fleet-deploy-speed-57`).

## Context

Issue #57 filed a deploy-speed analysis with an explicit suggested order:
measure first with `ansible.posix.profile_tasks`, then only act on items the
data actually supports. Followed that order exactly. Two of the five items
were cheap/safe/unconditional and just got implemented; the other two
(`strategy: free`, `termux-pkg-upgrade.yml`'s `serial: 1`) got real timing
data collected via a live fleet deploy across s24/hd8/p7a, and the data
argued against changing them — documented below rather than changed
speculatively.

## What shipped

### 1. `ansible.posix.profile_tasks` wired in globally (`control/lib/ansible_context.py`)

Added to `resolved_env()` — the single choke point already shared by every
fleet entry point (`deploy_fleet.py`, `deploy_termux.py`,
`termux_pkg_nightly.py`, `ansible_exec.py`, `firerpa_health_monitor.py`,
`verify_drift.py`) — rather than to the repo's own `ansible/ansible.cfg` or
the site overlay's `ansible.cfg`. Real production deploys read
`~/ops/site-djbclark/ansible.cfg` (a separate repo, a deploy-only checkout
per this session's `~/CLAUDE.md` policy — no worktree for it exists in this
task, and none was needed), not this repo's own `ansible.cfg`. Putting it in
`resolved_env()` means real per-task timing is on for every fleet entry
point regardless of which site's `ansible.cfg` is selected, with no
cross-repo change. Merges with any caller-set `ANSIBLE_CALLBACKS_ENABLED`
instead of clobbering it (same `dict.fromkeys` pattern already used for
`ANSIBLE_ROLES_PATH`/`ANSIBLE_COLLECTIONS_PATH` in the same function).
`ansible.posix` is already a required collection dependency
(`ansible/requirements.yml`) — no new dependency.

### 2. `--devices-only` flag (`control/bin/deploy_fleet.py`)

Per the issue's `deploy_fleet.py:245` citation: `--limit <device>` never
matches `localhost`, so `deploy()` always launched a second
`ansible-playbook` process for `control_node/site.yml` even on a
single-device run. `--devices-only` skips that second launch. Exposed via
`just deploy devices_only=1 hosts=s24` too (env-var-style, matching the
existing `hosts=`/`scope=` convention in the top-level `justfile` +
`just/fleet.just`). `deploy-check` untouched — check mode already returns
before the Mac pass runs, so the flag would be a no-op there.

### 3. `ansible-galaxy collection install` caching (`control/bin/deploy_fleet.py`)

Hash `ansible/requirements.yml` (sha256), stamp it at
`<collections_path>/.requirements-hash` after a successful install, skip the
subprocess entirely when the stamp matches **and** `<collections_path>/ansible_collections/`
still exists (so a manually-wiped collections dir can't silently pass a
stale-but-matching stamp). `.ansible/collections/` is already gitignored, so
the stamp never gets committed. Measured on this machine: cold
(forced-reinstall) `install_collections()` call = 0.588s; warm-cache skip =
0.002s. Small in absolute terms but it's pure fixed tax paid on every single
deploy invocation, including tiny `--limit oneui-device --devices-only`
iterate-on-one-device runs where it was proportionally the biggest single
cost after the fix above.

### 4. Real bug found + fixed: `termux_pkg_nightly.py` was broken in production

While setting up to gather `serial: 1` timing data (item 5 below) via
`CHECK=1 python3 control/bin/termux_pkg_nightly.py`, hit:

```
[ERROR]: couldn't resolve module/action 'stayturgid.termux.termux_pkg'.
```

Checked `~/.config/stayturgid/logs/termux-pkg-nightly.log` (the real nightly
launchd job's log, not just this session's run) — **this has been failing
with `rc=4` on every single invocation since 2026-07-28 00:04**, i.e. the
nightly package-upgrade job has been silently no-op-ing in production for
about a day and a half. Root cause: `termux_pkg_nightly.py` built its own
subprocess `env` by hand (`os.environ.copy()` + manually setting
`ANSIBLE_CONFIG`/`STAYTURGID_ROOT`) instead of calling the shared
`resolved_env()` helper every other entry point uses — so it never got
`ANSIBLE_ROLES_PATH`/`ANSIBLE_COLLECTIONS_PATH`, and `ansible-playbook`
couldn't resolve the `stayturgid.termux` collection (which lives directly
under this repo checkout, discoverable only via that env var). Fixed by
switching to `resolved_env(REPO_ROOT)` (same one-line pattern
`deploy_termux.py` already uses), keeping the existing launchd-minimal-PATH
prefix logic layered on top. Re-ran the same dry-run afterward — clean,
`rc=0`, all three hosts converge correctly (see timing data below). Updated
`tests/python/test_termux_pkg_nightly.py`'s existing
`test_nightly_runner_uses_resolved_site_config` to mock `resolved_env`
directly (matching how `test_deploy_fleet.py` mocks `install_collections`/
`run_playbook` wholesale rather than letting real env-resolution logic run
during a unit test) instead of relying on the mocked `resolve_ansible_context`
to propagate through — the previous test happened to pass only because
nothing exercised the broken code path.

**This was orthogonal to #57 but blocked verifying item 5**, and is a small,
obviously-correct, well-tested fix, so I fixed it rather than working around
it.

## Live fleet deploy — real timing data (per issue's step 1)

All three devices (s24, hd8, p7a) confirmed reachable via both USB and
Tailscale at the start of this session; inventory shows all three as active
`stayturgid` group members (no `stayturgid_fleet_status: offline` flag —
p7a's earlier offline flag from Agent 1's session has since been resolved).

Ran a real, non-check `python3 control/bin/deploy_fleet.py` (full fleet,
default scope) with `profile_tasks` active. Device-play (site.yml minus the
Mac pass) total: **11m16s** (`0:11:16.494`), `failed=0` on all three hosts.
Top task costs from the `TASKS RECAP`:

```
Deploy Python runtime scripts to ~/.stayturgid/bin -- 81.90s
Verify the repair script runs ------ 43.04s
Run stayturgid-repair and parse STATUS ----- 42.24s
Deploy battery color assets -------- 33.91s
Install fleet SSH private keys on device -- 24.26s
Deploy shared libs to ~/.stayturgid/lib -- 23.92s
```

Then, to isolate per-host cost (profile_tasks alone only gives per-task
aggregate time, not a per-host breakdown), ran three separate real
`--devices-only <host>` passes back to back against the now-converged fleet
(near-idempotent, `changed≈0` runs — safe, not a repeat of the earlier
mutating deploy):

| Host | Real time (full device play, solo) |
|------|-------------------------------------|
| s24  | 318.58s (~5m19s) |
| p7a  | 421.64s (~7m02s) |
| hd8  | 492.38s (~8m12s) |

Confirms the issue's suspicion — hd8 (Fire OS) is the slowest device — but
also shows **p7a is meaningfully slower than s24 too** (32% slower), not
just hd8 alone. Sum of solo times = 1232.6s vs. the actual combined
3-host `linear` run at 676s — `linear` already runs each task across hosts
concurrently (it's not literally sequential per-host; the barrier is
per-task, not per-host), so the real ceiling `strategy: free` could
theoretically reclaim is bounded by `676s - 492s ≈ 184s` (~27%), since
hd8's own 492s of real work is a hard floor no ansible strategy can avoid.

## Why `strategy: free` was NOT implemented (item 4) — real correctness risk, not just readability

The issue's own hedge was right, but the actual reason turned out to be
stronger than "log readability": grepped every device-targeting play/role
for `run_once`/`hostvars[` and found **real cross-host data dependencies**
that rely on `linear`'s per-task synchronization barrier for correctness:

- `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ssh_keys.yml:149` —
  `hostvars[item].stayturgid_device_ssh_pubkey` when installing the fleet
  SSH mesh `authorized_keys` on every host, looped over
  `groups[stayturgid_ssh_mesh_group]`. Needs every other host's pubkey fact
  to already be set by the time this host reaches this task.
- `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml:100,112` —
  `run_once: true` + `delegate_to: localhost` CFEngine policy build; a later
  task (`Deploy CFEngine Build artifact to device`) on **every** host copies
  the artifact this task builds.
- `.../tasks/otelcol.yml:9,19,30,49` — four `run_once: true` +
  `delegate_to: localhost` health/cache-verification checks (Vector, OTLP,
  OpenObserve, otelcol-contrib archive cache) gating the per-host otelcol
  deploy tasks that follow.
- `.../tasks/fleet_adbkey.yml:11,21` — `run_once: true` fleet ADB key stat,
  read by every host afterward.

Under `linear`, all hosts synchronize at every task boundary, so any
`run_once` task's side effect (a built artifact, a verified cache, a stat
result) is guaranteed available to every host by the time it reaches later
tasks that depend on it, and every host's own facts are guaranteed visible
via `hostvars[]` to every other host in the same play. `strategy: free`
removes that barrier entirely — hosts race ahead independently. Ansible's
own docs flag `run_once` under `free` as unreliable (no guarantee it runs
exactly once before dependents need its result, and a fast host can reach a
`hostvars[other_host]`-dependent task before that other host has set the
fact). Concretely: under `free`, a fast s24 could reach the SSH mesh task
before hd8's own pubkey fact is set, silently skip installing hd8's key
(the `when: hostvars[item]... is defined` guard just evaluates false — no
error, no warning), and leave the SSH mesh quietly incomplete. Same failure
shape for the CFEngine artifact (file not found or stale) and the otelcol
health gates.

Given the timing data only supports a bounded ~27% ceiling anyway, and the
correctness risk is real (not hypothetical) and touches three independent
subsystems inside a role shared by every device-targeting play, this is not
a "worth the log-readability tradeoff" decision — it's a "don't do this
without a real refactor" decision. Left `strategy` unset (linear, the
default) everywhere. If this is revisited later, the CFEngine
build/otelcol-verification/ADB-key-stat `run_once` tasks would need to move
to a small `serial`-safe pre-play (or `hosts: localhost` play) ahead of the
device-targeting play, and the SSH mesh task would need the pubkey facts
gathered in an earlier, still-`linear` play before any `free` play runs —
nontrivial restructuring, not a one-line `strategy: free` addition.

## Why `termux-pkg-upgrade.yml`'s `serial: 1` was left unchanged (item 5)

`termux-pkg-upgrade.yml` is **not** part of the normal `site.yml`/`just
deploy` chain — it's a separate playbook run only via nightly launchd
(`com.stayturgid.termux-pkg-nightly`) or `just termux-pkg-upgrade`, so the
step-1 timing data above doesn't cover it at all. Ran a safe, non-mutating
`CHECK=1 python3 control/bin/termux_pkg_nightly.py` (all three hosts) after
fixing the bug above: total wall time **27.05s**, `serial: 1` (s24 → p7a →
hd8 sequentially, ~9-12s each including mirror-pin + package-index-check
round trips over SSH). Removing `serial: 1` would save roughly two of those
per-host slices (~18s, since 3 hosts would run concurrently instead of
sequentially) for this dry-run case — real, but modest in absolute terms
for a job nobody waits on interactively.

Left unchanged: this is an **unattended nightly job** (currently running at
04:15 local per the log), not something in `just deploy`'s interactive path,
so shaving ~18s off it has no user-facing latency benefit. The issue's own
hedge — "possibly intentional (bandwidth/safety)" — is the more important
consideration: `serial: 1` means if a mirror hiccup or partial
`apt-get full-upgrade` corrupts package state, it happens to one device at a
time with the other two still in a known-good state, rather than all three
simultaneously. Given the modest speed upside and the real, if unquantified,
blast-radius downside for an unattended fleet-wide package mutation, kept
the current default. The var (`stayturgid_termux_pkg_upgrade_serial`) is
already overridable per-host/group if this default is ever reconsidered.

## Verification

```
cd ~/src/ops-worktrees/fleet-deploy-speed-57/stayturgid
just worktree-setup   # fresh worktree — .venv-test, node_modules, .ansible/collections
just check            # clean
just test             # clean (all pytest/ansible-test/shell-unit suites)
```

Live (real devices, not a dry run):
```
python3 control/bin/deploy_fleet.py                    # full fleet, confirmed failed=0 on s24/hd8/p7a
python3 control/bin/deploy_fleet.py --devices-only s24  # confirmed no second control_node/site.yml launch
CHECK=1 python3 control/bin/termux_pkg_nightly.py       # confirmed rc=0 after the bugfix, was rc=4 before
```

## Not done / left open

- `strategy: free` and `termux-pkg-upgrade.yml`'s `serial: 1` — evaluated
  with real data, deliberately not changed (see above). Any future attempt
  at `free` needs the `run_once`/`hostvars[]` restructuring described above
  first, not just flipping the setting.
- No further profiling/tuning attempted beyond what's above — the two
  cheap/safe items (`--devices-only`, collection-install caching) are the
  real, unconditional wins from this issue; the other two needed the
  correctness/blast-radius analysis this handoff documents instead of a
  code change.
