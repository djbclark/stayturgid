# stayturgid 2.0 — Architecture Proposal (Grok v1)

**Author:** Grok (xAI) as independent second opinion  
**Date:** 2026-08-08  
**Worktree:** `~/src/ops-worktrees/stayturgid-2.0/stayturgid` (`feature/stayturgid-2.0`)  
**Normative inputs:** operator requirements R1–R11 in
`docs/2.0/SECOND-OPINIONS-BRIEF.md`; live ground truth under `~/ops/` and
`~/src/ops-worktrees/`.

This document is self-contained. It evaluates the assigned stack options,
makes decisive calls, and delivers a migration plan with rollback points.

---

## 0. Executive verdict (read this first)

| Candidate | Verdict | Role in 2.0 |
| --------- | ------- | ----------- |
| **bgub/nix-macos-starter** | **Pattern source, not adoption** | Steal flake + nix-darwin + home-manager + mise cohabitation; do not replace ops with a personal starter |
| **mrkuz/macos-config** | **Pattern source, not adoption** | Steal modular hosts/profiles, brew-vs-nix package rule of thumb, optional linux-builder discipline; reject VM-first lifestyle (R3) |
| **Devbox (Jetify)** | **Reject as host/control plane** | Optional *per-repo* pure shell for contributors who want Nix packages without flakes; never owns launchd/systemd or fleet deploy |
| **Devenv.sh** | **Reject as host/control plane** | Strong project-env tooling (and secretspec integration in 2.0); useful later for contributor `devenv shell`, not for machine/fleet roles |
| **Custom layered stack (recommended)** | **Adopt** | **Role mesh + thin OS layer + thick product layer** — see §1 |

**One-sentence architecture:**

> Keep the three-repo ops suite and Ansible/CFEngine/Android product as the
> durable system of record for *fleet behavior*; add a thin, dual-exit
> declarative *host* layer (nix-darwin / NixOS + shared home-manager modules,
> with Ubuntu+mise as a first-class exit) so any macOS or Linux box can hold
> arbitrary feature roles without a permanent “control node,” while mise owns
> language runtimes and *only* its own `dev.mise.*` agents — never
> `com.stayturgid.*` / `com.djbclark.*`.

---

## 1. Overall architecture

### 1.1 Problems the current stack has (from ground truth)

Live fleet today (`~/ops/site-djbclark/inventory/hosts.yml`):

| Host | Status | Role today |
| ---- | ------ | ---------- |
| **mac** (M1 Air) | online | Sole control node: launchd agents, O-V-G-O, LiteLLM, landing, ADB/SSH/CFEngine/FIRERPA orchestration |
| **s24, p7a, hd8** | online (Tailscale) | Android fleet (Termux + native-agent + CFEngine + optional FIRERPA) |
| **mac-mini-intel** | offline_unprovisioned | Out of scope per R1 |
| **vps-primary** | offline_unprovisioned | Greenfield Linux (Hetzner planned) |

What works and must be preserved (R11):

- `~/src` + bare-store worktrees (`~/src/ops-worktrees`) as definitive source.
- Coordinated `ops-vMAJOR.MINOR.PATCH` release train across stayturgid /
  site-djbclark / site-private.
- secretspec as single *declaration* authority (unified in site-private;
  values still migrating).
- CFEngine on-device + remote last-ditch (`cf-runagent` / port 5308).
- Observability stack (Vector, OpenObserve, VictoriaMetrics, otelcol-contrib
  path, Grafana, OliveTin, Caddy front door) under site ownership labels
  `com.djbclark.*`.
- Beads / Ralph / Herdr agent orchestration (ops-djbclark + site skills).
- Path/port registries as allocation authorities (`registry/ports.yml`,
  `paths.yml`).
- Site Contract + Entangled `SITE-CONTRACT.md` literate scaffold.
- Four-tier device access: ADB :5555, SSH :8022, CFEngine :5308, FIRERPA :65000.

What breaks under R2 (switchable control node → no permanent control node):

- Launchd agents and many Python monitors assume “the Mac.”
- Linux control path is documented as partial (multi-site topology §3.2):
  launchd tasks fail, adb path defaults wrong, Handsets Mac-only.
- Serverapps are Mac-local loopback + Tailscale; no peer failover.
- Inventory still models `site_litellm` hosts as “control-ish,” not pure roles.

### 1.2 Target shape: **Ops Mesh** (roles, not nodes)

```text
                    ┌─────────────────────────────────────┐
                    │  Declarative SOURCES (git)          │
                    │  stayturgid | site-* | site-private │
                    │  + host-flake modules (new)         │
                    └───────────────┬─────────────────────┘
                                    │ ops-v tag / pull agent
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
   ┌──────────────┐         ┌──────────────┐          ┌──────────────┐
   │ Role: host-os│         │ Role: fleet  │          │ Role: obs    │
   │ nix-darwin / │         │ ansible +    │          │ vector/OO/VM │
   │ NixOS / Ubuntu│        │ just + CFE   │          │ grafana/...  │
   │ + HM + mise  │         │ Android peer │          │ main|backup  │
   └──────────────┘         └──────────────┘          └──────────────┘
          │                         │                         │
          └─────────────────────────┴─────────────────────────┘
                                    │
                         Tailscale mesh (identity)
                                    │
                    Android devices (Termux stack unchanged)
```

**Feature roles** (inventory-declared; any host may hold zero or more):

| Role ID | Purpose | Typical first holder |
| ------- | ------- | -------------------- |
| `role.host-os` | Declarative packages, defaults, user env | every Mac/Linux box |
| `role.android-peer` | ADB/SSH/CFEngine/FIRERPA client, deploy origin | mac today; any peer later |
| `role.obs-main` | Vector/OO/VM/Grafana/Caddy primary | mac today; VPS preferred long-term |
| `role.obs-backup` | Hot spare or scrape mirror | second Linux box |
| `role.ai-proxy` | LiteLLM / Open WebUI | optional |
| `role.apk-build` | JDK+SDK Gradle builder for agent/Shizuku (not architecture driver — R6) | any powerful peer |
| `role.release` | ops-v claim/cut/deploy tooling | any trusted peer |
| `role.agent-orch` | Herdr/Ralph/Beads controllers | laptop or always-on |

