# ADR 006: Peer-start coordination — push model with per-device phase stagger

**Status:** Accepted (2026-07-26)
**Context:** With Shizuku peer-start built into the agent APK
([#61](https://github.com/djbclark/stayturgid/issues/61)), a healthy peer
(s24/p7a) starts Shizuku on a Fire-OS target (hd8) over external ADB. The
question is how helpers and targets coordinate: should each healthy peer
proactively check its targets ("push"), or should the target discover and ask
helpers one at a time with randomization ("pull")? Decided with the operator.

## Decision

**Push model with static assignment.** Each healthy peer independently ensures
its assigned targets on a fixed interval (`peer.json` lists the targets a peer
is responsible for; the agent's screen-independent loop connects and runs the
starter if Shizuku is down). Multiple peers may be assigned the same target —
that redundancy is intentional (N-way coverage, no single point of failure).

**Do not** build the target-initiated "pull" model (target knows the helper
list, asks one at a time, first-up-wins, randomized). It was the earlier
Termux-era approach (`stayturgid_peer_bootstrap.py` + `~/.stayturgid/peers`,
sketched in [fire-os-local-adb.md](../../research/fire-os-local-adb.md)) and was
deliberately dropped in the agent rewrite.

**Add a per-device phase stagger** to the periodic loops so fleet devices don't
run coincidentally (`AgentSchedule`, applied in `HostService`). See below.

## Rationale

- **The target is the sick device.** When hd8 needs Shizuku restarted it is, by
  definition, degraded. A recovery system must not depend on the failing device
  to initiate its own rescue — the pull model asks hd8 to run a healthy agent,
  resolve a peer list, reach the network, pick a live helper, and handle
  retries, any of which may be broken in the exact situation being recovered.
  The push model asks nothing of the target except that its `adbd` accept a
  connection — the minimum that must hold for _any_ recovery.
- **Resource cost is trivial.** One check = a TCP connect + one RSA-2048
  signature + a few tiny shell commands over already-up Tailscale — <5 KB,
  sub-second. Two peers × 3/hour ≈ ~30 KB/hour to the target and a couple of
  sub-second wakeups per device. Even at 5 peers × 5 targets it is negligible.
- **"First available helper wins" already emerges.** Whichever peer reaches a
  down target first starts Shizuku; the others connect, see `ALREADY_UP`, and
  no-op. The behavior the pull model would engineer falls out of push for free,
  without the target choosing.
- **Simplicity / robustness.** Push needs zero coordination: no signaling
  protocol, no discovery, no randomized selection to build, debug, or break.

## The stagger (why, and how it stays safe)

Redundant checks are cheap, but every device running the same fixed-interval
loops can still align on the wall clock (fleet-wide boot, or a Doze maintenance
window batching wakeups), causing a coincident network/radio spinup burst and,
for peer-start, two peers hitting the same target at once (a harmless but untidy
double-start race).

`AgentSchedule` derives a **stable per-device fraction** in `[0, 1)` from
`Settings.Secure.ANDROID_ID` and offsets each periodic loop's steady-state phase
by `fraction × interval`. Critically the offset is applied **once, after the
first (prompt) iteration** of the co-monitor and peer-start loops — the first
post-boot check is never delayed, so recovery latency is unchanged; only the
subsequent cadence is spread. Urgent peer-start retries (authorization pending)
are never staggered. The local, screen-on ping loop is not staggered (no
cross-device cost).

## Consequences

- Adding a peer is just provisioning its `peer.json` — no coordination change.
  Provision **p7a as a second peer** for hd8 when it returns, for redundancy.
- One target may see a few checks per interval; accepted as cheap redundancy.
- The stagger makes fleet-wide coincident runs unlikely without alarms/wakelocks
  (it rides the existing FGS coroutine loops; it is best-effort, not a scheduler).

## Revisit if

The fleet grows an order of magnitude (dozens of helpers / many targets), where
all-check-all becomes a thundering herd and one-helper-per-target with
load-spreading (the pull model, or a lightweight lease) would earn its
complexity. At 2–3 devices it does not.

## Related

- [#61](https://github.com/djbclark/stayturgid/issues/61) peer-start,
  [ADR-003](003-shizuku-catastrophic-recovery.md) Shizuku recovery,
  [fire-os-local-adb.md](../../research/fire-os-local-adb.md) (the older pull
  sketch).
