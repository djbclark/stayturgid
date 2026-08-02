# ADR 005: Two-repo topology and phased structure improvements

**Status:** Accepted (2026-07-18)
**Context:** Segmentation of android-fleet management (stayturgid) from general
site/machine management (private site repo), decided with the operator while
standing up `site-djbclark`.

## Decision

Exactly **two repo kinds**, following the pattern every mature config-management
ecosystem converged on (Puppet control-repo + roles/profiles, Gruntwork
modules/live, Flux/Argo app-vs-config repos, Ansible inventory separation):

1. **stayturgid** (this repo, public product): fleet code, the shared-serverapp
   adapter roles it depends on (Caddy, Vector, OpenObserve, VictoriaMetrics,
   Grafana, OliveTin), and — Phase C — the site-contract tooling
   (`site-init` / `site-sync`, Entangled literate contract docs).
2. **site-\<operator\>** (private, per site): inventory for all hosts, port and
   path registries, secrets declarations, thin wrapper playbooks, operator
   docs, and any site-local roles (the Puppet "site-modules" pattern).

There is **no third "glue" repo**: composition logic ships product-side
(serverapp adapters with own-the-daemon vs inject-only modes) or site-side
(thin wrappers) — a middle repo is not an industry pattern and adds no value.
The full contract specification (CLI surface, lockfile semantics, adapter
interface, acceptance tests) is [site-contract.md](../site-contract.md).

Layout convention: a plain base directory (default `${OPS_ROOT:-~/ops}`, override
`OPS_ROOT`) holding sibling checkouts. **A private site repo must never be
nested inside a public repo's working tree** (allowlist-.gitignore schemes are
rejected: `git add -f`, allowlist drift, or `git clean -ffdx` could expose or
destroy site data).

The reference site is `site-djbclark` (private). Its
`docs/plans/site-djbclark-step1-segmentation-architecture-v1.md` carries the
full architecture, decision log, and research citations; its `registry/` is
the authority for ports and path ownership across the site.

## Phased structure improvements

Recorded here so later work lands in the permanent shape.

| Phase (site step1 doc §8) | Work in this repo                                                                                                                                                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B                         | Live inventory + operator docs move to the site repo (§4 of docs/architecture/multi-site-topology.md)                                                                                                                                                         |
| B/D                       | Collectionize `ansible/roles/control_node` → `stayturgid.control`; after inventory leaves, `ansible/` shrinks to cfg + example inventory                                                                                                                      |
| C                         | Site-contract tooling + Entangled `SITE-CONTRACT.md`                                                                                                                                                                                                          |
| D                         | Serverapp adapter roles; daemon instances handed to site-owned labels; `control/landing` + Caddy templates move next to the roles that deploy them; landing plists become Ansible-managed (today they are hand-maintained — found during the 2026-07-18 move) |
| —                         | Repo-root `.env` relocates to `~/.config/stayturgid/`                                                                                                                                                                                                         |

## Consequences

- `stayturgid` stops assuming it owns the machine; it declares defaults and
  contributes fragments, the site allocates.
- New general-purpose stacks (e.g. the operator's Goose/LiteLLM AI stack)
  incubate in the site repo and are extracted to their own public product
  repos only if they mature — they do not enter this repo.
- Closes platform-architecture §11 decision #1; half-closes #9 (ownership +
  port authority; Caddy route naming still open).