End-state (R2): **there is no privileged “control node” type** — only role
sets. A laptop that sleeps simply loses the roles it cannot fulfill while
asleep; always-on roles migrate to VPS/NUC. This matches the existing
scheduling doctrine (“Mac is a laptop; prefer GitHub Actions unless local
hardware is required”).

### 1.3 Where the source of truth lives (R2 / R5 / R10)

| Kind of truth | Authority | Why |
| ------------- | --------- | --- |
| Site identity (hosts, serials, TS IPs, taxonomy) | `site-*/inventory/hosts.yml` | Already correct (ADR 005); enables Free Sysadmin product without private facts |
| Port / path allocation | `site-*/registry/{ports,paths}.yml` | Collision authority; multi-writer prevention |
| Product desired state (Termux, agent, CFEngine policy, collections) | `stayturgid` (public) | R10 publishable glue |
| Secret *names/requirements* | `site-private/secretspec.toml` (symlinked) | Already unified |
| Secret *values* | secretspec providers (Keychain / 1Password / dotenv) | Never git |
| Host OS packages & system defaults | **New** host modules in a flake (prefer living in `site-djbclark/host/` or a small public `ops-host` extract later) | Dual-exit: NixOS *or* Ubuntu recipes projecting same role intent |
| Language runtimes (Python/Node/JDK pin) | **mise** project + global config | Fast pin, agent-friendly, already installed (`mise 2026.8.3`) |
| Fleet service agents (`com.stayturgid.*`, `com.djbclark.*`) | **Ansible roles only** | One writer; see §2 |
| Coordinated deploy version | `ops-release.json` + GitHub `ops-v*` | Preserve R11 |

**Not** a monorepo flake that swallows stayturgid. Nix is a *host substrate*,
not the product architecture. Product remains Python/Ansible/Kotlin/just so
Ubuntu exit (R5) and Free Sysadmin reuse (R10) stay cheap.

---

## 2. Verdict on the four named options (detail)

### 2.1 bgub/nix-macos-starter

**What it is (verified on disk `~/src/vendor/nix-macos-starter` + author post):**
flake → nix-darwin + home-manager + nix-homebrew + mise for runtimes; GUI via
Homebrew; beginner-oriented single host.

**Fit:** Excellent *teaching shape* for a first nix-darwin host module.
**Reject as product:** Zero multi-host roles, zero Android, zero Ansible mesh,
zero ops-v train, zero port registry. Personal Mac starter ≠ ops mesh.

**Borrow:** directory split `darwin/` / `home/` / `hosts/`; mise cohabitation
(Nix for stable CLI, mise for versioned toolchains).

### 2.2 mrkuz/macos-config

**What it is (verified `~/src/vendor/macos-config-mrkuz`):** opinionated
nix-darwin + home-manager + nix-homebrew; modular `modules/{darwin,home-manager,nixos,common}`;
package rule: App Store → brew cask/proprietary → nix → mise for some dev tools;
optional QEMU NixOS VMs and `nix.linux-builder`.

**Fit:** Best *structural* reference for multi-host flakes and a NixOS side.
**Reject as lifestyle:** VM playgrounds conflict with R3 (minimal VMs). Do not
run a permanent linux-builder VM on the M1 Air as the primary Linux build path —
laptop sleep + RAM contention. Use remote builder on the greenfield VPS once
it exists; optional linux-builder only as emergency.

**Borrow:** brew/nix/mise triage rule; host profiles; “stable vs unstable”
inputs discipline; *when* to enable linux-builder (not always-on KeepAlive).

### 2.3 Devbox (Jetify)

**What it is:** JSON/TOML package lists → isolated Nix-backed shells without
writing Nix; great for “clone and `devbox shell`.”

**Reject for host/fleet:** No launchd/systemd ownership model, no multi-role
inventory, no deploy train, no Android story. Adding Devbox as *the* stack
would duplicate mise (already present) and still leave Ansible for everything
that matters.

**Allowed niche:** Optional contributor path in public stayturgid
(`devbox.json` generating a pure shell for `just test`) — *never* required for
operators; never owns machine services.

### 2.4 Devenv.sh

**What it is (verified 2026 docs):** declarative project environments on Nix;
devenv 2.0 adds process supervision features and **first-class secretspec**
integration — strategically aligned with this suite’s secrets direction, but
still project-scoped.

**Reject for host/fleet:** Same boundary as Devbox. Process model competes with
launchd/systemd we already run for long-lived site services.

**Allowed niche:** Optional `devenv.nix` for contributors who live in Nix;
secretspec bridge is a *point of compatibility*, not a reason to re-platform
the control plane onto devenv processes.

### 2.5 Alternatives considered and rejected

| Alternative | Why not |
| ----------- | ------- |
| **Full NixOS-everywhere including Mac via heavy VM** | Violates R3 |
| **nix-on-droid on phones** | Explicitly rejected (R4): storage/RAM/process contention |
| **Ansible-only forever for host packages** | Weak reproducibility across Mac↔Linux role migration; slow for language toolchains |
| **mise bootstrap as sole host provisioner** | New (2026) and powerful — packages, files, launchd agents (`dev.mise.*`), systemd user units, remote bootstrap — but immature as *only* system of record for a multi-year Free Sysadmin product; label namespace collision risk if misused for `com.stayturgid.*`; no deep macOS system defaults parity with nix-darwin |
| **chezmoi / yadm alone** | Dotfiles only; does not replace package/service layers |
| **Puppet/Chef/Salt** | Extra stack; CFEngine already covers on-device congruence |

### 2.6 Recommended stack (decisive)

