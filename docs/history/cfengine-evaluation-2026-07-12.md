# CFEngine — Integration Evaluation (Revised 2026-07-12)

**Date:** 2026-07-12 (revised after on-device testing)
**Analyst:** DeepSeek V4 Pro
**Source:** https://github.com/cfengine/core (528 stars, 200 forks, 19,019 commits)
**Local:** `~/src/cfengine/`, `~/src/cfengine-buildscripts/`
**Version:** 3.27.1 (Termux package), 3.29.0 (git master)
**License:** GPL v3 + COSL, sponsored by Northern.tech AS

---

## On-Device Test Results (p7a, 2026-07-12)

CFEngine was installed and tested on the Pixel 7a via Termux:

```
$ pkg install cfengine
→ cfengine 3.27.1 (aarch64) installed with deps: liblmdb, librsync, libyaml

$ cf-agent --version
CFEngine Core 3.27.1

$ ls /data/data/com.termux/files/usr/bin/cf-*
cf-agent cf-check cf-execd cf-key cf-monitord cf-net
cf-promises cf-runagent cf-secret cf-serverd cf-support cf-upgrade
```

**12 compiled binaries** (cf-agent 320 KB, cf-serverd 115 KB, etc.) — all installed in Termux's `$PREFIX/bin`.

### Hello World test

```cfengine
bundle agent main {
  reports:
    "Hello from CFEngine $(sys.version) on $(sys.flavor) $(sys.arch)";
}
```

**Output:**

```
R: Hello from CFEngine 3.27.1 on termux aarch64
R: Platform classes: linux
R: Home: /data/data/com.termux/files/usr/var/lib/cfengine
```

**Confirmed:**

- `sys.flavor` = `termux` — correctly identifies the Termux environment
- `sys.arch` = `aarch64` — correct ARM64 detection
- Work directory uses `$PREFIX` (`/data/data/com.termux/files/usr/`) — no root filesystem access needed
- `linux` hard class present

### Known quirks

- **OS detection warning:** `"Operating System not properly recognized, setting sys.os_name_human to Unknown"` — cosmetic. The `android` hard class was NOT present in 3.27.1, suggesting 3.29.0 git source has newer platform detection that hasn't made it to the Termux package yet.
- **Policy validation works:** `cf-promises -f policy.cf` validates syntax before execution.

---

## What CFEngine is

CFEngine is one of the oldest configuration management systems still in active development. Created by Mark Burgess, now sponsored by Northern.tech AS. It uses a **declarative policy language** (`.cf` files) and compiled C agents to enforce desired state on managed hosts.

**Architecture:** Client/server pull model. A central policy server (`cf-serverd`) hosts policy files. Client agents (`cf-agent`) pull policies and enforce them locally every 5 minutes. A monitoring daemon (`cf-monitord`) collects metrics. A separate binary (`cf-promises`) validates policy syntax.

**Codebase:** 338 C files, 183,700 lines (88.6% C). Autotools build system (configure.ac). 12 compiled binaries. Submodule for libntech (reusable C library from Northern.tech).

---

## What CFEngine does exceptionally well

### 1. Verification (core competence)

CFEngine's `verify_*` subsystem is exactly what the user wants — a second opinion that confirms running state matches desired state:

| Module                  | Lines | What it verifies                             |
| ----------------------- | ----- | -------------------------------------------- |
| `verify_files.c`        | —     | File existence, permissions, content, hashes |
| `verify_packages.c`     | —     | Package installation state                   |
| `verify_processes.c`    | —     | Process running/matches criteria             |
| `verify_services.c`     | —     | Service state (running/stopped)              |
| `verify_users.c`        | —     | User accounts, groups                        |
| `verify_databases.c`    | —     | Database state                               |
| `verify_environments.c` | —     | Environment variables                        |
| `verify_exec.c`         | —     | Command execution output                     |
| `verify_methods.c`      | —     | Custom methods                               |
| `verify_acl.c`          | —     | POSIX ACLs                                   |
| `verify_storage.c`      | —     | Storage/filesystem state                     |

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

## Hard blockers for stayturgid integration (Revised)

### #1: Source code supports Android, but no pre-built binaries exist

**Correction from initial analysis:** CFEngine DOES have first-class Android support in the C source code. Evidence found:

| File                                      | Android support                                                             |
| ----------------------------------------- | --------------------------------------------------------------------------- |
| `libpromises/systype.h:52`                | `PLATFORM_CONTEXT_ANDROID` enum value                                       |
| `libpromises/systype.c`                   | 14 Android-specific paths and behaviors (e.g., `/system/xbin/busybox ps`)   |
| `libpromises/patches.c`                   | `#ifdef __ANDROID__` — `link()` not supported workaround                    |
| `libpromises/bootstrap.c`                 | `#if defined(**CYGWIN**)                                                    |     | defined(**ANDROID**)` |
| `libcfnet/client_code.c`                  | **`termux` referenced by name** — "Always say 'root' if windows or termux." |
| `libpromises/evalfunction.c`              | `#if defined(HAVE_GETPWENT) && !defined(__ANDROID__)`                       |
| 14 total references across 6 source files |                                                                             |

This is NOT a "needs porting" situation. The code already handles Android/Bionic libc, has Termux-specific behavior, and uses Android system paths. The developers explicitly designed for this platform.

**What's missing:** Pre-built Android/Termux binaries. The `buildscripts` repo and `platforms.json` only list Ubuntu and Debian targets. The downloads page has no Android packages. Building from source would require:

1. Cross-compiling on a Linux host targeting `aarch64-linux-android` (or compiling directly in Termux using its native gcc/make)
2. Building all bundled dependencies (OpenSSL, PCRE2, libcurl, libxml2, libyaml, LMDB, zlib) for Android bionic
3. Packaging as a Termux-compatible `.deb` or tarball

**This is feasible but non-trivial** — the build scripts support the autotools toolchain, and Termux provides a full build environment. A CI pipeline could produce Android binaries from the existing source.

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

| Capability              | stayturgid (current)                                               | CFEngine                                             |
| ----------------------- | ------------------------------------------------------------------ | ---------------------------------------------------- |
| **Verification engine** | `device_tier.py` (bash TAP) + `stayturgid_verify` (Ansible module) | `verify_*.c` (183k lines C)                          |
| **Policy format**       | Ansible YAML                                                       | CFEngine policy language (.cf)                       |
| **Deployment model**    | SSH push (Mac → device)                                            | Agent pull (policy server → agent)                   |
| **Agent on device**     | None (SSH-based)                                                   | cf-agent (cross-compiled C binary)                   |
| **Language**            | Python + Bash                                                      | C (cross-compilation needed)                         |
| **Fleet integration**   | Native (Ansible inventory)                                         | Separate (cf-serverd inventory)                      |
| **Health monitoring**   | `fleet_health_monitor.py`                                          | `cf-monitord`                                        |
| **Android support**     | Native (Termux + Shizuku)                                          | None (no bionic builds)                              |
| **Drift detection**     | `verify-drift` (14 checks) + `device_tier` (16 checks)             | Built-in (continuous enforcement)                    |
| **Lines of code**       | ~200 (module) + ~500 (repair)                                      | 183,000                                              |
| **Dependencies**        | Python 3.9+ (already in Termux)                                    | None (standalone binary) but needs cross-compilation |

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

## Recommendation (Revised)

**CFEngine is worth deeper investigation but not immediate integration.** The initial evaluation understated its Android readiness — the C codebase has first-class `__ANDROID__` support and even references "termux" by name. However, the practical blockers remain significant:

| Blocker                      | Status                 | Notes                                                                                                |
| ---------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------- |
| **Android code support**     | ✅ **Resolved**        | `PLATFORM_CONTEXT_ANDROID` + `__ANDROID__` ifdefs + termux references in core                        |
| **Pre-built binaries**       | ✅ **Resolved**        | `pkg install cfengine` → v3.27.1 for aarch64 in Termux main repo. 12 binaries, tested working on p7a |
| **Separate policy language** | ❌ **Still a blocker** | Must maintain Ansible YAML AND CFEngine .cf policies for same fleet                                  |
| **Client/server model**      | ⚠️ **Partial**         | Can run in standalone mode (`cf-agent -f policy.cf`) — no server needed for verification             |
| **Infrastructure overhead**  | ⚠️ **Minimal**         | Standalone cf-agent is 320 KB. No server needed for local verification. cf-execd adds battery drain. |

**If someone wanted to pursue this:**

