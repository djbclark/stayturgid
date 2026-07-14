# Research: adding `ansible-pull` to stayturgid

**Date:** 2026-07-14  
**Status:** Research complete; implementation requires a staged pilot and a new ADR  
**Audience:** Maintainers and the junior developer implementing the pilot

## Executive recommendation

Add `ansible-pull` as an **optional, narrow device-local convergence layer**. Do not
replace the existing Mac-to-device Ansible deployment path, and do not run the current
`ansible/playbooks/site.yml` or `ansible/playbooks/fleet/fleet.yml` on an Android device.

The useful division of responsibility is:

| Layer                 | Responsibility                                                                                                         | Remains authoritative? |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| Mac push Ansible      | Bootstrap, credentials, APKs, ADB/SSH transport, UI-assisted setup, fleet coordination, and repair of the pull runtime | Yes                    |
| Device `ansible-pull` | A small allowlisted set of non-secret Termux files and local configuration                                             | Additive pilot         |
| Python repair loop    | Fast reachability and runtime repair when Git, Ansible, or the Mac is unavailable                                      | Yes                    |
| AutoJs6 watchdog      | In-app and catastrophic Android recovery                                                                               | Yes                    |
| CFEngine              | Small independent policy/recovery path already deployed to devices                                                     | Yes during the pilot   |

This is deliberately not a full “move to pull.” It gives devices eventual local
convergence while preserving stayturgid's independent recovery paths. A successful
pilot may make pull the primary delivery mechanism for its **local-policy subset**, but
push Ansible will still be necessary for initial bootstrap and operations that require
Mac credentials, ADB, fleet-wide knowledge, or operator interaction.

## Why consider it now

The current push design is appropriate for provisioning but has two limitations:

1. a device that is online but temporarily unreachable from the Mac cannot receive a
   normal Ansible correction; and
2. deployment and on-device recovery sometimes express overlapping desired state in
   YAML, Python, JavaScript, and CFEngine.

`ansible-pull` can help with the first limitation and can reduce some duplication for
ordinary local files. It does **not** solve Android accessibility consent, Shizuku
authorization, wireless-debugging approval, ADB key authorization, or a device whose
Termux/Python runtime is broken. The existing recovery layers remain necessary.

The earlier analysis in [ADR 004](../adr/004-self-heal-vs-ansible-coverage.md) correctly
rejected putting the full repair loop into Ansible: the dependency, secrets, Git access,
and Fire OS costs outweighed the small amount of duplicated repair logic. This proposal
is narrower. It runs infrequently, contains no reachability-critical hot-loop logic,
and starts with one harmless file on one modern phone. The pilot should determine
whether that narrower value is worth its ongoing complexity.

## Current stayturgid constraints

Before designing the pilot, read these local sources completely:

- [Architecture](../architecture.md) and
  [ADR 001: Ansible boundary](../adr/001-ansible-boundary.md)
- [ADR 004: self-heal versus Ansible coverage](../adr/004-self-heal-vs-ansible-coverage.md)
- [Ansible README](../../ansible/README.md),
  [fleet entry point](../../ansible/playbooks/fleet/fleet.yml), and
  [site entry point](../../ansible/playbooks/site.yml)
- [Termux runtime](../modules/termux.md) and
  [`start_adb.py`](../../device/termux/py/start_adb.py)
- [Coding rules](../coding-rules.md), [handoff](../handoff.md), and
  [options](../options.md)

GitHub equivalents for reviewers without the checkout:

- <https://github.com/djbclark/stayturgid/tree/master/ansible>
- <https://github.com/djbclark/stayturgid/blob/master/device/termux/py/start_adb.py>
- <https://github.com/djbclark/stayturgid/blob/master/docs/adr/004-self-heal-vs-ansible-coverage.md>

Important constraints:

- Android devices run unprivileged Termux. There is no normal `systemd` or root
  service manager.
- The existing Python boot supervisor already performs frequent, bounded local checks
  and a daily repository-version check. It is the natural scheduler seam, but the pull
  operation must not run inline in every repair iteration.
- Current fleet roles include `delegate_to: localhost`, Mac paths, ADB operations,
  secrets, application installation, and UI automation. They are not pull-safe.
