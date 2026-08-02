# Candidates for moving control-node/Termux functions into the agent APK

**Issue:** [#62](https://github.com/djbclark/stayturgid/issues/62).  
**Status:** investigation only — no move code in the PR that ships this
doc. Template pattern: [#61](https://github.com/djbclark/stayturgid/issues/61)
(external-ADB Shizuku peer-starter → `PeerStarter` /
`PeerStartCommands`).  
**Audit date:** 2026-08-01 (refresh of the 2026-07-28 snapshot from
PR #122 — several of that snapshot's "move next" items have already
shipped).

## Method

Read current owners under `control/bin/`, `device/termux/py/`,
`device/termux/boot/`, and
`device/native-agent/app/src/main/kotlin/org/stayturgid/agent/`, plus the
healing-coverage matrix in `tests/healing_registry.json` and ADR-003 /
ADR-004 / ADR-006. Focus:

1. Functions that **fail entirely** when the Mac is offline or Termux+SSH
   is down (the single points of failure #61's pattern eliminates).
2. The issue's named classes: peer-help verbs beyond Shizuku,
   SSH/Tailscale/sshd co-monitor split, Mac/Termux-gated repairs.
3. What has **already moved** so this doc does not re-propose shipped
   work.

### Already agent-side (do not re-propose)

| Capability                               | Where it landed                                                                                            | Source         |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------- |
| Peer `shizuku-start` (push model)        | `PeerStarter` + `HostService` peer-start loop (`peer.json`, ~20 min + stagger)                             | #61            |
| Peer `handsets-start` **implementation** | `HandsetsStarter` + APK asset `hs.jar`; **manual** trigger only (`HandsetsStartReceiver`)                  | #121 #156/#159 |
| Port-5555 catastrophic shell repair      | `CatastrophicRepair.tryShellWirelessRepair` (incl. `adb_wifi_enabled`; gated on `privilegedShellExpected`) | #60 / #116     |
| ADB baseline                             | `CatastrophicRepair.ensureAdbBaseline` from co-monitor                                                     | native-agent   |
| Shizuku HEADLESS_START                   | `CatastrophicRepair.headlessStart`                                                                         | agent          |
| Tailscale reconnect + always-on policy   | `CatastrophicRepair.repairTailscale` + `ComonitorProbes`                                                   | native-agent   |
| Co-monitor STATUS                        | `ComonitorProbes` (port / shizuku / sshd **probe-only** / wifi / tailscale)                                | HostService    |

## Candidates (remaining)

Summary table first; each row is expanded below with ownership detail.

| Candidate                           | Current owner (short)                        | Benefit of moving                    | Effort / risk       | Recommendation         |
| ----------------------------------- | -------------------------------------------- | ------------------------------------ | ------------------- | ---------------------- |
| Periodic peer handsets-start        | Agent impl + Mac/Termux auto only            | Mac/SSH-free Fire Handsets keepalive | Low                 | **Move — top**         |
| Peer re-assert `adb_wifi_enabled`   | Mac `fire_help_monitor` only                 | Steady-state Fire toggle without Mac | Low                 | **Move** (with above)  |
| Local Handsets ensure (self)        | Termux `stayturgid_handsets`                 | Termux-independent local daemon      | Medium              | **Defer**              |
| FIRERPA process keepalive           | Termux `start_adb` / Mac `firerpa_heal`      | Out-of-band path if Termux dies      | Medium–high         | **Investigate**        |
| Tailscale repair (Termux copy)      | Agent primary + Termux duplicate             | Cleanup only, not independence       | Verification        | **Audit redundancy**   |
| Termux wireless-debug ensure        | Termux + agent (agent already primary)       | Consolidation only                   | Low                 | **Don't move further** |
| sshd restart / stale `down` file    | Termux `stayturgid_repair`                   | None (sshd is Termux userland)       | Easy but empty      | **Don't move**         |
| Shizuku UID-2000 watchdog loop      | Termux via privileged shell                  | Circular bootstrap                   | N/A                 | **Don't move**         |
| SSH key bootstrap                   | Mac `bootstrap_ssh.py`                       | None (keys must stay Mac-only)       | Security regression | **Don't move**         |
| Dead-man's reachability monitor     | Mac `access_monitor.py`                      | Impossible on-device                 | N/A                 | **Don't move**         |
| Mac adb reconnect / fleet soft-heal | Mac launchd agents                           | Mac control-plane concerns           | N/A                 | **Don't move**         |
| Termux userland ensure\_\* helpers  | Termux repair (mirror, PATH, pkg, ET config) | Pure Termux filesystem/apt           | N/A                 | **Don't move**         |
| Screen / battery / agent-presence   | Termux boot-loop helpers                     | UX, not catastrophic connectivity    | Medium              | **Don't move** (#62)   |
| Legacy peer pull bootstrap          | Termux SSH → peer help                       | Superseded by ADR-006 push           | —                   | **Keep fallback only** |

### Detail: move / investigate

#### Periodic peer handsets-start — **Move (top priority)**

- **Current owner:** `HandsetsStarter` / `HandsetsStartCommands` are agent-side
  but **on-demand only** (`HandsetsStartReceiver` →
  `HostService.handsetsStartNow`). Automatic keep-alive still lives in Mac
  `control/bin/fire_help_monitor.py` (launchd →
  `fire_peer_help.cmd_handsets_start`) and Termux
  `stayturgid_peer_keepalive` / `stayturgid_peer_bootstrap` (SSH pull). The
  agent peer loop only runs `PeerStarter.startAll` (Shizuku).
- **Benefit:** Closes the last Mac/SSH dependency for the verb #121 already
  ported. Fire Handsets still dies when Mac is offline **and** peer Termux
  SSH is down, even though a healthy peer APK could restart it with code that
  already exists. Same push model as ADR-006.
- **Effort / risk:** **Low.** Call `HandsetsStarter.ensureHandsets` from the
  existing peer-start job (or a sibling loop). Optional `handsets_port` in
  `peer.json` (default 9012). Mitigate adb load with poll-before-start
  (`ALREADY_UP` style). No new privilege model.

#### Peer re-assert `adb_wifi_enabled` on Fire — **Move** (fold into peer path)

- **Current owner:** Mac-only
  `fire_help_monitor.ensure_wireless_debugging` (settings get/put over Mac
  adb). Fire cannot self-heal wireless ADB (`privilegedShellExpected=false`).
  Agent peer path connects externally but does not touch the toggle.
- **Benefit:** When a peer already has an authorized adbd session, keep the
  toggle from drifting off without the Mac — the gap
  `fire_help_monitor`'s docstring names. Does **not** restore adbd if port
  5555 is fully dead (USB/Mac still required for cold start).
- **Effort / risk:** **Low.** One `settings put global adb_wifi_enabled 1`
  (and maybe `adb_enabled`) via existing `AdbClient` shell at the start of
  `ensureShizuku` / `ensureHandsets`. Does not solve #188-class "shizuku
  never starts and 5555 never returns" without a live adbd.

#### Local Handsets ensure (self, non-Fire) — **Defer**

- **Current owner:** `device/termux/py/stayturgid_handsets.py` via
  `adb -s localhost:5555` when `STAYTURGID_NO_LOCAL_ADB` is unset.
- **Benefit:** Survives Termux death for local UI-automation daemon on phones
  that already have loopback shell.
- **Effort / risk:** **Medium.** UserService could launch `app_process` with
  the bundled jar, but Handsets demand on non-Fire is lower and not the Fire
  failure mode #61 targets. Prefer finishing peer auto-handsets first.

#### FIRERPA process keepalive — **Investigate, don't move yet**

- **Current owner:** Termux boot supervisor `start_adb.py`
  (`startup_firerpa` / `_launch_firerpa_via_shell`); Mac `firerpa_heal.py`
  when SSH/ADB are down.
- **Benefit:** FIRERPA is the Mac's out-of-band gRPC channel. If Termux
  bootloop dies, FIRERPA may die with it. Agent FGS + UserService could
  relaunch under uid 2000 without Termux.
- **Effort / risk:** **Medium–high.** Paths, cert, lifecycle argv, and "child
  dies when rish session closes" constraints are already non-trivial. Two
  supervisors thrashing would be worse than one. Decide single ownership
  before coding.

#### Tailscale repair (Termux copy) — **Audit redundancy only**

- **Current owner:** Agent `CatastrophicRepair.repairTailscale` is primary;
  Termux `stayturgid_repair.ensure_tailscale` now correctly returns
  `unknown` without privileged shell (hd8 false-down fix).
- **Benefit:** Not a Mac-independence gap. Termux copy is either useful
  boot-window backup or dead weight.
- **Effort / risk:** Field verification — does agent FGS repair fire before
  Termux's 5‑min loop matters after boot? Do not "port"; optionally thin
  Termux once agent preemption is proven.

### Detail: don't move

| Candidate                                      | Why leave it where it is                                                                                                                                                          |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Termux `ensure_wireless_debugging`             | Agent already owns the primary path post-#116 (`tryShellWirelessRepair` sets `adb_wifi_enabled`). Termux is backup/consolidation, not a #61-class win.                            |
| sshd restart / stale `down` file               | sshd is Termux userland (`runsv`). Agent shelling `sv up` still requires Termux (ADR-004).                                                                                        |
| Shizuku UID-2000 watchdog                      | Requires privileged shell already up — cannot bootstrap Shizuku from nothing. Peer-start is the real bootstrap. Textbook case of correct Termux/Mac gating.                       |
| SSH key bootstrap (`bootstrap_ssh.py`)         | "Keys are read from the Mac only — never committed to git." Bundling host keys into an APK is a security regression.                                                              |
| Dead-man's reachability (`access_monitor.py`)  | External reachability check by definition; a device cannot usefully answer "am I reachable from outside?" when the answer is no.                                                  |
| Mac `adb_reconnect` / fleet soft-health        | Mac control-plane (transport cache, operator notification, remote agent restart).                                                                                                 |
| Termux userland ensure\_\*                     | Mirror pin, PATH scrub, daily pkg upgrade, control-ET ssh config, os-release — pure Termux filesystem/apt state.                                                                  |
| Screen-awake / battery / agent-presence        | UX helpers on the Termux boot loop; not catastrophic connectivity under #62's framing.                                                                                            |
| Legacy peer pull (`stayturgid_peer_bootstrap`) | ADR-006 chose **push** over pull for agent. Keep as Handsets auto fallback until periodic peer handsets ships; then reassess retirement. Do **not** re-implement pull in the APK. |

## Summary

Of the issue's three named areas, **after** #61 / #121 / #116:

1. **Peer-help verbs beyond Shizuku** — implementation for `handsets-start` is
   done; the remaining gap is **scheduling** it like Shizuku (periodic push
   from assigned peers). Pair with peer-side `adb_wifi_enabled` re-assert so
   Mac `fire_help_monitor` is not required for steady-state Fire health.
2. **SSH / Tailscale / sshd split** — Tailscale and port-5555 catastrophic
   paths are already agent-primary. sshd stays Termux. Termux Tailscale /
   wireless copies are redundancy candidates, not independence wins.
3. **"Gated on Mac online / Termux+SSH"** — still-correct Mac gates:
   `bootstrap_ssh.py`, `access_monitor.py`, `adb_reconnect.py`. Still-correct
   Termux gates: sshd, package/mirror/PATH, Shizuku shell-watchdog. The
   remaining wrong-gate is automatic Fire Handsets (+ wireless-toggle
   re-assert) still depending on Mac launchd or Termux SSH pull.

**Net recommendation:** do **not** treat #62 as a broad "move everything"
initiative. File (or implement) one narrow follow-up:

1. **Periodic peer handsets-start** (+ optional `adb_wifi` re-assert on the
   same peer connection) — clear #61-pattern win, lowest risk.
2. **FIRERPA keepalive ownership design** — investigate only; no code until
   Termux vs agent ownership is decided.
3. Leave Tailscale Termux dedup and the "don't move" rows as documentation
   so they are not re-proposed without re-reading this file.

Related open work that is **not** a #62 move but blocks Fire independence in
practice: [#188](https://github.com/djbclark/stayturgid/issues/188) (hd8
`shizuku_server` never starts after reboot — peer-start is the intended
recovery when self-start fails, which makes the peer path's completeness
more important, not less).