```text
Layer A — Identity & product (unchanged spine)
  inventory + registry + secretspec + ops-v + Ansible collections
  + CFEngine policy + Termux + stayturgid-agent (Gradle)

Layer B — Host OS (new, thin, dual-exit)
  Primary path:  Determinate Nix (already installed) + nix-darwin (macOS)
                 + NixOS (greenfield Linux) + shared home-manager modules
  Exit path:     Ubuntu Server LTS + mise bootstrap (packages + systemd user
                 units) + same Ansible role catalog
  Both paths expose the same *role facts* to Layer A

Layer C — Toolchains
  mise: Python/Node/Bun/JDK/Rust versions, direnv-friendly, project .mise.toml
  uv / bun / ruff / biome: keep as today inside those pins

Layer D — Orchestration UX
  just (product + site) — remains human/agent CLI
  Beads/Ralph/Herdr — unchanged
```

**Why this beats “pick one of the four”:** R2 requires role mobility; R5
requires cheap Ubuntu exit; R3 forbids VM fat; R4/R6 keep Android out of Nix;
R10 requires public product code not entangled with private Nix home configs;
R11 requires preserving the suite. Only a *layered* design satisfies all of
them. The four options are valuable as *patterns* or *contributor DX*, not as
the mesh.

---

## 3. macOS layer ownership (two-writers hazard)

### 3.1 The hazard

Today, LaunchAgents are written by:

- Ansible `control_node` → `com.stayturgid.*`
- Ansible `site_agents` / serverapp adapters → `com.djbclark.*`
- Homebrew services → `homebrew.mxcl.*`
- Occasional hand/legacy plists

Introducing nix-darwin, home-manager, *and* mise bootstrap (which writes
`~/Library/LaunchAgents/dev.mise.<name>.plist` only under the `dev.mise.`
prefix — verified mise docs 2026-08) creates **up to five writers**. Double
management of the same label produces flapping, silent overwrites, and agent
confusion.

### 3.2 Ownership matrix (normative)

| Concern | Single writer | Label / path namespace |
| ------- | ------------- | --------------------- |
| Fleet monitors, adb-reconnect, fire-help, dashboard, FIRERPA helpers | **Ansible `control_node`** | `com.stayturgid.*` under `~/Library/LaunchAgents/` |
| Site serverapps (caddy, vector, openobserve, grafana, VM, OliveTin, landing, litellm, …) | **Ansible site / serverapp adapters** | `com.djbclark.*` |
| Homebrew formula services | **brew services** with claim in `registry/paths.yml` | `homebrew.mxcl.*` |
| nix-daemon, linux-builder (if ever enabled), nix-darwin system bits | **nix-darwin** | `org.nixos.*` / system domain as upstream defines |
| Pure user apps HM knows (syncthing-style optional) | **home-manager** | `org.nix-community.home.*` only |
| Personal utility agents (optional) | **mise bootstrap** | `dev.mise.*` **only** |
| Language runtimes | **mise** | shims / `~/.local/share/mise` — not launchd |
| GUI apps | **Homebrew** (via existing Merged-Brewfile *or* nix-homebrew — pick one per package, record in registry) | casks |
| CLI pure packages wanted identical on Linux | **home-manager / nix profile** | nix store paths |
| macOS defaults (Dock, Finder, Touch ID sudo) | **nix-darwin** (primary) or mise `bootstrap.macos.defaults` (secondary, only if not using nix-darwin yet) | N/A |

**Hard rule:** A plist label prefix has exactly one writer in CI lint
(`registry/paths.yml` + a new `registry/launchd-writers.yml`). `just lint`
fails if a role template emits a label outside its prefix.

### 3.3 Who owns launchd for *product* agents?

**Ansible remains the owner** of `com.stayturgid.*` and `com.djbclark.*`.

Rationale:

1. Agents are fleet-coupled (inventory host lists, secretspec env injection,
   site registry ports) — Ansible already has that graph.
2. Cross-platform projection is already designed: same role renders launchd
   *or* systemd user unit (`paths.yml` already reserves
   `~/.config/systemd/user/com.djbclark.*`).
3. Migrating dozens of live agents to nix-darwin `launchd.user.agents` in one
   cut is high-risk on a laptop that is also the production observability
   host.
4. mise’s launchd support is excellent for *new personal* agents but must not
   absorb production labels (different prefix, good — keep it that way).

**nix-darwin’s job on the Mac:**

- Nix settings (flakes already on via Determinate 3.21.9 / Nix 2.34.8).
- Optional system defaults and Touch ID sudo.
- Declarative Homebrew *only for packages not in site Merged-Brewfile* during
  transition; long-term either nix-homebrew *or* F4 Merged-Brewfile wins for
  each package — never both.
- **Not** fleet KeepAlive servers.

### 3.4 Migration sequence for Mac host layer

1. Add flake with empty/no-op darwin configuration (read-only validation).
2. Enable nix-darwin managing *only* Nix itself + one harmless default.
3. Move pure CLI tools that agents need on both OSes into home-manager
   packages (e.g. `jq`, `ripgrep` if not brew-pinned for a reason).
4. Keep Ansible as agent writer indefinitely for production labels.
5. Optionally express *developer* utilities in mise bootstrap with `dev.mise.*`.

---

## 4. Linux design and the NixOS exit hatch (R5)

### 4.1 Greenfield default: NixOS on `vps-primary`

When Hetzner (or similar) is provisioned:

- Install NixOS with a flake host config sharing **home-manager modules** and
  **role option modules** with the Mac flake (`roles.obs-main.enable = true`).
- System services for always-on roles use **native systemd** via NixOS modules
  *or* the same Ansible serverapp adapters projected to systemd — prefer
  **one** path per service family:

| Service family | Preferred on NixOS | Preferred on Ubuntu exit |
| -------------- | ------------------ | ------------------------ |
| O-V-G-O + Caddy | Ansible serverapp adapters → systemd (already site-owned) | same adapters |
| Host baseline (ssh, tailscale, fail2ban, unattended upgrades) | NixOS modules | cloud-init + mise bootstrap packages + ansible |
| User CLI parity | home-manager | home-manager *or* mise packages |
| Language toolchains | mise | mise |

