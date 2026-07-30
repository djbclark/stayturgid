# Site Contract v1 — stayturgid

This document is the **human-readable site contract** for the stayturgid
product and the **Entangled** literate source for the site-init scaffold
templates under `control/site_contract/templates/`.

If you refuse automation, you can still stand up a private site overlay by
following the layout and file contents below. If you accept automation,
`just site-init` copies (and lightly renders) the same scaffold for you, and
`just site-sync` later maintains only `generated/stayturgid/`.

Companion specs: [docs/architecture/site-contract.md](docs/architecture/site-contract.md),
[ADR 005](docs/architecture/adr/005-two-repo-topology.md),
[multi-site-topology.md](docs/architecture/multi-site-topology.md) §4.

## 1. Purpose

The site contract is the interface between this **product** (public stayturgid
repo) and one operator's **site** (private `site-<name>` directory/repo). It
lets a user who knows nothing about Ansible bootstrap a working site layout,
while letting an experienced user remap paths via optional `site-map.yml`.

| Term           | Meaning                                                            |
| -------------- | ------------------------------------------------------------------ |
| product        | This public repo (roles, defaults, adapters, fragments, tooling)   |
| site dir       | The operator's private directory (`site-<name>`)                   |
| generated area | `generated/stayturgid/` inside the site dir; owned by `site-sync`  |
| user area      | Everything else in the site dir; never resynced by product tooling |

## 2. CLI (automation)

From a product checkout:

```text
just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
just site-sync [dir=<path>] [mode=apply|dry-run|docs] [force-generated=1]
```

- `mode=apply` (default): perform actions.
- `mode=dry-run`: print the exact per-file action list; write nothing.
- `mode=docs`: emit this document (self-contained, generic values only); write nothing.
- Exit codes: `0` success/no-op; `1` precondition/input failure; `2` would overwrite
  user content (`site-init`) or generated-area drift (`site-sync`).

Default destination for `site-init` is `$OPS_ROOT/site-<name>` (`OPS_ROOT`
defaults to `${OPS_ROOT:-~/ops}`). The destination must **never** nest inside the product
working tree (ADR 005). Bare sitename matches `^[a-z][a-z0-9-]*$` (no `site-`
prefix).

`mode=docs` always uses generic example identity only (RFC 5737 documentation
addresses, `example` sitename, example product path `/srv/products/stayturgid`).
It never reads a live overlay, operator home, or production inventory.

## 3. Site directory layout

What `site-init` creates (Site Contract v1 §3):

```text
site-example/
  README.md                  # generated once, then user-owned (never resynced)
  ansible.cfg                # inventory here; roles/collections → product checkout
  justfile                   # thin wrappers; OPS_ROOT / product path detection
  .gitignore                 # secrets patterns; does not ignore generated/
  inventory/
    hosts.yml                # from product example; user edits
    group_vars/
  registry/
    ports.yml                # product port defaults (generator-owned seeds)
    paths.yml                # product path defaults (generator-owned seeds)
  secretspec.toml            # secret *declarations* only (values in a provider)
  generated/
    stayturgid/              # site-sync owned; committed; never hand-edit
  docs/                      # operator notes (user area)
```

Optional `site-map.yml` at the site root remaps contract path keys
(`inventory`, `registry_ports`, `registry_paths`) and may declare
`serverapps` for Phase D. Unknown keys fail closed.

## 4. Manual equivalent of site-init

1. Create `site-example/` as a sibling of the product checkout (not inside it).
2. For each scaffold file below, write the destination path under the site dir
   (strip the `control/site_contract/templates/` prefix and any `.j2` suffix).
3. For `*.j2` files, substitute:
   - `site_name` → bare site name (e.g. `example`)
   - `product_root` / `stayturgid_root` → absolute path to the product checkout
   - `site_dir` → absolute path to the site directory
   - `inventory_path`, `registry_ports_path`, `registry_paths_path` → relative
     paths (defaults: `inventory/hosts.yml`, `registry/ports.yml`,
     `registry/paths.yml`), or values from `site-map.yml` when remapped
4. Copy non-`.j2` files byte-for-byte (including empty-dir `.gitkeep` files).
5. Install registry seeds from the product's checked-in
   `control/site_contract/templates/registry/{ports,paths}.yml` (see §6).
