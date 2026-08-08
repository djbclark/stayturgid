# SECOND-OPINIONS BRIEF — stayturgid 2.0 architecture proposal

You are one of three independent AI architects asked for a second opinion.
Work happens in this git worktree:
`/Users/djbclark/src/ops-worktrees/stayturgid-2.0/stayturgid` (branch
`feature/stayturgid-2.0`). Your vendor slug is given in your launch prompt.

## Deliverable

Write **one file**: `docs/2.0/architecture-proposal-<your-slug>-v1.md` —
a comprehensive, self-contained architectural proposal + migration plan for
the operator's device-management/ops infrastructure. It will be compared
side-by-side with proposals from other AIs.

## Hard rules

1. **INDEPENDENCE:** Do NOT read `docs/2.0/architecture-proposal-v1.md`
   (Claude's proposal) or the other vendors' proposals until AFTER your own
   proposal is complete. Then you MAY append a final section
   "## Critique of Claude's proposal" if you wish.
2. **PROTECTED FILES:** Never modify any file you did not create. Only
   create/edit `docs/2.0/architecture-proposal-<your-slug>-v1.md` and
   (optionally) `docs/2.0/questions-<your-slug>.md`.
3. **No git commits, no pushes, no branch operations.**
4. You MAY: read anything under `~/ops` and `~/src`; clone/download any
   code you need to inspect into `~/src/` (e.g. `~/src/vendor/`); search
   the web. IMPORTANT: several relevant tools gained major features in
   2025–2026 (e.g. mise's declarative `bootstrap` surface incl. launchd
   agents + systemd units). Verify current capabilities via the web; do
   not trust training-data memory for tool feature sets.
5. **Questions:** If operator input would improve your proposal, write
   questions to `docs/2.0/questions-<your-slug>.md` and end your turn;
   you will be resumed with an `## Answers` section appended to that file.
   Ask early, not at the end.

## The assignment (as given by the operator)

Evaluate these approaches for the core macOS/Linux stack and critically
pick/design the best:
1. `bgub/nix-macos-starter`  2. `mrkuz/macos-config`
3. Devbox (Jetify)  4. Devenv.sh
5. …or a custom stack (e.g. nix-darwin + home-manager + mise) or other
   full-stack options they missed.

## Operator-stated requirements (normative — from live dialogue)

- R1 Targets: macOS/Apple Silicon, Linux/x86_64, Linux/aarch64, Android.
  (Intel Mac mini out of scope.)
- R2 Control node must be switchable macOS↔Linux; end-state: NO control
  node — any macOS/Linux box holds arbitrary feature roles as
  main/backup/equal peer.
- R3 Resource efficiency: minimal-to-no VMs; no fat container images.
- R4 Android keeps Termux (+termux:api, +termux:x11), built-in Android
  Terminal app, Shizuku fork, stayturgid-agent, CFEngine self-heal +
  remote last-ditch fallback. nix-on-droid REJECTED (storage, RAM,
  process contention). Nix may serve Android only as zero-on-device-
  footprint artifact builder.
- R5 NixOS acceptable on greenfield Linux, but architecture must make a
  later move to e.g. Ubuntu Server "pretty easy" (cheap exit).
- R6 Shizuku + stayturgid-agent keep Gradle; suite orchestrates build
  invocation + deployment; APK build must not drive architecture.
- R7 Push AND pull deploys. Long-term: untrusted Android devices with
  consent-based deploys (contractually valid change descriptions,
  user-side AI advisor, opt-in feature sets, "app store for config",
  local-fix-until-upstream-heals, graded web of trust with durable
  attestations).
- R8 For v1: trust/consent layer = specified interfaces + minimal
  implementations; heavy machinery as roadmap.
- R9 Literate programming (entangle) expansion desired, calibrated to
  what Sonnet-5/DeepSeek-v4-Pro-class agents handle well (token cost vs
  code quality). Rich human narrative wanted where it doesn't tax agents.
- R10 Architecture should enable "Free Sysadmin": orgs (e.g. the FSF)
  publishing generic sysadmin glue safely — free software extended to
  glue code. Operator was an FSF sysadmin for 2 years.
- R11 Preserve: ~/src as definitive source + worktree discipline;
  ops-vX.Y.Z coordinated release train; secretspec as single secrets
  authority; CFEngine roles; observability stack (Vector, OpenObserve,
  VictoriaMetrics, otelcol-contrib); Beads/Ralph agent orchestration.

## Ground truth to read on disk (do read these)

- `~/ops/` = live deploy checkouts: site-djbclark, site-private,
  stayturgid (three-sibling suite; ops-v release contract).
- `~/ops/site-djbclark/inventory/hosts.yml` — ONLY home of site facts;
  live fleet = M1 MacBook Air control node + 3 Android devices (S24,
  Pixel 7a, Fire HD8) over Tailscale; `vps-primary` + Intel mini are
  offline_unprovisioned (Linux fleet is GREENFIELD; Hetzner planned).
- `~/ops/site-djbclark/registry/ports.yml`, `paths.yml` — allocation
  authorities. `justfile`, `playbooks/`, `roles/` — current Ansible.
- `~/ops/site-private/secretspec.toml` — unified secrets declaration.
- `~/ops/stayturgid/` — Android product repo (AGENTS.md, docs/,
  ansible collections, device/native-agent Kotlin APK, control/bin).
- `~/src/ops-worktrees/README.md` — worktree + cross-agent rules.
- `/nix` exists on the Mac (Determinate-style install already present).

## Required proposal contents (minimum)

Verdict on the 4 options + alternatives; overall architecture and where
the source of truth lives (justify against R2/R5/R10); macOS layer
ownership (nix-darwin vs home-manager vs mise bootstrap vs Ansible —
incl. who owns launchd and how the two-writers hazard is handled);
Linux design incl. the NixOS exit mechanism; Linux-closure build
topology honoring R3 (remote builders? build-on-target? caches?);
Android integration (R4/R6) incl. stayturgid-agent 2.0 direction;
deploy/release design (push+pull, ops-v train, signed manifests/change
plans, consent hooks per R7/R8); secrets; observability; literate
programming policy per R9 with evidence; Free Sysadmin publishing +
licensing recommendation per R10; phased migration plan with rollback
points; risks. Be decisive: make the calls, state trade-offs.