Keeping serverapps on Ansible adapters even on NixOS is intentional: it makes
the Ubuntu exit “pretty easy” — you do not rewrite Vector/Caddy ownership into
NixOS modules only to tear them out later.

### 4.2 Exit mechanism (document as a runbook, test once)

**Contract:** Layer A (inventory, roles, Ansible, secretspec, ops-v) never
requires NixOS.

**Exit steps:**

1. Provision Ubuntu Server LTS on equal hardware class.
2. Install: Tailscale, mise, just, uv, git, python3.12, android-platform-tools
   (if `role.android-peer`), secretspec CLI.
3. `mise bootstrap` applies `[bootstrap.packages]`, systemd user units for any
   *host* utilities, and files — **not** product agent labels.
4. Clone `~/ops` trio at current `ops-v*`; run `just ops-release-status`.
5. Apply Ansible with the same inventory role flags; serverapp adapters install
   systemd units under `com.djbclark.*`.
6. Drain roles from NixOS host; decommission.

**Success criterion:** A second engineer (or agent) can follow the runbook
without reading Nix.

### 4.3 macOS ↔ Linux control switch (near-term R2)

Before full mesh:

1. Parameterize all “control peer” facts through inventory
   (`stayturgid_control_peers: [mac, vps-primary]` list, not a single Mac
   hostname).
2. Ensure every `com.stayturgid.*` agent template has a systemd twin (or is
   marked `darwin_only` with an explicit role dependency).
3. Document: laptop may run `role.android-peer` while awake; VPS runs
   `role.obs-main` 24/7.

---

## 5. Linux-closure build topology (R3)

Goal: build Linux Nix closures / agent artifacts without fat local VMs.

| Path | When | Resource cost |
| ---- | ---- | ------------- |
| **Binary caches** (nixpkgs cache, optional Cachix/Attic later) | default | network only |
| **Build on target** (NixOS VPS builds its own system closure) | host updates | VPS CPU |
| **Remote builder** = VPS as `nix.buildMachines` from Mac | Mac needs aarch64-linux/x86_64-linux store paths | VPS CPU; **no** always-on Mac VM |
| **Determinate native Linux builder on Mac** | emergency offline; optional | uses Mac CPU; prefer off by default |
| **nix-darwin `linux-builder` QEMU** | last resort | violates R3 if KeepAlive; if used, `KeepAlive=false`, manual start (mrkuz pattern) |

**APK builds (R6):** Gradle on any peer with JDK 17/21 + Android SDK — *not*
driven by Nix. Optional Nix derivation only as a hermetic CI builder with zero
on-device footprint.

**Do not** introduce Docker-heavy image pipelines for host config.

---

## 6. Android integration (R4 / R6) and stayturgid-agent 2.0

### 6.1 Non-negotiables (R4)

On-device stack remains:

- Termux (+ termux:api, + termux:x11 as needed)
- Built-in Android Terminal app (where useful)
- Shizuku fork (independent release cadence — not ops-v)
- stayturgid-agent (Kotlin, Shizuku UserService, no Accessibility for input)
- CFEngine agent + serverd last-ditch
- Termux repair loop as primary routine heal

**nix-on-droid: rejected.** Nix may build artifacts off-device only.

### 6.2 stayturgid-agent 2.0 direction

Keep Gradle. Architecture drivers are *runtime contracts*, not build system.

**v2.0 goals (product):**

1. **Stable local API** — documented loopback endpoints / files under
   `/sdcard/stayturgid/` and `~/.stayturgid/` for heal status, peer list,
   consent receipts (see §7).
2. **Peer mesh** — continue peer ADB help (s24/p7a → hd8 pattern already in
   inventory); generalize to N peers without Mac.
3. **Pull-capable content channel** — agent can fetch a *signed change plan*
   (R7/R8) and apply only after local policy + optional user consent UI.
4. **Observability** — push OTLP/metrics via Vector-on-device or direct OTLP to
   `role.obs-main` (already Vector OTLP on :4318 non-loopback for fleet).
5. **No second self-heal religion** — agent owns catastrophic Shizuku/ADB path
   (post-K1); Termux owns sshd/packages; CFEngine is independent congruence;
   do not merge them into one process.

**Build/deploy:** suite invokes `./gradlew` / `just agent-assemble` and deploys
APK via existing roles; APK versioning stays on product tags / `version.json`
(fleet content notifier) independent of ops-v when needed, or co-released when
config+agent must move together.

### 6.3 Ansible / CFEngine boundary (preserve ADR 001 / 004)

- Ansible: declarative deploy, packages, files, one-time privileges.
- Termux loop + agent + CFEngine: runtime heal when control plane is asleep.
- Never put Accessibility enablement on an automatic path.

---

## 7. Deploy and release design (push + pull, R7 / R8)

### 7.1 Preserve: ops-v coordinated train

Keep exactly:

- Three-repo annotated tags `ops-vX.Y.Z`
- Matching GitHub Releases
- `ops-release.json` suite identity
- flock + claim files under `~/.local/state/site-djbclark/`
- Fast-forward-only `~/ops` checkouts
- Post-deploy apply split: `just deploy` (Android), `just deploy-mac` /
  future `just deploy-host` (peers), `just site-serverapps` (serverapps)

### 7.2 Push path (today → 2.0)

```text
operator/agent on any role.release peer
  → claim version
  → tag + GH release
  → ops-release-deploy (advance ~/ops)
  → ansible push to online hosts / devices
```

Push remains primary for trusted full-mesh sites (current home fleet).

### 7.3 Pull path (new, phased)

```text
device/peer pull agent
  → fetch signed manifest for channel (stable/beta)
  → verify sig + expiry + site allowlist
  → map to change plan (human-readable + machine)
  → consent gate (R7/R8)
  → apply subset of roles / files
  → report attestation
```

**v1 (R8 — minimal implementation, full interface):**

Define and ship:

