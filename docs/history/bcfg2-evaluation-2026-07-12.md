# Bcfg2 — Integration Evaluation

**Date:** 2026-07-12
**Analyst:** DeepSeek V4 Pro
**Source:** https://github.com/Bcfg2/bcfg2 (93 stars, 59 forks, 8,609 commits, BSD 2-clause)
**Local:** `~/src/bcfg2/`

---

## What Bcfg2 is

Bcfg2 is a Python-based configuration management system from Argonne National Laboratory (Mathematics and Computer Science Division). It helps system administrators produce "consistent, reproducible, and verifiable descriptions of their environment." It is the fifth generation of config management tools developed there.

**Architecture:** Server/client model with XML-based configuration descriptions. The server stores desired state; clients fetch it and verify/enforce locally. Plugin architecture for package managers, services, and file management.

**Codebase:** 203 Python files, 46,338 lines (93.3% Python). Last release: v1.3.5 (September 2014). Current version in git: 1.4.0pre2.

---

## What Bcfg2 has that stayturgid could use

### 1. Launchd management (macOS)

Bcfg2 has a `launchd.py` client tool (145 lines) that manages macOS launchd services:

- `VerifyService` — checks if a launchd service is loaded and running
- `InstallService` — loads/starts or unloads/stops a service
- `FindExtra` — finds launchd services not in the config (drift detection)
- `BundleUpdated` — reloads a plist after changes

This is exactly the kind of "verify only" tool the user is interested in — checking that launchd state matches desired state.

### 2. Package management plugins

Bcfg2 has client tools for:

- `APT.py` (253 lines) — Debian/Ubuntu APT
- `RPM.py` (2,229 lines) — Red Hat RPM
- `YUM.py` (1,116 lines) — YUM
- `HomeBrew.py` (54 lines) — macOS Homebrew
- `MacPorts.py`, `Pacman.py`, `Portage.py`, `Pkgng.py`, etc.
- `APK.py` (54 lines) — **Alpine Linux APK, NOT Android APK**

The `APK.py` tool handles Alpine Linux packages, not Android. There is no Android package management support.

### 3. Service management

Bcfg2 has client tools for `launchd`, `Systemd`, `SYSV`, `Upstart`, `SMF`, `Chkconfig` — most init systems. No Android/Termux service management.

### 4. Verification model

Bcfg2's core concept is "describe desired state → verify current state → report drift." This is what the user wants: a secondary verification system alongside Ansible.

---

## Code quality and maintainability assessment

### Structure

- **203 files, 46k lines** — manageable size
- **Plugin architecture** — extendable, but plugin interface is complex (multiple inheritance with Plugin, Structure, StructureValidator, XMLDirectoryBacked)
- **XML-based config** — verbose, harder to read than Ansible YAML
- **Genshi templating** — deprecated! The code itself warns: "Genshi XML namespace is deprecated"
- **lxml dependency** — requires compiled C extension on each device

### Python compatibility

- **Python 2-first design** — setup.py uses `execfile()` (Python 2 only), has `if sys.version_info[:2] < (2, 6)` shims
- **No Python 3 migration** — code has Python 2 constructs throughout
- **Would not run on Termux Python 3.9+** — major porting effort needed

### Activity level

- **Last release: September 2014** — 12 years without a release
- **Last commit: November 2023** — 2.5 years ago, and it was a minor IRC update
- **5 commits in 2023** — all trivial (IRC network, timezone, pip index URL)
- **93 stars, 59 forks** — small community, nearly inactive
- **19 open issues, 18 open PRs** — unmaintained backlog

### Dependencies (all stale)

| Dependency    | Last release | Status                         |
| ------------- | ------------ | ------------------------------ |
| lxml          | Active       | Only maintained dependency     |
| genshi        | 2012         | Deprecated, replaced by Jinja2 |
| python-daemon | 2019         | Stale, Python 2-era            |
| CherryPy      | Variable     | Framework dependency           |
| Django ORM    | —            | For database models            |

---

## Hard blockers for stayturgid integration

### #1: Abandonware

The project received its last release **before Android 5 existed**. It has not been meaningfully maintained since 2014. The git activity is housekeeping (IRC, timezone). There is no maintainer actively developing new features or fixing bugs. For a fleet management system that needs to stay reliable, depending on abandonware is a non-starter.

### #2: Python 2-era code

The codebase is Python 2 with partial Python 3 compatibility. It uses `execfile()`, `print` statements in some places, and Python 2-specific module paths. Termux ships Python 3.9+ only. Porting 46k lines of Python 2 code to Python 3 is not worth the effort.

### #3: No Android support

Bcfg2 has tools for macOS, Linux, FreeBSD, Solaris — but zero Android support:

- No Termux package management
- No runit/service management
- No Shizuku or ADB integration
- No ARM-specific handling
- No Android SELinux awareness

### #4: Wrong architecture for fleet

Bcfg2's server/client model is designed for managing servers in a datacenter (push-based, XML configs on a central server, clients pull). stayturgid operates over SSH to devices that are intermittently connected behind NAT (Tailscale). The Bcfg2 model doesn't fit.

### #5: XML configuration (not Ansible-compatible)

stayturgid uses Ansible YAML for configuration. Bcfg2 uses XML. Running both means maintaining two separate configuration description languages for the same fleet — doubling the maintenance burden and creating drift between the two.

### #6: Heavyweight client

Bcfg2 requires Python + lxml + genshi + other deps on each managed device. For stayturgid's Android devices, this means installing 50+ MB of Python packages on top of Termux, just for verification. The verification script would be heavier than the services it's verifying.

---

## The "verify only" idea is good — Bcfg2 is the wrong vehicle

Bcfg2's verification model (describe state → verify → report drift) is conceptually what the user wants: a secondary check that Ansible's desired state matches reality. However:

1. **stayturgid already does this** — `make verify` runs `tests/device_tier.py` which checks 16 things per device. The `firerpa_health_monitor.py` adds a second channel. The repair script's STATUS line is a third verification.

2. **A lightweight verification script would be better** — 100-200 lines of Python that reads Ansible inventory, SSHes to each device, and compares running state against desired state. No new dependencies, no new config format, no new daemon.

3. **The Ansible ecosystem has this covered** — `ansible-playbook --check --diff` IS the verification mode. Resources would be better spent extending the existing verify tests than integrating abandonware.

---

## What we COULD build instead

A lightweight "stayturgid-verify" that:

- Reads `ansible/inventory/hosts.yml` for desired state
- SSHes to each device (using existing SSH CA)
- Checks: packages installed, services running, files present, permissions correct
- Reports drift in a structured format (JSON or text)
- Runs from Mac as a launchd agent alongside existing monitors
- ~200 lines of Python, no external dependencies beyond what stayturgid already has

This gives the "verify only second opinion" the user wants without importing 46k lines of Python 2 abandonware.

---

## Recommendation

**Do not integrate Bcfg2.** It is abandonware (last release 2014, before Android 5), Python 2-era code, has zero Android support, and its server/client architecture doesn't fit stayturgid's SSH-based fleet model. The verification concept it embodies is already covered by `make verify`, `ansible-playbook --check`, and the FIRERPA health monitor.

If a lightweight secondary verification system is desired, build one from scratch using stayturgid's existing Python libraries and Ansible inventory — ~200 lines of code vs. importing 46k lines of dead code.
