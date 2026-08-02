# Normal-deploy convergence (always-on rule)

`just deploy` is the authoritative path from any supported starting state to
the fleet's declared configuration. This includes a newly reset device once
the unavoidable Android trust bootstrap (developer mode plus one authorized
ADB connection) is available.

## Required invariant

- Every durable device change must be represented in Ansible and verified in
  the same normal deploy.
- A repair, rollout helper, UI action, or one-off command may accelerate or
  diagnose convergence, but it must not create a durable state that the normal
  deploy cannot reproduce from inventory and versioned product defaults.
- Factory-reset installation and routine upgrades use the same desired-state
  catalog. Do not maintain a separate "first install" version source.
- A coordinated `ops-v*` release must lock external artifacts by exact release
  tag, asset name, installed version, and checksum. Never resolve mutable
  repository-wide "Latest" during deployment.
- Post-install requirements—conflicting package removal, permissions,
  configuration files, service start, and verification—are part of the
  deployment transaction, not operator follow-up.

## Human-gated state

Android deliberately requires physical consent for some trust boundaries,
including the first ADB authorization and some Shizuku grants. Ansible must
drive the device to the consent prompt, fail or report the gate honestly, and
converge when the operator reruns the same normal deploy after approval. Do not
bypass or weaken the consent mechanism.

## Release discipline

Artifact pins advance only in a versioned ops release. Publishing an
independent application release does not silently alter deployed state; update
the lock, test a normal deploy, and cut the next coordinated ops release.

## Regression requirements

Tests must cover:

1. Missing package (factory-reset case).
2. Stale or wrong package version.
3. Multiple release streams in one GitHub repository.
4. Conflicting package variants.
5. Required post-upgrade service/configuration state.

See also [deploy/self-heal/catastrophic coverage](deploy-self-heal-catastrophic.md).
