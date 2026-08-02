# Handoff — Ops Service Separation (Shelved)

Date: 2026-07-26

This is the public handoff for the next AI session.

## Session Summary

The session started by evaluating the "ops service separation" workstream, specifically the 7 ownership decisions tracked in Issue #50 (Dashboard ownership, Eternal Terminal/SSH CA, CFEngine retention, etc.).

After discussing the first two items (Dashboard and SSH CA), the operator chose to shelve the ownership decisions for a later time. No implementation was moved or changed during this session.

## Worktree Hygiene & Uncommitted Changes

At the start of this session, a hygiene check revealed uncommitted work in the `stayturgid` repo related to a `peer-start` capability:

- `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/PeerConfig.kt`
- `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/PeerStarter.kt`
- `control/tools/native-agent/provision_peer.py`
- and modifications to `HostService.kt`, `MainActivity.kt`, etc.

The next AI should preserve these files and confirm with the operator whether to continue the `peer-start` implementation or stash it. The `api` submodule in the Shizuku fork remains dirty and should be preserved.

## Loose ends and operator prompts

The previous loose ends remain unresolved. The next AI must prompt the operator with these items before starting new implementation (except for the `peer-start` work currently in progress):

1. **Issue #50 ownership decisions:** (Shelved during this session) dashboard ownership; Eternal Terminal/SSH CA; CFEngine retention; VLM site-versus-private ownership; generic app defaults versus site catalog; public research provenance; and generic peer-help protocol versus site-only feature.
2. **Shizuku release distribution:** decide whether release20 should receive a tag/GitHub release and be added to the normal APK/Obtainium path.
3. **p7a FIRERPA:** wait for a compatible upstream release, then retest and update the inventory classification.
4. **F1 FIRERPA MCP bridge (#46):** implementation awaits operator approval and the consent-surface choice (local dialog/notifications first versus MCP elicitation).
5. **Observability:** #44 (OpenObserve↔Vector 401) blocks #47 (Grafana/portal follow-ons).
6. **K1 residuals:** #43 and #45 still need native-agent cutover verification, soak evidence, and signed-release decisions.
7. **Stale backlog:** triage H1/H3, B63/B64, T2/T4, and settings issues #41/#42/#16.
8. **Codex memory ownership:** the live `~/.codex` entries are now symlinks, with durable memory/config in `site-private` and generated runtime state in its ignored `.codex-runtime/`. Decide which historical project-specific notes should be promoted into `stayturgid` or `site-djbclark` documents.

## Next-session hygiene

At start, inspect all four worktrees with `git status --short --branch`, verify the active remotes, and read this handoff plus `docs/STATUS.md`. Confirm the operator's intention regarding the uncommitted `peer-start` files before running commands that might overwrite or delete them. Do not merge or publish anything until the applicable decisions are answered and checks are green.
