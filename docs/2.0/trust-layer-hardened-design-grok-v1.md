# Hardened trust-layer design v1 (Grok defensive counter-pass)

- **Author posture:** Defense. The red-team findings are treated as largely
  correct; this document designs the smallest shippable system that closes
  the blockers, and names where the right answer is **not building the
  surface** rather than inventing machinery a solo operator will never run.
- **Slug:** `grok`
- **Date:** 2026-08-08
- **Answers:** `docs/2.0/redteam-trust-layer-openai-v1.md`
- **Architecture authority:** `docs/2.0/architecture-final-v1.md` (amends
  proposal §7–8/§12 only where this document says so for security gates)
- **Operator shape assumed:** one human, one laptop (M1 Air), three Android
  peers (s24, p7a, hd8), planned VPS/mac-mini not yet live, privileged
  SecretSpec handles including `SSH_CA_KEY` / `FLEET_ADBKEY` / cloud / obs /
  FIRERPA material (names only; values never read).

**Verdict of this counter-pass:** Agree with the red-team that **v1 must not
ship pull deployment or consent on the proposed one-key / one-manifest
design.** The fix is not “more roadmap labels.” It is:

1. **Aggressive scope cuts** that close Critical/High findings for free.
2. A **buildable TUF subset** + typed operation IR for what _does_ ship.
3. Explicit gates so Phase 5/6 cannot open until entry criteria hold.

---

## 1. Disposition of every red-team finding

Disposition vocabulary:

| Code                   | Meaning                                         |
| ---------------------- | ----------------------------------------------- |
| **FIX-IN-V1**          | Specify and build now (§2).                     |
| **CLOSE-BY-SCOPE**     | Vulnerable surface not built in v1; gate named. |
| **ACCEPT-RISK**        | Explicit blast radius + detection.              |
| **DEFER-WITH-TRIGGER** | Named condition forces the work.                |

### 1.1 Findings RT-01 … RT-09

| ID                                                   | Agree?    | Disposition                                                                                                                                     | Notes                                                                                     |
| ---------------------------------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **RT-01** One release key is fleet-root; no recovery | **Agree** | **FIX-IN-V1** (root metadata + recovery runbook for _any_ signed release path); **CLOSE-BY-SCOPE** for multi-role online timestamp if push-only | Solo 2-of-3 offline root (§2.1). Not full org-grade HSM mesh.                             |
| **RT-02** Replay / freeze / mix-and-match            | **Agree** | **FIX-IN-V1** for client protocol on anything that _pulls or verifies updates_; **CLOSE-BY-SCOPE** for fleet-wide pull until protocol is live   | §2.2 client algorithm. Push-only v1 still needs high-water state on _targets that apply_. |
| **RT-03** Signed plans do not constrain execution    | **Agree** | **FIX-IN-V1**                                                                                                                                   | Typed ChangePlan IR + executor allowlist (§2.3). Highest-value artifact.                  |
| **RT-04** `offer()` is consent theater               | **Agree** | **CLOSE-BY-SCOPE** for consent pilot; **FIX-IN-V1** interface spec so Phase 6 cannot regress                                                    | Spec in §2.4; **no consented device ships until** gate G6.                                |
| **RT-05** Builder/cache confused deputy              | **Agree** | **CLOSE-BY-SCOPE** for private cache/builder roles; **FIX-IN-V1** policy for public cache + optional later                                      | No harmonia/attic in first 90 days. When built: separated authorities (§2.5).             |
| **RT-06** SecretSpec handle injection                | **Agree** | **FIX-IN-V1** (minimal reference monitor)                                                                                                       | Deny-by-default map for services that already resolve secrets on operator hosts (§2.6).   |
| **RT-07** Role mesh lease/fencing + converger DoS    | **Agree** | **CLOSE-BY-SCOPE** autonomous failover; **FIX-IN-V1** single-writer = operator + flock; converger quotas only when pull exists                  | §2.7.                                                                                     |
| **RT-08** Android provenance gap                     | **Agree** | **CLOSE-BY-SCOPE** consent; **DEFER-WITH-TRIGGER** full SLSA-ish APK path; **FIX-IN-V1** digest + cert pin for _operator-pushed_ APKs           | Consent never for opaque Shizuku APKs.                                                    |
| **RT-09** local-fix → upstream-heal injection        | **Agree** | **CLOSE-BY-SCOPE** — do not automate                                                                                                            | Advisory-only; human threshold for any override. T4 stays roadmap, never auto-auth.       |

### 1.2 Systemic gaps (red-team §4)

| Gap                                   | Disposition                                                                              | Gate                                                                                                           |
| ------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Revocation / compromised-key recovery | **FIX-IN-V1**                                                                            | Required before any non-interactive apply of signed artifacts (including push that consumes signed manifests). |
| Key rotation                          | **FIX-IN-V1**                                                                            | Root version N→N+1 dual-threshold (§2.1).                                                                      |
| Rollback / downgrade protection       | **FIX-IN-V1**                                                                            | High-water marks (§2.2).                                                                                       |
| Time, replay, freeze                  | **FIX-IN-V1** for pull; **partial FIX** for push (expiry + channel on every signed plan) | Pull blocked until full algorithm.                                                                             |
| Metadata privacy                      | **CLOSE-BY-SCOPE** until consent pilot                                                   | Before Phase 6: local-first receipts; no public Rekor of device IDs without opt-in.                            |
| Quorum / split brain                  | **CLOSE-BY-SCOPE**                                                                       | No autonomous role failover in v1.                                                                             |
| Converge-agent DoS                    | **CLOSE-BY-SCOPE** until timers; **FIX-IN-V1** when pull agent exists                    | Resource limits mandatory with first timer.                                                                    |
| Trust bootstrap / TOFU                | **FIX-IN-V1** (operator install path)                                                    | Root shipped out-of-band with OS/agent image; no first-contact mirror trust.                                   |
| Source & approval provenance          | **FIX-IN-V1** (process + clean signing checkout)                                         | Signing forbidden from task worktrees; provenance script from 2026-08-06 incident.                             |
| `local-fix` injection                 | **CLOSE-BY-SCOPE**                                                                       | Do not automate.                                                                                               |
| Transparency-log equivocation         | **DEFER-WITH-TRIGGER**                                                                   | T1 only after clients can verify inclusion/consistency _and_ have a monitor; log never authorizes.             |

