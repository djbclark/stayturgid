# Research: one source of truth for site identity and secrets

**Date:** 2026-07-14  
**Status:** Research complete; implement as a staged migration  
**Audience:** Maintainers and the junior developer performing the migration

## Executive recommendation

Use the **site Ansible inventory as the sole authority for non-secret, declared site
identity**. Generate every machine-consumed derivative from Ansible's normalized
inventory. Keep runtime observations in a separate state store, and keep secret values
behind SecretSpec providers.

Do not create another hand-maintained `fleet.toml`, JSON device list, Python dictionary,
CFEngine list, dashboard list, or SSH list. That would merely move the duplication.
The repository already says that [`ansible/inventory/hosts.yml`](../../ansible/inventory/hosts.yml)
is the only place person/device-specific facts live, and the control-node role already
generates `devices.conf` and SSH configuration from it. The correct next step is to
finish enforcing that architecture.

The target model has four distinct kinds of data:

| Kind | Examples | Authority |
|---|---|---|
| Declared site identity | Stable device ID, aliases, USB serial, Tailscale address/name, control-node identity, ports, labels, taxonomy | Site Ansible inventory |
| Generic product policy | Default ports, package IDs, intervals, platform behavior | Role defaults and generic group vars |
| Observed runtime state | Current DHCP address, mDNS endpoint, online status, app version, last health result | Generated state/cache; never inventory authority |
| Secrets | Tokens, passwords, private-key material, sensitive account IDs | `secretspec.toml` defines requirements; configured SecretSpec provider stores values |

Generated files such as `~/.config/stayturgid/devices.conf`, the SSH fragment, CFEngine
run-agent targets, AutoJs6 profiles, and dashboard inputs are **projections**, not
authorities. They must carry a generated header and must never be hand-edited.

## Why this matters

The current inventory is already close to the desired design, but production identity
literals still appear in code, configuration, tests, plans, operational docs, and
historical reports. A change to a Tailscale IP or USB serial can therefore leave one
recovery path using stale data while another works. This is especially dangerous in a
system whose value comes from independent recovery paths.

Single source of truth does not mean a single file is read directly by every program.
It means each fact has one authoritative owner and every copy is reproducibly derived,
cached observation, example fixture, or documented exception.

The design must also preserve bootstrapping. A broken generated file cannot be allowed
to erase the last working SSH/ADB route before a replacement validates. Therefore the
migration needs schema validation, atomic generation, last-known-good output, and an
explicit small class of bootstrap-safe constants.

## Existing foundation and current gaps

Read these completely before implementation:

- [Architecture](../architecture.md), [other-site design](../other-sites.md), and
  [ADR 001](../adr/001-ansible-boundary.md)
- [Live inventory](../../ansible/inventory/hosts.yml),
  [example inventory](../../ansible/inventory/hosts.yml.example), and all files under
  `ansible/inventory/group_vars/`
- [Control-node agent tasks](../../ansible/roles/control_node/tasks/agents.yml),
  [`devices.conf` template](../../ansible/roles/control_node/templates/devices.conf.j2),
  and [SSH template](../../ansible/roles/control_node/templates/ssh_config_stayturgid.j2)
- [`stayturgid_device.py`](../../control/lib/stayturgid_device.py), which is the shared
  consumer of generated `devices.conf`
- [`secretspec.toml`](../../secretspec.toml), [coding rules](../coding-rules.md),
  [handoff](../handoff.md), and [options](../options.md)

GitHub equivalents:

- <https://github.com/djbclark/stayturgid/blob/master/ansible/inventory/hosts.yml>
- <https://github.com/djbclark/stayturgid/tree/master/ansible/roles/control_node>
- <https://github.com/djbclark/stayturgid/blob/master/control/lib/stayturgid_device.py>
- <https://github.com/djbclark/stayturgid/blob/master/secretspec.toml>
- <https://github.com/djbclark/stayturgid/blob/master/docs/other-sites.md>

