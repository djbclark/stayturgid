# Red-team report: trust, deploy, and consent layer v1

- **Reviewer posture:** Assume compromise, not operator error.
- **Scope:** The final architecture v1 is authoritative. This report tests its
  release manifests, change plans, pull converge, consent, builders/caches,
  role mesh, and secret delivery design. It does not review the broader Nix or
  Android migration for reliability.
- **Verdict:** **do not ship v1 pull deployment or consent on the proposed
  one-key/one-manifest design.** A valid signature currently means “one key
  signed these bytes.” It does not establish fresh authorization, a safe
  target, a bounded operation, independent provenance, or recoverability after
  compromise. Those missing properties are where the system breaks.

The architecture correctly identifies several of these concepts as roadmap
items. That is not a mitigation when Phase 5 puts a timer-driven agent on an
operator host and Phase 6 lets a consented Android device act on the same
release artifact. A roadmap is not an enforcement point.

## 1. Assets and actual trust boundaries

### Assets that must not be violated

1. **Execution authority:** no attacker may cause an operator host, builder,
   Android agent, or Shizuku-capable component to execute code or a privileged
   operation.
2. **Release integrity and freshness:** a host must apply the exact release
   authorized for _that host and channel_, once, in the intended order; it must
   not be frozen, replayed, mixed with another release, or silently downgraded.
3. **Consent authority:** a person’s approval must bind one comprehensible,
   bounded operation to their device, and a refusal must remain effective.
4. **Secrets and signing keys:** release, cache, SSH-CA, Android/ADB, cloud,
   and service credentials declared by the real `site-private/secretspec.toml`
   must not become available merely because a service, feature, or plan names
   a handle.
5. **Single-writer safety:** release publication, secret rotation, role
   leadership, and stateful service changes must not split brain during a
   partition or stale inventory view.
6. **Evidence:** receipts, release history, and deployment telemetry must be
   attributable and resistant to deletion, forgery, and equivocation.

### Boundaries as designed versus as they actually work