### 1.3 Disagreements with the red-team (narrow)

| Claim                                                                     | Position                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| “2-of-3 with hardware tokens is required for v1”                          | **Partial.** For a _solo_ operator, 2-of-3 **software-encrypted shares on physically separate devices** (laptop sealed keyfile + phone sealed keyfile + paper/USB cold share) is the MV threshold. YubiKey/HSM is **recommended** for the root ceremony later; requiring three hardware tokens before _any_ signed push would stall the suite indefinitely. Threshold still required for root/policy; release signing can be 1-of-N _targets_ key under a threshold-rooted policy. |
| “Full TUF client before any progress”                                     | **Disagree as sequencing.** Ship a **TUF subset** (root, targets-as-release, snapshot binding, expiry, high-water) first; online timestamp role can wait if update discovery is operator-initiated (push). Full timestamp/mirrors roles when pull timers exist.                                                                                                                                                                                                                    |
| “Independent rebuild of every privileged APK before any fleet APK deploy” | **Partial.** Required before **consent**; for **operator push** of stayturgid-agent, SHA-256 + Android signing-cert pin + dependency lock is enough v1; independent rebuild is the Phase-6 entry bar.                                                                                                                                                                                                                                                                              |

No Critical finding is rejected.

---

## 2. The hardened v1 design

### 2.1 Key / root model (answers RT-01)

#### 2.1.1 Design goals for one person

- Survive **theft of the laptop** without losing the fleet forever.
- Survive **theft of one share** without fleet takeover.
- Keep ceremony time under **~15 minutes** for a normal release.
- Avoid fake security (single minisign key in `~/.minisign` with password only).

Minisign remains the **signature primitive** (Ed25519, offline verify on
Termux, trusted comments for bound metadata). It is **not** the update
system. Minisign proves “holder of this secret signed these bytes”; trusted
comments can carry filename/version hints but do not give threshold,
revocation, or anti-freeze. Full TUF is overkill for three devices; the
subset below is not.

#### 2.1.2 Roles (TUF subset — what we take / leave)

| Role                  | Threshold (solo v1)                                 | Online?                   | Purpose                                                           |
| --------------------- | --------------------------------------------------- | ------------------------- | ----------------------------------------------------------------- |
| **root**              | **2-of-3** root keys                                | Offline                   | Keys for all other roles; revocation; root version bumps          |
| **targets** (release) | **1-of-1** _or_ 1-of-2 release keys listed in root  | Offline (laptop ceremony) | Signs release manifests + ChangePlans for a channel               |
| **snapshot**          | Same key as targets _or_ separate 1-of-1            | Offline with release      | Binds exact set of metadata digests/versions (anti mix-and-match) |
| **timestamp**         | **Deferred** if push-only                           | Would be online           | Freshness under pull; see §2.2                                    |
| **emergency**         | **2-of-3** root (or dedicated 2-of-3 emergency set) | Offline                   | Security downgrade, key wipe, “do not apply releases signed by K” |
| **cache-sign**        | Separate key; **not** root                          | Isolated later            | Only when private cache exists (§2.5)                             |

**Not in v1:** multi-level target delegations, mirrors role, path-hash
delegations, online automated snapshot.

#### 2.1.3 Where shares live (solo operator)

Generate three Ed25519 root keys (`root-a`, `root-b`, `root-c`). Root
metadata requires any **two** signatures.

| Share | Location                                                                                     | Protection                                                                |
| ----- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **A** | Operator laptop, path _outside_ git/worktrees (e.g. `~/.config/stayturgid/trust/root-a.key`) | minisign/age password; file mode 600; never in agent-writable dirs        |
| **B** | Phone (Termux or password manager attachment) _or_ second machine when online                | Separate password; not backed up to the same cloud as A                   |
| **C** | Paper backup (minisign secret printed / metal) **or** USB in a drawer                        | Physical; never photographed into the same Photos library as daily driver |

**Release (targets) key:** one daily-driver key on the laptop, passworded,
listed in root. Optional second release key on the phone for travel
signing. Compromise of the release key alone → attacker can sign releases
**until** root rotates targets keys (2-of-3 ceremony). That is intentional
blast-radius reduction vs compromise of root threshold.

**Do not** store root or release secrets in:

- task worktrees under `~/src/ops-worktrees/`
- agent-accessible secrets that coding agents can `cat`
- the public stayturgid repo or site-djbclark git history

#### 2.1.4 Root metadata object (concrete)

File: `root.json` (canonical JSON, signed by ≥2 root keys). Clients ship
with a **pinned** copy from out-of-band bootstrap.

```json
{
  "_type": "root",
  "spec_version": "stayturgid-1",
  "version": 1,
  "expires": "2027-08-08T00:00:00Z",
  "consistent_snapshot": true,
  "keys": {
    "root-a": {
      "keytype": "ed25519",
      "scheme": "ed25519",
      "keyval": { "public": "…" }
    },
    "root-b": {
      "keytype": "ed25519",
      "scheme": "ed25519",
      "keyval": { "public": "…" }
    },
    "root-c": {
      "keytype": "ed25519",
      "scheme": "ed25519",
      "keyval": { "public": "…" }
    },
    "release-1": {
      "keytype": "ed25519",
      "scheme": "ed25519",
      "keyval": { "public": "…" }
    }
  },
  "roles": {
    "root": { "keyids": ["root-a", "root-b", "root-c"], "threshold": 2 },
    "targets": { "keyids": ["release-1"], "threshold": 1 },
    "snapshot": { "keyids": ["release-1"], "threshold": 1 },
    "emergency": { "keyids": ["root-a", "root-b", "root-c"], "threshold": 2 }
  }
}
```

Signatures: minisign over canonical bytes **or** embedded multi-sig list
compatible with TUF-style verification. Implementation choice: **prefer
native minisign multi-file** (`root.json` + N `.minisig` files with trusted
comment `role=root;version=N`) if multi-sig JSON is too heavy for Termux
v1 — client still enforces threshold count of distinct keyids.

#### 2.1.5 Recovery runbooks

**A. Laptop lost / stolen (assume release key + root-A compromised)**

1. From phone + paper: collect **B + C** (or any 2 remaining if A is dead).
2. On a **clean** machine (borrowed Mac with live USB, or reinstalled laptop):
   generate new `release-2` and optionally new `root-a'`.