What already works:

- `hosts.yml` defines device aliases, stable Tailscale addresses, USB serials, LAN
  addresses, labels, and taxonomy membership.
- `ansible/roles/control_node/tasks/agents.yml` renders `devices.conf` and the fleet SSH
  fragment from inventory.
- Most Python control programs consume `devices.conf` through shared helpers rather than
  embedding their own fleet list.
- `secretspec.toml` declares the project's secret names and intended uses.
- `hosts.yml.example` and `docs/other-sites.md` already define a future generic-upstream
  plus private-site-overlay shape.

Representative remaining gaps:

- `control/cfengine/cf-runagent.cf` embeds all production Tailscale IPs.
- Several FIRERPA tools, tests, and plans contain production device addresses or serials.
- `AGENTS.md`, `ansible/README.md`, `docs/hacking.md`, and `docs/handoff.md` duplicate
  live identity facts for convenience.
- Mac identity and network facts are concentrated in
  `ansible/inventory/group_vars/stayturgid.yml`, while device facts are in `hosts.yml`;
  that is acceptable within one inventory tree, but consumers must not recopy them.
- `devices.conf` is an intentionally simple compatibility projection, but its line
  format has become an implicit API and needs a versioned contract or replacement path.
- Historical documents legitimately preserve old command lines. A naive global ban on
  addresses would create noise and encourage blanket exclusions.

### Seed alias scan (2026-07-14)

A repository-wide, case-insensitive scan including hidden files and excluding only
`.git/` found the logical aliases in **177 files and 1,140 matching lines**:

| Alias | Occurrences |
|---|---:|
| `s24` | 710 |
| `p7a` | 358 |
| `hd8` | 454 |

Files containing at least one alias were provisionally classified as:

| Area | Files |
|---|---:|
| Active code/config (broad first-pass category) | 84 |
| Current docs/research/incubator | 39 |
| Tests, including collection tests | 33 |
| History | 12 |
| Plans | 3 |
| Inventory authority | 3 |
| Examples | 3 |

Reproduce the seed scan with:

```bash
rg -n -i --hidden --glob '!.git/**' '\b(s24|p7a|hd8)\b' .
```

These numbers are a census, not 1,522 defects. A stable alias used as an operator command
argument is a reference to identity, not a second definition of identity. Tests may use
short fixture aliases, and history may preserve evidence. Conversely, code that branches
on `host == "hd8"` may be an architectural violation even though it contains no IP: the
behavior probably belongs to a taxonomy group/host variable. Phase 0 must classify each
use before changing it. After the alias pass, repeat the census using the actual IPs,
serials, labels, usernames, DNS names, and absolute paths extracted from inventory.

## Research basis and tool boundaries