| Claimed boundary                                      | What it actually proves                                                                                                                                                                                                                                      | What it does **not** prove                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Minisign/Ed25519 manifest signature                   | A holder of the pinned private key signed the exact input bytes. Minisign is deliberately a small file-signing tool built on Ed25519. [Minisign README](https://github.com/jedisct1/minisign#overview)                                                       | That the signer was the operator, that the release is current, that the plan is safe, that the source was reviewed, or that a target may perform the operation. |
| `nix store diff-closures` plan                        | A package/closure delta for the selected Nix generations.                                                                                                                                                                                                    | Effects of activation scripts, runtime services, Ansible tasks, fetched data, mutable state, or an APK’s behavior. It is evidence, not an execution sandbox.    |
| Ansible `--check --diff` plan                         | A best-effort prediction by modules that support check mode under current facts.                                                                                                                                                                             | That every task is represented, that runtime facts will match, or that normal execution cannot perform additional effects.                                      |
| SSH CA and Tailscale                                  | SSH peer authentication and encrypted network transport. Tailscale says tailnet connections are end-to-end encrypted, but application authorization remains separate. [Tailscale encryption](https://tailscale.com/docs/concepts/tailscale-encryption)       | Builder provenance, cache-output correctness, application authorization, release freshness, or protection from an authorized hostile peer.                      |
| Harmonia/Attic cache signature                        | A configured cache key vouched for a NAR/store object. Nix explicitly warns that a configured cache private key can substitute arbitrary files, including elevated executables. [Nix cache guide](https://nix.dev/guides/recipes/add-binary-cache.html)      | That the output was produced by the intended derivation, reviewed source, or an uncompromised builder.                                                          |
| `trust_tier: consented`                               | At most, a classification in the Site Model; the proposal also excludes direct site-secret references for that tier.                                                                                                                                         | An OS-level security boundary unless every executor and resolver independently enforces it. It does not turn a hostile handset into a truthful consent witness. |
| Local append-only receipt and future transparency log | A local statement that an agent claims a decision occurred. Rekor-style logs can make append-only history auditable only when inclusion/consistency proofs and monitors are actually verified. [Rekor overview](https://docs.sigstore.dev/logging/overview/) | A durable receipt today, prevention of device-local deletion, or detection of split views before T1 exists.                                                     |

The decisive boundaries are therefore: the source-to-signing pipeline, the
release-key policy, the client’s persisted update state, the executor’s
operation allowlist, the secret resolver, Android’s package/privilege boundary,
and the cache signing key. The manifest, plan, SSH CA, and `trust_tier` labels
are inputs to those boundaries, not replacements for them.

The current real-world configuration makes this distinction material:
`site-private/secretspec.toml` declares highly privileged handles (including
SSH-CA, ADB, service, cloud, and cache-bootstrap-adjacent material), while the
inventory currently contains operator-controlled Android peers plus planned
host roles. Naming a handle or assigning a role must never imply authority to
receive it.

## 2. Attacker models

| Adversary                                                           | Capability assumed                                                                                                                                       | Primary findings    |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| Compromised release signer / stolen release key                     | Signs arbitrary manifests, plans, and artifacts; may retain an old valid key.                                                                            | RT-01, RT-02, RT-03 |
| Malicious or compromised AI coding agent with worktree write access | Alters source, release tooling, plan renderer, lock files, or policy before a legitimate signing ceremony.                                               | RT-03, RT-09        |
| Insider with legitimate release or site access                      | Uses valid authority outside intended scope, or exfiltrates a signing/cache/secret key.                                                                  | RT-01, RT-05, RT-06 |
| Compromised builder or cache                                        | Builds a malicious closure, signs a NAR, uses its trusted SSH identity, or serves selective outputs.                                                     | RT-05               |
| Malicious feature-bundle author                                     | Hides a privileged effect behind a broad declared capability or a plan representation that the executor does not constrain.                              | RT-04, RT-06        |
| Hostile or compromised consented device                             | Forges/deletes local receipts, prompts repeatedly, replays acceptance, exports metadata, or attacks peers over allowed paths.                            | RT-02, RT-04, RT-07 |
| Active network attacker or malicious mirror on/near the tailnet     | Blocks, delays, reorders, replays, or selectively serves already valid artifacts. A network-only attacker cannot forge Tailscale traffic or a signature. | RT-02, RT-07        |
| Nixpkgs/input/cache supply-chain attacker                           | Causes a locked input, builder, or configured cache key to yield an unwanted executable closure.                                                         | RT-03, RT-05        |
| Compromised upstream Shizuku or Android dependency                  | Delivers a validly signed-but-malicious privileged APK/dependency through the normal release path.                                                       | RT-08               |
| Local-fix/upstream-heal attacker                                    | Gets a local emergency patch or purported upstream replacement accepted as the healing path.                                                             | RT-09               |

## 3. Findings

### RT-01 — One release key is fleet-root and there is no recovery protocol

- **Severity:** Critical
- **Preconditions:** Theft of the minisign private key; compromise of the host
  used for signing; or an insider permitted to use it.
- **Attack walkthrough:**
  1. The attacker produces an `ops-v` release with a valid manifest, per-host
     plans, and artifacts that contain an SSH persistence hook, altered
     converge agent, or Android APK.
  2. They sign it with the one accepted key and publish it through an available
     mirror/release channel.
  3. The pull agent’s stated algorithm is only “fetch latest `ops-v*` tag →
     verify signature → if new, apply.” It accepts the attacker as the release
     authority. A push path consumes the same artifact.
  4. The malicious converge agent survives later remediation and can accept a
     replacement root/key policy before the operator discovers the theft.
- **What breaks:** Every host trusting the key, including the release and
  deployment machinery itself. Offline verification makes availability
  independent, but makes a single stolen root sufficient. A `key id` is only a
  selector; it is not threshold authorization, scoped delegation, revocation,
  or an incident response channel.
- **Concrete mitigation:** Do not make v1 clients trust one release key. Ship a
  versioned root metadata object with at least a 2-of-3 offline threshold for
  root/release-policy changes; keep signing shares on separate devices and use
  a hardware-backed or air-gapped ceremony. Use separate, scoped keys for
  releases, emergency recovery, and low-risk delegated content. Clients must
  accept a root/key revocation only under the old-and-new threshold policy and
  have an out-of-band emergency root update procedure. This is not gold
  plating: TUF explicitly treats threshold roles, offline root keys, revocation,
  and key migration as core update-system properties. [TUF specification](https://theupdateframework.github.io/specification/latest/)

### RT-02 — Valid old releases can be replayed, frozen, and mixed

- **Severity:** High
- **Preconditions:** Access to any old signed release asset, a malicious
  mirror, an attacker who can delay traffic, a compromised device clock, or
  ambiguous “latest tag” ordering. No signing-key theft is required.
- **Attack walkthrough:**
  1. The attacker retains a signed release from before a security repair or
     revocation.
  2. They block discovery of newer releases and serve the old manifest/plan and
     matching immutable artifacts to a newly provisioned, reset, or partitioned
     host.
  3. The v1 manifest described in the authoritative proposal has release id,
     hashes, and key id, but no required channel, monotonically increasing
     target version, expiry, signed timestamp, snapshot binding, persisted
     highest-seen state, or anti-mix-and-match rule.
  4. The host verifies a real signature and applies vulnerable state. A hostile
     handset can similarly present a previously accepted plan to its own local
     logic if acceptances are not nonce- and sequence-bound.
- **What breaks:** Security rollback protection, revocation, freshness, and
  coherent fleet state. The ordinary network MITM does not decrypt Tailscale;
  it can still deny service, while a mirror or authorized endpoint can replay
  authentic bytes. A signature alone cannot distinguish “old but authentic”
  from “authorized now.” TUF names rollback, freeze, and mix-and-match as
  separate update threats for exactly this reason. [TUF threat goals](https://theupdateframework.github.io/specification/latest/#152-goals-to-protect-against-specific-attacks)
- **Concrete mitigation:** Before pull ships, define a client update protocol:
  pinned root; channel-specific targets; signed metadata version and expiry;
  timestamp/snapshot/targets binding; exact artifact length/digest; and durable
  per-target highest-seen version/hash. Reject regressions and inconsistent
  metadata. Use a monotonic-clock strategy resilient to a bad wall clock, and
  make any security downgrade an explicitly named, threshold-signed emergency
  action with a bounded expiry and local evidence. Test replay, freeze,
  fast-forward, target mix, reset, and clock-rollback cases.

### RT-03 — Signed plans do not constrain execution, so source or pipeline compromise is laundered

- **Severity:** Critical
- **Preconditions:** A compromised AI agent/insider can write a task worktree,
  release input, Ansible role, Nix activation script, lock file, or plan
  generator; then a normal operator signs the resulting release. This is a
  realistic in-scope precondition: the cross-agent rules document a real
  2026-08-06 double-merge incident caused by shared-worktree/provenance
  failures.
- **Attack walkthrough:**
  1. The attacker adds a conditional Ansible task, activation hook, generated
     service, or dependency that opens a remote channel only on the production
     host/device.
  2. They adjust the human plan summary or rely on an Ansible module that has
     incomplete check-mode behavior. `diff-closures` shows a package delta;
     `--check --diff` predicts tasks. Neither is a complete semantic model of
     side effects.
  3. A legitimate release ceremony signs the exact hashes. Signature
     verification then certifies the attacker’s bytes, and the converge agent
     executes a general-purpose closure/playbook rather than a narrow
     capability program.
  4. Auditers see a valid manifest and a plausible plan, not the compromised
     source-to-signing provenance.
- **What breaks:** The central claim that a signed machine-readable plan is
  the authorization contract for push, pull, consent, advisors, and WoT. It is
  only a description unless the executor mechanically refuses effects outside
  the signed operation set. The proposed plan formats are especially weak for
  Android/Ansible; a hash of an APK or playbook identifies opaque code, not its
  authority.
- **Concrete mitigation:** Treat source-to-signing as part of the trusted
  computing base. Build/sign only from an isolated, clean, pinned checkout of
  reviewed commits; forbid signing from task worktrees. Require two-person
  provenance review for changes to release tooling, executors, policy,
  secrets, and privilege boundaries. Attach in-toto/SLSA-style attestations
  binding commits, lockfiles, builder identity, reproducibility result, plans,
  and artifacts. Most importantly, define a typed operation IR with declared
  preconditions, resources, capabilities, rollback, and target key; make push
  and pull executors enforce that IR, not execute arbitrary playbooks because
  their hash appears in a signed JSON object. Test that undeclared network,
  process, filesystem, secret, and package effects fail closed.

### RT-04 — `offer()` is consent theater without a capability-enforcing executor

- **Severity:** High
- **Preconditions:** A malicious feature-bundle author or valid release signer
  submits a plan whose displayed summary is narrower than its actual effect;
  or a hostile/compromised device reuses a prior approval.
- **Attack walkthrough:**
  1. A bundle declares a broad, superficially honest capability such as
     “manage recovery service” and a plan asks to update it.
  2. Its APK/Ansible payload installs a persistent daemon, changes peer targets,
     calls Shizuku beyond the user’s understanding, or phones home through an
     already-allowed path.
  3. The device renders the human-readable plan and receives `accept`. The
     specified v1 receipt is only “decision + manifest hash” in a local log;
     the interface provides no operation capability set, target public-key
     binding, expiry, nonce, refusal persistence, user-verifiable payload
     digest, or rule that timeout is deny.
  4. The generic executor applies the opaque artifact. The future catalog and
     advisor cannot repair approval that already delegated arbitrary execution.
- **What breaks:** Meaningful consent and least privilege. “A bundle cannot
  self-register undeclared daemons” is ineffective unless a local reference
  monitor knows every daemon, port, path, secret handle, Shizuku action,
  privilege, rollback action, and network destination it may use and blocks all
  others. The `trust_tier` label and a human prompt do not do this themselves.
- **Concrete mitigation:** Make v1 consent operation-specific: signed plan ID,
  target device public-key fingerprint, release sequence, exact capability
  vector, artifact digest, expiry, single-use nonce, and rollback identity.
  `timeout` and UI failure must be deny. Keep accepted grants in a
  integrity-protected local store and make the executor compare every requested
  operation to the grant; no broad “run bundle” permission. Ship a small
  capability map first (for example, one bounded peer-help action) and deny
  ports, service registration, package installs, secret access, and Shizuku
  operations unless individually granted. Receipts should be device-signed and
  exportable without revealing unnecessary identifiers.

### RT-05 — CA-bound builders and signed caches are a confused trust boundary

- **Severity:** Critical
- **Preconditions:** Compromise of a builder, Harmonia/Attic host, cache
  signing key, or an operator host permitted to configure trusted cache keys.
- **Attack walkthrough:**
  1. The attacker compromises an `operator`-tier builder or its cache service.
     Its SSH host certificate remains valid, so consumers can still connect.
  2. They serve a malicious NAR for a requested non-content-addressed store
     path and sign it with the configured cache key, or build a compromised
     output and upload it through a legitimate multi-uploader cache path.
  3. A consumer accepts it because the cache key is trusted. Nix documentation
     is explicit: trusted cache private-key possession permits arbitrary store
     object substitution, potentially including privileged executables.
  4. The release manifest’s proposed “closure hash” does not specify a
     per-NAR content-verification protocol, nor is independent reproduction
     required. The cache output reaches a system activation path.
- **What breaks:** All consumers of the cache. SSH CA binding authenticates the
  host that served/built content; it does not attest to the source, derivation,
  or bytes. Declaring builders `trust_tier: operator` acknowledges the blast
  radius but does not contain it. The bootstrap exception for a cache signing
  key further makes that key a fleet-critical secret before the regular secret
  machinery exists.
- **Concrete mitigation:** Separate builder identity, cache upload authority,
  cache serving authority, and release authorization; do not make any one of
  them sufficient for deployment. Pin Nix inputs and require reproducible,
  independently rebuilt critical closures before release. Bind every deployable
  closure to a signed inventory of NAR hashes/sizes and verify it after fetch
  before activation; prefer content-addressed/fixed-output artifacts where
  practical. Use distinct short-lived, scoped upload credentials; keep the
  cache signing key in hardware-backed or isolated service custody; rotate it
  under the RT-01 threshold protocol; and make a compromised cache removable
  without reinstalling the fleet. Nix’s default `require-sigs` only means a
  trusted key signed the object, not that it was safely built. [Nix `trusted-public-keys`](https://nix.dev/manual/nix/latest/command-ref/conf-file.html#conf-trusted-public-keys)

### RT-06 — SecretSpec handle injection becomes a privilege-escalation API

- **Severity:** High
- **Preconditions:** A malicious service contract, bundle, role assignment,
  playbook, or release gains the ability to name a SecretSpec handle; or a
  bootstrap host is compromised.
- **Attack walkthrough:**
  1. The attacker adds `secret_handle: SSH_CA_KEY`, a cloud token, cache key,
     ADB material, or another existing declaration to a service/bundle that is
     expected to run as the operator or a privileged agent.
  2. The proposed `secretspec` wrapper resolves the handle at runtime to honor
     the signed configuration. No v1 policy says the resolver verifies that
     this service identity, host role, and exact operation are entitled to the
     handle.
  3. The service exfiltrates the value through its network access, process
     arguments, logs, inherited environment, crash reporter, or a world-readable
     temporary file. A compromise of the bootstrap exception can similarly take
     the cache key before normal policy applies.
  4. The attacker moves from a service-level change to signing, remote access,
     fleet ADB, or cloud control.
- **What breaks:** The promise that no secret appears in a Nix store is much
  narrower than the security property needed. Secret _delivery_ is an
  authorization problem. The consented-device “no direct reference” lint does
  not protect operator/managed hosts, transitive service dependencies, or an
  already-compromised resolver.
- **Concrete mitigation:** Make the resolver a deny-by-default reference
  monitor. A signed policy must map `(service identity, host key/role, exact
capability, release sequence)` to an allowlisted secret handle; the resolver
  must reject all other requests and write non-secret audit events. Stage
  credentials as per-service, non-inherited runtime files/credentials with
  minimal OS permissions, not ambient environment variables; scrub logs and
  test process inspection. Separate bootstrap material into a minimal recovery
  root with its own threshold rotation and no access to normal site secrets.
  Add tests proving a bundle cannot obtain a handle by name, alias, template
  expansion, transitive dependency, or post-activation process injection.

### RT-07 — A role mesh has no specified lease/fencing protocol and its converger is trivially exhaustible

- **Severity:** High
- **Preconditions:** Network partition, stale Site Model/cache, clock skew,
  compromised peer, or a release that changes role assignments. For denial of
  service, only access to the configured release/mirror path or a costly valid
  artifact is needed.
- **Attack walkthrough:**
  1. Partition primary and backup role holders. Each sees a signed but different
     role assignment or waits according to a local interpretation of a timeout.
  2. Both conclude they may publish, rotate, lead an observability sink, or
     modify a singleton resource. The final document calls for “lease/fencing
     semantics” and a recorded handoff, but defines no lease issuer, quorum,
     epoch, durable witness, fence action, or behavior when the witness is
     unavailable.
  3. An attacker keeps the partition open or floods the ~50-line timer agent
     with expensive release checks/downloads/build attempts. CFEngine keeping
     the agent alive can amplify this into a restart loop rather than preserve
     availability.
- **What breaks:** Single-writer safety, secret rotation, release lineage, and
  host availability. An operator-signed _plan_ is not a distributed lease. A
  no-control-node mesh cannot get split-brain safety merely by putting ordered
  roles in YAML. Tailscale ACLs/grants can restrict network reachability, but
  application-level authorization is implemented by the application itself. [Tailscale grants limitations](https://tailscale.com/docs/features/access-control/grants#limitations-and-considerations)
- **Concrete mitigation:** Do not ship autonomous leadership or remote
  mutations in v1. For each singleton, choose a real authority: an
  operator-threshold-signed epoch with a durable quorum/witness, or a
  deliberately single designated owner that requires manual recovery. Fence
  the old holder before a new one acts; use monotonic epochs, bounded leases,
  idempotency keys, and a fail-closed partition state. For converge: immutable
  size limits, signed manifest-first fetch, bandwidth/CPU/disk quotas,
  exponential backoff with jitter, watchdog circuit breaker, rollback of the
  agent itself, and a locally operable kill switch. Test partitions and hostile
  mirrors, not only clean no-op updates.

### RT-08 — Privileged Android artifacts have no v1 provenance boundary

- **Severity:** High
- **Preconditions:** Compromise of Shizuku, its upstream distribution,
  stayturgid-agent dependency, Gradle/plugin supply chain, APK build machine,
  or the signer that publishes an opaque replacement APK.
- **Attack walkthrough:**
  1. A compromised dependency is incorporated into a normal Gradle build, or a
     malicious APK is produced on a trusted builder.
  2. Its SHA-256 is recorded in the manifest and the manifest is validly signed.
  3. The consent prompt truthfully says an APK changes, but it cannot establish
     source provenance, reproducibility, Android signing-certificate lineage,
     requested/used privileged APIs, or code behavior.
  4. Once installed, the component abuses the Shizuku/Android privilege
     boundary, alters recovery/peer behavior, or exfiltrates device data.
- **What breaks:** The claimed consent trust boundary on precisely the devices
  with the least reliable remote recovery and strongest local privilege
  consequences. The authoritative design postpones reproducible APK and
  artifact provenance to T6; a digest signed by the same compromised release
  authority cannot substitute for it.
- **Concrete mitigation:** Move a narrow Android provenance gate ahead of
  consent v1: immutable dependency locks; verified source revision; SBOM;
  isolated reproducible build; independent rebuild comparison for privileged
  APKs; signed provenance bound to the release manifest; Android signing
  certificate pin/rotation policy; and per-release diff of permissions,
  exported components, Shizuku operations, and network endpoints. Reject any
  artifact that lacks the evidence. Do not offer consent for an opaque
  Shizuku-capable binary and call it informed approval.

### RT-09 — The local-fix-until-upstream-heals loop is an unbounded code-injection channel

- **Severity:** High
- **Preconditions:** An attacker can propose or influence a local emergency
  patch, a supposedly fixed upstream release, an advisor result, or the agent
  that decides upstream has “healed.”
- **Attack walkthrough:**
  1. The attacker induces a failure and offers a local patch that restores
     service while adding persistence or altering the trust/update code.
  2. The local patch rides normal release signing because emergency operation is
     valuable. It has no declared maximum scope, expiry, provenance, or
     independent review requirement.
  3. Later, a release merely claiming to contain the upstream fix is signed or
     advisor-cleared. The converge agent “prefers upstream,” effectively making
     an automated merge/selection decision about privileged code.
  4. The attacker uses naming/version confusion, a compromised upstream, or a
     compromised advisor to preserve their patch or replace it with a different
     payload.
- **What breaks:** Change-control provenance precisely when the system is under
  operational pressure. The future transparency log records a bad decision; it
  does not authorize safe code selection. An AI advisor must never be an
  authorization oracle.
- **Concrete mitigation:** Remove automatic merge/selection from the trust
  model. An emergency local fix must be a separately scoped, threshold-signed
  override with a patch digest, target list, capability delta, expiry, rollback,
  and mandatory human review. Replacing it requires a deterministic patch/
  artifact equivalence or an explicit human approval of the semantic delta,
  never “version contains fix.” Advisor output may explain evidence but must not
  change authorization. Keep a kill switch that disables all local overrides.

## 4. Systemic gaps

These are absent or only gestured at; none should be represented as provided by
minisign, a Git tag, a CA-signed builder, or a future roadmap label.

| Gap                                         | Why the current design does not cover it                                                                                                                                                                                                                                                                 | Required disposition                                  |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| **Revocation and compromised-key recovery** | Key id recording has no signed revocation object, root policy, distribution channel, threshold, or out-of-band recovery.                                                                                                                                                                                 | **Before v1 pull.**                                   |
| **Key rotation**                            | There is no old/new key overlap rule, versioned root metadata, device update ordering, or lost-device process.                                                                                                                                                                                           | **Before v1 pull.**                                   |
| **Rollback/downgrade**                      | Nix rollback is operational recovery, not a secure update downgrade protocol. No release counter/high-water mark is defined.                                                                                                                                                                             | **Before v1 pull.**                                   |
| **Time, replay, and freeze**                | No expiry, timestamp, trusted-time strategy, persisted metadata version, or mirror consistency rule exists.                                                                                                                                                                                              | **Before v1 pull.**                                   |
| **Metadata privacy**                        | Release/plan/consent telemetry includes host/device and feature data, while consented-device pseudonymization, retention, access, and opt-out are undefined. A future public transparency log can make this permanent.                                                                                   | **Before consent pilot.**                             |
| **Quorum and split brain**                  | “Primary/backup/peer ordering,” timeout, and recorded handoff are requirements, not a lease/fencing protocol.                                                                                                                                                                                            | **Before autonomous role failover.**                  |
| **Converge-agent denial of service**        | The small size of the agent does not limit download, parsing, evaluation, disk, CPU, timer, or restart abuse.                                                                                                                                                                                            | **Before enabling timers.**                           |
| **Trust bootstrap / TOFU**                  | No trusted initial root distribution, device replacement procedure, or protection against first-contact mirror substitution is defined. TUF explicitly treats bootstrapping separately from normal update security. [TUF scope](https://theupdateframework.github.io/specification/latest/#14-non-goals) | **Before first non-operator client enrollment.**      |
| **Source and approval provenance**          | The documented double-merge incident proves repository/process provenance is an active boundary. A valid tag or green CI cannot establish it.                                                                                                                                                            | **Before signing ceremony.**                          |
| **`local-fix` injection**                   | The T4 preference rule does not establish identity, equivalence, expiry, or approval semantics.                                                                                                                                                                                                          | **Do not automate; gate any prototype.**              |
| **Transparency-log equivocation**           | T1 says append-only but not who operates witnesses, how clients verify inclusion/consistency, or how offline clients reconcile a split view.                                                                                                                                                             | **Before relying on log evidence for authorization.** |

## 5. Prioritized fix list

### Blockers before v1 ships

1. **Define and implement the client update protocol, not just a signed file.**
   Pinned versioned root, threshold roles, scoped delegations, key rotation and
   revocation, channel/target binding, expiry, monotonic state, rollback
   rejection, exact lengths/digests, and an out-of-band recovery runbook.
2. **Make the execution boundary real.** Define a canonical typed ChangePlan
   operation IR and have push, pull, Android, and consent executors reject any
   effect outside its signed per-target capabilities. Do not authorize arbitrary
   Ansible/playbook/APK execution merely by hashing it.
3. **Harden the source-to-signing pipeline.** Isolated clean release builds,
   commit/lockfile/artifact provenance, human provenance review, two-person
   approval for trust-boundary changes, reproducibility checks, and no signing
   from a task worktree. Treat the documented agent double-merge failure as a
   release-control test case.
4. **Contain cache and builder compromise.** Separate keys and roles; verify
   NAR content inventory before activation; use reproducible independent builds
   for privileged closures; scope/rotate cache upload/signing credentials; and
   prove a cache can be revoked without fleet reinstallation.
5. **Build SecretSpec runtime authorization.** Per-service/host/capability
   allowlists enforced by the resolver, non-ambient delivery, audit events,
   minimal bootstrap root, and exfiltration tests.
6. **Limit v1 topology.** Pull only on operator-owned hosts after the above
   checks; no autonomous role failover, secret rotation, release publication,
   or remote singleton mutation. Add converge resource limits and kill switch.

### Required before the first consented-device pilot

1. Default-deny, single-use, expiring, device-key-bound consent grants with an
   executor-enforced capability map and protected signed receipts.
2. Android provenance gate: reproducible privileged APK builds, dependency
   locks/SBOM, signing-certificate policy, and a machine-readable privilege/
   permission/network delta.
3. Consent privacy design: pseudonymous identifiers, local-first receipts,
   retention/access rules, and no public log replication without informed
   opt-in and verifiable inclusion/consistency handling.
4. A narrow pilot operation with proven rollback, adversarial UI/timeout/
   replay tests, and no generic feature bundle capability.

### Acceptable roadmap only after the blockers are closed

- Sigstore/Rekor integration as supplementary provenance/transparency. It is
  useful once clients verify inclusion/consistency and have monitor/witness
  operations; it cannot compensate for a compromised release root.
- Delegated feature catalogs and graded web-of-trust policies, but only with
  scoped threshold delegations, revocation, expiry, and a deterministic local
  policy evaluator.
- Autonomous role mesh and failover, but only after a real fencing/quorum
  design exists and survives partition tests.
- Builder/cache scale-out, after independently verifiable output provenance is
  routine.
- Local-fix/upstream-heal assistance, retained as an advisory workflow with
  explicit human/threshold approval; never an automatic authority path.

## Sources checked

- [stayturgid 2.0 final architecture v1](architecture-final-v1.md) —
  authoritative requirements and phase gates.
- [stayturgid 2.0 detailed proposal v1](architecture-proposal-v1.md) §§6–8,
  12, 14 — manifest, cache, pull, consent, secrets, and roadmap detail.
- [OpenAI alternative proposal](architecture-proposal-openai-v1.md) §5–6 —
  stronger but non-authoritative suggestions such as per-device pinning,
  capability maps, monotonic policy, and secret handles; their presence there
  does not make them v1 guarantees.
- [Grok alternative proposal](architecture-proposal-grok-v1.md) §7–8 —
  additional non-authoritative release/plan ideas.
- `/Users/djbclark/ops/site-private/secretspec.toml`,
  `/Users/djbclark/ops/site-djbclark/inventory/hosts.yml`, and
  `/Users/djbclark/ops/site-djbclark/registry/` — ground truth for the
  existence of privileged secret handles, Android peers, planned host roles,
  and service/network ownership. No secret values were read or recorded.
- [/Users/djbclark/src/ops-worktrees/README.md](/Users/djbclark/src/ops-worktrees/README.md)
  — cross-agent provenance rules and the documented 2026-08-06 double-merge
  incident.
- [The Update Framework specification](https://theupdateframework.github.io/specification/latest/),
  [Nix custom binary-cache guidance](https://nix.dev/guides/recipes/add-binary-cache.html),
  [Nix remote-build requirements](https://nix.dev/manual/nix/latest/advanced-topics/distributed-builds.html),
  [Minisign](https://github.com/jedisct1/minisign),
  [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/), and
  [Tailscale grants](https://tailscale.com/docs/features/access-control/grants)
  — current primary-source behavior used to separate transport/signature/cache
  guarantees from protocol and authorization guarantees.
