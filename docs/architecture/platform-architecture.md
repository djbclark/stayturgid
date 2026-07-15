# Platform Architecture: Identity, Topology, and Control Plane

> **Status:** Draft — replaces
> [site-identity-source-of-truth-2026-07-14.md](../research/site-identity-source-of-truth-2026-07-14.md),
> [multi-site-topology.md](multi-site-topology.md), and
> [unified-architecture-synthesis.md](../research/unified-architecture-synthesis.md).
> Once approved, those three documents become historical references under
> `docs/research/`.
>
> **Audience:** Operator-architects and autonomous agents implementing this
> system. Every decision in this document is traceable to either a project
> constraint, an Ansible community best practice, or an explicit operator
> choice.
>
> **Companion docs:**
> [core-architecture.md](core-architecture.md) (code layout, deploy flow,
> connection tiers),
> [ADR-001](adr/001-ansible-boundary.md) (Ansible boundary),
> [ADR-004](adr/004-self-heal-vs-ansible-coverage.md) (self-heal coverage),
> [adoption.md](../ansible/collections/adoption.md) (consuming collections at
> another site),
> [coding-rules.md](../coding-rules.md),
> [hacking.md](../hacking.md) (device setup walkthrough).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Single Source of Truth](#2-the-single-source-of-truth)
3. [The Canonical Site Inventory](#3-the-canonical-site-inventory)
4. [The Projection Pipeline](#4-the-projection-pipeline)
5. [Secrets Management](#5-secrets-management)
6. [The O-V-G-O Control Plane](#6-the-o-v-g-o-control-plane)
7. [Multi-Site Architecture](#7-multi-site-architecture)
8. [Trust Model](#8-trust-model)
9. [Control-Node OS Matrix](#9-control-node-os-matrix)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Decisions Requiring Operator Input](#11-decisions-requiring-operator-input)
12. [Appendix A: Seed Alias Census](#appendix-a-seed-alias-census)
13. [Appendix B: External References](#appendix-b-external-references)
14. [Appendix C: File and Code Index](#appendix-c-file-and-code-index)

---

## 1. Executive Summary

`stayturgid` keeps wireless ADB (port 5555), Shizuku, and SSH alive on
unrooted Android phones across reboots. A Mac control node orchestrates a
fleet of Android devices over Tailscale using Ansible, with four independent
connection tiers (ADB, SSH, CFEngine, FIRERPA gRPC) and multiple on-device
self-heal layers (Termux boot loop, AutoJs6 watchdog, CFEngine agent, repair
bridge).

This document defines three interlocking concerns:

1. **Identity and Configuration** — Where facts about the fleet live, how they
   flow to consumers, and how secrets are separated from configuration.
2. **The Control Plane** — The O-V-G-O stack (OpenObserve, VictoriaMetrics,
   Grafana, OliveTin) that replaces bespoke Python monitors and the Flask
   dashboard with industry-standard observability and operator tooling.
3. **Multi-Site Portability** — How the public `stayturgid` repository stays
   generic while production identity lives in a private site overlay.

### Guiding Principles

- **One fact, one place.** Every identity fact (hostname, IP, serial) is
  declared exactly once in the Ansible inventory. Everything else is generated.
- **Inventory is the data model.** Playbooks say _what to do_; inventory says
  _where, to whom, and how_. This is the
  [Ansible community's recommended separation](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html).
- **Push metrics, don't poll.** Devices push their own health telemetry via
  Vector to central time-series stores, rather than relying on fragile
  Mac-to-device SSH probes.
- **Fail closed, heal open.** Self-heal mechanisms on the device run
  independently of the control plane. The control plane observes and assists;
  the device is self-sufficient.
- **No secrets in version control.** Secret _declarations_ live in
  [`secretspec.toml`](../../secretspec.toml); actual values live in provider
  backends (macOS Keychain, dotenv files outside git, CI environment).

---

## 2. The Single Source of Truth

### 2.1 The Four Kinds of Data

Every piece of configuration data in `stayturgid` belongs to exactly one of
four categories. The authority for each category is different, and mixing them
is the root cause of configuration drift.

| Kind                       | Examples                                                                                                   | Authority                                              | Mutability       |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------- |
| **Declared site identity** | Device alias, USB serial, Tailscale IP, management port, device label, taxonomy groups                     | Site Ansible inventory (`ansible/inventory/hosts.yml`) | Operator edit    |
| **Generic product policy** | Default ADB port (5555), SSH port (8022), package lists, scrape intervals, self-heal timer cycles          | Role defaults + generic `group_vars/`                  | Code review      |
| **Observed runtime state** | DHCP LAN address, mDNS endpoint, device online/offline, app versions, battery level, last scrape timestamp | Runtime state store (`~/.config/stayturgid/state/`)    | Automated update |
| **Secrets**                | API tokens, SSH private keys, ADB keys, Play Store credentials                                             | [SecretSpec](https://secretspec.dev) providers         | Operator rotate  |

This taxonomy is adapted from the
[Ansible community's variable hierarchy](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
and the
[NetBox "Source of Truth" philosophy](https://netboxlabs.com/blog/netbox-the-source-of-truth-for-network-automation/)
where the canonical data model owns _declared_ state and observations live in a
separate, non-authoritative store.

### 2.2 What "Single Source of Truth" Means in Practice

Single source of truth does **not** mean a single file is read directly by
every program. It means:

1. **One canonical location** declares each fact (the inventory).
2. **A deterministic pipeline** transforms inventory data into the formats
   that consumers need (projections).
3. **No consumer may independently maintain** its own copy of an inventory
   fact. If a program needs a device's Tailscale IP, it reads a projection
   that was generated from inventory — it does not hardcode `100.123.218.30`.
4. **Validation tooling** rejects new code that introduces hardcoded
   production identity literals.

This is the same principle behind Kubernetes
[Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
(base + overlays), Helm values files, and
[CUE's](https://cuelang.org/docs/usecases/) constraint-based configuration:
separate the _data model_ from the _templates_ that consume it.

### 2.3 What Already Works

The project is approximately 60% of the way to a clean single source of truth:

| Component                                         | Status                          | Notes                                                               |
| ------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------- |
| `ansible/inventory/hosts.yml`                     | ✅ Authoritative                | Declares aliases, Tailscale IPs, USB serials, LAN IPs, labels       |
| `ansible/inventory/group_vars/`                   | ✅ Authoritative                | Taxonomy quirks by vendor/model/OS version                          |
| `ansible/roles/control_node/tasks/agents.yml`     | ✅ Generates from inventory     | Renders `devices.conf`, SSH fragment, launchd agents from templates |
| `control/lib/stayturgid_device.py`                | ✅ Reads projection             | Parses `devices.conf` for device resolution                         |
| `secretspec.toml`                                 | ✅ Declares secret names        | All secret metadata; values in providers                            |
| `control/cfengine/cf-runagent.cf`                 | ❌ Hardcoded IPs                | Embeds production Tailscale IPs directly                            |
| `AGENTS.md`, `docs/hacking.md`, `docs/handoff.md` | ❌ Duplicated identity          | Fleet table duplicates IPs and serials from inventory               |
| Several FIRERPA tools, tests, and plan documents  | ❌ Scattered literals           | Production addresses and serials appear in active code              |
| `device/termux/py/stayturgid_peer_bootstrap.py`   | ❌ Hardcoded `DEFAULT_SSH_USER` | `djbclark` instead of reading from inventory/projection             |
| `ansible_collections/*/peers.json.j2`             | ❌ Hardcoded `ssh_user`         | `djbclark` instead of `{{ ansible_user }}`                          |

### 2.4 Representative Gaps (Seed Alias Scan)

A scan on 2026-07-14 found **177 files with 1,140 matching lines** containing
production device aliases (`s24`, `p7a`, `hd8`):

| Classification            | Files | Lines |
| ------------------------- | ----: | ----: |
| Active code/config        |    84 |       |
| Documentation/research    |    39 |       |
| Tests                     |    33 |       |
| Session history           |    12 |       |
| Plans                     |     3 |       |
| Inventory (authoritative) |     3 |       |
| Examples                  |     3 |       |

The active code/config category is the priority. Documentation and history
files will be addressed during the upstream scrub (§7.4).

### 2.5 Active Code/Config Violations Breakdown

The following active files contain hardcoded production literals (`s24`, `p7a`, `hd8`, or their respective Tailscale IPs and USB serials), which must be refactored to read from the site inventory projection or structured variables:

| File Path                                         | Gaps Identified                                   | Classification / Action Required                                   |
| :------------------------------------------------ | :------------------------------------------------ | :----------------------------------------------------------------- |
| `control/cfengine/cf-runagent.cf`                 | Hardcoded Tailscale IPs for all three devices     | `violation` — Migrate to Jinja2 template rendered via Ansible      |
| `control/landing/services.json`                   | Hardcoded hostnames, Tailscale IPs, LAN IPs       | `violation` — Separate static catalog from dynamic discovery state |
| `control/landing/discover.py`                     | Reference to production aliases and IPs           | `violation` — Read from inventory projections                      |
| `control/bin/cf-run.sh`                           | Embedded `s24`, `p7a`, `hd8` aliases              | `violation` — Require explicit target host argument                |
| `control/bin/firerpa_heal.py`                     | Reference to production aliases and IPs           | `violation` — Resolve addresses dynamically using `resolve_adb`    |
| `control/bin/firerpa_health_monitor.py`           | Reference to production aliases and IPs           | `violation` — Resolve addresses dynamically                        |
| `control/tools/autojs6/deploy.py`                 | Default arguments and aliases `s24`, `p7a`, `hd8` | `violation` — Make targets required CLI arguments                  |
| `control/tools/autojs6/enable_autojs6_shizuku.py` | Reference to production aliases                   | `violation` — Pass as arguments                                    |
| `control/tools/autojs6/grant_shizuku.py`          | Reference to production aliases                   | `violation` — Pass as arguments                                    |
| `control/tools/autojs6/run_test.py`               | Default targets `s24`, `p7a`, `hd8`               | `violation` — Make targets required CLI arguments                  |
| `control/tools/autojs6/set_automation_mode.py`    | Reference to production aliases                   | `violation` — Pass as arguments                                    |
| `control/tools/autojs6/setup_autojs6.py`          | Reference to production aliases                   | `violation` — Pass as arguments                                    |
| `control/tools/autojs6/start_watchdog.py`         | Reference to production aliases                   | `violation` — Pass as arguments                                    |
| `control/tools/autojs6/test_tailscale_down.py`    | Default targets and serials                       | `violation` — Parametrize with arguments                           |
| `control/tools/obtainium/*.py`                    | Reference to production aliases                   | `violation` — Require CLI arguments                                |
| `control/tools/play/*.py`                         | Reference to production aliases                   | `violation` — Require CLI arguments                                |
| `device/termux/py/stayturgid_peer_help.py`        | References to sibling hostnames                   | `violation` — Read peers list from `peers.json` projection         |

---

## 3. The Canonical Site Inventory

### 3.1 Schema

The site Ansible inventory is the **sole authority** for non-secret, declared
site identity. The file is
[`ansible/inventory/hosts.yml`](../../ansible/inventory/hosts.yml).

**Per-device required fields:**

| Field                | Type      | Example          | Constraint                                              |
| -------------------- | --------- | ---------------- | ------------------------------------------------------- |
| `inventory_hostname` | string    | `s24`            | Lowercase ASCII alias; immutable logical device ID      |
| `ansible_host`       | IPv4/IPv6 | `100.123.218.30` | Stable management address (Tailscale IP or MagicDNS)    |
| `device_usb_serial`  | string    | `RFCX219CHKA`    | USB serial from `adb devices`; optional if no USB route |
| `device_label`       | string    | `Galaxy S24`     | Human-readable device name                              |
| `device_lan_ip`      | IPv4      | `192.168.68.54`  | DHCP hint; non-authoritative, may be stale              |

**Per-fleet group variables** (in
[`group_vars/stayturgid.yml`](../../ansible/inventory/group_vars/)):

| Variable                       | Type    | Default | Notes                                              |
| ------------------------------ | ------- | ------- | -------------------------------------------------- |
| `ansible_port`                 | integer | `8022`  | Termux sshd port                                   |
| `ansible_user`                 | string  | —       | SSH user (`djbclark` in prod, `termux` in example) |
| `ansible_python_interpreter`   | path    | —       | Termux Python path                                 |
| `ansible_ssh_private_key_file` | path    | —       | Path to Termux SSH key                             |
| `stayturgid_device_id`         | string  | —       | `{{ inventory_hostname }}`                         |
| `stayturgid_automation_mode`   | string  | —       | `autojs6` or `none`                                |

**Taxonomy groups** describe device characteristics. Group membership controls
which `group_vars/` quirk files apply. The variable precedence hierarchy
follows Ansible's standard order
([docs](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)):

```
role defaults < all < android_* < vendor_* < oneui_* < model_* < host_vars
```

Current taxonomy groups: `android_16`, `android_11`, `vendor_google`,
`vendor_samsung`, `vendor_amazon`, `oneui_7`, `model_pixel_7a`,
`model_galaxy_s24`, `model_kindle_hd8`.

### 3.2 Normalization Rules

1. **Aliases** are lowercase ASCII (e.g., `s24`, not `S24` or `Galaxy-S24`).
2. **USB serials** are exact strings from `adb devices`. Optional only when a
   device has no USB route (e.g., remote-only Tailscale devices).
3. **Stable management address** (`ansible_host`) may be an IP address or a
   DNS/MagicDNS name. The operator decides (see §11).
4. **LAN addresses** are informational hints. DHCP may change them. They are
   never used as primary management addresses.
5. **Ports** are integers; fleet defaults live in `group_vars/`, not per-host.
6. **Taxonomy** is expressed via group membership, not per-host variables.
7. **No secrets in inventory.** Ever. Not even "non-sensitive" tokens. If it
   could be rotated or revoked, it belongs in SecretSpec.

### 3.3 The Normalized Inventory Interface

Consumers should not parse `hosts.yml` directly. Instead, use Ansible's
built-in inventory export:

```bash
ansible-inventory -i ansible/inventory/hosts.yml --list
```

This produces a deterministic JSON representation of all hosts, groups, and
variables that any language can consume.

**Proposed:** Create `control/lib/site_identity.py` — a typed Python module
that:

1. Calls `ansible-inventory --list` and caches the result.
2. Exposes immutable `dataclass` records: `Site`, `ControlNode`, `Device`.
3. Validates the schema (required fields, IP format, no duplicates).
4. Provides deterministic host ordering for tests and templates.
5. Uses only the Python standard library (`dataclasses`, `ipaddress`, `json`,
   `pathlib`, `subprocess`).

This module becomes the single import for all Python code that needs device
identity, replacing ad-hoc parsing of `devices.conf` in individual scripts.

### 3.4 Validation Tooling

**Proposed:** Create `control/bin/validate_site_identity.py` that enforces:

- **Schema:** Required fields present, valid IP format, no duplicate aliases
  or serials.
- **Anti-drift:** No production identity literals (`100.123.218.30`,
  `RFCX219CHKA`, `s24` outside approved contexts) in active code.
- **Projection freshness:** Generated files match current inventory (checksum
  comparison).
- **Secrets hygiene:** No secret-shaped values (tokens, long hex strings) in
  inventory files.

**Classification system** for production literals:

| Classification       | Allowed? | Example                                          |
| -------------------- | -------- | ------------------------------------------------ |
| `authoritative`      | ✅       | `ansible/inventory/hosts.yml`                    |
| `generated-template` | ✅       | `devices.conf.j2` (uses `{{ ansible_host }}`)    |
| `generic-fixture`    | ✅       | Tests using `192.0.2.x` (RFC 5737 TEST-NET)      |
| `historical`         | ⚠️       | Session logs (read-only, no enforcement)         |
| `bootstrap-constant` | ⚠️       | ADB port `5555`, Tailscale CGNAT `100.64.0.0/10` |
| `violation`          | ❌       | Hardcoded `100.123.218.30` in a Python script    |

**Test fixtures** must use
[RFC 5737](https://www.rfc-editor.org/rfc/rfc5737) reserved addresses:
`192.0.2.0/24` (TEST-NET-1), `198.51.100.0/24` (TEST-NET-2),
`203.0.113.0/24` (TEST-NET-3). Hostnames must use `.example` per
[RFC 2606](https://www.rfc-editor.org/rfc/rfc2606). Serial numbers must
use `EXAMPLE-SERIAL-*`.

### 3.5 Bootstrap-Safe Constants

Some production-adjacent values are legitimate and must not be flagged by the
validator. These are protocol constants that any site would use:

- Loopback: `127.0.0.1`, `::1`
- ADB default port: `5555`
- SSH default port: `8022` (Termux convention)
- CFEngine port: `5308`
- FIRERPA gRPC port: `65000`
- Tailscale CGNAT range: `100.64.0.0/10`
- Generic Android package names: `com.termux`, `org.nicholasmole.shizuku`, etc.
- Repository URLs: `https://github.com/djbclark/stayturgid.git`
- IETF documentation networks (for test fixtures)

These are maintained in a small, reviewed allowlist within the validator.

---

## 4. The Projection Pipeline

### 4.1 What is a Projection?

A **projection** is a generated configuration file whose content is derived
entirely from the Ansible inventory. Projections are not authoritative — they
are outputs of a deterministic transformation. If a projection is deleted, it
can be perfectly regenerated from the inventory.

This is the same concept as:

- [Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
  generating Kubernetes manifests from base + overlays
- [Jsonnet](https://jsonnet.org/learning/getting_started.html) or
  [CUE](https://cuelang.org) generating JSON/YAML from a programmable data
  model
- Ansible's own
  [Jinja2 template module](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/template_module.html)
  rendering config files from variables

In `stayturgid`, the Jinja2 template module is the projection engine. The
inventory is the data model. Templates in
`ansible/roles/control_node/templates/` are the transformation rules.

### 4.2 Current Projections

| Projection                | Template                                                                                          | Consumer                                           | Rendered by                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------- | ----------------------------------------------------------------- |
| `devices.conf`            | [`devices.conf.j2`](../../ansible/roles/control_node/templates/devices.conf.j2)                   | `control/lib/stayturgid_device.py`, Python scripts | [`agents.yml`](../../ansible/roles/control_node/tasks/agents.yml) |
| SSH config fragment       | [`ssh_config_stayturgid.j2`](../../ansible/roles/control_node/templates/ssh_config_stayturgid.j2) | `ssh`, `scp`, `rsync`                              | `agents.yml`                                                      |
| launchd agent plists      | `com.stayturgid.*.plist.j2`                                                                       | macOS `launchd`                                    | `agents.yml`                                                      |
| CFEngine `cf-runagent.cf` | ❌ **Currently hardcoded** — needs migration to template                                          | `cf-runagent`                                      | ❌ Manual                                                         |

### 4.3 Planned Projections (O-V-G-O Stack)

When the O-V-G-O stack is deployed (§6), additional projections will be
generated from the same inventory:

| Projection                 | Template (proposed)            | Consumer                  | Notes                                        |
| -------------------------- | ------------------------------ | ------------------------- | -------------------------------------------- |
| OliveTin `config.yaml`     | `olivetin-config.yaml.j2`      | OliveTin web UI           | One button per device per `just` recipe      |
| Vector edge config         | `vector.toml.j2`               | Vector agent in Termux    | Per-device labels, sink endpoints            |
| Grafana provisioning JSON  | `grafana-provisioning.json.j2` | Grafana auto-provisioning | Data source + dashboard definitions          |
| VictoriaMetrics scrape cfg | `vmagent-scrape.yml.j2`        | VictoriaMetrics vmagent   | If pull-mode scraping is used alongside push |

### 4.4 Projection Lifecycle

Every generated file must follow this lifecycle:

```
site inventory
  → ansible-inventory --list (JSON)
  → strict schema validation (validate_site_identity.py)
  → Jinja2 template rendering (ansible template module)
  → output validation (syntax check of generated file)
  → atomic file replacement (ansible copy/template with backup)
  → service reload (handler notification)
  → record source commit SHA + file checksum in state
```

Every generated file must carry a header:

```
# Generated by stayturgid from site inventory; do not edit.
# Source: ansible/inventory/hosts.yml @ <commit-sha>
# Schema: devices.conf v2
# Regenerate: just deploy-mac
```

### 4.5 Runtime Discoveries (Non-Authoritative State)

Some facts are discovered at runtime and are explicitly **not** part of the
inventory:

- Current DHCP LAN IP (may differ from `device_lan_ip` hint)
- mDNS endpoint resolution
- Device online/offline status
- Installed app versions
- Battery level, WiFi state, signal strength
- Last successful scrape timestamp

These observations are stored in
`~/.config/stayturgid/state/fleet-health/<host>` as timestamped JSON files.
They are caches, not authorities. Background monitors may write them, but they
must never edit Git-tracked files.

**Address resolution policy** (used by `control/lib/resolve_adb.py`):

1. USB serial (direct cable)
2. Fresh LAN observation (from state store)
3. Declared `device_lan_ip` hint (from inventory)
4. Stable Tailscale IP (`ansible_host`)
5. Other channels (FIRERPA gRPC, CFEngine)

---

## 5. Secrets Management

### 5.1 SecretSpec

[SecretSpec](https://secretspec.dev) is a declarative secrets management tool
by [Cachix](https://github.com/cachix/secretspec). It separates secret
_declaration_ (what secrets exist, what they're for) from secret _storage_
(where the actual values live).

**How it works in `stayturgid`:**

1. [`secretspec.toml`](../../secretspec.toml) declares every secret the
   project needs — name, description, whether it's required, and default
   paths. This file is safely committed to Git.
2. Actual secret values live in **provider backends** (macOS Keychain, dotenv
   files outside Git, CI environment variables). They are never committed.
3. `just secretspec-check` (or `secretspec check`) validates that all
   required secrets are available before a deploy.
4. `secretspec run -- <command>` injects secrets into a subprocess's
   environment at runtime.

### 5.2 Current Secret Declarations

From [`secretspec.toml`](../../secretspec.toml):

| Secret                   | Required | Provider                             | Purpose                   |
| ------------------------ | -------- | ------------------------------------ | ------------------------- |
| `TELEGRAM_BOT_TOKEN`     | ✅       | `~/.hermes/.env`                     | Hermes notifications      |
| `TELEGRAM_ALLOWED_USERS` | ❌       | `~/.hermes/.env`                     | Telegram allowlist        |
| `GEMINI_API_KEY`         | ❌       | `~/.config/stayturgid/gemini.env`    | VLM cloud checks          |
| `ANTHROPIC_API_KEY`      | ❌       | `~/.config/stayturgid/anthropic.env` | VLM cloud checks          |
| `FIRERPA_API_KEY`        | ❌       | `~/.config/stayturgid/firerpa.env`   | gRPC backup channel       |
| `FIRERPA_CERTIFICATE`    | ❌       | `~/.config/stayturgid/firerpa.pem`   | gRPC/SSH certificate      |
| `SSH_TERMUX_KEY`         | ❌       | `~/.ssh/termux_key`                  | Fleet SSH key             |
| `SSH_CA_KEY`             | ❌       | `~/.ssh/stayturgid_ca`               | SSH Certificate Authority |
| `FLEET_ADBKEY`           | ❌       | `~/.config/stayturgid/adbkey`        | Fleet ADB key             |
| `GITHUB_TOKEN`           | ❌       | `gh auth login`                      | GitHub CLI                |

### 5.3 Secrets Architecture Principles

1. **`secretspec.toml` is the declaration layer.** It says _what_ secrets exist
   and _where_ programs expect to find them. It contains no actual values.
2. **Provider backends store values.** Currently dotenv files (mode `0600`) and
   file paths. Future migration target: macOS Keychain for workstation
   secrets (see §11).
3. **Ansible Vault is not used.** The project uses SecretSpec instead of
   [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/)
   because vault-encrypted files produce opaque Git diffs and require vault
   passwords at every playbook run. SecretSpec's declaration-only model
   keeps Git diffs clean.
4. **No secret-shaped values in inventory.** The Telegram user ID in
   `hosts.yml` (`stayturgid_hermes_telegram_allowed_users`) is a site fact,
   not a secret, but it should move to the site overlay (§7) because it is
   operator-specific.

### 5.4 Comparison of Secrets Approaches

For reference, here is how `stayturgid`'s approach compares to alternatives:

| Feature              | SecretSpec (current)        | Ansible Vault                                                                  | SOPS                             | External (Vault/AWS SM)        |
| -------------------- | --------------------------- | ------------------------------------------------------------------------------ | -------------------------------- | ------------------------------ |
| Git diffs            | Clean (no secrets in Git)   | [Opaque blobs](https://docs.ansible.com/ansible/latest/vault_guide/vault.html) | Keys visible, values encrypted   | N/A (not in Git)               |
| Setup complexity     | Low (`brew install`)        | Built-in                                                                       | Medium                           | High (infrastructure required) |
| Dynamic rotation     | Manual                      | Manual                                                                         | Manual                           | Automatic                      |
| Audit trail          | Via provider backend        | None                                                                           | Limited                          | Full                           |
| Fit for `stayturgid` | ✅ Designed for small teams | ❌ Opaque diffs, password management                                           | ⚠️ Overengineered for this scale | ❌ Infrastructure overhead     |

---

## 6. The O-V-G-O Control Plane

### 6.1 Architecture Overview

The **O-V-G-O** stack replaces the legacy bespoke Python monitors and Flask
dashboard with industry-standard, single-binary observability and operations
tooling:

- **O** — [OpenObserve](https://openobserve.ai/) (logs and traces)
- **V** — [VictoriaMetrics](https://victoriametrics.com/) (time-series metrics)
- **G** — [Grafana](https://grafana.com/) (unified dashboards, read UI)
- **O** — [OliveTin](https://olivetin.app/) (operational web UI, write/execute UI)

```text
[Android Fleet (Termux)]
   └── Logcat Daemon Script ──> local file ──> Vector (aarch64)
   └── Scheduled exec (Battery/WiFi) ────────┘
                                                │ (Intermittent / Gzip JSON)
                                                ▼
[Central Infrastructure (Mac Control Node)]
   ├── Ingestion ──> OpenObserve (Logs/Traces) & VictoriaMetrics (Metrics)
   ├── Read UI   ──> Grafana (Unified Dashboards)
   └── Write UI  ──> OliveTin (Web buttons calling local 'just' recipes)
```

All four components are native single-binary programs with negligible RAM
footprints. No Docker, no JVM. Installed via Homebrew on macOS.

### 6.2 Why O-V-G-O (Not ONGAO, Not ELK)

An earlier research document
([ongao-rollout-plan.md](../operations/plans/ongao-rollout-plan.md)) proposed
**Netdata** for metrics and **Aurora SRE** for AIOps. The O-V-G-O stack
supersedes that plan for these reasons:

| Concern           | Netdata                                                              | VictoriaMetrics                                       | Decision            |
| ----------------- | -------------------------------------------------------------------- | ----------------------------------------------------- | ------------------- |
| Fleet aggregation | Per-host dashboards; needs Netdata Cloud or streaming for fleet view | Purpose-built TSDB; native PromQL; fleet-wide queries | **VictoriaMetrics** |
| Grafana compat    | Limited; separate UI                                                 | Drop-in Prometheus data source                        | **VictoriaMetrics** |
| Resource use      | Higher (built-in ML, per-host agent)                                 | Single binary, ~30MB RAM for small fleet              | **VictoriaMetrics** |
| Edge push         | Streaming protocol                                                   | Standard `remote_write` (Prometheus ecosystem)        | **VictoriaMetrics** |

Aurora SRE (local LLM via Ollama + LangGraph) remains a valid future
enhancement (see [on-device-llm.md](../research/experiments/on-device-llm.md))
but adds significant complexity. It is **not part of the core O-V-G-O stack**.
Implement it only after the base stack is stable and the operator explicitly
requests it.

### 6.3 Component Details

#### 6.3.1 OpenObserve (Logs and Traces)

- **Binary:** Native `arm64` (macOS) from
  [GitHub releases](https://github.com/openobserve/openobserve/releases).
- **Role:** Ingests structured logs from Vector, stores as Parquet files on
  local disk.
- **Key advantage:** Accepts out-of-order logs gracefully. When a device
  reconnects after days offline and dumps a massive backlog, OpenObserve
  handles it without the chronological rejection errors that
  [Grafana Loki](https://grafana.com/docs/loki/latest/) would produce.
- **API:** HTTP `/_json` endpoint for log ingestion from Vector.

#### 6.3.2 VictoriaMetrics (Metrics)

- **Install:** `brew install victoriametrics`.
- **Binary:** Single-binary TSDB, speaks native PromQL.
- **Role:** Accepts metrics from Vector via `remote_write` (standard
  Prometheus protocol). Stores battery levels, WiFi state, scrape freshness,
  custom health metrics from the fleet.
- **Grafana integration:** Add as a Prometheus data source. Existing PromQL
  queries and community dashboards work unchanged.
- **Reference:**
  [VictoriaMetrics single-node docs](https://docs.victoriametrics.com/single-server-victoriametrics/).

#### 6.3.3 Grafana (Unified Dashboards)

- **Install:** `brew install grafana`.
- **Role:** Read-only visualization layer. Connects to VictoriaMetrics
  (metrics) and OpenObserve (logs) as data sources. Provides a unified "Fleet
  Control Room" dashboard.
- **Provisioning:** Dashboard and data source definitions are generated as
  projections from the Ansible inventory (§4.3). A new device in inventory
  automatically appears in Grafana.
- **OliveTin integration:** Grafana
  [Data Links](https://grafana.com/docs/grafana/latest/panels-visualizations/configure-data-links/)
  point device-specific panels to OliveTin action endpoints, enabling
  "click-to-heal" from the dashboard.

#### 6.3.4 OliveTin (Operational Web UI)

[OliveTin](https://docs.olivetin.app/) is an open-source tool that provides a
web interface for running predefined shell commands. It replaces the legacy
Flask dashboard's "write" functionality.

- **Install:** `brew install olivetin` or download from
  [GitHub](https://github.com/OliveTin/OliveTin).
- **Configuration:** `config.yaml` is generated from inventory (§4.3). Each
  device gets buttons for common operations:
  - `just --set hosts <alias> deploy`
  - `just --set hosts <alias> verify-heal`
  - `just --set hosts <alias> firerpa-heal`
  - `just health`
- **Security best practices** (from
  [OliveTin docs](https://docs.olivetin.app/)):
  - **Prefer `exec` over `shell`** to prevent shell injection.
  - **Never expose publicly** — run behind Tailscale or Caddy reverse proxy.
  - **Use input validation** — restrict argument types to `ascii_identifier`.
  - **Enable ACLs** for multi-operator sites.
- **Environment:** The OliveTin daemon must run with the same `PATH`,
  `STAYTURGID_ADB`, and virtualenv paths as the operator's terminal session.
  The Ansible-rendered launchd agent handles this.

### 6.4 The Hardened Edge (Vector in Termux)

[Vector](https://vector.dev/) is a high-performance observability data
pipeline written in Rust. It runs natively in Termux as a single
`aarch64-unknown-linux-musl` binary.

**Deployment topology:**
[Agent role](https://vector.dev/docs/setup/deployment/roles/#agent) on each
device, pushing to central
[aggregators](https://vector.dev/docs/setup/deployment/roles/#aggregator)
(VictoriaMetrics + OpenObserve). This follows Vector's recommended
[unified architecture](https://vector.dev/docs/setup/deployment/topologies/#unified).

**Logcat strategy (mitigation applied):**

Do **not** stream `logcat` inside a Vector `exec` block. Instead, deploy a
dedicated Termux boot script that continuously rotates logcat to local files:

```bash
# Runs as a Termux boot hook; Vector watches the output files
shizuku exec logcat -v time -f ~/logs/logcat.log -r 2048 -n 3
```

Point Vector's `file` source at `~/logs/logcat.log`. It handles rotation,
file pointers, and crash recovery natively.

**Metrics strategy:**

Use Vector's `scheduled` `exec` sources to run lightweight CLI commands
(`termux-battery-status`, `/proc/net/dev` stats) every 30–60 seconds. Use
[VRL (Vector Remap Language)](https://vector.dev/docs/reference/vrl/) to
transform output into metrics before shipping.

**Buffering for intermittent connectivity:**

Configure Vector with a filesystem-backed buffer inside Termux's private
storage, capped at 1 GiB:

```toml
[sinks.victoria.buffer]
type = "disk"
max_size = 1073741824 # 1 GiB
when_full = "block"
```

This allows devices to withstand days of offline state and flush the backlog
when connectivity returns.

**Ansible provisioning:**

The existing `termux_userland` role will be extended to deploy the Vector
binary, `vector.toml` (generated from inventory), and the logcat boot hook.
A new device added to inventory gets the full O-V-G-O edge configuration via
`just deploy`.

### 6.5 What O-V-G-O Replaces

| Legacy Component                                          | Replacement                             | Status           |
| --------------------------------------------------------- | --------------------------------------- | ---------------- |
| `control/bin/dashboard.py` (Flask/HTMX on :4097)          | Grafana (read) + OliveTin (write)       | Active → retire  |
| `control/bin/fleet_health_monitor.py` (Mac SSH polling)   | Vector push + VictoriaMetrics freshness | Active → retire  |
| `control/bin/access_monitor.py` (Mac SSH probe)           | Vector push + Grafana alerts            | Active → retire  |
| `control/bin/check_fleet_health.py` (grep flat log files) | Grafana log exploration via OpenObserve | Active → retire  |
| Mac launchd agents for above monitors                     | Launchd agents for O-V-G-O services     | Active → replace |

**Important:** Legacy monitors must not be removed until the O-V-G-O stack is
fully deployed and validated. The transition is phased (§10).

### 6.6 The Network Landing Page and Caddy

The project already uses [Caddy](https://caddyserver.com/) as an HTTPS
reverse proxy, deployed via
[`agents.yml`](../../ansible/roles/control_node/tasks/agents.yml). Caddy
will front all O-V-G-O services behind a single TLS endpoint, with
Tailscale-restricted access.

---

## 7. Multi-Site Architecture

### 7.1 The Two-Repository Model

`stayturgid` is designed to be consumed by operators at other sites. The
repository model follows the
[Kustomize base/overlay pattern](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/),
adapted for Ansible:

| Repository                                  | Visibility | Contains                                                        |
| ------------------------------------------- | ---------- | --------------------------------------------------------------- |
| `stayturgid` (upstream)                     | Public     | Platform code, collections, playbooks, tests, example inventory |
| `stayturgid-site-<operator>` (site overlay) | Private    | Real inventory, secrets, operator notes, session docs           |

The playbooks are the **base**. The inventories are the **overlays**. This is
the Ansible community's standard pattern for multi-site management
([Ansible Tips and Tricks](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html)):
same roles and playbooks, different inventory directories per site.

### 7.2 Adoption Tiers

New operators choose a tier based on their fleet size, control-node OS, and
desired feature set:

| Tier                     | Control Node   | Devices       | Effort | What You Get                                            |
| ------------------------ | -------------- | ------------- | ------ | ------------------------------------------------------- |
| **A — Termux only**      | Any OS w/ SSH  | 1+            | Low    | Repair scripts, boot loop, sshd keepalive; no AutoJs6   |
| **B — Ansible fleet**    | Linux or macOS | 2+            | Medium | Full `site.yml` deploy; manual adb keepalive on Linux   |
| **C — Reference parity** | macOS          | 3+ incl. Fire | High   | launchd health, O-V-G-O dashboards, VLM, Fire peer-help |

**Tier A** is available today via
[`examples/consumer-termux-only/`](../../examples/consumer-termux-only/).

**Tier B** works on Linux with caveats (§9).

**Tier C** is the reference deployment (macOS with full O-V-G-O stack).

### 7.3 New Operator Checklist

1. **Clone upstream:**
   `git clone https://github.com/djbclark/stayturgid.git`

2. **Create site overlay repo:**

   ```bash
   mkdir stayturgid-site-acme && cd stayturgid-site-acme
   git init
   ```

3. **Install tools** per your OS (§9):
   - macOS: `brew install ansible uv just adb`
   - Linux: `sudo apt install ansible python3-pip adb`

4. **Generate SSH identity:**

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/termux_key -N ""
   ```

5. **Generate fleet ADB key:**

   ```bash
   adb keygen ~/.config/stayturgid/adbkey
   ```

6. **Create site inventory** in the site overlay repo:

   ```yaml
   # stayturgid-site-acme/inventory/hosts.yml
   all:
     children:
       stayturgid:
         hosts:
           myphone:
             ansible_host: 100.x.y.z # Your Tailscale IP
             device_usb_serial: YOUR_SERIAL
             device_label: My Pixel 9
         vars:
           ansible_port: 8022
           ansible_user: termux
           ansible_python_interpreter: /data/data/com.termux/files/usr/bin/python
           ansible_ssh_private_key_file: "{{ lookup('env', 'HOME') }}/.ssh/termux_key"
           stayturgid_device_id: "{{ inventory_hostname }}"
           stayturgid_automation_mode: autojs6
   ```

7. **Wire the overlay to upstream** via `ansible.cfg`:

   ```ini
   # stayturgid-site-acme/ansible.cfg
   [defaults]
   inventory = inventory/hosts.yml
   collections_path = ../stayturgid/ansible_collections:~/.ansible/collections
   roles_path = ../stayturgid/ansible/roles

   [ssh_connection]
   pipelining = true
   ```

8. **Install Galaxy collections:**

   ```bash
   ansible-galaxy collection install -r ../stayturgid/ansible/requirements.yml
   ```

9. **Per-device hardware prep** → add to inventory → `just bootstrap-ssh` →
   `just deploy` → one-time UI on device.

### 7.4 What Moves to the Site Overlay

| Content                          | Why it moves                                       |
| -------------------------------- | -------------------------------------------------- |
| Production `hosts.yml`           | Contains real IPs, serials, aliases                |
| `group_vars/stayturgid.yml`      | Contains `ansible_user: djbclark`, real peer paths |
| Operator session docs            | `docs/handoff.md`, `human/*` are operator-specific |
| Live device notes                | Not generic; specific to the operator's fleet      |
| Secret dotenv files              | `play.env`, `firerpa.env` — never in public Git    |
| Telegram user IDs                | Operator-specific identity, not platform policy    |
| `HOSTS=s24` convenience defaults | Not applicable to other sites                      |

### 7.5 What Stays in Upstream

| Content                                   | Why it stays                                    |
| ----------------------------------------- | ----------------------------------------------- |
| `hosts.yml.example`                       | Generic example with RFC 5737 addresses         |
| All collections, playbooks, roles         | Platform code, reusable across sites            |
| `device/` code                            | Runs on any Android, not site-specific          |
| `control/` code                           | Runs on any Mac/Linux control node              |
| Unit tests (using example hostnames)      | Generic; use `192.0.2.x` and `EXAMPLE-SERIAL-*` |
| `docs/hacking.md`, `docs/coding-rules.md` | Platform documentation, not operator-specific   |
| `examples/consumer-*/`                    | Reference deployments for new operators         |

### 7.6 Example Upstream Inventory After Scrub

[`ansible/inventory/hosts.yml.example`](../../ansible/inventory/hosts.yml.example)
currently uses platform-describing hostnames. After the scrub, all upstream
documentation and tests will use these names:

| Example Hostname       | Replaces | Platform Description |
| ---------------------- | -------- | -------------------- |
| `oneui-device`         | `s24`    | Samsung OneUI        |
| `stock-android-device` | `p7a`    | Stock Android/Pixel  |
| `fireos-device`        | `hd8`    | Amazon Fire OS       |

Placeholder addresses use RFC 5737 TEST-NET:

| Example Address | Type         |
| --------------- | ------------ |
| `100.0.0.11`    | Tailscale IP |
| `192.0.2.11`    | LAN IP       |

### 7.7 Code Scrub Targets

| File/Area                                             | Action                                            |
| ----------------------------------------------------- | ------------------------------------------------- |
| `AGENTS.md` fleet table                               | Replace with example hostnames or `hosts.yml` ref |
| `docs/hacking.md`, `docs/handoff.md`                  | Move operator-specific content to site overlay    |
| `control/bin/*.py` default adb path                   | Use `shutil.which("adb")` or `STAYTURGID_ADB`     |
| `peers.json.j2` hardcoded `ssh_user: djbclark`        | Replace with `{{ ansible_user }}`                 |
| `stayturgid_peer_bootstrap.py` `DEFAULT_SSH_USER`     | Read from inventory/projection or require arg     |
| `control/tools/play/obtain_play_aas.py` default email | Remove; require explicit argument                 |
| Tests using `s24`/`p7a`/`hd8`                         | Replace with example hostnames + RFC 5737 IPs     |
| `control/cfengine/cf-runagent.cf`                     | Generate from inventory template                  |

### 7.8 Site Overlay Layout

```
stayturgid-site-acme/
├── README.md
├── ansible.cfg                      # Points inventory + collections to upstream
├── inventory/
│   ├── hosts.yml                    # Real devices, real IPs
│   └── group_vars/
│       └── stayturgid.yml           # Real ansible_user, peer paths
├── docs/
│   └── handoff.md                   # Operator-specific session context
├── human/
│   └── HANDOFF-HUMAN.md             # Operator tasks needing human hands
├── justfile                         # Site-specific just recipes
└── just/
    └── site.just                    # Overlay recipes
```

Wire via environment:

```bash
export STAYTURGID_ROOT=~/src/stayturgid
export ANSIBLE_CONFIG=$PWD/ansible.cfg
```

---

## 8. Trust Model

### 8.1 Current Model: Full Mesh

The current deployment uses a **full-mesh SSH trust model**:

- Every `*.pub` under `stayturgid_ssh_keys_dir` (default `~/.ssh/`) is
  installed on every device.
- Each device's `id_ed25519_fleet` public key is installed on all peers.
- When `stayturgid_ssh_distribute_private_keys: true`, control-node private
  keys are copied to every device.
- **Implication:** Any compromised device can SSH to all siblings.

**Fire peer-help** uses a restricted second channel:

- Fire's `id_ed25519_peerhelp` key can only run
  `stayturgid-peer-help-force.sh` on helper devices via `ForceCommand`.
- This limits blast radius but does not eliminate cross-device trust.

### 8.2 Future: Trust Groups (Proposed)

For multi-operator sites, the full mesh is insufficient. Proposed trust groups:

| Group            | Members         | Access                    |
| ---------------- | --------------- | ------------------------- |
| `trust_sysadmin` | Control node    | All devices, all commands |
| `trust_bob`      | Bob's devices   | Only Bob's devices        |
| `trust_alice`    | Alice's devices | Only Alice's devices      |

Implementation would require:

1. Per-operator SSH key pairs
2. Filtered `authorized_keys` per device (only keys from matching trust group)
3. Trust-aware `peers.json` (only intra-group peer-help)
4. Separate ADB keys per trust group
5. Optional Tailscale ACLs for network-level isolation

**Status:** Design only. Implementation deferred until an operator requests
multi-tenant support. Single-owner sites should use the full mesh.

### 8.3 Recommendations by Site Shape

| Site Shape   | Recommended Trust | Notes                                            |
| ------------ | ----------------- | ------------------------------------------------ |
| Single owner | Full mesh         | Current model; simple and effective              |
| Small team   | Separate keys     | Per-operator SSH keys; shared fleet access       |
| Multi-tenant | Trust groups      | Do not use production mesh; implement §8.2 first |

---

## 9. Control-Node OS Matrix

### 9.1 macOS (Reference Platform)

Fully supported. All features work:

- Ansible deploy via `site.yml`
- Homebrew for all tools (`adb`, `uv`, `just`, `biome`, etc.)
- Background launchd agents for health monitoring
- VLM sidecar for verification gates
- Handsets UI driver for app-store automation
- Fire peer-help target
- O-V-G-O stack services (Homebrew installs)

**Tested:** macOS Sequoia 15.x+, Python 3.14.x, ADB 37.x.

### 9.2 Debian/Ubuntu Linux

Partially supported. Works for fleet management; missing Mac-specific features:

| Feature              | Status | Notes                                  |
| -------------------- | ------ | -------------------------------------- |
| Ansible fleet deploy | ✅     | `site.yml` works                       |
| Python/git/SSH       | ✅     | Standard packages                      |
| ADB                  | ⚠️     | Must set `STAYTURGID_ADB=/usr/bin/adb` |
| `just test` / CI     | ✅     | Tested in GitHub Actions               |
| launchd agents       | ❌     | Use systemd user units instead         |
| Handsets UI driver   | ❌     | macOS binary only                      |
| VLM sidecar          | ⚠️     | Needs separate setup                   |

### 9.3 Linux Work Needed

**P0 — Unblock `just deploy` on Linux:**

- Guard `control_node/agents` tasks with `meta: end_host` when not Darwin.
- Fix adb defaults: `shutil.which("adb")` fallback or `STAYTURGID_ADB`.
- Document `--skip-tags mac` for Linux operators.

**P1 — Operator Ergonomics:**

- Create `ansible/playbooks/linux-control.yml` with systemd user units.
- `just deploy` target for apt-based systems.
- OS-agnostic `devices.conf` + SSH fragment generation.

**P2 — Feature Parity:**

- Handsets on Linux (if upstream supports it).
- VLM on Linux.
- Linux consumer example in `examples/`.

---

## 10. Implementation Roadmap

### Phase 0: Census and Schema Validation (No Code Changes)

**Goal:** Understand the current state. Produce a decision table.

- [x] Run seed alias scan to classify every production literal.
- [x] Review each gap against the classification system (§3.4).
- [x] Document operator decisions needed (§11) and obtain answers.
- [x] Fix stale reference in `hosts.yml.example` (currently points to
      nonexistent `docs/other-sites.md`; should point to
      `docs/architecture/platform-architecture.md §7.3`).

### Phase 1: Identity Validator and Python Interface

**Goal:** Build the tooling that enforces the single source of truth.

- [ ] Create `control/lib/site_identity.py` (§3.3).
- [ ] Create `control/bin/validate_site_identity.py` (§3.4).
- [ ] Add `just validate-identity` recipe.
- [ ] Integrate into `just check` and CI.
- [ ] Convert `devices.conf` to versioned schema with generated header.

### Phase 2: Migrate Active Code Consumers

**Goal:** Eliminate hardcoded production identity from active code, one file at
a time.

- [ ] Template `control/cfengine/cf-runagent.cf` from inventory.
- [ ] Fix `peers.json.j2` (`ssh_user: djbclark` → `{{ ansible_user }}`).
- [ ] Fix `stayturgid_peer_bootstrap.py` `DEFAULT_SSH_USER`.
- [ ] Fix `control/bin/*.py` adb path defaults.
- [ ] Fix `control/tools/play/obtain_play_aas.py` default email.
- [ ] Verify each migration with `validate_site_identity.py`.

### Phase 3: Deploy O-V-G-O Core Services

**Goal:** Stand up the central observation and control infrastructure.

- [ ] Install OpenObserve, VictoriaMetrics, Grafana, OliveTin via Homebrew.
- [ ] Create Ansible templates for OliveTin config, Grafana provisioning.
- [ ] Create launchd agents for O-V-G-O services.
- [ ] Integrate into `just deploy-mac`.
- [ ] Build initial Grafana "Fleet Control Room" dashboard.

### Phase 4: Deploy Edge Vector

**Goal:** Replace Mac-side polling with device-side push.

- [ ] Extend `termux_userland` role to deploy Vector `aarch64` binary.
- [ ] Create `vector.toml.j2` template (generated from inventory).
- [ ] Deploy logcat rotation boot hook.
- [ ] Validate metrics appear in VictoriaMetrics, logs in OpenObserve.
- [ ] Confirm Grafana dashboards populate correctly.

### Phase 5: Retire Legacy Monitors

**Goal:** Remove bespoke Python monitors and Flask dashboard.

- [ ] Confirm O-V-G-O provides feature parity with legacy monitoring.
- [ ] Remove `control/bin/dashboard.py` and its launchd agent.
- [ ] Remove or scale back `fleet_health_monitor.py`, `access_monitor.py`.
- [ ] Remove legacy Caddy routes for Flask dashboard.
- [ ] Update `just health` to query Grafana/VictoriaMetrics instead of flat
      log files.

### Phase 6: Documentation Scrub and Lint Enforcement

**Goal:** Remove production identity from upstream documentation.

- [ ] Scrub `AGENTS.md`, `docs/hacking.md`, `docs/handoff.md`.
- [ ] Replace all production hostnames in tests with example names.
- [ ] Add `validate_site_identity.py` to `just lint` / CI.
- [ ] Move operator-specific docs to site overlay template.

### Phase 7: SecretSpec Provider Hardening

**Goal:** Migrate from dotenv files to macOS Keychain.

- [ ] Evaluate macOS Keychain provider for workstation secrets.
- [ ] Migrate `TELEGRAM_BOT_TOKEN` and other required secrets.
- [ ] Document CI integration (environment-variable provider).
- [ ] Update `just secretspec-check` for new provider.

### Phase 8: Private Site Overlay Split

**Goal:** Create the `stayturgid-site-<operator>` repository pattern.

- [ ] Create template site overlay repository.
- [ ] Move production `hosts.yml` and `group_vars/` to site repo.
- [ ] Move `docs/handoff.md`, `human/*` to site repo.
- [ ] Verify upstream works with example inventory only.
- [ ] Document the overlay workflow in `docs/hacking.md`.

---

## 11. Decisions Requiring Operator Input

The following decisions require explicit operator judgment. Junior developers
and autonomous agents must **not** make these unilaterally:

| #   | Decision                                          | Options                                                | Impact                         |
| --- | ------------------------------------------------- | ------------------------------------------------------ | ------------------------------ |
| 1   | Private site overlay repo + access model          | GitHub private, self-hosted, local-only                | Security, backup, CI           |
| 2   | Tailscale IP vs MagicDNS as `ansible_host`        | IP (current), MagicDNS name, both                      | DNS dependency, readability    |
| 3   | `devices.conf` format: keep INI or switch to JSON | INI (current), versioned JSON, both during transition  | Compatibility, tooling         |
| 4   | SecretSpec provider for Mac and CI                | dotenv (current), macOS Keychain, 1Password, Bitwarden | Security, convenience          |
| 5   | Migration of existing secret values               | In-place, fresh rotation, gradual                      | Security posture               |
| 6   | Credential rotation from Git history              | `git filter-repo`, accept risk, rotate all             | Git history, key compromise    |
| 7   | Bootstrap exceptions with production identity     | Case-by-case allowlist, zero exceptions, grace period  | Recovery path safety           |
| 8   | Service reloads during projection updates         | Immediate, batched, maintenance-window only            | Device uptime, recovery        |
| 9   | O-V-G-O port assignments and Caddy routing        | Default ports, custom ports behind Caddy               | Network layout, firewall rules |
| 10  | Aurora SRE / AIOps integration timeline           | Never, after O-V-G-O stable, concurrent                | Complexity, resource use       |

---

## Appendix A: Seed Alias Census

Scan performed 2026-07-14 across the full repository. Production aliases
(`s24`, `p7a`, `hd8`) matched in 177 files, 1,140 lines:

| Alias | Matches |
| ----- | ------: |
| `s24` |     710 |
| `hd8` |     454 |
| `p7a` |     358 |

**Classification breakdown:**

| Category                  | Files |
| ------------------------- | ----: |
| Active code/config        |    84 |
| Documentation/research    |    39 |
| Tests                     |    33 |
| Session history           |    12 |
| Plans                     |     3 |
| Inventory (authoritative) |     3 |
| Examples                  |     3 |

---

## Appendix B: External References

### Ansible Best Practices

- [Building Ansible Inventories](https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html)
  — Official guide to static and dynamic inventory structure.
- [Ansible Tips and Tricks](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html)
  — Variable hierarchy, `group_vars/` organization, multi-environment patterns.
- [Variable Precedence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
  — The authoritative list of Ansible's 22-level variable precedence order.
- [Dynamic Inventory](https://docs.ansible.com/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
  — Inventory plugins for cloud, CMDB, and custom backends.
- [Ansible Vault Guide](https://docs.ansible.com/ansible/latest/vault_guide/)
  — Built-in secrets encryption (not used by this project; see §5).

### Configuration-as-Code and Overlays

- [Kustomize: Managing Kubernetes Objects](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
  — The base/overlay pattern that inspired this project's site overlay model.
- [CUE Language](https://cuelang.org/) — Constraint-based configuration
  language; "types are values" philosophy.
- [Jsonnet](https://jsonnet.org/learning/getting_started.html) — Data
  templating language for reducing JSON/YAML boilerplate.
- [Dhall](https://dhall-lang.org/) — Programmable, typed, non-Turing-complete
  configuration language.

### Secrets Management

- [SecretSpec Documentation](https://secretspec.dev) — Declarative secrets
  management tool used by this project.
- [SecretSpec GitHub](https://github.com/cachix/secretspec) — Source code and
  issue tracker.
- [SecretSpec Providers](https://secretspec.dev) — Supported backends (macOS
  Keychain, 1Password, AWS SM, HashCorp Vault, etc.).

### O-V-G-O Stack Components

- [OpenObserve](https://openobserve.ai/) — Rust-based log and trace engine
  with Parquet storage.
- [VictoriaMetrics](https://victoriametrics.com/) — High-performance,
  cost-effective time-series database.
- [VictoriaMetrics Single-Node Docs](https://docs.victoriametrics.com/single-server-victoriametrics/)
  — Setup and configuration reference.
- [Grafana](https://grafana.com/) — Open-source observability dashboards.
- [Grafana Data Links](https://grafana.com/docs/grafana/latest/panels-visualizations/configure-data-links/)
  — Click-to-action from dashboard panels.
- [OliveTin](https://olivetin.app/) — Web UI for predefined shell commands.
- [OliveTin Documentation](https://docs.olivetin.app/) — Configuration,
  ACLs, security best practices.
- [OliveTin GitHub](https://github.com/OliveTin/OliveTin) — Source code.

### Edge Observability

- [Vector](https://vector.dev/) — High-performance observability data
  pipeline (Rust).
- [Vector Deployment Roles](https://vector.dev/docs/setup/deployment/roles/)
  — Agent, aggregator, and unified topologies.
- [Vector Unified Topology](https://vector.dev/docs/setup/deployment/topologies/#unified)
  — Recommended architecture for mixed-environment deployments.
- [VRL (Vector Remap Language)](https://vector.dev/docs/reference/vrl/)
  — Data transformation language for Vector pipelines.

### Network Standards (Test Fixtures)

- [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737) — IPv4 address blocks
  reserved for documentation (`192.0.2.0/24`, `198.51.100.0/24`,
  `203.0.113.0/24`).
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606) — Reserved DNS names
  for documentation (`.example`, `.test`).

### Source of Truth Philosophy

- [NetBox as Source of Truth](https://netboxlabs.com/blog/netbox-the-source-of-truth-for-network-automation/)
  — NetBox Labs' articulation of the SoT concept for infrastructure automation.
- [Network to Code Blog](https://networktocode.com) — Deep dives on Ansible
  inventory as data model, constructed inventory plugins.

---

## Appendix C: File and Code Index

### Authoritative Files (Inventory and Schema)

- [`ansible/inventory/hosts.yml`](../../ansible/inventory/hosts.yml) —
  Production site inventory (the Single Source of Truth).
- [`ansible/inventory/hosts.yml.example`](../../ansible/inventory/hosts.yml.example)
  — Generic example inventory with RFC 5737 addresses.
- [`ansible/inventory/group_vars/`](../../ansible/inventory/group_vars/) —
  Taxonomy quirk variables by group.
- [`secretspec.toml`](../../secretspec.toml) — Secret declarations
  (names, descriptions, defaults).

### Projection Templates

- [`ansible/roles/control_node/templates/devices.conf.j2`](../../ansible/roles/control_node/templates/devices.conf.j2)
  — Device alias → serial/IP mapping.
- [`ansible/roles/control_node/templates/ssh_config_stayturgid.j2`](../../ansible/roles/control_node/templates/ssh_config_stayturgid.j2)
  — SSH config fragment for fleet hosts.
- [`ansible/roles/control_node/tasks/agents.yml`](../../ansible/roles/control_node/tasks/agents.yml)
  — The main projection engine (renders all templates).

### Python Libraries

- [`control/lib/stayturgid_device.py`](../../control/lib/stayturgid_device.py)
  — Device resolution from `devices.conf` projection.
- [`control/lib/resolve_adb.py`](../../control/lib/resolve_adb.py) — ADB
  target resolution with fallback chain.
- [`control/lib/stayturgid_root.py`](../../control/lib/stayturgid_root.py) —
  Repository root discovery.
- **Proposed:** `control/lib/site_identity.py` — Typed inventory interface.
- **Proposed:** `control/bin/validate_site_identity.py` — Identity validator.

### Legacy Monitors (Retire After O-V-G-O)

- [`control/bin/dashboard.py`](../../control/bin/dashboard.py) — Flask/HTMX
  dashboard on port 4097.
- [`control/bin/fleet_health_monitor.py`](../../control/bin/fleet_health_monitor.py)
  — Mac-side SSH polling health monitor.
- [`control/bin/access_monitor.py`](../../control/bin/access_monitor.py) —
  Mac-side SSH probe / access check.
- [`control/bin/check_fleet_health.py`](../../control/bin/check_fleet_health.py)
  — CLI tool to grep flat log files.

### Architecture Decision Records

- [`docs/architecture/adr/001-ansible-boundary.md`](adr/001-ansible-boundary.md)
  — What Ansible manages vs. what on-device code manages.
- [`docs/architecture/adr/002-ansible-ui-tasks.md`](adr/002-ansible-ui-tasks.md)
  — Ansible's role in UI automation tasks.
- [`docs/architecture/adr/003-shizuku-catastrophic-recovery.md`](adr/003-shizuku-catastrophic-recovery.md)
  — Recovery procedures for Shizuku failure.
- [`docs/architecture/adr/004-self-heal-vs-ansible-coverage.md`](adr/004-self-heal-vs-ansible-coverage.md)
  — Boundary between self-heal and Ansible coverage.

### Consumer Examples

- [`examples/consumer-termux-only/`](../../examples/consumer-termux-only/) —
  Minimal Tier A deployment.
- [`examples/consumer-full-fleet/`](../../examples/consumer-full-fleet/) —
  Full Tier C deployment.
- [`examples/consumer-fdroid-only/`](../../examples/consumer-fdroid-only/) —
  F-Droid-only deployment.
- [`docs/ansible/collections/adoption.md`](../ansible/collections/adoption.md)
  — How to consume collections at another site.

### Related Research (Historical)

- [`docs/research/site-identity-source-of-truth-2026-07-14.md`](../research/site-identity-source-of-truth-2026-07-14.md)
  — Original SoT research (superseded by this document §2–§5).
- [`docs/research/unified-architecture-synthesis.md`](../research/unified-architecture-synthesis.md)
  — Original O-V-G-O synthesis (superseded by this document §6).
- [`docs/research/ovgo-stack-architecture.md`](../research/ovgo-stack-architecture.md)
  — Original O-V-G-O stack design rationale.
- [`docs/operations/plans/ongao-rollout-plan.md`](../operations/plans/ongao-rollout-plan.md)
  — Earlier ONGAO plan using Netdata + Aurora (superseded by §6).