| Artifact | Content |
| -------- | ------- |
| `ChangePlan` | JSON: id, ops_version, summary, risk_class, effects[], requires_consent_bool, rollback_tag |
| `SignedManifest` | plans[] + ed25519 signature by release key; publish as GH release asset |
| `ConsentRecord` | local-only: plan_id, decision, timestamp, device_id (not exfiltrated) |
| `Attestation` | optional push to obs-main: plan_id, result, hashes |

Interfaces in stayturgid (Python + on-device stub):

- `control/lib/change_plan.py` — schema + verify
- `device/termux/py/pull_apply.py` — verify + stage + call existing repair/deploy hooks
- Agent UI shell: notification “Update available: {summary}” → Approve / Defer

**Heavy machinery (roadmap, not v1):**

- User-side AI advisor over change plans
- Opt-in feature sets / “app store for config”
- Graded web of trust (site keys, peer keys, upstream product keys)
- Local-fix-until-upstream-heals channels

### 7.4 Trust model progression

| Stage | Who can deploy what |
| ----- | ------------------- |
| **Now** | Full mesh: operator keys; Ansible from trusted peers |
| **v1** | Same + signed manifests; devices *may* pull if policy `pull_enabled` |
| **Later** | Untrusted devices: only consented plans; feature packs; attestations |

---

## 8. Secrets

**Keep secretspec as single declaration authority** (already true in
site-private; stayturgid + site-djbclark symlink).

Actions for 2.0:

1. Finish value migration off scattered `~/.config/stayturgid/*.env` into
   providers (macOS Keychain / 1Password) per existing project notes.
2. Every launchd/systemd unit that needs secrets: wrap with
   `secretspec run -- …` or render env files mode-0600 outside git via Ansible
   from secretspec at apply time (current Vector/OpenObserve pattern).
3. Do **not** adopt agenix/sops as a second declaration system. If Nix needs
   secrets at activate time, bridge from secretspec → temporary env, or use
   sops only as a *provider backend* if secretspec gains/needs it — one schema.
4. Free Sysadmin public product ships `secretspec.toml` examples with
   `required = false` and empty site overlay instructions.

---

## 9. Observability

Preserve O-V-G-O + Vector + Caddy (+ blackbox_exporter, OliveTin).

2.0 deltas:

1. **Role-based placement:** `role.obs-main` prefers always-on Linux; Mac
   laptop becomes `role.obs-backup` or edge collector when VPS is ready.
2. **Push-first from devices** (already Vector OTLP :4318 on non-loopback) —
   reduce dependence on Mac SSH scrape when laptop sleeps.
3. **Registry remains authority** for ports; moving a service host updates
   inventory + ports.yml + Caddy fragments via site-sync, not ad-hoc.
4. **Dashboards as code** continue under generated Grafana fragments.
5. **No second observability product** (datadog, etc.) unless operator opts in.

---

## 10. Literate programming policy (R9)

### 10.1 Evidence from this suite

Current `entangled.toml` is deliberately narrow: **only** `SITE-CONTRACT.md`
is literate; product roles, adapters, and registries stay conventional. That
was the right calibration:

- Agents and humans get a narrative bootstrap contract.
- Hot-path Python/Kotlin/Ansible remains greppable, testable, and
  PR-reviewable without detangle steps.
- Token cost for agents stays on code + small ADRs, not on woven novels.

### 10.2 Policy for 2.0

| Material | Literate? | Why |
| -------- | --------- | --- |
| Site contract, Free Sysadmin “how a site works” | **Yes (Entangled)** | Narrative is the product; scaffold files are generated |
| ADRs / architecture proposals | Markdown narrative, **not** tangled code | Agents need stable IDs and grep |
| Ansible roles, Python control plane, Kotlin agent | **No** | Tests, ruff, detekt, healing_registry — code is source |
| CFEngine bundles | **No** (keep `.cf` source) | Operational critical path |
| Host flake modules | **No** | Nix already declarative; comments + options.md |
| Operator runbooks | Rich Markdown in `docs/` | Human narrative without agent tax |
| Port/path registries | YAML only | Machine authority |

**Expansion rule:** add a literate file only when (a) it generates a *scaffold
boundary* between product and site, or (b) it is a Free Sysadmin tutorial that
literally emits starter files. Never entangle weekly feature work.

**Agent calibration:** Sonnet/DeepSeek-class agents should receive:

- short ADRs + this proposal + `AGENTS.md` + registries
- not a 50-page woven literate monorepo

---

## 11. Free Sysadmin (R10) — publishing and licensing

### 11.1 Intent

Extend free software culture to **sysadmin glue**: generic roles, heal
policies, observability adapters, and site-contract tooling that an FSF-like
org could publish without shipping any site’s private inventory.

### 11.2 Repo split (aligned with ADR 005, extended)

| Repo | Visibility | Contents |
| ---- | ---------- | -------- |
| **stayturgid** | Public | Android product, collections, serverapp adapters, site-contract, generic examples |
| **ops-host** (optional extract when Layer B stabilizes) | Public | Shared nix-darwin/NixOS/home-manager *modules* with zero private facts |
| **site-\*** | Private | inventory, registries, memory, personal agents |
| **site-private** | Private | secretspec values declarations + private memory |

Do not publish site-djbclark. Do publish patterns as `examples/consumer-*`.

### 11.3 Licensing recommendation

| Component | License | Rationale |
| --------- | ------- | --------- |
| stayturgid product code (Python/Ansible/Kotlin) | **GPL-3.0-or-later** (or keep existing if already set; if currently more permissive, **do not weaken** without operator legal review) | Copyleft on glue discourages proprietary SaaS enclosure of Free Sysadmin modules while remaining FSF-compatible |
| Documentation / examples | **GFDL-1.3-or-later** or **CC-BY-SA-4.0** | Share-alike docs |
| Schemas (`ChangePlan`, registries JSON Schema) | **CC0-1.0** or **Apache-2.0** | Maximize interop for consent/attestation ecosystem |
| Shizuku fork | Keep upstream-compatible license | Separate product |

**Practical note:** confirm current LICENSE files before any change; this
proposal recommends *direction*, not a silent relicense. If the tree is MIT
today, moving to GPL-3.0 is an operator decision with grandfathering for
prior contributors.

