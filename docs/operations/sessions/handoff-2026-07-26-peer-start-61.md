# Handoff — 2026-07-26 Peer-start built into the agent APK ([#61](https://github.com/djbclark/stayturgid/issues/61))

Built the external-ADB Shizuku peer-starter **into the `stayturgid-agent` APK**
(issue #61, the prior handoff's #1 priority). Code is complete, builds, unit-
tested, and the core wire path was validated live against hd8. One operational
step remains: a one-time "Always allow" authorization tap on hd8.

## What shipped (code)

A peer device (s24/p7a) can now start Shizuku on a Fire-OS device (hd8) over
external ADB **with no Mac dependency** — the capability lives in the agent's
app process (the peer does **not** need its own Shizuku for this).

- **Embedded ADB client** — ported from the Shizuku fork's `manager/adb/` into
  `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/adb/`:
  `AdbProtocol`, `AdbMessage`, `AdbException`, `AdbKey`, `AdbClient`. Adaptations:
  package rename, `unsafeLazy`→`lazy(NONE)`, `BuildUtils.atLeast29`→inline SDK
  check, dropped the debug `logd`, added a configurable `readTimeoutMs`
  (default 60s) so the one-time auth wait can't wedge the thread, and fixed a
  latent socket-field leak in upstream `close()`.
- **Key model = best practice** (see #61 decision + research): the agent
  **generates its own RSA key on-device**, AES/GCM-wrapped by the hardware
  AndroidKeyStore, never exported (exactly Shizuku's `AdbKey`). Per-device
  credentials + revocation, not a shared fleet secret. Cost: one "Always allow"
  authorization per peer on the target's adbd.
- **`PeerStarter` + `PeerStartCommands`** — connect to `<target>:5555`, check
  `pgrep -f '[s]hizuku_server'`; if down, `pm path` → `<apkdir>/lib/arm64/
libshizuku.so` under `LD_LIBRARY_PATH` (fallback `start.sh`). Faithful to
  `control/bin/fire_peer_help.py:cmd_shizuku_start`. Command builders are pure +
  unit-tested.
- **`PeerConfig`** — static assignment from `peer.json` (`filesDir` preferred,
  external-files fallback): `{ "targets": ["100.x:5555"], "shizuku_pkg": "…" }`.
  No targets ⇒ no-op. Targets are non-secret (no key is provisioned).
- **Trigger** — a screen-independent loop in `HostService` (every 20 min, 30s
  after boot) runs peer-start in-process. Manual kick via **broadcast** (not an
  activity — see gotcha below): `PeerStartReceiver`.
- **Manifest** — added `INTERNET` permission + the exported `PeerStartReceiver`.
- **Deps/build** — `org.bouncycastle:bcpkix-jdk18on:1.80` (TLS cert for the
  A_STLS path), packaging excludes for BC's duplicate metadata, proguard keeps.
  Version bumped **10 → 11** (`0.4.0-peerstart`).
- **Ops tooling** — `control/tools/native-agent/provision_peer.py` +
  `just agent-peer-provision <peer> <target:5555>` / `agent-peer-start <peer>` /
  `agent-peer-show <peer>`.
- **Tests** — 17 JVM unit tests (`app/src/test/`): AdbMessage framing, command
  builders, target parsing. `just agent-assemble` (debug) **and**
  `assembleRelease` (R8 + BouncyCastle) both green.

## Live validation (s24 → hd8, 2026-07-26)

- ✅ **Core path proven.** s24's agent (v0.4.0) completed the full ADB handshake
  to hd8's real `adbd`: `A_CNXN` → hd8 `A_AUTH` token → s24 `A_AUTH SIGNATURE`
  (256B, signed with its on-device key) → hd8 re-challenge → s24 `A_AUTH
RSAPUBLICKEY` (718B, ending ASCII `stayturgid-agent\0`). hd8 then raised the
  `UsbDebuggingActivity` authorization dialog. **Every line of the new code path
  (socket, framing, RSA sign, pubkey encoding) exercised against the real
  target.** Captured in logcat.
- ✅ **hd8 untouched.** hd8's Shizuku was UP throughout and stayed UP — peer-
  start never reached the start command (blocked at the auth gate), so zero risk
  realized. No hd8 reboot.
- ⏳ **Remaining: the one-time authorization.** hd8's adbd doesn't yet trust the
  agent's new key. Persisting it needs a human to check **"Always allow from
  this computer"** + **Allow** on hd8's screen — the deliberate one-time cost of
  the per-device key model. The keyevent helper
  (`adb_cli.dismiss_usb_debugging_dialog`) does **not** reliably tick the
  "Always allow" checkbox on Fire OS 8 (it accepts allow-once, so the dialog
  reappears next connect). Do this tap by hand.

### To finish activation (≈2 min, needs a tap on hd8)

```bash
# 1) assign hd8 to s24 (also sets the "approve on hd8" reminder on hd8)
just agent-peer-provision s24 100.124.55.39:5555
# 2) kick a peer-start (headless broadcast — does NOT foreground the UI)
just agent-peer-start s24
# 3) on hd8's screen: tick "Always allow from this computer", tap Allow
# 4) confirm
just agent-peer-show s24      # expect PEERSTART … outcome=ALREADY_UP (hd8 Shizuku is up)
```

After the tap, hd8 trusts the agent's key permanently (survives reboot), and the
20-min loop keeps hd8's Shizuku up Mac-independently. To exercise the _start_
path (not just ALREADY_UP), do it when hd8's Shizuku is actually down.

### Guided activation UX (v0.5.0-peerstart-ux — commit 10a346a)

The authorization no longer relies on remembering commands. Once a peer is
assigned:

- **On the peer (s24/p7a):** while a target is `AUTH_PENDING` (reachable but not
  yet approved), the agent posts a high-priority, re-alerting **"Peer-start needs
  a one-time approval"** notification (tap = retry), shows a banner + **"Authorize
  peer-start now"** button in its GUI, and **auto-retries every 3 min** (vs 20) so
  the target's dialog is reliably up. All of this is **headless** — verified it
  does **not** foreground the agent GUI (the earlier activity-trigger footgun is
  gone; the trigger is now `PeerStartReceiver`, a broadcast).
- **On the target (hd8):** its own agent shows a **"Approve peer-start on this
  device"** reminder notification + banner (from a marker `provision_peer.py`
  drops on it), telling the operator to tick "Always allow" + Allow when the
  dialog appears. The peer **clears that marker automatically** over the
  authorized ADB connection once peer-start succeeds. _Live-verified on s24_
  (target-reminder notification posts on the high-importance channel and
  auto-clears when the marker is removed, no GUI foregrounding).
- The `AUTH_PENDING` state is distinct from `UNREACHABLE` (offline never nags),
  and clears itself on the next successful `ALREADY_UP`/`STARTED`.

**Deploy dependency:** the hd8-side reminder only shows once hd8's agent is
updated to v0.5.0+. The peer-side nag works as soon as the peer runs v0.5.0
(s24 is on it now).

## Gotchas found this session (also in lessons-learned)

- **Never trigger peer-start via an activity.** The first cut launched
  `MainActivity` with an intent extra → the agent GUI popped to the foreground on
  every kick (operator-visible, disruptive). Fixed: headless `PeerStartReceiver`
  broadcast; `MainActivity` no longer a trigger surface. Verified s24's focus
  stayed on the foreground app across a broadcast trigger.
- **Fire OS "Always allow" checkbox isn't reliably keyevent-toggleable.**
  `dismiss_usb_debugging_dialog`'s TAB/SPACE/ENTER heuristic accepts allow-once
  but doesn't tick the persist checkbox on Fire OS 8 → authorization doesn't
  survive. New-key authorization here is a human tap.

## State

- **stayturgid `master`**: peer-start committed + pushed (this session). All
  prior work from the sibling handoff (Shizuku release23, group_vars de-dup, VLM
  removal) already landed.
- **Devices:** hd8 Shizuku UP (manual start, unchanged — #61 makes it self-
  healing once authorized). s24 on v0.4.0 agent, `peer.json` currently **removed**
  (so no dialog churn); re-provision per the activation steps above. p7a OFFLINE
  (still, dead battery) — provision it too when it returns.

## Next

1. **Finish #61 activation** — the one-tap authorization above; then a full
   green-path E2E when hd8's Shizuku is down (STARTED, not just ALREADY_UP).
   Keep #61 open until that E2E passes.
2. Provision p7a as a second peer when it's back (redundancy for hd8).
3. Prior open loose ends unchanged: p7a on release21 (needs release23), #57/#59.