6. Edit inventory and registries for this site; provide secret values via a
   secretspec provider; never commit secret values.

After that, product upgrades use `site-sync` for `generated/stayturgid/` only.

## 5. Literate scaffold sources (Entangled)

Fenced blocks below tangle into `control/site_contract/templates/` via
[Entangled](https://entangled.github.io/) (`annotation = "naked"` so tangled
output has no extra comment markers). CI and `just site-contract-check` fail
when this document and those files drift.

**Scope discipline:** only this contract document is literate. Product roles,
playbooks, adapters, and control scripts remain conventional code.

**Registry exception:** `registry/ports.yml` and `registry/paths.yml` are
**not** fenced here. Their values are derived programmatically from product
role defaults (single authority). See §6.

## 6. Registry seeds (generator-owned, not tangled)

Port and path seed files under `control/site_contract/templates/registry/` are
produced by:

```text
python3 -m control.site_contract.generate_registry_seeds
python3 -m control.site_contract.generate_registry_seeds --check
```

`registry_sources.yml` holds selectors only (file paths + YAML/JSON/regex
keys) — never port numbers or path literals. The generator resolves those
selectors against product role defaults and writes the committed seeds. The
`--check` mode fails closed if seeds are stale.

This document deliberately does **not** copy those literals. Doing so would
create a second authority and invite drift. `site-init` still installs the
generator-produced files into the site's `registry/` directory.

Checked-in paths:

- `control/site_contract/templates/registry/ports.yml`
- `control/site_contract/templates/registry/paths.yml`

## 7. Scaffold file sources

Each fenced block is the exact source for one template path. Destinations in a
site dir drop the `control/site_contract/templates/` prefix and any trailing
`.j2`.

### `.gitignore` — Site .gitignore

```{.gitignore file="control/site_contract/templates/.gitignore"}
# Secret values and local credentials. Declarations remain committed.
*.env
*.pem
*.key
*.crt
id_*

# Local caches and editor state.
.DS_Store
.ansible/
.claude/
.pytest_cache/
__pycache__/

# generated/ is intentionally not ignored: site-sync output is reviewable and committed.
```

### `README.md.j2` — Site README (Jinja2; rendered once by site-init, then user-owned)

```{.j2 file="control/site_contract/templates/README.md.j2"}
# site-{{ site_name }}

This is a private site overlay for the **stayturgid** product. It holds site
inventory, allocation registries, secret declarations, and operator notes;
secret values live in a provider and never in this repository.

This README is generated once by `site-init`. After creation it is user-owned:
product syncs never replace or modify it. Everything outside
`generated/stayturgid/` is likewise user-owned unless a file explicitly says
otherwise.

## Layout

- `{{ inventory_path }}` starts from the product's generic example. Replace all
  RFC 5737 addresses, example aliases, and placeholder serials before deploy.
- `{{ registry_ports_path }}` and `{{ registry_paths_path }}` contain product defaults to
  reconcile with this site's actual allocations.
- `secretspec.toml` declares the stayturgid secret profile without storing any
  values.
- `generated/stayturgid/` is committed, reviewable output owned by
  `site-sync`; never hand-edit it.
- `docs/` is available for operator-owned notes.

## Product checkout

The wrapper `justfile` locates the public product at
`$STAYTURGID_ROOT`, or `$OPS_ROOT/stayturgid`, or
`${OPS_ROOT:-~/ops}/stayturgid` in that order. The site and product must remain sibling
checkouts; never nest this private repository inside the public product tree.

Review `{{ inventory_path }}` and the two registries before running a deployment.
Then use `just inventory-check`, `just deploy-check`, and `just deploy`.
```

### `ansible.cfg.j2` — ansible.cfg (Jinja2)

```{.j2 file="control/site_contract/templates/ansible.cfg.j2"}
[defaults]
inventory = {{ inventory_path }}
roles_path = {{ product_root }}/ansible/roles
# Product collections are supplied by the stayturgid checkout rendered above.
collections_path = {{ product_root }}/.ansible/collections:{{ product_root }}
host_key_checking = False
retry_files_enabled = False
interpreter_python = auto_silent

[ssh_connection]
pipelining = True
```

### `justfile.j2` — Site justfile wrappers (Jinja2; {% raw %} protects just syntax)