### 11.4 Safe publishing checklist

- `just validate-identity` hard-fails private literals in public trees.
- Example inventory only RFC 5737 / documentation Tailscale ranges.
- CI scrub job on stayturgid for real serials, real 100.x from live site.
- Secrets only as names in examples.

---

## 12. Phased migration plan (with rollback points)

### Phase 0 — Paper & inventory (1–3 days)

**Do:** Adopt this ownership matrix in site docs; add
`registry/launchd-writers.yml`; inventory sketch of roles as host vars
(`host_roles: [android-peer, obs-main, …]`).  
**Do not:** Install nix-darwin yet.  
**Rollback:** delete docs.  
**Exit criteria:** lint schema for roles; no runtime change.

### Phase 1 — Host flake skeleton (3–7 days)

**Do:** Create `site-djbclark/host/flake.nix` (or `~/src` public draft) with
darwinConfiguration for the M1 Air matching Determinate Nix already present;
`darwin-rebuild build` only (no switch) until reviewed.  
**Rollback:** ignore flake; system unchanged.  
**Exit criteria:** flake evaluates; CI optional.

### Phase 2 — mise as toolchain SSOT (2–5 days)

**Do:** Project `.mise.toml` / global config pins for Python, Node, JDK 21;
document in `docs/toolchain.md`; ensure launchd agents use absolute paths or
mise shims consistently.  
**Do not:** migrate `com.stayturgid.*` to `dev.mise.*`.  
**Rollback:** brew formulae remain.  
**Exit criteria:** `mise doctor` clean; `just test` green under mise env.

### Phase 3 — Role parameterization of control peer (1–2 weeks)

**Do:** Replace single-Mac assumptions in templates with role-based peer lists;
systemd twins for critical agents; `just deploy-host` entrypoint.  
**Rollback:** inventory flag `legacy_single_control: true`.  
**Exit criteria:** dry-run deploy with `vps-primary` mock; laptop-only still works.

### Phase 4 — Greenfield Linux (when hardware exists)

**Do:** NixOS VPS with `role.obs-main` candidate; remote builder for Mac;
shift OTLP sink DNS/Tailscale name to role VIP or MagicDNS name.  
**Rollback:** point Vector sinks back to Mac; keep VPS as builder only.  
**Exit criteria:** 7-day clean obs on VPS; Mac sleep does not drop fleet
telemetry.

### Phase 5 — Signed change plans (v1 trust) (1–2 weeks)

**Do:** Schema + signing in release cut; device pull stub behind flag;
ConsentRecord local store.  
**Rollback:** flag off; push-only.  
**Exit criteria:** one device applies a no-op signed plan end-to-end.

### Phase 6 — Ubuntu exit drill (2–3 days)

**Do:** Throwaway Ubuntu VM or second VPS; follow §4.2 runbook; apply one
serverapp.  
**Rollback:** N/A (drill).  
**Exit criteria:** written proof that R5 holds.

### Phase 7 — Free Sysadmin extract (ongoing)

**Do:** Publish modules/examples; identity CI; licensing decision.  
**Rollback:** public repo simply lags private.

### Explicit non-goals for first 90 days

- Rewriting Ansible roles into NixOS modules wholesale
- nix-on-droid
- Replacing CFEngine
- Moving production launchd labels to mise or nix-darwin
- Always-on linux-builder VM on the Air
- Full web-of-trust consent marketplace

---

## 13. Risks and mitigations

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Two-writers on launchd | Service flapping, outage of obs | Namespace matrix §3; CI lint; Ansible sole writer for production labels |
| Nix complexity tax on agents | Slower PR velocity | Keep product code non-Nix; flake only for host substrate |
| Laptop sleep drops control plane | Fleet heal delayed | Role move obs-main to VPS; device self-heal already multi-layer |
| mise bootstrap immaturity | Broken host apply | Use for toolchains + optional personal agents; not fleet |
| Determinate Nix / upstream Nix divergence | Surprise daemon behavior | Pin installer major; read release notes on upgrade |
| Signed manifest key compromise | Malicious pull | Offline key + short manifest TTL + device allowlist; push can revoke channel |
| Scope creep into “rewrite everything in Nix” | Miss R5/R10 | Exit drill Phase 6 is mandatory gate |
| Intel mini / accidental support | Wasted effort | R1 out of scope; inventory stays offline_unprovisioned |
| Secret double systems | Leak / drift | secretspec only for declarations |
| Agent orchestration (Ralph) auto-commit on main | Bad deploys | Keep ralph worktrees; ops-v still gates `~/ops` |

---

## 14. Comparison table: how each option fails or serves R1–R11

| Req | R1 multi-arch | R2 no control node | R3 no fat VMs | R4 Android | R5 Ubuntu exit | R6 Gradle | R7/R8 consent | R9 literate | R10 Free Sysadmin | R11 preserve suite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nix-macos-starter alone | partial | weak | ok | no | weak | n/a | no | no | weak | no |
| mrkuz macos-config alone | better (has nixos/vms) | weak | **risk** (VMs) | no | partial | n/a | no | no | weak | no |
| Devbox alone | dev only | no | ok | no | n/a | n/a | no | no | weak | no |
| Devenv alone | dev only | no | ok | no | n/a | n/a | secretspec yes | no | weak | no |
| **Ops Mesh (this proposal)** | **yes** | **yes** | **yes** | **yes** | **yes** | **yes** | **interfaces v1** | **calibrated** | **yes** | **yes** |

---

## 15. Concrete file/layout sketch (target)

```text
~/ops/
  stayturgid/                 # product (public)
  site-djbclark/              # site (private)
    inventory/hosts.yml       # + host_roles:
    registry/
      ports.yml
      paths.yml
      launchd-writers.yml     # NEW
    host/                     # NEW thin flake (or submodule)
      flake.nix
      modules/{darwin,nixos,hm,roles}
    ...
  site-private/               # secretspec + memory

~/src/ops-worktrees/          # definitive development (unchanged)

On each peer:
  ~/ops → ops-v pin
  mise  → toolchains
  nix-darwin | NixOS | Ubuntu+mise → host substrate
```

