# Handoff — 2026-07-26 Peer-start activation, UX, and fleet fixes ([#61](https://github.com/djbclark/stayturgid/issues/61))

Continuation of [handoff-2026-07-26-peer-start-61.md](handoff-2026-07-26-peer-start-61.md)
(read that first for the initial build). This session: built the guided
activation UX, authorized the agent key on hd8 **live**, fixed a Tailscale
GUI-popping bug and a duplicate-agent problem, and found three more bugs — one
fixed-but-not-live-verified, two filed. **Pick up at "Next agent: do this
first."**

## ✅ #61 green path PROVEN (2026-07-26, end of session)

hd8's adbd **trusts the agent's key** (operator ticked "Always allow"). The
stream-id bug (`not A_WRTE or A_CLSE` from reusing ADB stream id 1 across the
several shell commands per peer-start) was **fixed in `d5b2ff5` (v0.5.1) and
live-verified**: s24 on v0.5.1 → `just agent-peer-start s24` returned
**`ALREADY_UP` three times in a row**, hd8 Shizuku stayed up, **no dialog**. The
peer's 20-min loop now keeps hd8's Shizuku monitored Mac-independently. The full
pipeline (embedded ADB client → auth → multi-command shell exec → status) works.

**What actually remains on #61:**

- The **`STARTED`** path (vs `ALREADY_UP`) — i.e. the agent actually running
  `libshizuku.so` — is unobserved because hd8's Shizuku is up. It's the same
  exec path with a different command, so high-confidence, but not seen. Prove it
  only when hd8's Shizuku is genuinely down (do **not** down it artificially:
  hd8's Shizuku only recovers via external ADB, and don't reboot hd8 —
  recovery-bootloop hazard).
- Provision **p7a as a second peer** when it's back.
- Then close #61.

Fallback if the stream-id issue ever recurs: reconnect-per-command in
`PeerStarter` (one `AdbClient.connect()` per shell command) — fine now that the
key is persisted (Always-allow), just more overhead.

## Current fleet state (verified this session)

