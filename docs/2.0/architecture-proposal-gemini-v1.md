# stayturgid 2.0 Architecture Proposal (Gemini)

## 1. Executive Summary & Verdict on Options

After evaluating the four specified options and custom alternatives against the normative requirements, the recommendation is a **Custom Stack: `mise` (Declarative Bootstrap) + Ansible + Nix (as a pure artifact builder)**.

### Verdict on the Candidates

1. **`bgub/nix-macos-starter` & `mrkuz/macos-config` (Pure Nix/nix-darwin):**
   _Verdict: Rejected for Host Provisioning._ While Nix offers unmatched atomic rollbacks via closure-diffs and hermetic reproducibility, adopting it for full system configuration violates **R5** (cheap exit to Ubuntu). It heavily couples the architecture to Nix modules, forcing a massive rewrite of existing macOS `launchd` and Linux `systemd` configurations into Nix language abstractions.
2. **Devbox (Jetify) & Devenv.sh:**
   _Verdict: Rejected for System Architecture._ These are excellent for project-bound developer environments but lack native, robust integration with background system daemons (macOS `launchd` `gui/501` and Linux `systemd` user units) that start on boot.
3. **The Custom Stack (`mise` + Ansible + Nix builder):**
   _Verdict: Selected._ `mise`'s new declarative `bootstrap` features natively manage `launchd` and `systemd` without abstraction leaks. Ansible orchestrates multi-node operations. Nix is relegated strictly to an artifact builder for zero-footprint deployment, satisfying **R3** and **R4**.

### The NixOS Rollback Trade-off

Choosing `mise` + Ansible over NixOS/nix-darwin means forfeiting native atomic rollbacks. A NixOS closure allows instant reversion to a previous system state if a deploy fails. With `mise`/Ansible, mid-flight failures leave the system in an intermediate state. We accept this trade-off to preserve the **R5** exit mechanism and **R10** (Free Sysadmin), relying instead on APFS/Btrfs/ZFS snapshots for state rollbacks and strict Git Ops-V versioning.

---

## 2. Architecture & Source of Truth

The definitive Source of Truth remains `~/src` and the `ops-worktrees` layout (**R11**).

**Satisfying R2 (Switchable Control Node):**
Any macOS or Linux peer can assume the control node role. The orchestration layer (Just + Ansible) requires only standard POSIX tools and `mise`. Because configuration is declarative and pulled from Git, any node can bootstrap itself into a control node by checking out the repository and running `just bootstrap`.

---

## 3. macOS Layer Ownership & The Two-Writers Hazard

The architecture explicitly divides ownership to prevent the Two-Writers Hazard (where two systems fight over the same `.plist` or config file).

- **`mise bootstrap` Owns:** User-space toolchains, Homebrew packages, and user-level `launchd` agents (`~/Library/LaunchAgents/com.djbclark.*.plist`).
- **Ansible Owns:** System-level configuration (macOS `defaults write`), multi-node orchestration, and the installation of the `mise` binary itself.
- **Hazard Mitigation:** Strict namespacing. Ansible is strictly forbidden from writing to `~/Library/LaunchAgents`. If a legacy Ansible role manages a service, it must be fully migrated to `mise.toml` before `mise` is allowed to touch it.

---

## 4. Linux Design & NixOS Exit Mechanism

For greenfield Linux deployments (e.g., Hetzner VPS), the system base is provisioned via Ansible.

- **NixOS Exit Mechanism (R5):** If NixOS is utilized for the base OS, it is configured minimally (networking, SSH, and the Nix package manager). All user-space services (litellm, open-webui, observability) are defined as `systemd` user units inside `mise.toml`. Because the service definition lives in `mise`, migrating to Ubuntu Server requires zero config rewrites—you simply provision an Ubuntu node, install `mise`, and apply the exact same `mise.toml`.

---

## 5. Linux-Closure Build Topology (R3)

To satisfy **R3** (minimal VMs, no fat containers), we rely on native binaries.

- **Topology:** The macOS control node (or a remote Linux builder) utilizes Nix _strictly as a build tool_. Nix evaluates the derivation and builds the closures.
- **Deployment:** The resulting binaries/closures are copied to the target Linux nodes or Android devices (via `rsync` or Tailscale).
- **Footprint:** The target nodes do not need the Nix package manager installed, preserving storage and memory.

---

## 6. Android Integration (R4 & R6)

Android devices remain a first-class target without relying on `nix-on-droid` (rejected due to overhead).