Inventory fragment (illustrative):

```yaml
mac:
  ansible_connection: local
  host_roles:
    - host-os
    - android-peer
    - obs-main          # until VPS takes it
    - agent-orch
    - release
vps-primary:
  ansible_host: 100.x.y.z
  host_roles:
    - host-os
    - obs-main
    - apk-build
    - remote-nix-builder
```

---

## 16. Decisive calls (summary list)

1. **Do not** adopt any of the four named options as the system architecture.
2. **Do** adopt **Ops Mesh**: role inventory + preserved three-repo suite + thin dual-exit host layer.
3. **Ansible owns** `com.stayturgid.*` and `com.djbclark.*` launchd/systemd forever (or until a deliberate ADR moves a single label with dual-running).
4. **mise owns** language runtimes; may own only `dev.mise.*` agents.
5. **nix-darwin / NixOS + home-manager** own host substrate packages/defaults; **not** fleet agents.
6. **NixOS default on greenfield Linux**; **Ubuntu+mise+Ansible** is a tested exit, not a second-class myth.
7. **No always-on Linux VM on the Air**; remote builder on VPS; caches first.
8. **Android stays Termux/agent/CFEngine**; Nix off-device only.
9. **ops-v train stays**; add signed ChangePlan interfaces in v1; heavy consent later.
10. **secretspec stays** the only secret schema.
11. **Literate programming stays narrow** (site contract / Free Sysadmin scaffolds).
12. **Publish glue under copyleft-friendly terms** after license audit; never publish site inventory.

---

## 17. What I would implement first if authorized tomorrow

1. `registry/launchd-writers.yml` + lint.
2. `host_roles` in inventory (data only).
3. mise pins checked into stayturgid / site docs.
4. Flake skeleton that evaluates on the existing Determinate Nix install.
5. ChangePlan JSON Schema + ed25519 verify library with unit tests.
6. Draft Ubuntu exit runbook in `docs/operations/` (not in this restricted second-opinion file set if elsewhere — here, content is complete).

---

## Appendix A — Tool capability verification (2025–2026)

Checked against live docs / install on 2026-08-08 (not training memory):

| Tool | Finding |
| ---- | ------- |
| **Determinate Nix** | Installed: 3.21.9 / Nix 2.34.8; `/nix` present |
| **mise** | 2026.8.3 on PATH; **bootstrap** is a full host-provisioner: packages (apt/brew/…), files, repos, dotfiles, macOS defaults, **launchd agents** (`dev.mise.*` prefix only), **systemd user units**, remote bootstrap, secrets hooks |
| **mise launchd** | User agents only; no LaunchDaemons; explicit apply; declarative merge across config hierarchy |
| **nix-darwin** | launchd agents + homebrew module + linux-builder option; HM integration standard |
| **home-manager** | Cross-platform user config; services map to systemd (Linux) / launchd (via darwin) with `org.nix-community.home.*` style labels |
| **Devbox / devenv** | Project environments; devenv 2.0 integrates secretspec; neither replaces fleet Ansible |
| **bgub / mrkuz** | Vendor trees under `~/src/vendor/`; patterns as cited in §2 |

## Appendix B — Live fleet anchors used

- `~/ops/site-djbclark/inventory/hosts.yml` — mac + s24/p7a/hd8 live; VPS/mini unprovisioned
- `registry/ports.yml` / `paths.yml` — ownership prefixes for site vs stayturgid vs brew
- `docs/OPS-RELEASES.md` — ops-v contract and apply split (deploy vs deploy-mac vs site-serverapps)
- `site-private/secretspec.toml` — unified secret declarations
- stayturgid ADRs 001/004/005, core-architecture connection tiers, entangled.toml scope
- LaunchAgents currently loaded: mix of `com.stayturgid.*` and `com.djbclark.*` (observed)

---

---

## Critique of Claude's proposal

Read **after** this document was complete (`docs/2.0/architecture-proposal-v1.md`,
Claude Fable 5, 2026-08-08). This section is optional second-pass comparison.

### Where we agree (high)

Claude and Grok independently converge on the important spine:

| Agreement | Claude | Grok |
| --------- | ------ | ---- |
| None of the four named options is the architecture | §1 table | §0 / §2 |
| Role mesh, no permanent control node | R2 / Site Model roles | Ops Mesh `host_roles` |
| bgub / mrkuz = pattern donors only | §3.1–3.2 | §2.1–2.2 |
| Devbox not system layer | rejected | rejected |
| NixOS greenfield + cheap Ubuntu exit | mise adapter | Ubuntu+mise+Ansible exit drill |
| No always-on Mac linux-builder VM (R3) | explicit reject | explicit reject |
| Android Termux/agent/CFEngine unchanged; nix-on-droid out | §5.4 | §6 |
| ops-v train + secretspec preserved | §7–8 | §7–8 |
| Signed release manifest + change plan as R7/R8 seed | §7.2 | §7.3 |
| Free Sysadmin extract / copyleft-friendly glue | `freeops`, GPLv3+ | §11 |
| Port/path registries stay allocation authorities | §4 | §1.3 |

That convergence is evidence the requirements force the design, not vendor
taste.

### Material disagreements (decide these)

#### 1. End-state owner of production launchd / systemd

**Claude (§5.1 / Phase 3):** end state is **home-manager / Nix** generated
from `services.yml`; Ansible *retires* from Mac launchd entirely
(`managed_by: ansible → nix` flips until “Ansible manages no launchd on the
Mac”).

**Grok (§3):** **Ansible remains the permanent single writer** for
`com.stayturgid.*` and `com.djbclark.*`; Nix owns host substrate only; mise
only `dev.mise.*`.

**Why Grok still prefers Ansible permanence:**

1. Those agents are **fleet-coupled** (inventory peers, secretspec injection,
   registry ports, Android host lists). Rendering them from Nix still needs
   the Site Model *and* a second apply path; you have not deleted complexity,
   only moved the renderer.