| Device  | adb                                                    | Agent                                                             | Notes                                                                                                                                                                                                                                                                                                                                                    |
| ------- | ------------------------------------------------------ | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **hd8** | USB `GN43T503430603PS`; Tailscale `100.124.55.39:5555` | **v0.5.0-debug**, single build, **1** userservice, Shizuku **UP** | Key **authorized** (Always-allow tapped). No `peer.json` (it's the target). Reminder marker **not set** (Fire OS blocks it — see #66). Mac reaches it via **USB**, not its Tailscale IP. Optional: update to v0.5.1 (cosmetic — a Fire target never uses the peer-side ADB client; use the safe `agent-install`+`agent-start`, **not** `agent-rollout`). |
| **s24** | `100.123.218.30:5555`                                  | **v0.5.1-debug**, single build, peer role working                 | Has `peer.json` → target `100.124.55.39:5555`; peer-start returns `ALREADY_UP`. The active, verified peer for hd8.                                                                                                                                                                                                                                       |
| **p7a** | OFFLINE (dead battery)                                 | old, likely duplicate builds                                      | When back: `just agent-dedupe p7a`, `just agent-rollout p7a` (→ v0.5.1), provision as a 2nd peer for hd8.                                                                                                                                                                                                                                                |

Git: `master` = `d5b2ff5`, clean, pushed. Agent version **13 / 0.5.1-peerstart-ux**.

## What shipped this session (commits)

- `7ad421a` — peer-start built into the agent APK (embedded ADB client, own
  hardware-backed key, PeerStarter, config, broadcast trigger). See prior handoff.
- `12c0b61` — **Tailscale GUI-foreground fix (#64)**: `stayturgid_repair.py`
  read `/proc/net/dev` from the Termux app-uid (EACCES on modern Android) →
  false "down" every cycle → foregrounded Tailscale ~every 15 min. Now reads via
  the uid-2000 shell. Deployed to s24, verified. **Fleet deploy to p7a/hd8 still
  pending.**
- `10a346a` — **guided activation UX (#61)**: `AUTH_PENDING` outcome; peer nag
  notification (re-alerting, tap=retry) + GUI banner/button while pending;
  3-min retry while pending; `AuthorizeReminder` target-side reminder; peer
  auto-clears the marker on success. Target-reminder path live-verified on s24.
- `53047f2` — docs for the above + the Termux `/proc` lessons-learned entry.
- `323ab47` — **one agent per device on install**: `rollout.py`
  `enforce_single_variant()` + `just agent-install` + `just agent-dedupe`
  force-stop and uninstall the _other_ build (debug vs release install
  side-by-side under different applicationIds, each running its own FGS).
- `d5b2ff5` — **stream-id fix**: unique local stream id per
  `AdbClient.command()`; `readForStream()` skips stray frames. v0.5.1.
  **Live-verified** (s24→hd8 `ALREADY_UP` ×3, no dialog).

## Research & findings (all of it, for context)

### Why peer-start exists (proven earlier, #60)

Fire OS `adbd` drops connections whose peer is **device-local** (loopback), so
Shizuku can't self-start on Fire devices; an **external** peer is accepted. Hence
a healthy peer starts Shizuku on hd8 over ADB. The agent embeds a minimal ADB
client to do this without the Mac.

### ADB-key model — best practice (web research → decision)

Sources: [Android Keystore](https://developer.android.com/privacy-and-security/keystore),
[Shizuku wireless-adb](https://deepwiki.com/RikkaApps/Shizuku/3.4-wireless-adb-startup),
[OWASP Key Management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).
Consensus: generate keys on-device, keep them non-exportable/hardware-backed
(Shizuku's `AdbKey` wraps the RSA private key with an AES/GCM key in the
AndroidKeyStore); prefer **per-device credentials + a central trust list** over a
shared secret (smaller blast radius, revocable, no key transport). **Decision:**
the agent generates its own hardware-backed key (Shizuku's `AdbKey`), authorized
once per peer on the target via the system "Always allow" dialog — not the shared
fleet adbkey.

### ADB handshake — verified live (s24 → hd8)

`A_CNXN "host::"` → hd8 `A_AUTH` token → s24 `A_AUTH SIGNATURE` (RSA-signed) →
hd8 re-challenge → s24 `A_AUTH RSAPUBLICKEY` (ends ASCII `stayturgid-agent\0`) →
hd8 raises the `UsbDebuggingActivity` dialog. After the operator's Always-allow,
`A_CNXN` succeeds and shell streams open. The classic `tcpip 5555` path uses
legacy RSA `A_AUTH` (not the TLS `A_STLS`/pairing flow), so the `AdbKey` TLS path
is unused against hd8.

### Fire OS "Always allow" is a manual tap

`/data/misc/adb/adb_keys` is root-only; adbd writes it only after the dialog is
confirmed **with the checkbox ticked**. `adb_cli.dismiss_usb_debugging_dialog`'s
TAB/SPACE/ENTER keyevent heuristic accepts _allow-once_ but does **not** reliably
tick the persist checkbox on Fire OS 8 — so the operator must tap it by hand
(done this session).

### Two SELinux/storage asymmetries between Termux app-uid, shell (uid 2000), and Fire OS

- **`/proc/net/*` is per-uid restricted**: the Termux app uid gets EACCES; uid
  2000 (shell / the agent's Shizuku UserService) can read it. Root cause of the
  Tailscale bug (#64). Rule: read `/proc/net/*` via the device shell, never in a
  Termux process. (Same class as the agent's `listeningOn()` `ss`/`/proc/net/tcp`
  fallbacks.)
- **`/sdcard/Android/data/<pkg>/` write access differs by ROM**: OneUI (s24)
  lets adb shell write it; **Fire OS (hd8) returns Permission denied**. This
  breaks the external-dir reminder-marker approach on Fire OS (#66).

### Duplicate agent builds

Debug (`.debug` applicationIdSuffix) and release are **different package ids** →
install side by side, each runs its own `HostService` FGS → two non-dismissable
"UserService bound" notifications + two agents racing to bind Shizuku. `adb
install -r` only replaces the same package. Found live on **both hd8 and s24**;
cleaned both; prevention added (`323ab47`). Keeper is the **debug** build
(provisioning's `run-as` needs a debuggable build).

## Open issues (GitHub)

- **[#61](https://github.com/djbclark/stayturgid/issues/61)** peer-start — nearly
  done; needs the v0.5.1 re-test above (green path) to close.
- **[#62](https://github.com/djbclark/stayturgid/issues/62)** audit more
  functions to move into the agent APK.
- **[#63](https://github.com/djbclark/stayturgid/issues/63)** CFEngine update.
- **[#64](https://github.com/djbclark/stayturgid/issues/64)** Tailscale
  GUI-foreground — Termux fix landed + deployed to s24; **fleet deploy (p7a/hd8)
  - the native-agent `repairTailscale` activity-fallback footgun remain**.
- **[#65](https://github.com/djbclark/stayturgid/issues/65)** Shizuku
  UserService leak (22 stale on hd8; worked around). Fix: reap on bind / share
  `stop_stale_user_services` in `start_agent.py` / stable UserService tag.
- **[#66](https://github.com/djbclark/stayturgid/issues/66)** target reminder
  marker fails on Fire OS (adb shell can't write `/sdcard/Android/data`), and
  `set_target_reminder()` assumes the Mac reaches the target at the peer's
  host:port. **Operator wants to discuss unifying to one mechanism for all
  platforms** (likely `run-as` + internal `filesDir` everywhere, mirroring
  `PeerConfig`'s dual read) rather than two ways — **discuss before
  implementing.** Until fixed, hd8 shows no reminder (harmless; the s24-side nag
  and the system dialog still drive the flow).

## Hazards (unchanged)

- **Do not `adb reboot` hd8** — recovery-bootloop risk. Bring Shizuku up via
  external ADB, not reboot.
- Do not restart hd8's Shizuku via the local `/data/local/tmp/shizuku_starter`
  (loopback → EOF on Fire OS; it would take Shizuku down with no local recovery).
  This session updated hd8's agent APK **without** touching Shizuku for exactly
  this reason — use `agent-install`/`agent-start` on hd8, **not** `agent-rollout`
  (which restarts Shizuku).
