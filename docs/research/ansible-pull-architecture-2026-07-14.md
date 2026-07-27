<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Research: adding `ansible-pull` to stayturgid

**Date:** 2026-07-14 (Updated 2026-07-27)
**Status:** Hybrid Pilot Approved (under strict constraints)
**Audience:** Maintainers

## Executive recommendation

**The Verdict: Do not build a standalone, always-on `ansible-pull` daemon. However, a strictly gated, on-demand Ansible run triggered by the Kotlin agent is a viable secondary capability.**

Pure on-device Ansible orchestration is an architectural anti-pattern for Android due to process sandboxing, SELinux constraints, and the Phantom Process Killer. However, if treated as a secondary tool—triggered only by the Android-native `stayturgid-agent` under strict battery/charging gating—it can complement our architecture for heavier declarative tasks without fighting the OS.

The useful division of responsibility is:

| Layer                 | Responsibility                                                                                                         | Remains authoritative? |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| Mac push Ansible      | Bootstrap, credentials, APKs, ADB/SSH transport, UI-assisted setup, and fleet coordination                             | Yes (Primary)          |
| Kotlin Agent          | Native health checks, fast reachability, Shizuku bindings, and gating/scheduling for on-device Ansible                 | Yes (Primary)          |
| Device `ansible-pull` | A small allowlisted set of non-secret declarative tasks, executed infrequently via local connection                    | Hybrid Pilot           |
| Python repair loop    | Deprecated in favor of the Kotlin agent for on-device repair                                                           | No                     |

## Technical Feasibility & Constraints

Our research into Android 12+ process management and Shizuku (`rish`) privilege escalation reveals several hard constraints that shape how Ansible must run on the device.

### 1. Privilege Escalation & SELinux

`rish` grants an unrooted `shell` (UID 2000) execution context. However, we **cannot** use `rish` as a custom Ansible `become_method` for executing Python payloads.

Ansible relies on writing temporary compiled Python modules to the local filesystem (e.g., inside Termux at `~/.ansible/tmp/`) and then executing them with elevated privileges. Because Termux runs as an isolated app user (e.g., `u0_a100`) and UID 2000 is heavily restricted by Android's strict SELinux MAC (Mandatory Access Control) policies, `rish` cannot read or execute files within Termux's private data directory. Attempting this results in SELinux "Permission denied" errors.

**Mitigation:** We must use `connection: local` exclusively. Playbooks run as the unprivileged Termux user. For the few tasks requiring privileges, we must explicitly wrap them using the `shell` or `command` modules:
```yaml
- name: Set a secure setting
  shell: rish -c "settings put secure some_key some_value"
```

### 2. The Android Phantom Process Killer (Android 12 through 17)

Starting in Android 12, and persisting through Android 16 and 17, the OS aggressively monitors forked background child processes. If a background app exceeds 32 child processes across the system, or consumes excessive CPU, Android terminates it with `SIGKILL` (signal 9).

Ansible relies heavily on `fork()` to spawn worker processes. Running an `ansible-playbook` locally is exactly the type of workload the Phantom Process Killer targets, especially on lower-end devices like the Fire HD 8.

**Mitigation:** 
1. **Disable Child Process Restrictions:** Android 14+ (including Android 16 and 17) includes a "Disable child process restrictions" toggle in Developer Options. Push Ansible must enable this during initial provisioning, or the Kotlin agent must enforce this setting via Shizuku (`device_config put activity_manager max_phantom_processes 2147483647` or equivalent native secure settings).
2. **Strict Gating:** Runs must only occur when the device is charging, idle (screen off), and battery is >50%.
3. **Kotlin Agent Wrapper:** The `stayturgid-agent` must hold a WakeLock during the run.
4. **Pre-flight Check:** A very cheap native/shell drift check must gate the Ansible run so we don't pay the Python startup cost just to find out nothing changed.

### 3. Resource & Secret Hazards

Ansible is not designed for battery-powered execution. Furthermore, using `ansible-pull` requires playbooks and inventory variables to exist on the local filesystem.

**Mitigation:** 
- Keep secrets off-device. No long-lived Vault passwords should be stored on the phone.
- Use `ansible-pull` to fetch the playbook, run it, and exit. Do not run a long-lived `ansible-playbook` daemon.

## Architecture Comparison

- **Mac Push + Kotlin Agent (Current):** Lightweight on-device footprint, native OS integration, excellent secret handling. Weakness: requires Mac reachability for declarative updates.
- **Standalone On-device Ansible:** Heavy footprint, fights the OS (Phantom Process Killer), SELinux friction, secret sprawl.
- **Hybrid (Recommended):** The Kotlin agent remains the primary local health and recovery layer. It triggers an on-device Ansible run only for heavier, infrequent, declarative configuration passes that are currently pushed from the Mac.

## Actionable Recommendation: The Hybrid Pilot

We will build a **limited proof-of-concept pilot** with the following constraints:

1. Install `ansible-core` in Termux on one flagship device (e.g., S24) first.
2. Write a minimal playbook that performs 2-3 privileged actions explicitly via `rish -c`.
3. The Kotlin agent (`stayturgid-agent`) will act as the scheduler:
   - Checks gating conditions (charging, idle).
   - Holds a WakeLock.
   - Triggers `ansible-pull` to execute the local playbook.
4. Measure wall time, peak memory, and battery delta on the S24 before considering the Fire HD 8.

If the overhead is acceptable, this will become a complementary self-configuration path. The Kotlin agent remains the primary control plane on the device.