3. Sign `root.json` version **N+1** with 2-of-3 (must satisfy both old and
   new root threshold rules for intermediate roots — TUF §5.3 style):
   - Signatures valid under root N **and** under root N+1.
4. Publish `N+1.root.json` via GitHub Release + out-of-band channel
   (Signal-to-self, printed QR, second mirror).
5. **Manually** update each host once (USB/ADB/SSH push of new root) if
   pull is not yet trustworthy; with pull, clients walk N→N+1.
6. Revoke: root N+1 drops compromised keyids.
7. Rotate SSH CA / ADB / FIRERPA if laptop may have held them (ops
   incident, not only trust-meta).

**B. Release key stolen, root intact**

1. 2-of-3 root ceremony: new `release-k`, root version bump, drop old
   release keyid.
2. Force clients to reject any release signed only by old key after root
   update.
3. Audit last N releases; re-push known-good if needed.

**C. Two root shares lost (cannot form threshold)**

1. Treat as **catastrophic**. Out-of-band re-bootstrap: physical access to
   every host, install new root as TOFU replacement **with human
   verification of fingerprint** (compare short hash on paper).
2. Document fingerprints in site-private offline; never only in chat logs.

**D. Threshold of root compromised**

1. Assume malware on affected machines. Rebuild hosts from clean media.
2. New root generated entirely offline; distributed only by physical
   presence / verified side channel.
3. TUF correctly calls this nearly unrecoverable in-band — we do not pretend
   otherwise.

#### 2.1.6 What full TUF we deliberately skip

| Full TUF piece                           | Why skip in solo v1                                                |
| ---------------------------------------- | ------------------------------------------------------------------ |
| Online timestamp role                    | No always-on signer; push-initiated freshness                      |
| Deep target delegations                  | One release authority is enough                                    |
| Mirrors metadata role                    | Fixed mirror list (GitHub Releases + optional R2) in client config |
| Multi-repo roots                         | Single suite root                                                  |
| Consistent snapshot file naming at scale | Optional until multi-artifact races matter                         |

We **keep** from TUF: threshold root, version monotonicity, expiry,
snapshot binding of metadata digests, exact length+hash of targets,
persisted high-water, root rotation with dual-threshold, rollback rejection.

---

### 2.2 Update protocol (answers RT-02)

#### 2.2.1 Artifact set per release

Published under `ops-vMAJOR.MINOR.PATCH` (existing train) **plus**:

| File                                  | Signed by                               | Contents                                          |
| ------------------------------------- | --------------------------------------- | ------------------------------------------------- |
| `root.json` (+ sigs)                  | root threshold                          | Only when root changes                            |
| `snapshot.json`                       | snapshot role                           | Digests/versions of targets metadata + release id |
| `targets.json` / `manifest.json`      | targets/release                         | Channel, seq, per-host plans, artifact inventory  |
| `plan/<host>.json`                    | targets (or covered by manifest digest) | Typed ChangePlan IR (§2.3)                        |
| Artifacts (APKs, tarballs, NAR lists) | content-addressed; digests in targets   | Exact length + sha256                             |

Channels: `stable` (default), `emergency` (requires emergency role or
root-threshold). Clients pin channel in local config.

#### 2.2.2 Required metadata fields (manifest / targets)

```json
{
  "_type": "targets",
  "spec_version": "stayturgid-1",
  "channel": "stable",
  "release_id": "ops-v1.4.0",
  "sequence": 1400,
  "version": 42,
  "expires": "2026-09-08T00:00:00Z",
  "created": "2026-08-08T18:00:00Z",
  "targets": {
    "plans/mac.json": {
      "length": 8192,
      "hashes": { "sha256": "…" },
      "custom": {
        "host_id": "mac",
        "host_pubkey_fpr": "sha256:…",
        "plan_id": "plan-mac-ops-v1.4.0"
      }
    },
    "artifacts/stayturgid-agent-universal.apk": {
      "length": 12345678,
      "hashes": { "sha256": "…" },
      "custom": {
        "android_cert_sha256": "…",
        "package": "…",
        "version_code": 42
      }
    }
  },
  "snapshot_hash": "sha256:…",
  "root_version_required": 1
}
```

Rules:

- `sequence` is a **fleet-global integer** strictly increasing per channel
  (not semver alone — semver can be re-tagged by humans; sequence is the
  anti-rollback counter).
- `expires` max horizon for stable: **≤ 45 days** from `created` (solo
  operator can re-sign; short expiry defeats freeze).
- Every target has **length + sha256**.
- `host_pubkey_fpr` binds plan to inventory identity (SSH host key or
  device install-time key), not just hostname string.

#### 2.2.3 Client persisted state (per host)

Path example: `/var/lib/stayturgid/update-state.json` (Linux),
`~/Library/Application Support/stayturgid/update-state.json` (macOS),
Termux: `$PREFIX/var/lib/stayturgid/update-state.json`.

```json
{
  "channel": "stable",
  "trusted_root_version": 1,
  "highest_sequence": 1399,
  "highest_release_id": "ops-v1.3.11",
  "last_targets_version": 41,
  "last_snapshot_hash": "sha256:…",
  "last_success_monotonic": 1234567.89,
  "last_success_wall": "2026-08-01T12:00:00Z",
  "root_keyids": ["root-a", "root-b", "root-c"]
}
```

Atomic write (temp + rename). Corrupt state → fail closed, require operator
`stayturgid-update recover` with fingerprint confirm.

#### 2.2.4 Clock strategy

| Check     | Rule                                                                                                                                                                                       |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Expiry    | Compare metadata `expires` to **update-start wall clock**; if clock is before `last_success_wall - 1d`, **abort** (clock rollback suspicion) unless emergency channel with root-threshold. |
| Freeze    | If pull mode: if no newer timestamp/sequence for > `max_stale` (default 14d) while network OK, alert; do not silently keep applying old.                                                   |
| Monotonic | Always prefer `sequence` and metadata `version` over wall clock for rollback decisions.                                                                                                    |
| Android   | If automatic time disabled / skew > 6h vs last success, fail closed to operator.                                                                                                           |

#### 2.2.5 Client verification algorithm (ordered, testable)

**Inputs:** channel C, local state S, mirror URLs, pinned bootstrap root R0.