2. Serverapp adapters and site_agents already encode dual
   launchd/systemd projection and site ownership — reimplementing that in
   HM modules is a large rewrite with weak R5 payoff (Ubuntu exit must
   re-render the same services without Nix generations anyway).
3. Phase-3 flip risk on the **live observability host** (this Mac) is
   operationally expensive; Claude’s per-service boolean is good mitigation
   but still optimizes for a destination Grok thinks is optional.
4. R10 Free Sysadmin consumers may adopt **only** the Android+Ansible
   product without ever installing nix-darwin — keeping agents in Ansible
   keeps the publishable product self-sufficient.

**Hybrid worth considering:** Claude’s `services.yml` as **inventory of
intent** + Grok’s writer matrix; `managed_by` may flip *individual*
low-coupling utilities to HM, but fleet/obs labels stay Ansible unless a
later ADR proves a win.

#### 2. How formal the “Site Model” is on day one

**Claude:** new `registry/services.yml` + `roles.yml` as the spine;
adapters are pure projections; exit = generate mise.toml from the model.

**Grok:** extend inventory with `host_roles` + `launchd-writers.yml`;
avoid a full parallel service IR until push comes to shove.

**Trade-off:** Claude’s model is cleaner for R5/R7 and Free Sysadmin
generators; Grok’s is lower up-front tax and matches how agents already
work (edit hosts.yml, run just). **Recommendation if merging:** adopt
Claude’s *schemas* early (Phase 0) but do **not** require every live plist
to be generated from them before Phase 2 — transcribe gradually (Claude
already says this) and keep Grok’s lint on writer prefixes from day one.

#### 3. mise’s role weight

**Claude:** mise bootstrap is the **certified exit adapter** (dormant but
CI-proven generator). Correct and strong.

**Grok:** mise is **toolchain SSOT** + optional personal agents; Ubuntu
exit leans on **existing Ansible serverapp adapters** for O-V-G-O, not a
full re-render into mise units.

**Merge:** Claude’s exit-drill CI is worth taking. Prefer generating
*packages + host baseline* via mise, and *site serverapps* via the already
debugged Ansible adapters on Ubuntu — otherwise the exit reimplements
Vector/Caddy ownership twice (mise units *and* freeops generators).

#### 4. Devenv

**Claude:** optional per-repo adoption where useful.  
**Grok:** optional niche, cooler on promotion.

No operational conflict. Prefer **not** standardizing devenv in AGENTS.md
until a concrete repo benefits; secretspec kinship is not a reason to
mandate it.

#### 5. Literate programming ambition

**Claude (§10):** selective entangle + `stitch` so agents edit tangled
files while literate sources absorb changes; human-facing asides stripped
from agent context.

**Grok (§10):** keep entangled **narrow** (site-contract / Free Sysadmin
scaffolds only); hot-path stays plain code.

**Risk on Claude’s side:** stitch/conflict under multi-agent worktrees is
called out in Claude’s own risks — and this suite already has painful
cross-agent git rules. Expanding literate surface before Free Sysadmin
extraction may tax agents more than it helps. Take Claude’s *ablation*
idea (human asides not in agent context) without expanding watch_list
aggressively.

#### 6. Scope of future device classes

**Claude §5.5** sketches routers, iPhone, glasses, microcontrollers.  
**Grok** deliberately omits them.

Fine as extension-point prose; dangerous if it dilutes the 90-day plan.
Keep as appendix, not Phase 0 schema load.

#### 7. Naming / extraction timing of `freeops`

**Claude** front-loads a public `freeops/` module home.  
**Grok** extracts after host modules stabilize.

Agree on destination; prefer **Grok timing** (prove modules inside
site-djbclark/stayturgid first) to avoid a fourth repo in the ops-v train
prematurely. ops-v already serializes three repos — adding freeops early
costs release ceremony for little gain.

### What Grok would steal from Claude on a merge pass

1. **`services.yml` / `roles.yml` schemas** and Phase-0 transcription.
2. **`managed_by` ownership fact** (even if most production rows stay
   `ansible` indefinitely).
3. **Exit-drill CI** rendering a host as Ubuntu/mise (and shellcheck).
4. **Stricter reject** of linux-builder VM (Grok allowed emergency; Claude
   cleaner under R3).
5. **Trust roadmap T0–T6** structure (transparency log, advisor API,
   feature catalog) as the long-term R7 appendix — Grok’s §7.4 is thinner.
6. **deploy-rs / build-on-target** language for NixOS phase 1.
7. **harmonia-or-attic** as future `cache` role (demand-driven).

### What Claude should take from Grok

1. **Do not schedule “Ansible manages no launchd” as a success criterion.**
   That optimizes for Nix purity over R5/R10 and fleet coupling.
2. **Namespace firewall now** (`com.stayturgid.*` / `com.djbclark.*` /
   `dev.mise.*` / `org.nixos.*`) as lint, independent of Site Model
   maturity.
3. **Live launchd census** (this Mac already runs a large mix of site and
   stayturgid agents) as the migration unit of account — flip cost is not
   uniform.
4. **APK/Gradle stays outside flake mental model** even when `nix run`
   wraps JDK — R6 must remain true in docs so agents do not invent Nix
   Android SDKs.
5. **Determinate Nix is already live** — Phase 1 should assume that
   installer, not a greenfield Nix install narrative.

### Bottom line

The two proposals are **compatible second opinions of the same
architecture family** (tool-neutral facts + replaceable host adapters +
preserved Android/ops-v spine). The fork that actually matters is:

> **Are production `com.djbclark.*` / `com.stayturgid.*` services a Nix
> generation problem, or an Ansible role problem that merely *runs on*
> a Nix-managed host?**

Grok votes **the latter** for v1–v2. Claude votes **migrate to the
former**. Operator should pick that binary explicitly; everything else
merges cleanly.

---

*End of Grok v1 proposal (including post-hoc critique of Claude v1).*
