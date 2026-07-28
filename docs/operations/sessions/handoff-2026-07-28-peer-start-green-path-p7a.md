# Handoff — 2026-07-28 Peer-start `STARTED` green path + p7a as second peer ([#61](https://github.com/djbclark/stayturgid/issues/61))

Continuation of [handoff-2026-07-26-peer-start-activation.md](handoff-2026-07-26-peer-start-activation.md)
(read that first for the full build + activation history). This session
closed out the two remaining items the issue's own last comment called out:
the `STARTED` path (vs the already-proven `ALREADY_UP` no-op) observed live
with hd8's Shizuku genuinely down, and p7a provisioned + verified as a
second peer. **No application code changes were needed** — this was a pure
live-verification unit against the peer-start feature already shipped in
v0.5.1/v0.5.2. This PR is docs-only (this handoff) plus the pointer to a new
issue filed for a real device-side bug hit along the way.

## ✅ #61 CLOSED — both remaining items proven live

### 1. `STARTED` green path (s24 → hd8, hd8 Shizuku genuinely down)

hd8's Shizuku was up at session start (pid 21945). Brought it down
deliberately via the Mac's own already-trusted **external** adb (`adb -s
GN43T503430603PS shell kill 21945`) — not the hazardous local/loopback
`shizuku_starter` path, not a reboot. Confirmed down (`pgrep -f
'[s]hizuku_server'` → no match). Triggered `just agent-peer-start s24`:

```
[agent] PEERSTART target=100.124.55.39:5555 outcome=ALREADY_UP  ts=10:00:11   (baseline, pre-kill)
[agent] PEERSTART target=100.124.55.39:5555 outcome=STARTED     ts=10:20:06   ← the proof
[agent] PEERSTART target=100.124.55.39:5555 outcome=ALREADY_UP  ts=10:20:12   (independent re-confirm, 6s later)
```

`STARTED` in `PeerStarter.ensureShizuku()` isn't just "we ran the start
command" — it's a `Thread.sleep(1800ms)` then an independent re-probe
(`isShizukuUp`) via the same connection, so the outcome itself already
encodes a live confirmation. Also independently verified from the Mac side:
`ps -A` on hd8 showed the new daemon (pid 3315, ppid 1, owned by `shell`,
`shizuku_server`) running and stable across multiple checks over the
following ~90s (a brief single `pgrep` miss right at the ~19s mark was a
timing/self-match artifact of my own diagnostic command, not a real state
flap — `ps -A` at the same moment showed the process present).

### 2. p7a provisioned as second peer, own path verified

`just agent-peer-provision p7a 100.124.55.39:5555` — p7a already had the
debug agent installed and running (`HostService` loop alive, logging
`NO_TARGETS` every ~25 min pre-provisioning), so no rollout was needed.
peer.json wrote successfully to both filesDir (run-as) and the external
fallback; the target-reminder marker also wrote successfully to hd8 (hd8's
agent build is debug too, so `run-as` works there despite the external-dir
write restriction #66 documented).

p7a generates its **own** on-device RSA key (distinct from s24's — by design,
per-device credentials), so hd8 needed a **second, independent** one-time
"Always allow" authorization. First attempt logged `AUTH_PENDING` as
expected — but then hit a real bug (see below) that took several rounds to
work around. Once unstuck:

```
[agent] PEERSTART target=100.124.55.39:5555 outcome=AUTH_PENDING  ts=10:22:53
[agent] PEERSTART target=100.124.55.39:5555 outcome=AUTH_PENDING  ts=10:24:44
[agent] PEERSTART target=100.124.55.39:5555 outcome=AUTH_PENDING  ts=10:27:17
[agent] PEERSTART target=100.124.55.39:5555 outcome=STARTED       ts=10:29:16   ← p7a's own STARTED, live
[agent] PEERSTART target=100.124.55.39:5555 outcome=ALREADY_UP    ts=10:29:37   (re-confirm)
```

Confirmed on-device: `ps -A` on hd8 showed pid 14182 (`shell`, ppid 1,
`shizuku_server`) running and stable. p7a is now a fully working, verified
second peer for hd8 — redundancy for the #61 feature is in place.

## New finding: Fire OS `adbd` can silently get stuck skipping the auth prompt

Filed as **[#114](https://github.com/djbclark/stayturgid/issues/114)** (full
writeup + logcat excerpts there). Summary: p7a's first connection attempt
should have raised hd8's dialog, but nothing appeared on-screen (confirmed
by screenshot, not just window-dump inference) across 3 retries over ~5
minutes. `adbd`'s own log revealed the real cause:

```
adbd: prompting user to authorize key
adbd: adbd_auth: sending prompt with id 326
adbd: adbd_auth: prompt currently pending, skipping
```

`adbd` has a single internal "prompt outstanding" flag that got stuck (most
likely: the first prompt's UI lifecycle didn't cleanly notify the daemon)
and silently dropped every later `send_auth_request` — no error surfaced to
the ADB client, indistinguishable from "target just hasn't tapped yet" from
the peer's side. **Fix:** toggling hd8's Developer Options → USB debugging
off then back on restarted `adbd`'s auth state; the very next attempt raised
a fresh dialog, was tapped, and completed. `persist.adb.tcp.port=5555`
survived the toggle (Tailscale listener came back with no further action),
and — important — **existing trusted keys were not revoked** (verified: `adb
devices` still showed both the Mac's key and s24's peer key trusted
afterward, and s24's periodic loop kept logging `ALREADY_UP` unaffected
throughout). This is a much lighter fix than "Revoke USB debugging
authorizations," which would have wiped the whole trust list.

**Anyone authorizing a new peer key on a Fire OS target in the future should
know this**: if repeated peer-start retries never show a dialog, don't
assume the client/UX code is broken — check the target's own `adbd` logcat
for `prompt currently pending, skipping`, and toggle USB debugging off/on to
clear it.

## Current fleet peer-start state (verified this session)

| Device | Role | Key status | Last verified outcome |
| --- | --- | --- | --- |
| **s24** | peer (only) | trusted on hd8, long-standing | `ALREADY_UP` (periodic loop, continuous) + `STARTED` (this session, deliberate test) |
| **p7a** | peer (only) | **newly trusted on hd8, this session** | `STARTED` → `ALREADY_UP` (this session) |
| **hd8** | target (only) | trusts both s24 and p7a's keys | Shizuku up, pid stable, both peers independently confirmed reachable |

hd8's Shizuku is up and stable at end of session (confirmed via `ps -A`,
pid 14182). Neither peer's key was disturbed by the other's authorization
flow or by the `adbd` toggle.

## Devices/tools used, none left in a bad state

- All actions used **external** adb (Mac's own already-trusted USB/Tailscale
  session, or the agents' own embedded ADB client) — never the local/loopback
  `shizuku_starter` path, never a reboot of hd8.
- `screencap`-based screenshot used to definitively rule out a dialog being
  present (rather than relying on `dumpsys window`, which doesn't reliably
  surface system alert dialogs) — worth remembering for future device-state
  debugging on this fleet: hd8 is USB-attached to the Mac with debugging on,
  so `adb shell screencap -p` + `adb pull` is a fast, low-risk way to see
  what's actually on a Fire device's screen without asking the operator to
  describe it.
- No rollout, dedupe, or APK changes needed on any of the three devices.

## What's NOT done / follow-ups

- **#114** (this session's new finding) is documentation-only; no code fix
  is possible on the stayturgid side (the bug is in Fire OS's own `adbd`).
  Worth folding a short "if the dialog never appears, toggle USB debugging"
  note into the guided-activation-UX notification text or docs at some
  point — flagged in #114, not done here.
- p7a's peer.json currently targets only hd8. If a third Fire-OS target is
  ever added, provisioning it will need its own peer(s) assigned the same
  way — expect the same `adbd` gotcha on first authorization.
- Everything else from the prior handoffs' "Open issues" list (#62–#66) is
  unchanged by this session.

## Hazards (unchanged, reconfirmed safe this session)

- **Do not `adb reboot` hd8** — recovery-bootloop risk. This session's
  Shizuku kill/recovery cycle used external ADB exclusively, exactly the
  supported recovery path — never a reboot.
- Do not restart Shizuku via the local `/data/local/tmp/shizuku_starter`
  loopback path on hd8.
- The USB-debugging-toggle fix in this session is a Developer Options
  action, not a factory-reset-adjacent one — confirmed it does not revoke
  existing trusted keys. "Revoke USB debugging authorizations" (the harder
  reset) was *not* used and would have required re-authorizing every peer.