1. **Record** `t0 = now()` (wall) and reject if `t0 < S.last_success_wall - 24h`.
2. **Load trusted root** from disk (R). If missing, install only from
   bootstrap package with printed fingerprint match — never from mirror alone.
3. **Update root (optional path):** For n = R.version+1 …:
   - Fetch `n.root.json` (size cap 64 KiB).
   - Verify ≥ threshold sigs under R **and** under the new file’s root role.
   - Require new.version == R.version+1.
   - Persist; set R = new. Cap 32 steps.
4. **If R.expires ≤ t0:** abort (freeze / expired root) — operator must
   refresh root offline.
5. **Fetch snapshot** (size cap from config, default 256 KiB):
   - Verify snapshot role threshold under R.
   - Check snapshot.version ≥ S (if any) and not less.
   - Check snapshot.expires > t0.
6. **Fetch targets/manifest** at version/hash listed in snapshot:
   - Size must match snapshot meta length if present.
   - Hash must match snapshot meta hash.
   - Verify targets role threshold under R.
   - Require `channel == C`.
   - Require `sequence > S.highest_sequence` (equal → no-op success; less →
     **rollback attack**, abort).
   - Require `expires > t0`.
   - Require `root_version_required <= R.version`.
7. **Select this host’s plan** by inventory host id + optional pubkey fpr:
   - Fetch plan bytes; verify length+hash against targets entry.
   - Parse ChangePlan IR; reject unknown schema major.
8. **Fetch each artifact** listed in the plan’s `artifacts[]`:
   - Enforce per-file max size from plan (and global cap).
   - Verify sha256 and length.
   - For APKs: verify Android signing cert digest matches
     `custom.android_cert_sha256` if present.
9. **Executor gate (§2.3):** dry-run capability check; refuse undeclared
   effects.
10. **Apply** only if mode allows (push operator-driven, or pull if enabled).
11. **On success:** update S (sequence, hashes, times) **before** reporting
    success; emit receipt (local append-only).
12. **On any failure:** leave S unchanged (except maybe last_error log);
    do not partially mark sequence advanced.

**Tests required (CI + one device):** bad sig; expired; sequence downgrade;
snapshot/target hash mismatch; channel mismatch; host fpr mismatch; oversize
download; clock rollback; truncated body; mix plan from release A with
artifact from release B.

#### 2.2.6 Push path (v1 default)

Push is **not** exempt from verification:

- Operator host builds artifacts in a **clean release checkout**
  (see §2.3.5).
- Signs snapshot + targets with release key.
- `just deploy-host` **verifies** the same algorithm steps 5–9 locally
  against the just-built metadata **before** Ansible/deploy-rs runs.
- Target host re-verifies plan hash + IR before activation (Android agent /
  thin wrapper).

This closes “signature launders arbitrary playbook” only together with §2.3.

---

### 2.3 Typed operation IR (answers RT-03 / RT-04 core)

#### 2.3.1 Principle

A signature over a playbook hash authorizes **nothing** except “these bytes
are authentic.” Authorization is: **executor may perform only effects listed
in the signed ChangePlan operation set for this host.** Anything else is a
hard deny — including “helpful” Ansible handlers not listed.

Human-readable `summary` is **display only**. It is never parsed for
authorization.

#### 2.3.2 Schema (`ChangePlan` v1)

```json
{
  "schema": "stayturgid.changeplan/1",
  "plan_id": "plan-mac-ops-v1.4.0",
  "release_id": "ops-v1.4.0",
  "sequence": 1400,
  "channel": "stable",
  "expires": "2026-09-08T00:00:00Z",
  "nonce": "base64url-16-bytes",
  "target": {
    "host_id": "mac",
    "platform": "macos",
    "inventory_group": "site_litellm",
    "host_pubkey_fpr": "sha256:abcd…",
    "trust_tier": "operator"
  },
  "summary": "Update mise toolchains; restart vector with same config hash.",
  "operations": [
    {
      "op_id": "op-1",
      "type": "nix.activate_profile",
      "capabilities": ["nix.profile.write", "nix.gc.root"],
      "resources": {
        "profile": "/nix/var/nix/profiles/system",
        "closure_hash": "sha256:…",
        "nar_inventory_hash": "sha256:…"
      },
      "preconditions": {
        "min_disk_mb": 2048,
        "required_root_version": 1
      },
      "rollback": {
        "type": "nix.rollback_generation",
        "generation": "previous"
      }
    },
    {
      "op_id": "op-2",
      "type": "ansible.task_bundle",
      "capabilities": ["fs.write.prefix", "service.restart"],
      "resources": {
        "allowed_path_prefixes": [
          "/Users/djbclark/Library/LaunchAgents/com.stayturgid.",
          "/opt/stayturgid/"
        ],
        "allowed_services": ["com.stayturgid.vector"],
        "bundle_digest": "sha256:…",
        "max_tasks": 40
      },
      "preconditions": {},
      "rollback": {
        "type": "ansible.restore_snapshot",
        "snapshot_id": "pre-ops-v1.4.0-mac"
      }
    }
  ],
  "artifacts": [
    {
      "path": "artifacts/vector-config.tar.zst",
      "length": 4096,
      "sha256": "…",
      "purpose": "op-2"
    }
  ],
  "secrets": {
    "handles_allowed": ["VECTOR_INGESTION_TOKEN"],
    "handles_forbidden_note": "resolver still checks policy map"
  },
  "network": {
    "egress_allow": ["100.64.0.0/10:443"],
    "egress_mode": "declare_only_v1"
  },
  "evidence": {
    "diff_closures_digest": "sha256:…",
    "ansible_check_digest": "sha256:…"
  }
}
```

**Capability vocabulary (v1 closed set — unknown capability = reject plan):**

| Capability             | Meaning                                                     |
| ---------------------- | ----------------------------------------------------------- |
| `nix.profile.write`    | Activate listed Nix profile / generation                    |
| `nix.gc.root`          | Add/remove gc roots listed only                             |
| `fs.write.prefix`      | Write only under `allowed_path_prefixes`                    |
| `fs.read.prefix`       | Read only under listed prefixes                             |
| `service.restart`      | Restart/reload `allowed_services` only                      |
| `service.install_unit` | Install unit files under allowed prefixes + names           |
| `pkg.install`          | Install packages from allowlisted names/versions            |
| `android.apk.install`  | Install APK with matching cert + package                    |
| `android.shizuku.call` | Only listed Shizuku binder methods                          |
| `secret.use`           | Request handles in `secrets.handles_allowed`                |
| `net.bind`             | Bind listed ports                                           |
| `peer.help`            | One bounded peer-help action (consent pilot)                |
| `exec.argv`            | Run only exact argv digests (rare; prefer higher-level ops) |

