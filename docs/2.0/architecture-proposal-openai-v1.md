# stayturgid 2.0 architecture proposal — OpenAI

**Status:** proposed architecture and migration plan
**Scope:** macOS/Apple Silicon; Linux `x86_64` and `aarch64`; Android
**Decision:** adopt a small custom stack: **Nix flakes + nix-darwin + Home
Manager + mise, with Ansible and CFEngine retained as the deployment and
reconciliation plane**. NixOS is an optional Linux substrate, not the
application-control plane. Android remains deliberately non-Nix.

This is a proposal, not a claim that the current fleet is already converted.
It is based on the live three-sibling release suite and its site inventory at
2026-08-08: one Apple-Silicon Mac is online; s24, p7a, and hd8 are Android
targets; the VPS and Intel mini are explicitly `offline_unprovisioned`.

## Executive verdict

Do not adopt any of the four evaluated projects as the architecture. They are
useful source material, but each has the wrong boundary for this fleet.

| Option                   | Verdict                                                         | Why                                                                                                                                                                                                                                                                                                                    |
| ------------------------ | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bgub/nix-macos-starter` | **Reference only**                                              | A clean beginner layout for one Mac, but its one-user/one-host shape and Nix-owned Homebrew make it a poor authority for the existing multi-repo, site-owned service estate. The README currently even points its clone command at a different GitHub owner, so it is not a stable foundation contract.                |
| `mrkuz/macos-config`     | **Reference only**                                              | Its explicitly personal, modular `nix-darwin`/Home Manager configuration is a strong example of module structure and an optional Linux builder. It is intentionally opinionated and VM-oriented, which conflicts with the no-always-on-VM requirement and does not model Android consent or the present release train. |
| Devbox                   | **Adopt only per-repository if a repository prefers it**        | Devbox gives reproducible, isolated developer shells without Docker and may be a friendly on-ramp for contributors. It is not the source of truth for a host, services, fleet secrets, or cross-repo releases. Its global mode would create a second host-package authority.                                           |
| devenv.sh                | **Adopt selectively for complex development/test environments** | It has excellent process/service/test ergonomics, but `devenv up` is a development supervisor, not a production launchd/systemd contract. It must not become a persistent control-plane service manager.                                                                                                               |
| Custom composition       | **Chosen**                                                      | It keeps the existing proven control boundaries, lets Nix solve reproducible tools and optional NixOS hosts, gives mise its now-real bootstrap role, and avoids asking a package manager to replace Ansible, CFEngine, consent, or release governance.                                                                 |

The governing principle is **one writer for each kind of state**. A host is no
longer a “control node”; it is a member with one or more feature roles. The
role assignment is portable and replicated in the release manifest and site
inventory, not encoded in the identity of the current Mac.

## Evidence and constraints carried forward

The proposed design does not replace the things that are already deliberately
separated.

- `~/src` remains the development source of truth, with one task worktree per
  task. `${OPS_ROOT}/` remains deploy checkouts advanced only by a coordinated
  `ops-vMAJOR.MINOR.PATCH` release, never by a casual pull of `master`.
- Site facts stay only in `site-<name>/inventory/hosts.yml`; the live inventory
  already distinguishes online hosts from `offline_unprovisioned` ones. Port
  and path registries remain allocation authorities.
- `site-private/secretspec.toml` stays the one declaration authority for the
  suite. The existing `_secretspec` wrapper model is retained where a
  privileged automation boundary is needed; it is intentionally not claimed
  to defend against the same root-capable administrator.
- Android keeps Termux, termux:api, Termux:X11, Android Terminal, the Shizuku
  fork, the Kotlin `stayturgid-agent`, CFEngine local repair, and FIRERPA as a
  remote last-ditch channel. No Nix store, daemon, or Nix-on-Droid is put on a
  handset.
- Vector, OpenObserve, VictoriaMetrics, `otelcol-contrib`, CFEngine roles,
  Beads, and Ralph remain products in the system. 2.0 should make their
  interfaces more portable, not force a rewrite.

The current Mac has a Determinate Nix installation but no configured remote
builders and `builders-use-substitutes = false`. That is a useful baseline,
not a Linux build strategy. Nix-darwin documents a Linux-builder feature, but
its own virtualized builder is not enabled by this proposal as a permanent
service because it violates R3's resource intent.

## 1. Target architecture

```text
                         signed ops-v release bundle
         +-----------------------------------------------------+
         | manifest + change plans + SBOM/provenance + digests |
         +------------------------+----------------------------+
                                  |
              +-------------------+-------------------+
              |                                       |
      push: Ansible/SSH/ADB                   pull: role agent / device agent
              |                                       |
  +-----------v------------+              +-----------v------------+
  | any macOS/Linux member |              | Android consent gateway |
  | feature roles:         |              | + local self-heal       |
  | deploy, build, relay,  |              | + peer aid              |
  | observability, backup  |              +------------------------+
  +-----------+------------+
              |
     native OS service manager
  +-----------+------------+
  | launchd on macOS       |   systemd on Linux
  +------------------------+

  Nix: system/tool realization and reproducible builds
  Ansible: desired-state deployment and native-service rendering
  CFEngine: local Android reconciliation and catastrophe recovery