- **stayturgid-agent 2.0:** The Kotlin APK (built via Gradle on the control node) is the heart of the Android strategy. Termux, Shizuku, and the native agent operate in tandem.
- **Build Flow:** The `justfile` orchestrates the Gradle build and pushes the APK via ADB over Tailscale. The APK build does not dictate the infrastructure; it is merely an artifact deployed by the control node.

---

## 7. Deploy & Release Design (R7 & R8)

**Ops-V Release Train & Push/Pull Mechanics:**

- **Push:** The control node uses `just deploy <target>` to push configurations via Ansible/SSH.
- **Pull:** Edge nodes run a lightweight cron/systemd timer that polls the Git repository for signed tags matching the `ops-vX.Y.Z` train.
- **Signed Manifests:** Every release is accompanied by a cryptographically signed manifest detailing the expected state hash. Nodes verify the signature before pulling.

**Consent Hooks (R7/R8):**
For untrusted Android devices, deploys are consent-driven. The pull agent downloads the signed manifest and change plan. Before execution, `stayturgid-agent 2.0` intercepts the request and displays a UI prompt detailing the contractual changes (e.g., "Updating Termux packages, modifying backup cron"). The user must explicitly approve the deployment.

---

## 8. Secrets Management

- **Authority:** `~/ops/site-private/secretspec.toml` remains the single source of truth (**R11**).
- **Implementation:** Secrets are encrypted at rest using SOPS or Age. At deploy time, secrets are decrypted in-memory and passed as environment variables via `mise`'s built-in secrets management or Ansible Vault. Secrets are never written to disk in plain text within `launchd` or `systemd` configuration files.

---

## 9. Observability

The existing stack (Vector, OpenObserve, VictoriaMetrics, otelcol-contrib) is preserved (**R11**).

- **Management:** Observability daemons are managed as `launchd` / `systemd` user units via `mise.toml`.
- **Telemetry:** Daemons ship logs and metrics over Tailscale to the central OpenObserve/VictoriaMetrics instances.

---

## 10. Literate Programming Policy (R9)

- **Policy:** Documentation and configuration are entangled using literate programming techniques, but tightly constrained to ensure AI parsing efficiency.
- **Evidence/Implementation:** LLMs (like Sonnet-3.5 and DeepSeek-v4) excel at generating and modifying fenced Markdown code blocks. Rich narrative human text exists outside the blocks. A deterministic tangling script (`just tangle`) extracts the fenced blocks into the final `mise.toml` or Ansible playbooks. This allows agents to understand the _why_ (narrative) without hallucinating syntax, while the _how_ (code) remains strictly structured.

---

## 11. Free Sysadmin & Licensing (R10)

- **Recommendation:** Glue code (Ansible roles, `mise` bootstrap templates, Justfiles) should be modularized and published under the **GPLv3** or **AGPLv3** to align with FSF principles.
- **Implementation:** Abstract site-specific variables (from `site-djbclark`) away from the core logic (`stayturgid`). The generic roles can be published publicly, allowing the community to utilize and improve the "Free Sysadmin" glue safely.

---

## 12. Phased Migration Plan

- **Phase 1: Toolchain Standardization.** Move all `brew install` commands for CLI tools (uv, bun, rg) to `mise.toml`. Run `mise` alongside Ansible.
- **Phase 2: Simple Service Cutover.** Migrate observability agents (Vector) from Ansible to `mise bootstrap` `[bootstrap.macos.launchd]`. Monitor for Two-Writers Hazards.
- **Phase 3: Android Pull & Consent Hooks.** Deploy `stayturgid-agent 2.0` with baseline consent UI. Switch Android devices from Push to Pull deploys.
- **Phase 4: Full Declaration.** Migrate `litellm` and `open-webui` to `mise`. Demote Ansible to purely OS-level bootstrapping and control node orchestration.

---

## 13. Risks & Mitigations

1. **`mise` Maturity:** `mise bootstrap` is relatively new. _Mitigation:_ Fall back to Ansible for complex services if `mise` lacks necessary features (e.g., complex `launchd` KeepAlive configurations).
2. **Lack of Atomic Rollbacks:** As discussed, `mise` cannot atomically rollback state like NixOS. _Mitigation:_ Leverage APFS/ZFS snapshots prior to deployment, and rely on Git reverts for configuration rollbacks.
3. **Literate Programming Complexity:** Tangling adds a build step, potentially obscuring line numbers in error logs. _Mitigation:_ The tangling script must inject source-map comments into the generated config files to trace errors back to the Markdown source.