No capability ⇒ no effect. Plans may not include `exec.shell` or
`ansible.unrestricted` in v1 — those types are **forbidden**.

#### 2.3.3 Worked example — Android no-op peer verify

```json
{
  "schema": "stayturgid.changeplan/1",
  "plan_id": "plan-s24-ops-v1.4.0-noop",
  "release_id": "ops-v1.4.0",
  "sequence": 1400,
  "channel": "stable",
  "expires": "2026-09-08T00:00:00Z",
  "nonce": "dGVzdC1ub25jZS0xMjM0",
  "target": {
    "host_id": "s24",
    "platform": "android",
    "host_pubkey_fpr": "sha256:s24fpr…",
    "trust_tier": "managed"
  },
  "summary": "No-op: verify agent can validate a signed empty plan.",
  "operations": [
    {
      "op_id": "op-verify-only",
      "type": "agent.verify_only",
      "capabilities": [],
      "resources": {},
      "preconditions": {},
      "rollback": { "type": "none" }
    }
  ],
  "artifacts": [],
  "secrets": { "handles_allowed": [] },
  "network": { "egress_allow": [], "egress_mode": "deny" },
  "evidence": {}
}
```

Executor on device: accepts plan, writes receipt, **must not** install
packages, touch Shizuku, or open network.

#### 2.3.4 Executor enforcement by platform

**Common (all platforms)**

1. Parse IR; reject unknown `schema` major or unknown `type` / capability.
2. Check `expires`, `sequence`, target binding, nonce unused (if consent).
3. For each op, enter a sandbox policy derived **only** from that op’s
   capabilities + resources.
4. Any kernel/API effect outside policy → abort op, mark plan failed, run
   rollback if partial.
5. Log structured event: `plan_id`, `op_id`, `deny_reason` (no secrets).

**Nix host (nix-darwin / NixOS) — deploy-rs path**

- Allowed op types: `nix.activate_profile`, `nix.rollback_generation`,
  `agent.verify_only`.
- Before activate: verify `closure_hash` and optional `nar_inventory_hash`
  (list of store-path → nar hash) after fetch; mismatch → no activate.
- deploy-rs magic rollback remains **operational** safety; IR rollback is
  **authorization** of which generation is allowed.
- Forbidden: arbitrary `nix-shell` scripts, unsigned `system.activationScripts`
  blobs not covered by closure hash, adding substituters/keys from the plan
  unless capability `nix.trust_config` exists (**not in v1**).

**Ansible / Linux+macOS**

- Op type `ansible.task_bundle` points at a **precompiled task list**
  (JSON) whose digest is `bundle_digest`, not a free-form playbook path on
  disk chosen at runtime.
- Wrapper (`stayturgid-ansible-exec`) loads bundle, and for each task:
  - Module allowlist (e.g. `copy`, `template`, `service`, `launchd`,
    `file`, `lineinfile` with path constraints).
  - `copy`/`template` dest must match `allowed_path_prefixes`.
  - `service` name ∈ `allowed_services`.
  - Reject `command`, `shell`, `raw`, `ansible.builtin.unarchive` to
    absolute paths outside prefixes, `sysctl`, `user`, unless explicitly
    capability-gated later.
- `--check --diff` output is **evidence only** (`evidence.ansible_check_digest`);
  never authorization.

**Android agent**

- Op types: `agent.verify_only`, `android.apk.install`, `android.file.deploy`,
  `android.shizuku.call`, `peer.help`.
- `android.apk.install`: package name + versionCode monotonic + cert pin +
  apk sha256.
- `android.shizuku.call`: each call must appear in resources
  `shizuku_methods: ["method.signature", …]` — no wildcards in v1.
- `peer.help`: single structured action (e.g. “push known-good agent apk to
  peer X”) with peer id + artifact digest; no generic shell.
- CFEngine remains break-glass **outside** this IR; must not be invoked by
  the converge agent as a way to skip IR. Document CFEngine as
  operator-triggered recovery only.

#### 2.3.5 Source-to-signing pipeline (closes RT-03 precondition)

1. **Release checkout:** clean worktree from annotated tag only
   (`git worktree add` from bare store; `git status` empty; no task branch).
2. **Provenance gate script** (encode 2026-08-06 lessons): refuse if
   commits in range have unexpected authors/committers without
   `STAYTURGID_ALLOW_FOREIGN=1` operator env; refuse dirty tree; refuse if
   claim file says another agent owns path.
3. **Build** artifacts; produce plans from generators that emit IR (not
   free text).
4. **Two-person rule for trust-boundary paths** (solo adaptation): the
   **same human** must run a delayed second review (`git show` + checklist)
   for changes under `freeops/update/`, executors, secrets policy, root
   metadata. Coding agents may prepare diffs; they must not run
   `minisign -S` (PATH wrapper denies agents / requires TTY + key passphrase
   interactively).
5. **Sign** only on the clean tree. Record `git rev-parse HEAD`, lockfile
   hashes, builder id in release evidence JSON (not yet full in-toto).

---

### 2.4 Consent v1 (answers RT-04; ship gated)

**Interface (stable now):**

```
offer(Offer) → Decision
```

```json
{
  "offer_id": "uuid",
  "plan_id": "…",
  "plan_sha256": "…",
  "release_id": "…",
  "sequence": 1400,
  "target_device_pubkey_fpr": "sha256:…",
  "capability_vector": ["peer.help"],
  "artifact_digests": ["sha256:…"],
  "summary": "…",
  "expires": "2026-08-08T19:00:00Z",
  "nonce": "single-use",
  "timeout_sec": 120,
  "timeout_policy": "deny"
}
```

**Rules:**