- Network, GitHub, Doze, app lifecycle, and Termux process survival are unreliable by
  design. Pull failure must not disable SSH, ADB, CFEngine, or the repair loop.
- HD8 is slow and has old Fire OS behavior. It must not be the first pilot and may remain
  pull-disabled permanently if the dependency or runtime cost is excessive.

## Relevant upstream behavior and best practices

The design below is based on current official Ansible documentation:

- [`ansible-pull` CLI documentation](https://docs.ansible.com/projects/ansible/latest/cli/ansible-pull.html)
  says that it checks out playbooks from version control and runs them locally. It also
  warns that Ansible CLI tools are not designed to run concurrently; an external
  scheduler and/or lock is required.
- The CLI supports a branch, tag, or commit with `--checkout`, randomized startup delay
  with `--sleep`, check/diff mode, a fixed checkout directory, and GPG verification with
  `--verify-commit`.
- [`ansible.builtin.git`](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/git_module.html)
  documents commit verification and a signer fingerprint allowlist. It also warns that
  accepting an unknown SSH host key weakens man-in-the-middle protection.
- [Check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
  are useful gates, but modules may only partially support check mode. A clean check run
  is evidence, not proof that the live apply will succeed.
- [Ansible Vault](https://docs.ansible.com/projects/ansible/latest/vault_guide/index.html)
  protects data at rest, not after decryption. For this pilot, avoiding secrets in the
  pull checkout is safer than distributing a vault password to every device.

Apply these practices to stayturgid as follows:

1. **Lock every run.** Use a nonblocking `fcntl.flock()` in the Python runner. A skipped
   run due to contention is healthy, not an error.
2. **Pin and verify what executes.** Production devices must not execute an unsigned,
   floating `master` checkout merely because it changed.
3. **Use least privilege.** Run as the Termux user with local connection and no become.
   The playbook must never prompt for a password.
4. **Keep secrets out.** Use a public repository or read-only repository credential.
   Keep device secrets in separately provisioned `0600` files outside the checkout.
5. **Bound resource use.** Add jitter, a hard timeout, low frequency, bounded logs, and
   failure backoff. Treat no network as normal.
6. **Keep a last-known-good revision.** Never destroy the only known working policy
   before the candidate has been verified and applied successfully.
7. **Observe every run.** Record the requested and applied commit, start/end timestamps,
   duration, result, and compact Ansible recap in standard syslog format.
8. **Keep bootstrap independent.** Pull must not be the only mechanism capable of
   installing or repairing Git, Python, `ansible-core`, its runner, or its trust keys.
9. **Converge even without a code update.** Do not use `--only-if-changed` for the normal
   scheduled convergence run; doing so would leave local drift uncorrected when Git is
   unchanged. It is acceptable for a separate update-only command.
10. **Test rollback, not just success.** A bad signature, invalid YAML, unreachable
    repository, timeout, and failing task all need explicit expected outcomes.

## Desired architecture

### 1. Control plane and release channel

The stayturgid repository remains the source of policy, but production devices consume
a deliberately promoted revision rather than the tip of the development branch.

Recommended sequence:

```text
developer commit -> CI/test -> signed release tag or approved commit SHA
                 -> device stages revision -> verifies -> validates -> applies
                 -> records successful SHA as last-known-good
```

Start the pilot with an exact commit SHA selected in inventory. Before unattended use,
configure a dedicated signing key and require `--verify-commit`. A signed release tag is
useful to humans, but verify the actual checked-out commit too. Store the trusted public
key/fingerprint on the device through push Ansible, outside the pulled checkout.

Do not use `--accept-host-key`. For an SSH Git URL, seed and pin the Git host key during
bootstrap. HTTPS to a public repository avoids a deploy key and is the simplest pilot
transport. If the repository later becomes private, use a read-only, narrowly scoped
credential unique to this purpose; do not copy the Mac's SSH or GitHub credentials.

### 2. Pull-safe playbook boundary

Create a separate entry point, proposed as:

```text
ansible/playbooks/pull/device-local.yml
ansible/inventory/pull/localhost.yml
ansible/roles/device_pull_local/
```

It must target only a literal local inventory and local connection. It must not import
the fleet or site playbooks. Prefer fully qualified built-in module names and avoid
external collections during the first pilot.

Initial allowlist:

- a harmless sentinel containing the applied policy revision;
- non-secret files under `~/.stayturgid/`;
- local scripts and templates that are already pushed by Ansible, after parity tests;
- file modes and directories owned by the Termux user; and
- prebuilt CFEngine policy artifacts, only if building remains a Mac/CI responsibility.

Explicit denylist for the pilot:

- APK installation or application data changes;
- accessibility, Shizuku, wireless-debugging, or other UI/consent operations;
- ADB commands, Mac delegation, and fleet-to-fleet operations;
- SSH/ADB private keys, vault passwords, tokens, and host-specific secrets;
- Termux package upgrades or self-updating `ansible-core`;
- changing/restarting the transport used to recover the device;
- AutoJs6 project launch and UI automation; and
- anything requiring root, `sudo`, or Ansible become.

Do not copy tasks into the pull role casually. First classify each candidate task as
`push-only`, `pull-safe`, or `shared artifact`. When push and pull both manage a file,
they must render identical bytes from the same source template and tests must prove it.

### 3. Device-side runner

Implement orchestration in Python, consistent with the repository's Python-first rule.
The proposed file is:

```text
device/termux/py/stayturgid_ansible_pull.py
```

The runner, not shell or a playbook, should own:

- configuration parsing and an `enabled: false` default;
- interval, stable per-device jitter, timeout, and failure backoff;
- a nonblocking process lock;
- disk/free-space and battery sanity checks;
- staging and last-known-good paths;
- exact-ref checkout and signature verification;
- syntax check, optional check/diff preflight, live apply, and post-validation;
- atomic status and timestamp files;
- bounded syslog-format logs; and
- manual `status`, `check`, `run`, and `rollback` subcommands.

Suggested device layout:

```text
~/.stayturgid/ansible-pull/
├── config.json                 # 0600; provisioned by push Ansible
├── current -> releases/<sha>   # last successfully promoted policy
├── candidate/                  # disposable staging checkout
├── releases/<sha>/             # bounded last-known-good checkouts
├── state.json                  # atomic machine-readable status
├── run.lock
└── trusted-signers/            # provisioned independently
~/.stayturgid/logs/ansible-pull.log
~/.stayturgid/venv/ansible-pull/
```

Do not assume native `ansible-pull` alone provides transactional rollback. A small
Python wrapper may use `ansible-pull` for the manual prototype, but the unattended
version should explicitly stage and verify a checkout before calling
`ansible-playbook` locally. This makes current/candidate/last-known-good state
unambiguous and testable.

`state.json` should contain at least:

```json
{
  "schema": 1,
  "enabled": true,
  "phase": "idle",
  "requested_ref": "0123456789abcdef...",
  "applied_commit": "0123456789abcdef...",
  "last_started_at": "2026-07-14T20:00:00Z",
  "last_succeeded_at": "2026-07-14T20:00:19Z",
  "last_result": "ok",
  "consecutive_failures": 0
}
```

Write it to a same-directory temporary file, `fsync`, and atomically replace it. Never
put secrets or full noisy command output in this file.

### 4. Runtime and scheduling

Push Ansible installs a pinned `ansible-core` into a dedicated virtual environment. Do
not modify the host-development `pyproject.toml` assumption that Python is at least
3.12 until the actual Termux Python versions on S24, P7A, and HD8 are measured. Select
an `ansible-core` version whose controller Python requirement all enrolled devices meet,
pin the exact version, and test a clean installation. Record installed size and elapsed
time, especially on HD8.

The first phase is manual only. Later, let `start_adb.py` launch the runner as a bounded
child when a durable next-run timestamp is due. It must not wait for the pull to finish
inside the reachability-critical loop. Use stable device-derived jitter so all devices
do not contact GitHub simultaneously.

Recommended initial unattended cadence:

- normal run: every 24 hours;
- jitter: up to 60 minutes;
- hard runtime: 10 minutes on S24/P7A, separately measured for HD8;
- after failure: exponential or stepped backoff capped at 24 hours; and
- manual trigger: allowed at any time if the lock is free.

The existing daily repository-version check may later be consolidated with this
scheduler, but do not remove it during the pilot.

### 5. Coexistence with push, repair, and CFEngine

The on-device runner must never take the global repair lock for its entire Git/network
operation. Use a dedicated pull lock. For the brief live-apply phase, introduce a shared
configuration-apply lease that other local policy writers can respect. The junior
developer must document which existing processes can touch each pull-managed file.

Push Ansible remains able to overwrite/repair pull-managed files. After a push deploy,
it should update the pull state to the same policy commit or explicitly schedule a
reconciliation. This prevents a device from immediately “correcting” a newer push back
to an older pull revision.

Do not remove CFEngine coverage during the pilot. If both systems manage the same path,
choose one owner or generate the same artifact; two independent engines repeatedly
changing a file is a configuration fight, not redundancy.

### 6. Health and operator control

Expose these fields through the existing fleet health/dashboard path:

- `pull=disabled|never|ok|running|stale|failed|blocked`;
- requested and applied short commit;
- age of last success;
- consecutive failure count; and
- a short sanitized failure reason.

Eventually add a dashboard action to request `check` or `run` immediately. It must use
the existing authenticated action/audit pattern, show the target and requested commit,
and return quickly after creating a request. The background runner performs the work.
Do not make an HTTP request hold open for a ten-minute apply.

## Command prototypes

These are research examples, not commands to run fleet-wide. Use S24 only after the
bootstrap and playbook boundary exist.

Native manual dry run against an exact commit:

```bash
ansible-pull \
  --url https://github.com/djbclark/stayturgid.git \
  --checkout FULL_40_CHARACTER_COMMIT_SHA \
  --directory "$HOME/.stayturgid/ansible-pull/candidate" \
  --inventory localhost, \
  --connection local \
  --check --diff \
  ansible/playbooks/pull/device-local.yml
```

Signature-enforced form after the trusted public key is installed:

```bash
ansible-pull \
  --url https://github.com/djbclark/stayturgid.git \
  --checkout FULL_40_CHARACTER_COMMIT_SHA \
  --verify-commit \
  --directory "$HOME/.stayturgid/ansible-pull/candidate" \
  --inventory localhost, \
  --connection local \
  ansible/playbooks/pull/device-local.yml
```

Do not add `--force`, `--clean`, `--accept-host-key`, `--ask-vault-pass`, or
`--ask-become-pass` to the unattended command. Do not pass secrets through `--extra-vars`
because command lines can be exposed in process listings and logs.

The final operator interface should be the Python runner, for example:

```bash
python3 ~/bin/stayturgid_ansible_pull.py status
python3 ~/bin/stayturgid_ansible_pull.py check --ref FULL_COMMIT_SHA
python3 ~/bin/stayturgid_ansible_pull.py run --ref FULL_COMMIT_SHA
python3 ~/bin/stayturgid_ansible_pull.py rollback
```

## Junior-developer implementation plan

Only begin this work after the maintainer explicitly selects the ansible-pull pilot.
Do one phase per reviewable commit. Stop at every approval gate.

### Phase 0 — inventory and feasibility, no device mutation

1. Read every file listed in “Current stayturgid constraints,” plus all repository agent
   rules and the current handoff.
2. List every task in the Termux-related fleet roles and classify it as `push-only`,
   `pull-safe candidate`, or `shared artifact`. Include its file/module, inputs, secrets,
   transport, privilege, rollback method, and current recovery owner.
3. Inspect S24, P7A, and HD8 read-only for Python version, available storage, Git version,
   GPG capability, and whether `ansible-core` can be installed in an isolated venv.
4. Research the exact supported Python range of the selected pinned `ansible-core`
   release. Do not simply install the newest release.
5. Add unit-test fixtures for S24/P7A/HD8 capability results. Do not enroll devices yet.

**Gate:** Present dependency size, install time estimate, compatibility matrix, and task
classification. Ask before installing Ansible on a device.

### Phase 1 — pull-safe playbook on the Mac

1. Add the dedicated local inventory, playbook, and role described above.
2. Manage one sentinel file only. It must contain no secret and must not affect recovery.
3. Assert local connection, the Termux user, allowed path prefixes, and
   `stayturgid_ansible_pull_enabled`. Fail closed on an unexpected platform or path.
4. Add syntax, lint, check-mode, idempotence, and molecule/fixture tests appropriate to
   the repository. Two consecutive applies must report no change on the second run.
5. Add a CI job that exercises only the pull-safe entry point and rejects imports of the
   site/fleet/control-node playbooks, `delegate_to`, `become`, and obvious secret paths.

**Gate:** No phone changes. Review the boundary and tests before proceeding.

### Phase 2 — Python runner and failure tests on the Mac

1. Implement the Python runner with dependency injection for clock, subprocess, network,
   battery, and filesystem boundaries.
2. Unit-test lock contention, no network, invalid ref, bad signature, syntax failure,
   check failure, apply timeout, apply failure, validation failure, atomic status writes,
   successful promotion, and rollback.
3. Ensure logs use the repository's standard logging helpers and UNIX syslog format.
4. Ensure every subprocess has an explicit timeout and argument list; do not use
   `shell=True`.
5. Add a report-only configuration. `enabled` must default to false everywhere.

**Gate:** Run the full repository checks. Ask before device bootstrap.

### Phase 3 — manual S24 pilot

1. Use push Ansible to install the isolated, pinned runtime and trusted signer on S24.
2. Seed a known-good exact commit and leave scheduling disabled.
3. Run `status`, then `check`; inspect logs and state before a live run.
4. Apply only the sentinel. Run twice and prove idempotence.
5. Exercise bad signature, network loss, lock contention, timeout, and rollback without
   impairing SSH, ADB, CFEngine, the repair loop, or AutoJs6.
6. Reboot S24 and confirm that existing recovery works before any pull is requested.

**Gate:** Observe S24 for at least several normal repair cycles. Review results before
enabling a schedule or adding managed files.

### Phase 4 — scheduled S24 and limited policy

1. Add the low-frequency scheduler hook with durable timestamps, jitter, and backoff.
2. Add health output and an operator-visible manual trigger request.
3. Move at most one low-risk file group at a time into the pull-safe role.
4. For every file, add push/pull byte-parity and ownership tests.
5. Verify offline boot, GitHub outage, a bad promoted revision, repeated failure, and
   recovery by Mac push.

**Gate:** Write a new ADR using measured resource, reliability, and operator results.
The ADR decides whether to stop, keep an optional hybrid, or expand the local subset.

### Phase 5 — P7A, then an explicit HD8 decision

Enroll P7A only after S24 is stable. Repeat failure tests rather than assuming parity.
HD8 comes last. Measure installation size, runtime, heat/battery impact, and Doze/Fire OS
process survival. It is acceptable—and likely prudent—for HD8 to remain disabled while
still being an active fleet member served by push Ansible, Python repair, and CFEngine.

## Acceptance criteria for a useful pilot

The pilot is successful only if all are true:

- a device converges the sentinel and approved local files without Mac reachability;
- it never executes an unapproved or unverifiable revision;
- no pull path contains or retrieves fleet-control secrets;
- no prompt, root, become, GUI, or operator approval is required during a scheduled run;
- overlapping runs cannot occur;
- network loss and failed applies preserve the last-known-good state;
- push Ansible can repair or disable the pull runtime;
- SSH/ADB/CFEngine/Python/AutoJs6 recovery continues independently;
- status is visible and actionable without reading a large raw Ansible log;
- repeated apply is idempotent; and
- measured CPU, storage, battery, and elapsed-time cost is acceptable on each enrolled
  device class.

Stop the pilot if it makes reachability less reliable, creates policy fights, requires
device-held high-value credentials, or costs more operational complexity than the few
local files it can safely own.

## Decisions intentionally deferred

The junior developer must not decide these implicitly while coding:

1. whether production promotion uses a signed tag, a signed commit on a deployment
   branch, or an inventory-pinned SHA distributed by push Ansible;
2. which signing identity and rotation/revocation procedure to use;
3. whether the public GitHub repository remains the production source or a release
   artifact/mirror is introduced;
4. whether pull eventually owns any CFEngine-generated artifacts;
5. whether P7A and HD8 enroll; and
6. whether the successful pilot changes ADR 004's project-wide recommendation.

Record the measured pilot results and these decisions in a new ADR. Do not rewrite
ADR 004 as though its earlier reasoning never existed.
