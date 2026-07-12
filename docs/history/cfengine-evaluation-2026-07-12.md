# CFEngine — Integration Evaluation

**Date:** 2026-07-12
**Analyst:** DeepSeek V4 Pro
**Source:** https://github.com/cfengine/core (528 stars, 200 forks, 19,019 commits)
**Local:** `~/src/cfengine/`
**Version:** 3.29.0 (commit 2 days ago — actively maintained)
**License:** GPL v3 + COSL (Commercial Open Source License), sponsored by Northern.tech AS

---

## What CFEngine is

CFEngine is one of the oldest configuration management systems still in active development. Created by Mark Burgess, now sponsored by Northern.tech AS. It uses a **declarative policy language** (`.cf` files) and compiled C agents to enforce desired state on managed hosts.

**Architecture:** Client/server pull model. A central policy server (`cf-serverd`) hosts policy files. Client agents (`cf-agent`) pull policies and enforce them locally every 5 minutes. A monitoring daemon (`cf-monitord`) collects metrics. A separate binary (`cf-promises`) validates policy syntax.

**Codebase:** 338 C files, 183,700 lines (88.6% C). Autotools build system (configure.ac). 12 compiled binaries. Submodule for libntech (reusable C library from Northern.tech).

---

## What CFEngine does exceptionally well

### 1. Verification (core competence)

CFEngine's `verify_*` subsystem is exactly what the user wants — a second opinion that confirms running state matches desired state:

| Module | Lines | What it verifies |
|--------|-------|-----------------|
| `verify_files.c` | — | File existence, permissions, content, hashes |
| `verify_packages.c` | — | Package installation state |
| `verify_processes.c` | — | Process running/matches criteria |
| `verify_services.c` | — | Service state (running/stopped) |
| `verify_users.c` | — | User accounts, groups |
| `verify_databases.c` | — | Database state |
| `verify_environments.c` | — | Environment variables |
| `verify_exec.c` | — | Command execution output |
| `verify_methods.c` | — | Custom methods |
| `verify_acl.c` | — | POSIX ACLs |
| `verify_storage.c` | — | Storage/filesystem state |

CFEngine's entire philosophy is "promise theory" — you declare desired state ("promises"), and the agent continuously verifies and enforces. This is the most mature verification engine in open source configuration management.

### 2. Monitoring built-in

`cf-monitord` collects system metrics (CPU, memory, disk, processes) without external dependencies. Comparable to stayturgid's `fleet_health_monitor.py` but compiled C, no Python interpreter needed.

### 3. Active development

Last commit: **July 10, 2026** (2 days ago). Version 3.29.0 is current. Northern.tech has commercial incentives to keep the project alive (Enterprise edition). This is the opposite of Bcfg2 (abandonware 2014).

### 4. Policy validation

`cf-promises` validates policy files for syntax errors BEFORE deployment. Ansible has `--syntax-check` but CFEngine's validation is more thorough (type checking, dependency resolution).

### 5. Cross-platform

CFEngine runs on Linux, macOS, Windows, AIX, Solaris, HP-UX. The `configure.ac` build system handles diverse platforms. The INSTALL file specifically mentions ARM64 builds.

---

## Hard blockers for stayturgid integration

### #1: Written in C — cannot run on Android/Termux without cross-compilation

The entire CFEngine agent is compiled C (183k lines). To run on an Android device:

1. Cross-compile for aarch64-linux-android (different from aarch64-linux-gnu)
2. Link against Android's bionic libc (not glibc)
3. Package as a Termux-compatible binary
4. Maintain custom builds for every CFEngine release

CFEngine does not distribute Android binaries. The ARM64 support in INSTALL refers to ARM Linux servers (e.g., AWS Graviton), not Android devices. This is a **compilation blocker** — not just a "needs testing" gap.

### #2: Client/server pull model incompatible with SSH push model

CFEngine works by:
1. Policy server (`cf-serverd`) runs on a central host, hosts `.cf` policy files
2. Agents (`cf-agent`) pull policies from the server on a schedule (default 5 minutes)
3. Agents enforce policies locally and report back

stayturgid works by:
1. Ansible control node runs on Mac
2. Push commands via SSH to each Android device
3. No agent, no server, no pull model

These are fundamentally incompatible architectures. You can't "just use cf-agent for verification" — the agent requires a policy server, a policy distribution mechanism, key trust bootstrapping, and a reporting infrastructure.

### #3: Separate policy language (.cf) alongside Ansible YAML

CFEngine has its own policy language:

```cfengine
bundle agent main {
  reports:
    "Hello, world";
  
  files:
    "/etc/ssh/sshd_config"
      perms => mog("0600", "root", "root"),
      edit_line => ensure_present("PerSourcePenalties no");
}
```