| Rule               | Behavior                                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Device binding     | Plan `target.host_pubkey_fpr` must match this device’s install key                                                              |
| Nonce              | Single-use; stored in integrity-protected grant DB                                                                              |
| Expiry             | Wall-clock; fail closed                                                                                                         |
| Timeout / UI crash | **deny**                                                                                                                        |
| Accept             | Writes grant: exact capability_vector + plan_sha256 + nonce spent                                                               |
| Executor           | Every op must be ⊆ grant; grant does not include “run any future plan”                                                          |
| Reject             | Persist reject for (plan_id, sequence) to suppress re-prompt loops for 24h                                                      |
| Receipt            | Device-signed: `{decision, plan_sha256, sequence, ts, device_fpr}` exportable; **no** site secrets; **no** automatic public log |

**v1 pilot operation only:** `peer.help` with proven rollback (uninstall or
revert agent version). No generic feature bundles. No Shizuku-capable APK
consent without RT-08 gate.

**Phase 6 must not enable** until G6 (§4).

---

### 2.5 Builder / cache containment (answers RT-05)

#### 2.5.1 v1 (now)

- **No** private Harmonia/Attic role.
- Use `cache.nixos.org` + build-on-target for Linux; no custom
  `trusted-public-keys` for operator-controlled caches.
- Nix docs are explicit: a trusted cache private key can substitute
  **arbitrary** store paths, including elevated executables. Do not add one
  until §2.5.2 is implemented.

#### 2.5.2 When builder/cache roles open (Phase 8 gate)

Separate authorities (none alone deploys):

| Authority     | Key / identity                  | May do                          | Must not do                                   |
| ------------- | ------------------------------- | ------------------------------- | --------------------------------------------- |
| Builder SSH   | SSH CA host cert, tag `builder` | Compile                         | Sign releases; own cache signing key          |
| Cache upload  | Short-lived credential          | Upload NARs for paths it built  | Sign root/release; configure clients          |
| Cache signing | Offline or HSM-isolated key     | Sign NAR info                   | Held on builder SSH account                   |
| Release       | release key under root          | Authorize deploy of **digests** | Trust “came from builder” without inventory   |
| Client        | verifies release NAR inventory  | Activate only listed paths      | Trust cache sig alone for privileged closures |

**Mandatory before any client trusts a private cache key:**

1. Signed `nar_inventory` in the ChangePlan / targets custom fields.
2. After substitute, re-hash NARs / use `nix store verify` against inventory.
3. Independent rebuild of critical closures (system path, update agent)
   on a second machine or rebuild-on-target comparison.
4. Cache key rotation under root-threshold; documented “remove substituter
   without reinstall” runbook (drop key from nix.conf via push of known-good
   generation stored offline).

---

### 2.6 SecretSpec reference monitor (answers RT-06)

Ground truth: `site-private/secretspec.toml` declares high-impact handles
(`SSH_CA_KEY`, `FLEET_ADBKEY`, cloud tokens, FIRERPA, obs passwords, etc.).
Naming a handle in a service unit must not yield the value.

#### 2.6.1 Policy object (signed, versioned)

`secrets-policy.json` (signed by release or root; shipped with suite):

```json
{
  "schema": "stayturgid.secrets-policy/1",
  "version": 3,
  "defaults": { "effect": "deny" },
  "allow": [
    {
      "service_id": "com.stayturgid.vector",
      "host_roles": ["obs-main", "obs-backup"],
      "host_ids": ["*"],
      "capabilities": ["secret.use"],
      "handles": ["VECTOR_INGESTION_TOKEN", "OPENOBSERVE_ROOT_PASSWORD"]
    },
    {
      "service_id": "com.stayturgid.ssh-ca-issue",
      "host_roles": ["release"],
      "host_ids": ["mac"],
      "capabilities": ["secret.use"],
      "handles": ["SSH_CA_KEY"]
    }
  ]
}
```

#### 2.6.2 Resolver algorithm

Wrapper around secretspec provider read:

1. Identify **service identity** (launchd label / systemd unit / agent id) —
   not argv[0] alone; prefer signed unit hard-coded id.
2. Identify **host_id** + roles from local inventory snapshot (hash-pinned
   in last applied plan).
3. Identify **capability** from calling code path (enum, not stringly).
4. Lookup allow entry; **deny** if no match.
5. If ChangePlan is active, further intersect with
   `plan.secrets.handles_allowed`.
6. Deliver secret as **non-inherited** credential file (mode 0400, per-service
   dir) or OS keychain item — **not** ambient environment for child shells.
7. Audit log: `{service_id, handle, decision, plan_id?}` — never value.
8. Bootstrap exception keys (cache sign, host SSH bootstrap) live in a
   **separate** policy file with empty intersection to normal site handles.

**Tests:** malicious unit listing `SSH_CA_KEY` → deny; template expansion /
alias → deny; transitive dependency requesting handle → deny.

**consented tier:** lint already forbids secret handles in manifests;
resolver double-denies if agent ever calls with `trust_tier=consented`.

---

### 2.7 Role mesh safety (answers RT-07)

**v1 rule: no autonomous failover.**

| Singleton       | v1 authority                               | Failover                            |
| --------------- | ------------------------------------------ | ----------------------------------- |
| Release publish | Operator laptop + flock/`ops-release.lock` | Manual only                         |
| Secret rotation | Operator ceremony                          | Manual only                         |
| obs-main        | Designated host in inventory               | Manual inventory edit + signed plan |
| deploy-origin   | Operator hosts only                        | n/a                                 |
| pull-converge   | **Disabled** until G5                      | —                                   |

Replace “lease/fencing semantics” rhetoric with:

1. **Single designated owner** in inventory for each singleton.
2. Any change of owner = normal signed ChangePlan applied by operator.
3. If owner is down, operator runs emergency plan (possibly emergency
   channel) after human confirmation — no timeout-based claim.

**When pull agent exists:** size caps, exponential backoff + jitter,
circuit breaker after N failures, local kill switch file
`~/.config/stayturgid/PULL_DISABLED`, CPU/disk quotas, manifest-first fetch
(never stream-apply).

---

## 3. Scope-cut proposal (aggressive)

### 3.1 Evaluating the suggested cut

> _“v1 is push-only from operator hosts; no autonomous pull; no consented
> devices; no autonomous role failover.”_