```

### 1.1 Replicated role model, not a successor control node

`site-<name>` gains a versioned, non-secret `roles.yml` (or an equivalent
inventory group projection) whose entries state:

- a stable role ID, capability and API version;
- eligible host selectors, ordered primary/backup/equal-peer candidates;
- its data owner and replication/backup policy;
- required transport, privilege, observability probes, and change class; and
- whether it can make a push, accept a pull, build an artifact, or only relay
  a signed release.

There is no global leader election in v1. For each release, the signed role
plan names deterministic preferences. A host only claims a role after passing
its local health and fencing checks; a backup may take over only after the
plan's lease/timeout and a recorded handoff. Partitioned peers therefore can
continue safe local healing but cannot both perform an externally visible,
single-writer mutation such as publishing a release or rotating a secret.
Those operations require an explicit operator-signed plan and the durable
release ledger. This is intentionally conservative: high availability for
diagnosis and local repair, not accidental split-brain administration.

At first, the Mac holds most roles. The first Linux host takes build/cache,
offsite observation, or backup roles without becoming a mandatory hub. Later,
any Mac or Linux host can be primary, backup, or peer for any role it has been
provisioned and authorized to perform. Android is a constrained peer: it may
heal itself and designated peers, but it is never a release authority.

### 1.2 Sources of truth

| Authority                            | Repository/location                                                                | Owns                                                                                                     | Does not own                                         |
| ------------------------------------ | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Generic product and feature contract | public `stayturgid`                                                                | Android agent, generic Ansible/CFEngine roles, schemas, capability interfaces, test fixtures             | people, devices, hostnames, secrets, site selections |
| Site realization                     | private `site-<name>`                                                              | inventory, role assignments, ports, paths, retention, selected feature sets, generated deployment inputs | generic product behavior or secret values            |
| Secret declaration and values        | private `site-private` plus its approved vault provider                            | SecretSpec manifest, secret values, rotation and publication procedure                                   | ordinary configuration, release policy               |
| Work orchestration                   | `ops-djbclark`                                                                     | Beads/Ralph routing, task metadata, cross-repo work policy                                               | runtime desired state                                |
| Reproducible tool/system definitions | a new public `ops-flake` directory/repository, introduced only when Phase 1 begins | shared flake inputs, host modules, dev shells, artifact derivations                                      | site facts, secrets, service runtime state           |
| Release truth                        | signed `ops-v` manifest mirrored with the three release artifacts                  | exact commit/tag/digest set and accepted change plans                                                    | mutable latest branches                              |

The `ops-flake` is deliberately an implementation substrate, not a fourth
deployment sibling on day one. It should become a separate public repository
only once it has two consumers; until then keep it under `stayturgid/nix/` so
there is no empty project to maintain. This preserves R2: source and portable
role specifications, rather than a machine-local dotfiles repository, are the
authoritative record. It preserves R5 because the application/service
contracts live outside NixOS modules. It preserves R10 because the generic
contracts are publishable without a site's private facts.

## 2. Ownership on macOS: prevent the two-writers hazard

The current site path registry already names `com.stayturgid.*` and
`com.<site>.*` LaunchAgent namespaces and observes some Homebrew services.
2.0 formalizes the following ownership table and enforces it in CI and
preflight.

| State                                                                                           | Sole writer                                  | Rule                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nix daemon settings, Nix GC, macOS defaults, minimal system packages, system-only LaunchDaemons | nix-darwin                                   | Small, audited host modules. Do not declare a service here that Ansible currently owns.                                                                                    |
| User dotfiles, CLI configuration, user packages that do not have an operational service         | Home Manager                                 | Treat generated files as immutable outputs; list their path owner in `paths.yml`.                                                                                          |
| Language runtimes, project tools, developer tasks, onboarding bootstrap                         | mise                                         | `mise.toml` is allowed in projects; global bootstrap installs prerequisites and activates shell integration. It must not own persistent fleet services.                    |
| Homebrew formulae/casks and brew services                                                       | current site Ansible/brew-fragment mechanism | Keep the existing site-owned projection until every formula has a reviewed Nix replacement. Do not let nix-homebrew migrate or run `brew bundle` over the existing estate. |
| User LaunchAgents and Linux user systemd units for fleet/site products                          | Ansible roles                                | The existing render/probe/bootout/bootstrap or daemon-reload/start sequence stays the production adapter.                                                                  |
| Android packages, Termux files, CFEngine policy, APK deployment                                 | stayturgid Ansible plus Android-local agents | Nix can build/download artifacts only; it never applies them on a device.                                                                                                  |

This is a deliberate choice not to use mise's new bootstrap service features
for production. Current mise can declaratively converge macOS user
LaunchAgents and Linux systemd user services, alongside packages, repositories,
dotfiles and shell activation. That makes it valuable for a fresh developer
machine, but adding it as a second production writer would make the present
Ansible `launchctl` and systemd adapters race or hide drift. The policy is:

1. `mise bootstrap` may install mise, Nix client prerequisites, developer
   tools, checked-out source scaffolding, and non-service dotfiles.
2. A LaunchAgent or systemd unit has exactly one owner namespace in
   `paths.yml`; a CI check fails if that label occurs in more than one
   nix-darwin, Home Manager, mise, Ansible, or Homebrew declaration.
3. Moving a service is a one-release migration: first add an ownership
   assertion, then remove the old writer and its live unit, then introduce the
   new one, then prove a no-change second apply and reboot/login behavior.
   Never “temporarily” run both.

Likewise, nix-darwin's `homebrew.*` support is not adopted as a blanket
replacement. The existing site registry and Ansible fragments already encode
service and data ownership. Moving every cask/formula merely to be
declarative would create a risky bulk migration with no R2/R3 benefit. New
pure CLI tooling goes in Nix first; GUI apps and vendor/updater-dependent
software remain site-owned Homebrew/App Store entries unless a concrete
reproducibility gain justifies moving them.

## 3. Linux design and the cheap NixOS exit

### 3.1 NixOS is permitted, but thin

For a greenfield VPS or appliance-like Linux host, use NixOS for the machine
foundation: boot, disks, users, SSH, Tailscale bootstrap, firewall, Nix daemon,
hardware module, automatic GC, and a minimal break-glass account. Pin it in the
flake and keep host-specific hardware facts in a generated/imported module,
never mixed into generic role logic. NixOS's atomic generations and
`nixos-rebuild test` before `switch` are meaningful operational advantages.

Do **not** encode the complete observability/product stack as NixOS service
modules. All portable applications continue to be rendered by the same
Ansible roles that already make a macOS LaunchAgent and Linux `systemd --user`
unit for LiteLLM. Services declare an OS-neutral contract: executable
artifact/version, data path, account, environment/SecretSpec handles, ports,
healthcheck, and an adapter. The adapter emits launchd or systemd unit syntax;
the contract and its tests are common.

### 3.2 Exit procedure: NixOS to Ubuntu Server (or another systemd distro)

The exit is cheap because NixOS has no unique application state or only-copy
service declaration.

1. From the signed release, export the host's inventory/role assignment,
   package/artifact lock, `systemd` unit projection, Caddy/Vector/OpenObserve/
   VictoriaMetrics configuration, and encrypted data backups. Verify restore
   hashes on a temporary target.
2. Provision Ubuntu with disk encryption and the base break-glass/Tailscale
   access path. Install Nix multi-user only if it is still useful for tools or
   artifacts; it is not a prerequisite for the application runtime.
3. Checkout the same signed `ops-v` release, restore data into portable XDG or
   `/var/lib/<service>` paths, and run the existing Ansible Linux adapter in
   check mode then apply mode. It owns `systemctl --user` units, so it does not
   need NixOS service modules.
4. Run push and pull health checks, dual-write/compare observability if needed,
   then change the site role plan. Retain the NixOS machine as a read-only
   rollback target until the new host has passed its stated soak.

No data resides in `/nix/store`; no service relies on a NixOS-only module;
and no host-specific secret is embedded in a closure. The required service
contract test runs in NixOS and Ubuntu CI/container-like test fixtures (not
the production topology). That is the actual exit guarantee, not a promise
that two operating systems have identical package names.

### 3.3 Linux closure/build topology (R3)

Use native builders and signed binary caches, in this order:

1. **Before a Linux builder exists:** build Darwin outputs locally; build Linux
   closures on the target Linux host during provisioning, with fixed flake
   locks. This costs time once and needs no VM.
2. **First x86_64 Linux VPS:** make it a restricted, native `x86_64-linux`
   SSH Nix builder and cache publisher. The Mac and other Linux members use it
   only for Linux derivations. Set the remote builder's SSH host key,
   supported features, `maxJobs`, memory/disk limits, and
   `builders-use-substitutes = true` after validation.
3. **aarch64 Linux:** add a native ARM Linux builder when there is a real
   workload. Do not silently use QEMU emulation or retain a local Linux VM for
   it. Until then, build on its target.
4. **Cache:** start with upstream cache.nixos.org plus the existing trusted
   Determinate/FlakeHub entries. Add a suite-owned cache only after key
   rotation, retention, access control, recovery, and publication provenance
   have been tested. Every added substituter has an explicitly reviewed public
   key; a cache is a supply-chain trust decision, not just an accelerator.

Nix's official distributed-build guidance supports SSH/`ssh-ng` builders and
requires explicit host keys; it also calls out `builders-use-substitutes` and
per-builder feature/capacity metadata. This plan uses that mechanism rather
than hiding a QEMU Linux builder behind macOS. nix-darwin's Linux-builder can
remain a short-lived, operator-invoked compatibility tool for a one-off
diagnosis, but it is disabled by default and never a required production
dependency.

Android APKs are different: Gradle remains the build authority for Shizuku and
`stayturgid-agent`. The suite pins JDK/Gradle/Android SDK inputs and invokes
Gradle from a reproducible development shell or native CI builder; it signs,
attests, stores and deploys the resulting APK as an ordinary artifact. The
APK build must not turn the device into a Nix client or dictate host management
architecture.

## 4. Android and the stayturgid-agent 2.0 direction

### 4.1 Keep the layered recovery model

The 2.0 agent is a constrained, visible, Kotlin foreground-service product,
not a general remote shell. It continues to use Shizuku/UserService only where
privilege is granted and retains the existing transport diversity:

| Layer                                      | Owner                     | Purpose                                                                               |
| ------------------------------------------ | ------------------------- | ------------------------------------------------------------------------------------- |
| Agent foreground service and peer receiver | `stayturgid-agent`        | visible liveness, Shizuku-gated repairs, permitted peer assistance, plan verification |
| Termux boot/supervisor and CFEngine        | device-local Termux       | package/userland repair, local policy convergence, SSH/Termux-specific recovery       |
| Android Terminal and user UI               | device owner              | diagnosis, explicit consent and review surface                                        |
| Remote Ansible/ADB/SSH and FIRERPA         | authorized Mac/Linux peer | push deployment, observation and last-ditch recovery                                  |

The architecture must not “solve” Fire OS or Shizuku boot failures by moving
everything to the APK. The present evidence already distinguishes repairs that
need a live privileged shell, Termux userland, a peer, or an external
reachability observer. Preserve that distinction and enforce a single owner
per repair verb so supervisors do not thrash one another.

### 4.2 Agent 2.0 contract

The next agent protocol should have a versioned, transport-independent
`DevicePlan` envelope:

```text
DevicePlan v1
  plan_id, release_id, issued_at, expires_at, target_device_id
  requested_feature_ids and bounded operations
  artifact digests + APK signing identity + SBOM/provenance references
  impact/rollback/consent class, authorizations, signature(s)
  health assertions required before and after application