```{.j2 file="control/site_contract/templates/justfile.j2"}
# site-{{ site_name }} — thin wrappers for the stayturgid product.

{% raw %}
set shell := ["bash", "-uc"]

ops_root := env_var_or_default("OPS_ROOT", home_directory() / "ops")
stayturgid_root := env_var_or_default("STAYTURGID_ROOT", ops_root / "stayturgid")
site_dir := justfile_directory()
hosts := env_var_or_default("hosts", "")

_product recipe:
    @test -f "{{ stayturgid_root }}/justfile" || { echo "stayturgid checkout not found at {{ stayturgid_root }}; set STAYTURGID_ROOT or OPS_ROOT" >&2; exit 1; }
    ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-{{ site_dir }}/ansible.cfg}" STAYTURGID_SITE_DIR="{{ site_dir }}" hosts="{{ hosts }}" just --justfile "{{ stayturgid_root }}/justfile" {{ recipe }}

deploy:
    @just _product deploy

deploy-check:
    @just _product deploy-check

verify:
    @just _product verify

verify-drift:
    @just _product verify-drift

inventory-check:
    ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-{{ site_dir }}/ansible.cfg}" ansible-inventory --list
{% endraw %}
```

### `secretspec.toml.j2` — secretspec.toml declarations (Jinja2; values never stored here)

```{.j2 file="control/site_contract/templates/secretspec.toml.j2"}
[project]
name = "site-{{ site_name }}"
revision = "1.0"

# The site's default profile declares stayturgid's secret inputs. Values live in a secretspec
# provider, never in this repository or generated/stayturgid/.
[profiles.default]
TELEGRAM_BOT_TOKEN = { description = "Telegram bot token for Hermes agent notifications", required = true }
TELEGRAM_ALLOWED_USERS = { description = "Comma-separated Telegram user IDs allowed to interact with Hermes", required = false }
TELEGRAM_HOME_CHANNEL = { description = "Telegram channel ID for Hermes notifications", required = false }
GPLAY_EMAIL = { description = "Google account email for Play Store APK downloads", required = false }
GPLAY_AAS_TOKEN = { description = "Google Play AAS token for apkeep downloads", required = false }
GPLAY_AUTH_TOKEN = { description = "Google Play auth token for gplaycli", required = false }
FIRERPA_API_KEY = { description = "FIRERPA gRPC API key", required = false }
FIRERPA_CERTIFICATE = { description = "Path to the FIRERPA service certificate and private key PEM", required = false, default = "~/.config/stayturgid/firerpa.pem" }
GITHUB_TOKEN = { description = "GitHub personal access token for gh CLI auth", required = false }
ANSIBLE_GALAXY_TOKEN = { description = "Ansible Galaxy API token", required = false }
OPENCODE_ZEN_API_KEY = { description = "OpenCode Zen API key for the Hermes provider", required = false }
DEEPSEEK_API_KEY = { description = "DeepSeek API key for the Hermes native DeepSeek provider", required = false }
OPENROUTER_API_KEY = { description = "OpenRouter API key for the Hermes OpenRouter provider", required = false }
SSH_TERMUX_KEY = { description = "Path to the Termux SSH private key", required = false, default = "~/.ssh/termux_key" }
SSH_CA_KEY = { description = "Path to the SSH CA private key", required = false, default = "~/.ssh/stayturgid_ca" }
FLEET_ADBKEY = { description = "Path to the fleet ADB private key", required = false, default = "~/.config/stayturgid/adbkey" }
DEBUG_KEYSTORE = { description = "Path to the Android debug keystore", required = false, default = "~/.android/debug.keystore" }
DEBUG_KEYSTORE_PASS = { description = "Android debug keystore password", required = false, default = "android" }
HANDSETS_JAR = { description = "Path to the Handsets jar", required = false, default = "~/.handsets/hs.jar" }
OPENOBSERVE_ROOT_PASSWORD = { description = "Administrator password for OpenObserve", required = false }
VECTOR_INGESTION_TOKEN = { description = "Bearer token for Vector ingestion", required = false }
```

### `inventory/hosts.yml` — Example inventory (RFC 5737 / §4.1 generic names)