1. **Build cf-agent for Termux** — try `./configure --host=aarch64-linux-android` in Termux native build environment, or cross-compile on a Linux host. Target just `cf-agent` and `cf-promises` (not the full stack).
2. **Write a .cf policy that mirrors Ansible desired state** — start with the 14 checks from `stayturgid_verify.py`, express them in CFEngine policy language.
3. **Run cf-agent in standalone mode** (no policy server) — CFEngine can run with local policy files: `cf-agent -f /path/to/policy.cf`
4. **Compare output** — cf-agent reports compliance state. Compare with Ansible's view.

**The killer use case:** CFEngine's promise theory aligns with the "secondary verify-only" concept. A lightweight standalone cf-agent binary with just the verify_* module could run every 5 minutes and report drift independently of Ansible's view. This would be more robust than the Python-based verify module (which depends on SSH being up, Python being available, etc.) — a compiled C binary has fewer failure modes.

**However:** The cost of building, packaging, and maintaining CFEngine binaries for 3 Android devices, plus authoring and maintaining parallel policy in a separate language, still exceeds the value over stayturgid's existing verification (250 lines of Python, no new deps, already works).

**Bottom line:** CFEngine is the most capable tool evaluated and the only one with genuine Android support in the codebase AND in the Termux package manager. If the existing verification infrastructure ever proves insufficient, CFEngine is the best candidate for a compiled-C fallback verification agent. The standalone mode (`cf-agent -f policy.cf`) avoids the infrastructure overhead and the dual-policy-language blocker is manageable for a verification-only use case.

## Plausible Next Steps for Parallel CFEngine Use

### 1. Write a verification-only .cf policy

Translate the 14 checks from `stayturgid_verify.py` into CFEngine policy language. Target: a standalone `verify.cf` that cf-agent runs locally with NO server infrastructure. Example:

```cfengine
bundle agent stayturgid_verify {
  vars:
    "termux_prefix" string => "/data/data/com.termux/files/usr";
    "stg_home" string => "/data/data/com.termux/files/home/.stayturgid";

  classes:
    "sshd_alive" expression => returnszero("$(termux_prefix)/bin/pgrep -x sshd", "useshell");
    "bootloop_alive" expression => returnszero("/usr/bin/test -f $(stg_home)/run/bootloop.pid", "useshell");

  reports:
    sshd_alive::
      "PASS: sshd running";
    !sshd_alive::
      "FAIL: sshd not running";
}
```

### 2. Run as a periodic check (event-driven, not daemon)

Instead of running `cf-execd` as a persistent daemon (battery drain from Doze conflicts), trigger `cf-agent` via:

- **Termux boot loop integration:** Add a cf-agent cycle to `start-adb.sh` alongside the existing repair loop
- **Tasker/MacroDroid:** On Wi-Fi connect → execute `cf-agent -f ~/verify.cf`
- **Mac launchd agent:** SSH to device → `cf-agent -f verify.cf` → collect output
- **Ansible playbook:** `ansible.builtin.command: cf-agent -f /path/to/verify.cf`

### 3. Use CFEngine for drift reporting alongside Ansible

CFEngine's "promise theory" model naturally produces compliance reports. Run `cf-agent -f verify.cf` every N minutes. If any promise fails, CFEngine logs it AND returns a non-zero exit code. This can feed into stayturgid's existing health monitoring:

```bash
# In fleet_health_monitor.py or a new check:
result = ssh(host, "cf-agent -f ~/verify.cf")
if result.rc != 0:
    log(f"{host}: CFEngine verification failed")
```

### 4. Gradual adoption — start with one check

Write a single CFEngine policy that checks ONE thing (e.g., sshd running) and runs alongside `stayturgid_verify`. Compare outputs for a week. If they always agree, great — you have a second opinion. If they disagree, you've found a bug in one of them.

### 5. Integrate as an Ansible module

Write an Ansible module that:

1. Templates a `.cf` policy from Ansible variables (desired state from inventory)
2. Copies it to the device
3. Runs `cf-agent -f policy.cf` and captures output
4. Parses CFEngine's JSON output format for structured results

This avoids maintaining parallel policy manually — Ansible IS the policy source, CFEngine is the verification engine.

### 6. Contact Northern.tech about the `android` hard class

The 3.27.1 Termux package doesn't expose the `android` hard class (returns `linux` instead). The 3.29.0 source code has `PLATFORM_CONTEXT_ANDROID`. Check if a newer Termux package is available or if the hard class detection needs a build flag. Having the `android` class would enable conditional policies like:

```cfengine
classify_android::
  "adb_enabled" expression => returnszero("adb connect localhost:5555", "useshell");
```