Ansible supports multiple inventory sources and recommends inventory plugins rather
than scripts when inventory is truly dynamic. Its
[dynamic inventory documentation](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
also makes an important distinction for stayturgid: cloud/discovery systems can be
authorities when hosts are inherently dynamic. This fleet is small and intentionally
declared, so a static site inventory plus runtime discovery cache is simpler and safer.

Ansible's
[`constructed` inventory plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/constructed_inventory.html)
can derive variables and groups from existing inventory. Use derivation for taxonomy or
convenience, not to hide essential device identity in complex expressions. Validation
should be strict so a missing field fails before generation.

SecretSpec's [configuration reference](https://secretspec.dev/reference/configuration/)
describes `secretspec.toml` as the version-controlled declaration of project secret
requirements. Its [provider documentation](https://secretspec.dev/concepts/providers/)
shows that storage is selected separately: Keyring is encrypted system credential
storage, environment is read-only and ephemeral, while dotenv is human-readable and
unencrypted. Therefore:

- SecretSpec is the source of truth for **which secrets exist and how programs request
  them**, but the selected provider is the authority for secret values.
- `secretspec.toml` is not a general-purpose fleet inventory.
- A SecretSpec declaration does not make a dotenv value encrypted or safely rotated.
- Non-secret hostnames and addresses should not be mislabeled as secrets merely to put
  all configuration into one tool.

## Desired architecture

### 1. Canonical site inventory

For the current checkout, the authority remains:

```text
ansible/inventory/hosts.yml
ansible/inventory/group_vars/stayturgid.yml
ansible/inventory/host_vars/<host>.yml       # only when a real host exception exists
```

Eventually, move the production version of that inventory tree to the private site
overlay proposed in [Running stayturgid at another site](../other-sites.md). The public
upstream should retain only generic examples and product taxonomy. This future move does
not change the schema or generation architecture.

Use `inventory_hostname` as the immutable logical device ID. A display name, Tailscale
DNS name, Android hostname, or hardware label is an attribute and may change without
renaming the logical device. Renaming an inventory ID requires an explicit migration
because it affects logs, SSH aliases, state paths, and operator habits.

Proposed required device fields:

```yaml
stayturgid:
  hosts:
    s24:
      device_label: Galaxy S24
      device_usb_serial: RFCX219CHKA
      ansible_host: 100.123.218.30
      device_lan_ip: 192.168.68.54
```

Do not mechanically add more fields. First determine whether a value is:

- a true site fact;
- generic policy that belongs in a role default/group var;
- derivable from another field;
- discoverable runtime state; or
- a secret/reference.

Suggested normalization rules:

- aliases are lowercase ASCII identifiers with no whitespace;
- USB serial is optional only when the device genuinely has no usable USB route;
- stable management address may be a validated IP or DNS name;
- LAN address is optional and explicitly treated as a hint because DHCP can change;
- ports are integers and normally inherit fleet defaults;
- taxonomy is represented by group membership, not repeated booleans; and
- no password, token, private key, or secret value appears in inventory.

### 2. Normalized inventory interface

Generators and validators should consume:

```bash
ansible-inventory -i ansible/inventory/hosts.yml --list
```

This JSON is Ansible's resolved view after group vars, host vars, and precedence. It
avoids every consumer implementing a subtly different YAML/inventory parser. Do not
make external programs inspect Ansible's inventory cache; official documentation treats
cache format as an internal implementation detail.

Create one Python library, proposed as:

```text
control/lib/site_identity.py
```

It should define typed immutable records such as `Site`, `ControlNode`, and `Device`,
load normalized `ansible-inventory` JSON, validate it, and expose deterministic ordering.
Use the standard library (`dataclasses`, `ipaddress`, `json`, `pathlib`) unless a real
schema requirement justifies another dependency.

Programs should consume the library when they need structured identity at generation
time. Existing runtime programs may continue using generated `devices.conf` through
`stayturgid_device.py` during a compatibility period.

### 3. Generated projection pipeline

The control-node configuration play should be the single generation entry point. Its
conceptual flow is:

```text
site inventory
  -> ansible-inventory normalized JSON
  -> strict identity validation
  -> render candidate projections
  -> validate each candidate
  -> atomic replacement
  -> reload only affected services
  -> record source commit and content checksums
```

Generated outputs should include:

| Projection | Consumer | Migration action |
|---|---|---|
| `devices.conf` | Python monitors, dashboard, tests | Continue generating; define/version its schema |
| SSH config fragment | OpenSSH/operator | Continue generating from inventory |
| CFEngine `cf-runagent.cf` | Mac repair channel | Replace hardcoded address list with a template |
| LaunchAgent arguments | Mac services | Render only from inventory-derived paths/aliases |
| AutoJs6 device profile | Device watchdog | Render per host from `hostvars`; no embedded site fallback |
| FIRERPA endpoint configuration | Backup health/heal tools | Generate from inventory, including port defaults |
| Dashboard device list | Web UI | Read generated projection or shared identity library |

Prefer Ansible/Jinja templates when Ansible already owns installation of the output.
Use the Python identity library for validations and formats that are awkward in Jinja.
Do not introduce an independent general-purpose “generate everything” script that
competes with the control-node role.

Every generated text file should begin with a header similar to:

```text
# Generated by stayturgid from site inventory; do not edit.
# Schema: stayturgid-site-identity/v1
# Source commit: <commit or dirty>
```

Generate into the destination directory, validate, preserve the current file as
last-known-good where recovery impact is high, then use atomic replacement. A generator
failure must leave the working outputs untouched.

### 4. Runtime discoveries are observations, not configuration

Wireless LAN IP, mDNS TLS endpoint, current ADB transport, battery level, reachability,
and application version can change without a configuration commit. Put observations in
`~/.config/stayturgid/state/`, with timestamp and provenance. Never rewrite canonical
inventory automatically from a single discovery result.

The resolution policy may use:

1. online USB serial from declared inventory;
2. fresh, device-identity-verified LAN observation;
3. declared LAN hint;
4. stable Tailscale address/name; and
5. other documented recovery channels.

If discovery repeatedly shows that a declared fact is stale, health should report a
drift proposal for operator review. A separate explicit command may update inventory,
show the diff, validate, and require a commit. Background monitors must not edit Git.

### 5. Secrets and SecretSpec

Keep `secretspec.toml` in the repository and commit only metadata: secret name,
description, whether it is required, safe non-secret defaults, and provider/reference
policy. Secret values remain outside Git.

Recommended workstation provider policy:

- macOS operator secrets: Keyring/macOS Keychain provider by default;
- CI: injected environment or CI secret-store provider;
- development-only low-sensitivity values: dotenv only when justified, ignored by Git,
  mode `0600`, and clearly identified as plaintext; and
- device secrets: provision the minimum required secret or public credential to the
  minimum devices, rather than copying the control node's whole environment.

The current `just secretspec-check` explicitly selects dotenv. Treat changing that as a
separate reviewed migration: inventory existing values, configure the desired provider,
import/copy values, verify consumers, and only then remove plaintext files. Never print
values during migration.

Applications should be launched with only the secrets they need:

```bash
secretspec run --reason "start Hermes gateway" -- <specific command>
```

Do not export every project secret into a long-lived shell or global LaunchAgent
environment. For services that require a file, generate a narrowly scoped `0600` file
at deployment/runtime, validate ownership, and ensure logs/templates cannot reveal its
contents.

Passwords deserve special treatment:

- prefer key/certificate/token authentication where the protocol supports it;
- declare unavoidable passwords in SecretSpec with no real default;
- do not store password values in Ansible host/group vars, generated `devices.conf`,
  command arguments, dashboards, logs, or documentation;
- distinguish a **path to a private key** from the private key value itself; the path is
  configuration, while access to the key is sensitive;
- document rotation and revocation separately because provider abstraction does not
  itself guarantee rotation; and
- run secret scanning before and after migration. If a real secret was ever committed,
  removal from the current file is insufficient—rotate it and assess Git history.

### 6. Bootstrap-safe and protocol constants

A hardcoded value is not automatically site identity. Keep a small, reviewed allowlist:

- protocol constants such as loopback addresses, ADB/SSH default ports, Tailscale's
  coordination address, and the Tailscale CGNAT range;
- IETF documentation networks in examples/tests;
- generic Android package/activity names;
- repository URLs needed to bootstrap; and
- historical records that are intentionally immutable.

A bootstrap exception may contain a site value only when there is no preceding source
available to obtain it. Each exception needs a machine-readable or adjacent comment
with owner, reason, recovery use, and removal condition. Keep the list small; “it was
easier than loading inventory” is not a bootstrap reason.

## Validation and anti-drift controls

Add a Python validation command, proposed as:

```text
control/bin/validate_site_identity.py
```

It should support human-readable output and `--json`, and should fail on:

- missing required fields;
- duplicate alias, USB serial, management address, or conflicting endpoint;
- malformed IP/DNS name, port, or unsupported field type;
- a secret-shaped field or known secret name in inventory;
- unknown group host references;
- unsafe label/newline content that could break generated line formats;
- a generated projection whose source checksum/schema is stale; and
- production identity literals outside approved source/generated/historical locations.

The last rule needs a maintainable registry, not only regular expressions. Generate a
set of current site literals from inventory, scan tracked files, and classify matches:

```text
authoritative       inventory and private site overlay
generated-template  references variables, never literal values
generic-fixture     reserved example domains/addresses/serials
historical          allowed, read-only record
bootstrap-exception reviewed allowlist entry
violation           code/config/current docs containing a live literal
```

Do not rewrite historical research merely to make a scanner green. Do prevent new code
from copying a production IP or serial. Current operator docs should link to inventory
or show commands that resolve aliases dynamically; historical docs can retain facts
with a directory-level exemption.

Add these gates to normal checks:

```bash
ansible-inventory -i ansible/inventory/hosts.yml --list
python3 control/bin/validate_site_identity.py
ansible-playbook ansible/playbooks/control_node/agents.yml --check --diff
```

Test fixtures must use reserved values such as `192.0.2.0/24`, `198.51.100.0/24`,
`203.0.113.0/24`, `.example` names, and explicit fake serials. Tests that specifically
reproduce a production incident may use a clearly named historical fixture, but should
normally test behavior rather than the operator's literal address.

## Junior-developer implementation plan

Do one phase per reviewable commit. Follow the repository session-start, warning/error,
device-safety, test, and Git rules. This plan authorizes research and code changes, not
device disruption or secret-value inspection.

### Phase 0 — census and decision table

1. Read every file listed under “Existing foundation and current gaps.”
2. Use `git grep`/`rg` plus parsed inventory to inventory all occurrences of aliases,
   Tailscale/LAN IPs, USB serials, control-node names, usernames, absolute operator paths,
   ports, and secret-shaped values.
3. Produce a checked-in table with: fact, authority, consumers, current duplicate
   locations, classification, sensitivity, volatility, bootstrap need, and migration
   owner.
4. Identify every parser of `devices.conf` and document the exact format it expects.
5. Run a secret scanner without printing candidate values into logs. Report findings to
   the maintainer privately if necessary; do not paste them into an issue or commit.

**Gate:** Review the census and classifications. Do not bulk-replace strings yet.

### Phase 1 — define and validate the canonical schema

1. Document the site identity v1 schema next to the inventory example.
2. Implement `control/lib/site_identity.py` against `ansible-inventory --list` output.
3. Implement `validate_site_identity.py` with structured diagnostics and no mutation.
4. Add tests for missing, malformed, duplicate, hostile, optional, and derived values.
5. Add a report-only `just` recipe and CI check. It may initially report known legacy
   duplicates from an explicit baseline, but any new violation must fail.

**Gate:** The validator must make no device or generated-file changes. Review false
positives and the bootstrap/historical allowlist.

### Phase 2 — convert active machine consumers

Migrate one consumer at a time in recovery-risk order:

1. template `control/cfengine/cf-runagent.cf` from the `stayturgid` inventory group;
2. convert FIRERPA health/heal endpoint literals to inventory-derived configuration;
3. verify all launchd jobs receive aliases/config paths rather than embedded endpoints;
4. generate AutoJs6 profile identity only from hostvars;
5. keep dashboard and Python monitors on the generated `devices.conf` API; and
6. remove production literals from active test fixtures.

For each consumer:

- capture current output as a fixture without secrets;
- render candidate output from inventory;
- compare semantic/byte parity as appropriate;
- validate twice for idempotence;
- atomically install through the existing control-node Ansible role;
- test a changed address in a temporary inventory and prove every relevant projection
  changes; and
- test invalid inventory and prove the live output remains untouched.

**Gate:** Run full checks after each consumer. Ask before reloading services or testing a
generated change against a device.

### Phase 3 — documentation and lint enforcement

1. Replace live identity tables in current generic docs with inventory lookup commands
   or links. Keep concise operational examples that use aliases.
2. Leave `docs/history/` and truly historical incident evidence intact and allowlisted.
3. Update `AGENTS.md`, `README.md`, `docs/hacking.md`, `docs/handoff.md`, and module docs
   to identify the authority and regeneration command.
4. Enable the identity-literal scanner as a hard CI failure after the active backlog is
   zero.
5. Add a test that modifying a fixture inventory regenerates all declared consumers and
   leaves unrelated output stable.

**Gate:** A new device or changed address should require one inventory edit, followed by
generation, with CI rejecting manual copies.

### Phase 4 — SecretSpec provider hardening

1. Make an inventory of secret **names and consumers**, never values in a report.
2. Confirm each declaration in `secretspec.toml` is correctly required/optional and has
   no unsafe real default.
3. Decide the operator and CI providers. Prefer macOS Keychain for workstation secrets;
   document exceptions.
4. Migrate one consumer at a time from ad hoc dotenv/file loading to scoped
   `secretspec run` injection or an explicitly rendered `0600` file.
5. Remove the forced dotenv provider from normal checks only after all required values
   exist in the selected provider and the maintainer approves.
6. Add redaction tests, provider-unavailable failure behavior, and a rotation runbook.

**Gate:** Any action that reads, migrates, deletes, or rotates real secret values needs
explicit operator approval. Never claim success based only on `secretspec check`; test
the actual consumer without exposing the value.

### Phase 5 — private site overlay

After the main tree has no active production identity literals, perform the split already
designed in `docs/other-sites.md`:

1. create the private site repository with the canonical inventory tree and site-only
   operational notes;
2. retain generic `hosts.yml.example` and taxonomy in upstream;
3. make inventory location configurable through a single supported mechanism;
4. test fresh clones of upstream plus overlay on macOS and CI;
5. document backup, access control, and recovery of the site repo; and
6. remove production facts from upstream only after the overlay deploy produces
   identical generated outputs.

Do not use a Git submodule by default unless its operational cost is justified. A sibling
checkout plus an explicit inventory path is easier to recover and keeps access controls
clear.

## Acceptance criteria

The migration is complete when:

- each declared site fact is edited in exactly one authoritative inventory location;
- every active machine consumer is generated from normalized inventory;
- changing a device address in a test inventory updates all relevant projections;
- invalid or incomplete inventory cannot replace working generated files;
- dynamic observations are timestamped state and never silently become declarations;
- no active code, config, current generic doc, or ordinary test embeds production
  aliases, addresses, serials, usernames, or absolute operator paths outside an approved
  bootstrap exception;
- `secretspec.toml` contains declarations but no real secret values;
- secret values are held by approved providers and injected only into intended consumers;
- plaintext dotenv use is explicit, minimal, ignored, and permission-checked;
- a new device can be added through one inventory change plus generation;
- a control-node or device rename has a documented migration path; and
- full checks, generation idempotence, service validation, and recovery tests pass.

## Decisions the junior developer must not make implicitly

Stop and request maintainer direction for:

1. the exact private site-overlay repository and access model;
2. whether Tailscale IP or MagicDNS name is the preferred stable management address;
3. whether `devices.conf` remains the long-term compatibility API or is replaced by a
   versioned JSON projection;
4. which SecretSpec provider is authoritative on the Mac and in CI;
5. migration or deletion of existing real secret values;
6. rotation of any credential found in Git history;
7. any bootstrap exception containing production identity; and
8. service reloads or device tests that could affect recovery paths.

The main architectural decision is not deferred: **inventory owns declared non-secret
site identity; state stores own observations; SecretSpec providers own secret values;
all other copies are generated projections or reviewed exceptions.**