```{.yaml file="control/site_contract/templates/inventory/hosts.yml"}
---
# Generic example inventory copied from stayturgid/ansible/inventory/hosts.yml.example.
# Replace every placeholder with this site's values before deploying.
all:
  children:
    stayturgid:
      hosts:
        oneui-device:
          ansible_host: 100.0.0.11
          device_usb_serial: EXAMPLE-SERIAL-ONEUI
          device_lan_ip: 192.0.2.11
          device_phone_number: "+15550100011"
          device_label: Example One UI phone
          stayturgid_native_agent_peer_targets:
            - "100.0.0.13:5555"
        stock-android-device:
          ansible_host: 100.0.0.12
          device_usb_serial: EXAMPLE-SERIAL-STOCK
          device_lan_ip: 192.0.2.12
          device_phone_number: "+15550100012"
          device_label: Example stock Android phone
          stayturgid_native_agent_peer_targets:
            - "100.0.0.13:5555"
        fireos-device:
          ansible_host: 100.0.0.13
          device_usb_serial: EXAMPLE-SERIAL-FIRE
          device_lan_ip: 192.0.2.13
          device_phone_number: "-"
          device_label: Example Fire OS tablet
      vars:
        ansible_port: 8022
        ansible_user: termux
        ansible_python_interpreter: /data/data/com.termux/files/usr/bin/python
        ansible_ssh_private_key_file: "{{ lookup('env', 'HOME') }}/.ssh/termux_key"
        stayturgid_device_id: "{{ inventory_hostname }}"
        # AutoJs6 is retired fleet-wide as of the K1 native-agent cutover
        # (2026-07-22/25, issue #43) — leave unset (native-agent devices need
        # no automation_mode) unless you're deliberately running the legacy
        # AutoJs6 automation stack under device/autojs6/.
        stayturgid_automation_mode: ""
        stayturgid_control_ssh_user: operator
        stayturgid_mac_peer:
          user: operator
          lan: 192.0.2.1
          tailscale: 100.0.0.1
        stayturgid_hermes_telegram_allowed_users: ""
        stayturgid_hermes_telegram_home_channel: ""

    android_16:
      hosts: { oneui-device: {}, stock-android-device: {} }
    android_11:
      hosts: { fireos-device: {} }
    vendor_samsung:
      hosts: { oneui-device: {} }
    vendor_google:
      hosts: { stock-android-device: {} }
    vendor_amazon:
      hosts: { fireos-device: {} }
    oneui_7:
      hosts: { oneui-device: {} }
    model_galaxy_s24:
      hosts: { oneui-device: {} }
    model_pixel_7a:
      hosts: { stock-android-device: {} }
    model_kindle_hd8:
      hosts: { fireos-device: {} }
```

### `inventory/group_vars/.gitkeep` — Placeholder so empty group_vars/ is tracked

```{.gitkeep file="control/site_contract/templates/inventory/group_vars/.gitkeep"}

```

### `docs/.gitkeep` — Placeholder so empty docs/ is tracked

```{.gitkeep file="control/site_contract/templates/docs/.gitkeep"}

```

### `generated/stayturgid/.gitkeep` — Placeholder so empty generated/stayturgid/ is tracked

```{.gitkeep file="control/site_contract/templates/generated/stayturgid/.gitkeep"}

```

## 8. After initialization

1. Edit `inventory/hosts.yml`: replace example aliases, RFC 5737 addresses
   (`192.0.2.0/24`, `100.0.0.0/24` documentation ranges), and placeholder
   serials with this site's values.
2. Reconcile `registry/ports.yml` and `registry/paths.yml` with local
   allocations (site inventory remains authoritative for the live site).
3. Provide secret _values_ via a secretspec provider (never commit them).
4. Point product tooling at the site via `STAYTURGID_SITE_DIR` or
   `ANSIBLE_CONFIG`, or place the site as the sole `site-*` checkout under
   `$OPS_ROOT`.
5. Later product upgrades: `just site-sync` for `generated/stayturgid/` only.

## 9. Invariants

- Everything outside `generated/stayturgid/` is user-owned after creation.
- `site-init` never overwrites a differing user file (exit 2).
- A second identical `apply` is a no-op (all files `skip`).
- Private site data must never nest inside the public product working tree.
- This document and the literate templates must stay in lockstep
  (`just site-contract-check` / Entangled parity).
- Registry seed values stay source-driven via `generate_registry_seeds`.