| Finding / gap                                 | Closed for free?                                          |
| --------------------------------------------- | --------------------------------------------------------- |
| RT-02 fleet-scale freeze via pull mirrors     | **Mostly yes** (still need anti-rollback on push targets) |
| RT-04 consent theater                         | **Yes**                                                   |
| RT-07 mesh split-brain + converger DoS        | **Yes** (failover); DoS deferred with pull                |
| RT-08 consent without provenance              | **Yes**                                                   |
| Systemic: quorum, privacy, TOFU for strangers | **Yes** / reduced                                         |
| RT-01 key theft                               | **No** — push still signs; still need root/threshold      |
| RT-03 execution laundering                    | **No** — push still executes                              |
| RT-05 cache                                   | **Yes** if we also skip private cache                     |
| RT-06 secrets                                 | **No** — already resolves secrets today                   |
| RT-09 local-fix auto                          | **Yes** if we refuse to build it                          |

**Score:** this cut closes or defers **~half the Critical/High surface**
and almost all mesh/consent complexity, while leaving the **real** work as
IR + signing hygiene + secrets monitor + root recovery.

### 3.2 Smallest useful v1 that is still safe

Ship:

1. **Root metadata + 2-of-3 ceremony + recovery runbook** (even if only used
   monthly).
2. **Signed manifest + ChangePlan IR** consumed by **push** (`just deploy-host`).
3. **Executor wrappers** for Ansible task bundles + Android verify/install
   path used today.
4. **SecretSpec deny-by-default** for production LaunchAgents.
5. **No-op signed plan** end-to-end on one Android device (operator-pushed).
6. **Provenance gate** on release signing (clean tree, no agent minisign).

Explicitly **do not ship:**

| Surface                            | Opens when                                     |
| ---------------------------------- | ---------------------------------------------- |
| Timer-driven pull                  | G5                                             |
| Consent UI live                    | G6                                             |
| Private Nix cache trust            | G8                                             |
| Autonomous role failover           | Never without fencing design + partition tests |
| local-fix auto-merge               | Never as authorization                         |
| OpenHands / LLM as gate            | Never (advisor only)                           |
| T4 advisor-cleared upstream prefer | Never as authorization                         |

**Minimum useful thing:** “Operator pushes a release that devices/hosts
**refuse** if signature, sequence, target binding, or IR capabilities fail”
— that is already a qualitative jump from “Ansible as root.”

---

## 4. Revised phase gates (Phases 4 / 5 / 6 + security entry criteria)

Phases 0–3 unchanged in spirit (map, flake, Mac substrate, role
parameterization). Security prerequisites are **entry** criteria, not
roadmap footnotes.

### Phase 4 — First NixOS host

|                         |                                                                                                                                                      |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Entry**               | Phase 3 done; inventory has `vps-primary`; **no** requirement for pull/consent. SSH CA + Tailscale as today.                                         |
| **Contents**            | nixos-anywhere bootstrap; Ansible→systemd adapters; deploy-rs for Nix profile with magic rollback; **push-only**. Do **not** add private cache keys. |
| **Security must-haves** | Host identity in inventory; deploy path does not grant cache signing; secrets for VPS via secretspec policy if any.                                  |
| **Exit evidence**       | Host recovers via Nix generation; services re-render via Ansible; STATUS note.                                                                       |
| **Rollback**            | Destroy VPS; roles fall back to Mac.                                                                                                                 |

### Phase 5 — Release / plan v1 (**hardened**)

Split into **5a** (push signed IR) and **5b** (pull).

#### 5a — Signed push (default “Phase 5” for solo)

|                   |                                                                                                                                                                                                                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Entry**         | Root 2-of-3 generated and fingerprints recorded offline; clean-signing checkout script green; ChangePlan schema + at least one executor wrapper (Ansible **or** Android verify); secrets policy v0 for one real service; fail-closed unit tests for RT-02 cases that apply to push. |
| **Contents**      | Manifest + IR; minisign release key under root; `just deploy-host` verifies before apply; one device no-op plan; deploy telemetry events.                                                                                                                                           |
| **Exit evidence** | Bad sig / bad sequence / bad host fpr / undeclared capability all denied on a real host; recovery runbook dry-run documented.                                                                                                                                                       |
| **Rollback**      | Feature flag: ignore manifests, classic Ansible push (document as degraded).                                                                                                                                                                                                        |

#### 5b — Pull converge (optional, later)

|                   |                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Entry**         | 5a soak ≥ 14 days; full client algorithm §2.2.5 implemented; resource limits + kill switch; snapshot binding + expiry short enough; **no** autonomous multi-host role changes. |
| **Contents**      | Timer agent on **operator-tier hosts only** (Mac, later VPS) — **not** on consented/untrusted devices.                                                                         |
| **Exit evidence** | Hostile-mirror tests: freeze, rollback, mix-and-match, oversize.                                                                                                               |
| **Rollback**      | `PULL_DISABLED`; remove timer; push-only.                                                                                                                                      |

**Architecture-final Phase 5 text is amended:** pull is **not** the default
exit criterion; 5a is.

### Phase 6 — Consent v1 (**hardened**)

|                   |                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Entry (G6)**    | 5a complete; Android provenance minimum: dependency locks, APK cert pin, permission/export/Shizuku/network **diff artifact** in release; offer() with nonce/expiry/device bind/timeout=deny; executor enforces capability_vector; privacy: local receipts only; Tailscale tags/grants so consented ↛ builder/SSH-CA paths; single pilot op `peer.help` with rollback drill. |
| **Contents**      | stayturgid-agent prompt + grant store + device-signed receipts on **one** opted-in device.                                                                                                                                                                                                                                                                                  |
| **Exit evidence** | Replay accept fails; timeout denies; summary/IR mismatch tests; revoke feature works.                                                                                                                                                                                                                                                                                       |
| **Rollback**      | Feature flag off; wipe grants; recorded rollback of pilot op.                                                                                                                                                                                                                                                                                                               |

### Phase 7–8 (unchanged intent, security delta)

- **7 Exit drill:** unchanged; must not require pull/consent.
- **8 Builder/cache:** only after §2.5.2; freeops extract still demand-driven.

---

## 5. Build order and effort

Estimates: **one operator + AI agents**, calendar time (not pure coding hours).
Flag multi-week impostors.

