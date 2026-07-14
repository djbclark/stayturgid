# nix-on-droid — Integration Evaluation

**Date:** 2026-07-12
**Analyst:** DeepSeek V4 Pro
**Source:** https://github.com/nix-community/nix-on-droid (2.1k stars, 460 commits, MIT, F-Droid installable)
**Local:** `~/src/nix-on-droid/`

---

## What nix-on-droid is

A single-click F-Droid-installable Nix package manager for Android. Uses a fork of Termux-the-terminal-emulator app (NOT Termux-the-distro — explicitly unrelated). Runs Nix inside `proot` (userspace chroot, no root required). Declarative config via `~/.config/nixpkgs/nix-on-droid.nix`.

**Key modules:** environment (packages, path, shell, login, networking, android-integration), home-manager, build/activation, nixpkgs config.

**What it provides:**

```nix
{ pkgs, ... }: {
  environment.packages = [ pkgs.vim pkgs.git pkgs.openssh ];
  system.stateVersion = "24.05";
}
```

That's the entire config — declarative, reproducible Nix packages across devices.

---

## Comparison with stayturgid's current stack

| Layer                   | stayturgid (current)                                     | nix-on-droid approach                                 |
| ----------------------- | -------------------------------------------------------- | ----------------------------------------------------- |
| **Package management**  | `pkg`/`apt` (Termux), mirror pinning required            | Nix (deterministic, binary cache, no mirror issues)   |
| **Shell environment**   | `.profile`/`.bashrc` via Ansible lineinfile (PATH leaks) | Nix profiles (isolated, no cross-contamination)       |
| **Dotfile management**  | Ansible templates + copy                                 | Home-manager (declarative, idempotent)                |
| **Init/boot hooks**     | Termux:Boot (start-adb.sh)                               | ❌ None — proot-based, no native boot hooks           |
| **Self-heal**           | `stayturgid_repair.py` (570+ lines, fleet-specific)      | ❌ None — just package activation                     |
| **Process model**       | Native Termux processes (sshd via runsv)                 | proot-wrapped (fake filesystem, PID namespace issues) |
| **Device APIs**         | termux-api (battery, notification, toast, wakelock)      | ❌ None — separate app, no API bridge                 |
| **Shizuku integration** | Via localhost:5555 (uid 2000 privileged shell)           | ❌ No Shizuku or ADB integration                      |
| **AutoJs6**             | JS watchdog + UI automation                              | ❌ No support                                         |
| **Fire OS**             | Specific adaptations (no localhost:5555, peer bootstrap) | ❌ Untested, unlikely to work                         |
| **Fleet orchestration** | Ansible (inventory, roles, playbooks)                    | ❌ Single-device only                                 |
| **Health monitoring**   | `fleet_health_monitor.py` + launchd                      | ❌ None                                               |

---

## What nix-on-droid COULD replace

### 1. Package management (theoretically)

Nix's deterministic package graph would eliminate:

- Mirror pinning issues (no apt mirrors needed)
- `pkg upgrade` conffile prompts
- Package version drift across devices
- The `ensure_termux_mirror()` self-heal function

### 2. Dotfile/shell config

Home-manager would solve the Mac PATH leakage problem at the root — no Ansible lineinfile regexes, no profile drift detection, no self-heal needed.

### 3. Development tools

Nix offers 80,000+ packages vs Termux's ~5,000. Development tools like `ripgrep`, `fd`, `bat`, `delta`, `lazygit` that don't exist in Termux would be available.

---

## Why it's a BAD idea for stayturgid

### Hard blocker #1: It replaces Termux

nix-on-droid explicitly states: **"has no relation to Termux-the-distro. Please do not pester Termux folks."** The entire stayturgid stack runs INSIDE Termux:

- `start-adb.sh`, `repair-bridge.sh`, `start-autojs6-watchdog.sh` (Termux:Boot hooks)
- `sshd` (Termux runsv managed)
- `stayturgid_repair.py` (needs Termux PATH, HOME, PREFIX)
- `stayturgid_agent_presence.py` (termux-notification, termux-toast)
- `stayturgid_battery_alarm.py` (termux-battery-status, termux-torch)
- `termux-api` (RUN_COMMAND bridge from AutoJs6)
- `termux-wake-lock` (Doze prevention)

Moving to nix-on-droid means porting or abandoning ALL of this. The termux-api functions have no nix equivalent.

### Hard blocker #2: proot fragility

The Nix environment runs inside `proot` — a userspace chroot. This means:

- Process visibility is restricted (AutoJs6 can't see Nix processes via `RUN_COMMAND`)
- PID namespaces may not work with `pgrep`, `kill`, `setsid`
- The Shizuku ADB bridge (localhost:5555) won't be accessible from inside proot
- `sshd` from Nix would run in a different context than Termux's runsv

### Hard blocker #3: Prototype quality

The README says: **"It's prototype-grade quality as of now, but hey, it works!"** This is not acceptable for a fleet management system where devices must stay reachable 24/7.

### Hard blocker #4: Single-device, no fleet

nix-on-droid is designed for ONE device. There's no inventory, no orchestration, no health monitoring. stayturgid's entire value proposition is fleet management across 3 heterogeneous devices (Samsung, Pixel, Fire OS).

### Hard blocker #5: Fire OS

nix-on-droid is "only tested with aarch64." Fire OS 11 on hd8 already has SELinux and background process issues. Adding a proot-based Nix environment on top would compound the problems.

---

## What COULD work: Supplementary Nix (NOT recommended)

A theoretical approach: install Nix INSIDE existing Termux, not via nix-on-droid's separate app. Use it only for CLI tools, leaving Termux services untouched:

```bash
# Inside Termux (not nix-on-droid):
pkg install proot
curl -L https://nixos.org/nix/install | sh  # (would need adaptation for Android)
```

But this:

- Requires proot anyway (same fragility issues)
- Adds ~500 MB of Nix store
- Duplicates package management (apt for system, nix for tools)
- Creates TWO self-heal targets instead of one

The complexity-to-value ratio is terrible.

---

## Recommendation

**Do not integrate nix-on-droid.** The stayturgid stack is deeply coupled to Termux's process model, boot hooks, API bridge, and self-heal architecture. Nix-on-droid is a separate ecosystem that doesn't solve any of stayturgid's hard problems (Shizuku crashes, sshd down file, Samsung process freezer, Fire OS quirks) while creating new ones (proot fragility, no fleet management, prototype quality).

The package management issues nix-on-droid would fix (mirror pinning, PATH leaks) have already been solved by self-heal code written in this session:

- `ensure_termux_mirror()` — re-pins mirror every 5 minutes
- `ensure_shell_profile_path()` — removes Mac PATH from profiles every 5 minutes

These are 20-line Python functions that work. Replacing them with a 500+ MB Nix proot environment would be a massive regression in reliability and maintainability.

**If you want deterministic package management on Android, wait for Termux to add Nix support natively — or contribute it yourself. The nix-on-droid prototype is not production-ready for fleet use.**
