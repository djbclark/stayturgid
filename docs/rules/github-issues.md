# GitHub issues policy (always-on rule)

This repository is **public**. GitHub issues are the canonical tracker for
discrete work items: bugs, ops follow-ups, and soak/verification tasks.
Strategic or deferred work with a stable ID stays in
[docs/options.md](../options.md) instead — issues are for things with a clear
done-state, options.md is for longer-running tracks.

## When to file an issue

- A reproducible bug or symptom (device or control-node side).
- A concrete follow-up from a session that a future agent or the operator
  needs to pick up (e.g. "verify X on device Y once it's back online").
- A soak/verification task with a defined pass condition.

Use a workstream label so related issues are easy to find:
`k1-native-agent`, `f1-mcp-bridge`, `observability`, `operator-action`.
Cross-link overlapping issues with a comment (`#41` mentions `#16` when
symptoms overlap) — don't let duplicate investigations run in parallel.

## Hygiene — mandatory, no exceptions

Because this repo is public and the fleet is a live personal deployment:

- **No raw device dumps** (`dumpsys`, `logcat`, full config exports) as issue
  attachments or inline text. If a raw artifact is genuinely needed for
  diagnosis, put it in the private site overlay repo (or a location the
  operator names) and reference it by description, not by uploading it here.
- **No real Tailscale IPs, device serials, or hostnames.** Use the example
  fleet aliases (`oneui-device`, `stock-android-device`, `fireos-device`) or
  the session aliases (`s24`, `p7a`, `hd8`) — never the underlying
  100.x.x.x addresses or serial numbers. See
  [multi-site-topology.md §4](../architecture/multi-site-topology.md#4-generic-upstream-vs-site-overlay-repository).
- **No operator contact information** (personal handles, phone, chat
  channels) in an issue body or comment.
- Sanitized excerpts (specific corrupted rows, correlated timestamps, a short
  log snippet with identifiers redacted) are fine and encouraged.

## What GitHub does not replace

- Session handoffs and continuation checkpoints still belong in
  [docs/operations/sessions/](../operations/sessions/) — an issue tracks one
  discrete item, a session doc captures what an agent did and what a
  successor should read first.
- Live operator credentials, device inventory, and site-specific facts still
  belong in the private site overlay repo, never in an issue.