| Order | Item                                                                     | Effort                      | Notes                                                                                                  |
| ----- | ------------------------------------------------------------------------ | --------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1     | ChangePlan schema + JSON Schema + golden fixtures                        | **2–4 days**                | Highest leverage; do first                                                                             |
| 2     | Ansible executor wrapper (module/path allowlist) for **one** play family | **1–2 weeks**               | Easy to underestimate — per-role migration is the multi-week trap; start with **one** LaunchAgent role |
| 3     | Root ceremony tooling + `root.json` verify CLI (Mac + Termux)            | **3–5 days**                | Includes recovery doc dry-run                                                                          |
| 4     | Manifest/snapshot sign + verify in `just ops-release-*` path             | **3–5 days**                | Wire to existing ops-v train                                                                           |
| 5     | Client state + sequence high-water on push target                        | **2–4 days**                |                                                                                                        |
| 6     | SecretSpec resolver policy for 2–3 real services                         | **3–5 days**                | Expand allowlist gradually                                                                             |
| 7     | Provenance gate script + deny agent signing                              | **1–2 days**                | Cheap, do early parallel with 1                                                                        |
| 8     | Android no-op plan verify in agent                                       | **3–5 days**                |                                                                                                        |
| 9     | Fail-closed test suite (RT-02/03 cases)                                  | **3–5 days**                |                                                                                                        |
| 10    | 5a soak on Mac + one phone                                               | **1–2 weeks** elapsed       | Mostly calendar                                                                                        |
| 11    | Pull agent + quotas (**5b**)                                             | **1–2 weeks**               | **Do not start before 10**                                                                             |
| 12    | Consent offer/grant/receipt (**6**)                                      | **2–3 weeks**               | Multi-week; includes UI + adversarial tests                                                            |
| 13    | Android provenance pack for consent                                      | **2–4 weeks**               | Multi-week impostor if “reproducible APK” means bit-identical; take cert pin + SBOM + diff first       |
| 14    | Private cache containment                                                | **2–4 weeks** when demanded | Multi-week; easy to hand-wave                                                                          |

### What to build first (this week)

1. Schema + deny-by-default executor stub.
2. Provenance gate on release.
3. Root key generation + paper backup (human afternoon).

### Multi-week projects masquerading as bullets

- “Typed IR for **all** Ansible roles” — **months**. Scope v1 to new/changed
  roles + one pilot role; legacy push remains flag-gated degraded mode.
- “Full TUF + Rekor + SLSA” — **months**. Subset only.
- “Reproducible APKs” — **weeks to months**; not a Phase 5a blocker.
- “Role mesh with leases” — **research project**; out of v1.

---

## 6. Critique of adjacent artifacts (separation of roles)

### Red-team (OpenAI) — fair

Correctly treated roadmap as non-enforcement; correctly separated
transport/signature from authorization; correctly used real secretspec and
double-merge incident as preconditions. Severity ordering is right: RT-01/03/05
before consent cosmetics.

### Final architecture (Claude synthesis) — gaps this doc patches

- Phase 5 bundles pull with first signed plan — **too early**.
- “minisign now, TUF later” without high-water/expiry — **unsafe for pull**.
- Role lease/fencing named but unspecified — **correctly blocked here**.
- Consent v1 as prompt+log — **insufficient**; interface retained, enforcement
  added, pilot gated.

### Tooling reviews (Grok/OpenAI)

Agree: minisign is floor not protocol; OpenHands Surface B forbidden as gate;
Harmonia deferred; deploy-rs is activation convenience not authorization.
This design implements those verdicts as gates rather than tool swaps.

### Ideas dump

Agree offline Ed25519 floor vs Rekor-only; Nix cache trust is total; Tailscale
ACLs must be explicit before consent. Captured in §2.4/§2.5/G6.

---

## 7. Acceptance checklist (operator)

v1 trust layer is “done enough to expand” when:

- [ ] Root 2-of-3 exists; recovery B/C practiced once on a scratch file
- [ ] No production deploy path applies unsigned IR on new roles
- [ ] Sequence downgrade denied on a real device
- [ ] Undeclared Ansible module/path denied in wrapper tests
- [ ] `SSH_CA_KEY` denied to a deliberately misconfigured unit
- [ ] Pull timer **off**
- [ ] Consent feature **off**
- [ ] Private cache **untrusted**
- [ ] local-fix **manual only**

Until then, treat architecture-final Phase 5/6 dates as **aspirational**,
not authorization to ship the weak design the red-team killed.

---

## 8. Sources

### In-tree / ground truth

- `docs/2.0/redteam-trust-layer-openai-v1.md`
- `docs/2.0/architecture-final-v1.md`
- `docs/2.0/architecture-proposal-v1.md` §7–8, §12
- `docs/2.0/tooling-assumptions-review-grok-v1.md`
- `docs/2.0/tooling-assumptions-review-openai-v1.md`
- `docs/2.0/ideas-dump-claude.md`
- `~/ops/site-private/secretspec.toml` (handle **names** only)
- `~/ops/site-djbclark/inventory/hosts.yml` (s24, p7a, hd8, mac, planned VPS)
- `~/ops/site-djbclark/registry/` (paths, ports, identity-patterns)
- `~/ops/stayturgid/ops-release.json` (suite version train)
- `~/src/ops-worktrees/README.md` (2026-08-06 double-merge / provenance rules)

### Web-verified (protocol/tool facts)

- [TUF specification](https://theupdateframework.github.io/specification/latest/) — threshold root, offline keys, rollback/freeze/mix-and-match goals, client workflow (root dual-threshold rotation, version monotonicity, expiry, snapshot binding)
- [Minisign](https://jedisct1.github.io/minisign/) — Ed25519 file signatures; trusted comments; not a multi-role update system
- [Nix custom binary cache guide](https://nix.dev/guides/recipes/add-binary-cache.html) — trusted cache key ⇒ arbitrary store substitution warning
- [deploy-rs](https://github.com/serokell/deploy-rs) — magic rollback / activation confirmation; operational, not authz
- [Sigstore Rekor overview](https://docs.sigstore.dev/logging/overview/) — inclusion/consistency monitoring required; not a substitute for release root
- [Android APK Signature Scheme v3](https://source.android.com/docs/security/features/apksigning/v3) — cert rotation lineage; pin policy still required for trust

---

_End of hardened design. File is advisory to the Decision Register; it does
not modify `architecture-final-v1.md` without operator approval._