```

The agent verifies a pinned Ed25519 release key (with a signed key-rotation
set), target identity, expiry, artifact digest and capability scope before it
does anything. It persists the accepted plan hash, decision, actor, outcome
and rollback reference locally and emits the same privacy-filtered event to
the observability pipeline when available.

V1 deliberately implements only:

- read-only inspection without consent;
- pre-approved, bounded self-heal verbs already granted by the owner;
- an Android-visible summary with accept/reject/defer for a feature/deploy
  plan; and
- peer aid only for named peers and named, bounded recovery operations.

It does **not** implement a user-side LLM that approves actions, a global web
of trust, arbitrary third-party plug-ins, autonomous escalation, or a remote
shell. The local AI advisor in R7 is therefore a future advisory interface: it
explains a signed, deterministic plan and links evidence, but may not sign or
override consent. The device owner remains the authorization point.

## 5. Deploy, pull, trust and release design

### 5.1 Preserve and strengthen `ops-v`

Keep the coordinated three-repository `ops-vX.Y.Z` train and its current
preflight/deploy discipline. Extend each release with a small, canonical
`release-manifest-v1.json`, attached to all three releases and mirrored in the
site's release ledger:

```json
{
  "schema": "org.stayturgid.release/v1",
  "release": "ops-v2.0.0",
  "components": {
    "stayturgid": { "commit": "...", "tag": "ops-v2.0.0" },
    "site": { "commit": "...", "tag": "ops-v2.0.0" },
    "site-private": { "commit": "...", "tag": "ops-v2.0.0" }
  },
  "artifacts": [{ "name": "stayturgid-agent.apk", "sha256": "..." }],
  "change_plans": ["sha256:..."],
  "signing_key_id": "..."
}
```

Use signed Git tags for developer provenance and an offline-verifiable
Ed25519/minisign (or equivalent) signature over the canonical manifest and
plans for machine/device verification. Do not make a handset's ability to
verify a release depend on GitHub, a transparency-log network call, or a
currently reachable Mac. An operator may additionally publish Sigstore
attestations, but they are supplementary to the offline signature.

The release preflight verifies: exact tag/commit agreement; all manifest and
APK digests; signature/key validity; schema compatibility; SecretSpec
declarations without printing values; ownership registry uniqueness; SBOM and
provenance presence; capability/consent requirements; and the relevant unit,
agent and policy tests. Deployment records the manifest and plan hashes, not
only a semantic version.

### 5.2 Push and pull paths

**Push** remains Ansible over SSH/ADB and is the fast path for owned fleet
devices. The role host fetches/verifies the manifest, produces a target
specific plan, applies only operations permitted by that plan, and records
before/after evidence. Push is not authorized to bypass a device's consent
gate.

**Pull** is a signed-release fetch triggered by a host/device role agent. It
downloads only from configured mirrors, verifies the same manifest and plan,
and then either applies a pre-authorized operation or queues an on-device
consent request. In a partition it may run only local self-heal with a stored,
unexpired policy; it cannot roll forward to an unseen release.

For v1 the artifact channel may simply be GitHub Releases plus an authenticated
tailnet mirror. The interface should already support a content-addressed
mirror, resumable downloads, release-key rotation, monotonic release policy
and revocation list. That gives a practical migration path to an app-store-like
catalog without prematurely building one.

### 5.3 Consent and graded trust roadmap

| Stage | What ships                                                                                                                               | What is explicitly deferred                               |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| v1    | signed manifests, typed change plans, per-device key pinning, bounded capability map, owner-visible accept/reject/defer, durable receipt | third-party marketplace, social trust scores, AI approval |
| v1.x  | feature catalog UI, consent expiry/revocation, signed key rotation, remote policy explainability, reproducible receipt export            | automatic cross-organization trust                        |
| v2    | delegated issuers, organization policies, feature bundles, user-side advisor operating only on signed facts                              | global reputation as an authorization substitute          |
| later | graded web-of-trust attestations with issuer scope, expiry, evidence and revocation                                                      | any opaque score that silently grants privilege           |

An attestation must identify issuer key, subject digest/device/feature, scope,
time, evidence URI/digest, expiry and revocation state. Trust is capability-
and scope-specific: “may publish generic read-only metrics bundle” is not
“may install an APK” or “may read secrets.”

## 6. Secrets, data and observability

### 6.1 Secrets

SecretSpec remains the declaration authority. Add a `secret_handle` to every
service contract; templates receive the handle through the existing narrow
resolver, never a secret literal in a flake, `mise.toml`, inventory, release
manifest, Nix store path, Ansible log, or device plan. Continue to use
mode-0600 service units only where an environment variable is unavoidable,
and prefer a root-owned/narrow wrapper or a runtime credential file whose
owner matches the service.

The system must distinguish three facts in reporting: a declaration exists;
the vault publication is fresh; and a service successfully consumed a current
credential. The current OpenObserve/Vector incident is precisely why those are
not interchangeable. Rotation produces a signed non-secret change plan,
refreshes consumers in a bounded order, verifies authentication with a
non-secret probe, and retains the previous credential only for the approved
overlap window.

### 6.2 Observability

Keep the Vector -> OpenObserve and metrics -> VictoriaMetrics pathways, with
`otelcol-contrib` as a collector/translation point where appropriate. Standardize
a small event schema for release, plan, consent and self-heal events:

```text
timestamp, event_type, release_id, plan_hash, feature_id, role_id,
host_or_pseudonymous_device_id, actor_type, consent_state, outcome,
error_class, artifact_digest
```

Do not export secret values, raw command arguments that could contain them, or
unnecessary personal device data. The dashboard presents release/provenance and
consent outcomes next to health, but cannot become an approval bypass. Preserve
the existing port/path registries and label every listener/data path with one
owner; use their lint as a release gate.

## 7. Literate programming policy

The repository has already made the right initial call: `SITE-CONTRACT.md` is
the Entangled source for a bounded scaffold-template set, CI checks byte-level
parity, and product roles/adapters remain normal code. Expand that pattern,
not literate programming everywhere.

**Use Entangled Markdown for:** stable contracts, schemas, feature-bundle
specifications, generation templates, protocol examples, and a short manual
equivalent where exact code and explanation must remain inseparable. Every
tangled output carries a generated marker, has exactly one source, and is
checked in CI. Keep each tangle target small, explicit and independently
testable.

**Keep conventional files for:** Kotlin, Python, Ansible roles/playbooks,
CFEngine policy, service adapters, Gradle build logic, large test fixtures,
generated locks, secrets, and fast-changing operational runbooks. Narrative
near these files should link to the code rather than reproduce it.

This calibration serves both humans and agents. Rich rationale, diagrams,
decision tables and examples are cheap and useful context. Interleaving a
large operational codebase into one document makes dependency tracing,
diffs, test failures and agent edits worse. Require a short decision record
before any new literate source: what it tangles, why ordinary code plus docs is
insufficient, owner, generated paths, and parity test.

## 8. Free Sysadmin: publish safe glue, not site authority

Make “Free Sysadmin” a first-class public distribution model. A generic
organization can publish a **feature bundle**, not a privileged opaque
installer. A bundle contains:

- a semverred capability contract and JSON schema for site-supplied inputs;
- generic Ansible collection roles and optional Nix modules, never site facts
  or secret values;
- a machine-readable change/privilege declaration, rollback, ports/paths and
  data-retention declaration;
- tests, a manual procedure, SBOM, source/provenance and artifact digests;
- a signed release key/attestation and revocation mechanism; and
- an explicit compatibility range for `stayturgid` and the plan schema.

The site operator imports a named version, reviews its declared capability
surface, supplies values in the site overlay, and signs a local change plan.
The feature cannot self-register an unmanaged daemon, allocate an undeclared
port, inspect arbitrary secrets, or substitute a deployment manifest. A
bundle from the FSF can be useful without granting the FSF runtime authority
over a device.

License new generic glue **GPL-3.0-or-later** with SPDX identifiers; it keeps
improved operational glue reciprocally available, fitting the stated Free
Software goal. License prose and diagrams **CC-BY-SA-4.0**. Keep site overlays
and private operational values private by location, not by pretending the GPL
prohibits private deployment. Require Developer Certificate of Origin or a
comparable contributor policy, reproducible release instructions, and signed
maintainer keys.

## 9. Migration plan and rollback points

No phase changes fleet runtime ownership without a small, reversible proof.
Do not combine this migration with the outstanding Fire OS/`CLOSED_NO_SHELL`
soak or the OpenObserve clean-log acceptance work.

| Phase                                | Change                                                                                                                                                                          | Acceptance evidence                                                                                                                           | Rollback                                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| 0 — freeze and map                   | Inventory every current package, unit label, data path, port, builder, secret consumer and writer; add the ownership matrix as generated documentation only.                    | Second inventory pass finds no unowned persistent service; no live mutation.                                                                  | Delete only new docs/generated reports.                                                      |
| 1 — reproducible developer substrate | Add a pinned flake/dev shell for `just`, Python/uv, Bun, Android build prerequisites and policy tools; add mise tasks that invoke it. Do not migrate host packages or services. | Existing focused tests plus shell entry on Apple Silicon and Linux; lock update is reviewed.                                                  | Stop using the shell; existing Homebrew/uv/Bun paths still work.                             |
| 2 — macOS boundary                   | Introduce minimal nix-darwin and Home Manager modules for Nix/CLI/dotfile state, guarded by the writer registry. Keep Ansible and Homebrew service ownership intact.            | `darwin-rebuild build`, Home Manager build, dry-run Ansible, registry uniqueness, login/reboot check on the Mac.                              | Select previous nix-darwin generation or disable the new modules; no application data moved. |
| 3 — portable service contract        | Refactor one low-risk, stateless site service to an OS-neutral contract with launchd and systemd adapters. Keep its current Ansible label/paths.                                | macOS second apply is no-op; Linux integration test starts, health-checks, restarts and removes the same unit.                                | Reapply the old template from the released checkout.                                         |
| 4 — first Linux peer                 | Provision greenfield x86_64 NixOS or Ubuntu with Tailscale, SecretSpec access, a non-secret role, and a native Nix builder/cache pilot. It is backup/observer only.             | Signed release applied; remote build provenance; cache key test; loss of the Mac does not destroy collected data or block local Android heal. | Remove role assignment and cache substituter; Mac remains primary.                           |
| 5 — release/plan v1                  | Produce signed manifest and change-plan schemas; verify them in preflight and on one opt-in Android device in read-only mode.                                                   | Bad signature, expired plan, wrong target and digest mismatch all fail closed; valid read-only plan creates a receipt.                        | Feature flag off: retain old `ops-v` procedure, with no unverified device changes.           |
| 6 — consented mutation               | Enable one bounded, reversible feature deployment on an opted-in device; then one peer-help operation.                                                                          | Device-visible decision, durable receipt, before/after health and rollback all proven.                                                        | Revoke feature; apply recorded rollback; retain forensic receipt.                            |
| 7 — role portability                 | Move one noncritical primary role to Linux with a Mac backup, then exercise planned failover.                                                                                   | No split brain; release ledger, health and observability agree through failover/failback.                                                     | Pin role to former primary and restore its signed state snapshot.                            |

After each phase, publish the exact evidence, known gaps and operator gates in
`docs/STATUS.md`/the appropriate site status document. A green build, Nix
evaluation, cache warmup, or configuration diff is not a live-device
verification.

## 10. Principal risks and decisions

| Risk                                                    | Decision/mitigation                                                                                                                                                               |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nix complexity becomes a new monolith                   | Keep Nix responsible for realization and builds, not deployment, consent, data policy or service orchestration. Pin inputs and make a simple non-Nix Linux adapter a tested exit. |
| Two service managers fight                              | One label/path writer registry; Ansible remains production service owner; mise bootstrap service support is intentionally unused there.                                           |
| Nix macOS Linux-builder VM violates R3                  | Do not enable it as baseline. Use native target/remote builders, and add ARM capacity only when demanded.                                                                         |
| Closure/cache supply-chain compromise                   | Explicit trusted keys, signed manifests, review of new substituters, SBOM/provenance, and no implicit cache trust.                                                                |
| “No control node” becomes unsafe distributed automation | Static signed role plans, narrow leases/fencing, local-only behavior under partition, and operator signatures for singleton/external mutations.                                   |
| Consent theater or AI overreach                         | Device verifies deterministic signed plans; AI explains only; default deny outside bounded capability grants.                                                                     |
| Android agent becomes a privileged shell                | Versioned operation allowlist, Shizuku gate, visible FGS/consent, separate recovery owners and local receipts.                                                                    |
| NixOS exit is fictional                                 | Keep application state and unit contracts portable; rehearse restore to Ubuntu before treating NixOS as a production dependency.                                                  |
| Literate source harms agents                            | Limit it to small, mechanically verified contracts and templates; conventional code remains searchable/testable files.                                                            |
| Free Sysadmin bundle imports unsafe glue                | Capability manifests, site-local binding/signature, declared ports/paths/secrets, reproducibility and GPL source availability.                                                    |

## References checked for this proposal

- [mise bootstrap](https://mise.jdx.dev/bootstrap.html) and its
  [launchd support](https://mise.jdx.dev/bootstrap/launchd.html) document the
  current declarative bootstrap scope, including LaunchAgents and systemd user
  units. The capability is real; the decision here is to avoid dual ownership.
- [nix-darwin options](https://nix-darwin.github.io/nix-darwin/manual/) document
  `nix.linux-builder`; [nix.dev's distributed-build guide](https://nix.dev/tutorials/nixos/distributed-builds-setup.html)
  documents SSH builders, host-key protection and substitute behavior.
- [NixOS system configuration](https://wiki.nixos.org/wiki/NixOS_system_configuration)
  and the [NixOS manual](https://nixos.org/manual/nixos/stable/) support the
  generation/test/switch rollback model used here.
- [Devbox configuration](https://www.jetify.com/docs/devbox/configuration) and
  [FAQ](https://www.jetify.com/docs/devbox/faq/index) describe project-scoped
  Nix-backed shells without Docker; [devenv](https://devenv.sh/) documents its
  development process/service/testing scope.
- The evaluated upstream snapshots were inspected at
  [`bgub/nix-macos-starter`](https://github.com/bgub/nix-macos-starter) commit
  `be8f6df68c5cdeacc6e7f4d8a37b1c785b0fb9f5` and
  [`mrkuz/macos-config`](https://github.com/mrkuz/macos-config) commit
  `54651b81549c9a83e3abf1a6703b162aa71bb60e`.
