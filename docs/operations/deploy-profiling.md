# Deploy pipeline profile and measurement plan (#166)

Written 2026-10-09 (ClaudeHelm, no device access) from the playbooks alone;
the numbers that need a phone are marked **measure**. Tracks
[#166](https://github.com/djbclark/stayturgid/issues/166): a no-op
`just deploy` of one host took about 5:22 wall-clock on 2026-07-31.

## 1. Where a one-host deploy spends its tasks

`ansible-playbook ansible/playbooks/site.yml --list-tasks --limit oneui-device`
(generic example inventory, this branch). Loops count as one task here but
cost one round trip per item; `include_tasks` files are dynamic and are not
listed, so they are added by hand.

| Play                                                         | Listed tasks | Included files                                                 | Runs against |
| ------------------------------------------------------------ | -----------: | -------------------------------------------------------------- | ------------ |
| 1–3 bootstrap-apks ensure / verify / Shizuku                 |           18 | install_apk.yml ×N apps, check_apk.yml                         | adb (Mac)    |
| 4–5 SSH preflight                                            |            7 | –                                                              | ssh + adb    |
| 7 fleet deploy: termux_userland                              |           53 | otelcol 20, ssh_keys 26, ca 10, control_et 8, adbkey 7, rish 4 | ssh (Termux) |
| 7 fleet deploy: shizuku_config                               |           18 | –                                                              | ssh + adb    |
| 7 fleet deploy: tailscale, play, ensure_apps, app_privileges |           12 | –                                                              | adb (Mac)    |
| 8 peer-help ForceCommand                                     |            2 | –                                                              | ssh          |
| 9–11 firerpa, post-ui, validate                              |           14 | –                                                              | ssh + adb    |
| 12–14 control_node (Mac, `always`)                           |           61 | hermes, firerpa_venv, launchd_ensure                           | localhost    |

Per-item loops on the Termux side on top of that: the three shell-profile
`lineinfile` tasks (3 files each, +6), `Ensure stayturgid home directory
tree` (+4), CFEngine artifact copy (+1), fleet private keys copy + stat
(2 × number of keys), mesh `known_hosts` (one per fleet host), retired boot
scripts (one per entry). **About 210–240 Termux round trips per host on a
no-op run**, plus roughly 30 adb invocations from the Mac.

The fleet plays all set `gather_facts: false` and the inventory pins
`ansible_python_interpreter`, so there is no fact gathering and no
interpreter discovery on the phones. The time is the round trips.

### The floor per round trip is the whole story

With pipelining on, every task still costs one SSH exec on the phone that
starts Termux Python, unpacks the AnsiballZ payload, imports
`module_utils.basic` and runs the module. On a phone that is 1–1.5 s even
for a no-op `stat`; the 2026-07-31 recap shows it directly: `Deploy CFEngine
Build artifact to device` (two small `copy` items, nothing changed) took
7.2 s, `Deploy boot scripts` (then a per-file loop) 6 s. 220 round trips ×
1.3 s ≈ 4:45, which is the observed 5:22 minus the Mac pass. So the lever is
the number of round trips, not what any one task does, and the first thing
to measure is that floor (§3a).

## 2. Changes on this branch, with estimates

| Change                                                                                                                                                                                   | Commit scope                                           | Estimated saving                                                                                                                         | Risk                                                           |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `scripts` deploy scope: `hosts=s24 just deploy-scripts` runs only the 20 tagged termux_userland tasks (bin/lib/boot/tasker syncs, retired cleanup, repair check) plus the `always` plays | termux_userland tags, deploy_fleet.py, just/fleet.just | a code-only push: ~5 min → **~40–60 s** (24 device round trips + rsync); no change to a full deploy                                      | none for full deploys: tags only add selection                 |
| `gather_subset: [min]` on the three control-node plays                                                                                                                                   | ansible/playbooks/control_node/*.yml                   | 2–4 s per gather on a loaded Mac (hardware/network/virtual collectors skipped); facts used are os_family, architecture, ansible_env.HOME | none                                                           |
| `ANSIBLE_GATHERING=smart` from `resolved_env()`                                                                                                                                          | control/lib/ansible_context.py                         | the second and third localhost plays reuse the first play's facts: 2 gathers saved, **~3–8 s** per deploy with the subset above          | none: device plays do not gather; an explicit env setting wins |

Already on master or on `claudehelm/stayturgid` (both are in this branch):
rsync for the bulk syncs (#166 item 1), `--scope bootstrap-apks` (item 2),
one round trip for retired-file cleanup and one `authorized_key` call per key
set (3873f53).

## 3. Measurement plan (operator, needs a phone)

Everything below reads the recap `ansible.posix.profile_tasks` already
prints (#57). Set `PROFILE_TASKS_TASK_OUTPUT_LIMIT=all` to list every task
instead of the top 20, and `PROFILE_TASKS_SORT_ORDER=none` to keep play
order. Keep each log; never judge a run through a pipe (`cmd > log 2>&1;
echo rc=$?`).

### a. The round-trip floor (5 min, do first)

```bash
cd ~/ops/stayturgid
export ANSIBLE_CONFIG=~/ops/site-djbclark/ansible.cfg
time ansible localhost -c local -m ansible.builtin.command -a true >/dev/null   # Ansible's own startup
time (for i in 1 2 3 4 5 6 7 8 9 10; do ansible s24 -m ansible.builtin.command -a true >/dev/null; done)
```

(per-call wall − the localhost figure) is the floor. With 220 round trips,
floor × 220 is the predicted no-op deploy time; if it lands within ~20 % of
the measured full deploy, round-trip count is confirmed as the lever and
§4 is the roadmap. If it does not, a few tasks are slow on their own and
`PROFILE_TASKS_TASK_OUTPUT_LIMIT=all` on a full run says which.

### b. Baseline and after, full no-op deploy

A `deploy-check` run skips the synchronize tasks (they cannot dry-run), so
use a real deploy of an already-converged host; it is idempotent. Run each
twice and keep the second (warm SSH ControlMaster, warm caches).

```bash
cd ~/ops/stayturgid
git switch master && git pull --ff-only
PROFILE_TASKS_TASK_OUTPUT_LIMIT=all hosts=s24 just deploy > ~/deploy-s24-before.log 2>&1; echo rc=$?
PROFILE_TASKS_TASK_OUTPUT_LIMIT=all hosts=s24 just deploy > ~/deploy-s24-before2.log 2>&1; echo rc=$?
git switch claudehelm/st-deploy   # or master after merge
PROFILE_TASKS_TASK_OUTPUT_LIMIT=all hosts=s24 just deploy > ~/deploy-s24-after.log 2>&1; echo rc=$?
PROFILE_TASKS_TASK_OUTPUT_LIMIT=all hosts=s24 just deploy > ~/deploy-s24-after2.log 2>&1; echo rc=$?
grep -E 'Playbook run took|^(stayturgid|control_node)' ~/deploy-s24-before2.log | head -40
```

Compare `Playbook run took` for the device pass and the Mac pass separately
(two `ansible-playbook` invocations, two recaps). Expected on this branch:
device pass unchanged, Mac pass 5–12 s shorter.

### c. The scripts scope

```bash
time hosts=s24 just deploy-scripts > ~/deploy-scripts-s24.log 2>&1; echo rc=$?
```

Expected: under a minute. Then edit one byte in `device/termux/py/` (or
`control/lib/` for an on-device lib), run it again and confirm the
`restart boot loop` handler fired and the device's `bootloop.pid` changed.
That is also the real-device verification for the tag selection: a scripts
push must leave `pkg`, SSH keys, CFEngine and otelcol tasks unlisted in its
recap.

### d. Multi-host in one invocation

```bash
time hosts="s24 hd8 p7a" just deploy > ~/deploy-fleet.log 2>&1; echo rc=$?
```

Hosts in one `ansible-playbook` run already execute each task in parallel
(`forks` default 5, linear strategy), so this should be close to the slowest
single host, not the sum. The `fleet_deploy_lock` only serialises separate
invocations; the 2026-07-31 collision was two `just deploy` processes, which
this replaces with one.

## 4. Not done, with estimates (next steps in order of payoff)

1. **Gate `ssh_keys.yml` + `ca.yml` (36 tasks, ~45 s) and `otelcol.yml`
   (20 tasks, ~20 s) behind a content hash** of their inputs (keys dir
   listing + CA cert + sshd config template; otelcol version + rendered
   config), the #224 technique, recording the hash on the device after a
   successful pass. Saves **~60 s** of every no-op deploy. Not done here
   because it changes the self-heal contract: a device-side deletion would
   go unrepaired until the inputs change or the marker is removed. Needs an
   operator decision on whether the device repair loop already covers that
   drift (sshd config and authorized_keys: partly; CA certs: no).
2. **Fleet private keys** (`copy` + `stat` per key, ~16 s measured): one
   `copy` of a tar or a single `stayturgid.termux` module call. Left alone
   on purpose in 3873f53 (secret material, `no_log`); revisit only with a
   test that proves modes and contents.
3. **Shell profiles**: three `lineinfile` tasks × three files = 9 round
   trips (~10 s) → one check-mode-safe script per file, or one `blockinfile`
   per file. Behaviour change on `.profile`/`.bashrc`/`.bash_profile`
   ordering (`insertbefore: BOF`); needs a test like
   `test_termux_retired_cleanup.py` before switching.
4. **Directory creation**: the 5-item `file` loop plus five single `file`
   tasks and the shell `mkdir -p` = 11 round trips (~12 s) → one script
   that creates and `chmod`s, reports `created:`/`fixed:` lines, `DRY_RUN=1`
   in check mode (the retired-cleanup shape). Low risk; not done for time.
5. **shizuku_config** (18 tasks, half adb): the checksum compare + push
   could collapse into one adb shell script; **bootstrap_apks** per-app
   read-only checks likewise (#166 item 3). Needs live adb to verify output
   parsing: **measure** first.
6. **`strategy: free`** (#166 item 4): **not safe** for `fleet.yml` as
   written. `Install fleet device SSH public keys (mesh)` reads every other
   host's `stayturgid_device_ssh_pubkey` from `hostvars`, published earlier
   in the same play, and the CFEngine/otelcol `run_once` + `delegate_to:
localhost` steps assume the lock-step order; a fast host would reach the
   mesh task before a slow one published its key. §3d shows the parallelism
   is already there within one invocation; raise `forks` (`ANSIBLE_FORKS`)
   only if the fleet grows past five hosts.
7. **SSH `ControlPersist`**: Ansible's default `-o ControlPersist=60s`
   keeps the master alive between tasks and plays; the only gap longer than
   that is the Mac pass, which runs after all device plays. Nothing to gain.
8. **Fact caching** (`jsonfile`): would only speed the first localhost play
   across _separate_ runs (~1 s with the min subset). Skip.