stayturgid already has infrastructure-as-code in Ansible YAML (`hosts.yml`, `group_vars/*.yml`, playbooks). Maintaining two separate configuration languages for the same fleet doubles the maintenance burden. Every change to desired state would need to be expressed in BOTH Ansible and CFEngine policy language.

### #4: Full deployment would require policy server infrastructure

To use CFEngine verification, you need:

1. Policy server host (another machine to maintain)
2. cf-serverd running and reachable
3. Key trust bootstrapped (cf-key)
4. Policy files authored in CFEngine language
5. cf-agent installed on every device (cross-compiled for Android)
6. cf-execd scheduling agent runs

This adds an entire parallel infrastructure stack alongside the existing Ansible stack.

### #5: GPL v3 license implications

CFEngine Community is GPL v3. While this doesn't prevent usage, it means any modifications to the C agent would need to be released under GPL. The Enterprise edition uses COSL (Commercial Open Source License) which has different terms. This is a consideration if stayturgid ever needed to modify the agent.

### #6: Package size and dependencies

Cross-compiled cf-agent binary would likely be 2-5 MB (C, statically linked). Plus the policy files, plus cf-execd, plus cf-monitord, plus libpromises, plus libntech. The full stack could be 10-20 MB per device. Compare to stayturgid's verification which is a zero-dependency Python script running over SSH.

---

## Comparison with stayturgid's existing verification

| Capability | stayturgid (current) | CFEngine |
|-----------|---------------------|----------|
| **Verification engine** | `device_tier.py` (bash TAP) + `stayturgid_verify` (Ansible module) | `verify_*.c` (183k lines C) |
| **Policy format** | Ansible YAML | CFEngine policy language (.cf) |
| **Deployment model** | SSH push (Mac → device) | Agent pull (policy server → agent) |
| **Agent on device** | None (SSH-based) | cf-agent (cross-compiled C binary) |
| **Language** | Python + Bash | C (cross-compilation needed) |
| **Fleet integration** | Native (Ansible inventory) | Separate (cf-serverd inventory) |
| **Health monitoring** | `fleet_health_monitor.py` | `cf-monitord` |
| **Android support** | Native (Termux + Shizuku) | None (no bionic builds) |
| **Drift detection** | `verify-drift` (14 checks) + `device_tier` (16 checks) | Built-in (continuous enforcement) |
| **Lines of code** | ~200 (module) + ~500 (repair) | 183,000 |
| **Dependencies** | Python 3.9+ (already in Termux) | None (standalone binary) but needs cross-compilation |

---

## The verification engine is excellent — but we can't extract it

CFEngine's `verify_*` subsystem is the most mature and well-tested verification engine in open source configuration management. The "promise theory" model is philosophically aligned with what the user wants: a separate, independent verification that current state matches desired state.

However, the verification engine cannot be used independently. It is deeply embedded in the CFEngine architecture:
- `verify_files.c` depends on `promises.h`, `eval_context.h`, `cf-agent.c`
- Policy evaluation requires the full agent infrastructure
- There is no "cf-verify" standalone binary — verification IS the agent

**Extracting just the verification logic would require:**
1. Porting 50+ C source files to a standalone library
2. Replacing CFEngine's policy parser with Ansible YAML input
3. Cross-compiling for Android bionic
4. Maintaining this fork against upstream changes

This is a months-long engineering project with ongoing maintenance burden.

---

## Recommendation

**Do not integrate CFEngine.** Despite being the most mature and actively maintained of the three config management tools evaluated, the hard blockers are:

1. **No Android builds** — 183k lines of C need cross-compilation for bionic libc. No Termux package exists.
2. **Architectural mismatch** — client/server pull model vs stayturgid's SSH push model
3. **Separate policy language** — would need to express fleet state in BOTH Ansible YAML and CFEngine `.cf` policy
4. **Infrastructure overhead** — would need policy server, key trust bootstrapping, agent scheduling

**The verification functionality CFEngine provides is already implemented in stayturgid:**

| CFEngine capability | stayturgid equivalent |
|--------------------|----------------------|
| `verify_files` | `device_tier.py` check 15 (scripts match) + `stayturgid_verify` (scripts_match) |
| `verify_processes` | `device_tier.py` checks 2-3, 5, 7 (sshd, bootloop, bridge, watchdog) + module checks |
| `verify_services` | `device_tier.py` checks 2-3 + `stayturgid_verify` (sshd, bootloop, shizuku) |
| `verify_packages` | `device_tier.py` check 10 (mirror) + Ansible `termux_pkg` module |
| `cf-monitord` | `fleet_health_monitor.py` + `firerpa_health_monitor.py` |

**CFEngine's approach is admirable and the "promise theory" philosophy is worth studying, but the engineering cost of integration far exceeds the value it would add over stayturgid's existing verification infrastructure.**
