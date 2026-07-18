<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Research — Fire OS local ADB block (hd8)

Date: 2026-07-09. Device: Fire HD 8 (`KFRASWI`), Fire OS **8.0** / Android **11** (SDK 30), build `RS8338.3339N`, USB `GN43T503430603PS`.

## Problem

Termux Handsets (and any on-device privileged shell) needs **shell UID** via `adb -s localhost:5555`. On hd8 that path is dead:

| Client                  | Target                   | Result                                                      |
| ----------------------- | ------------------------ | ----------------------------------------------------------- |
| Termux on hd8           | `127.0.0.1:5555`         | `offline` / failed to connect                               |
| Termux on hd8           | LAN `192.168.1.157:5555` | `offline` (same-device bind check)                          |
| Termux on hd8           | Tailscale IP             | no iface / same block                                       |
| Mac / external          | USB or LAN `:5555`       | **OK** (`device`)                                           |
| Termux on s24 → hd8 LAN | `192.168.1.157:5555`     | reaches adbd; needs RSA allow (`unauthorized` until prompt) |

`adbd` listens on `*:5555`, `adb_enabled=1`, `service.adb.tcp.port=5555`. The daemon is up; **on-device clients are rejected**.

Fleet already sets `STAYTURGID_NO_LOCAL_ADB=1` on hd8 and routes post-UI through Mac Handsets.

## What Amazon blocked

Publicly documented for **Fire TV** (Feb 2024), same symptom on this **Fire tablet**:

- [AFTVnews](https://www.aftvnews.com/amazon-blocks-long-running-fire-tv-capability-breaking-popular-apps-with-no-warning-and-giving-developers-the-runaround/) — apps on the device can no longer open local ADB; external PC/phone still can.
- [CVE-2024-27350](https://nvd.nist.gov/vuln/detail/CVE-2024-27350) — Fire OS 7 &lt; 7.6.6.9 / 8 &lt; 8.1.0.3 “allowed” local ADB (Amazon framed the fix as security).
- Detection heuristic (AFTVnews comments): try to **bind** the connect address; success or `EADDRINUSE` ⇒ treat as local ⇒ refuse. That is why LAN self-connect fails too.

XDA “Tailscale bypass” threads are **second device → Fire**, not Termux-on-Fire → self. Finnzz: Amazon only blocked same-device app→adbd.

## Workarounds searched (and verdict for fleet)

### 1. Stock Android Wireless Debugging + `adb pair 127.0.0.1` — **N/A on this build**

Works on Pixel/Samsung for Termux self-ADB. On hd8:

- QS tile class exists: `DevelopmentTiles$WirelessDebugging`.
- Activities `WirelessDebuggingActivity` / `Settings$WirelessDebuggingActivity` **do not exist** (TabletSettings APK).
- `settings put global adb_wifi_enabled 1` does not stick (`0`); no TLS pairing port.
- Classic `tcpip 5555` already active — still same-device offline.

Amazon Kids 8 (2024) reports Wireless Debugging UI broken; Amazon acknowledged (Feb 2026). Not a fleet path.

### 2. External ADB (Mac / second phone) — **works; current design**

Mac USB/LAN/Tailscale → `adb shell` as shell UID. This is how Shizuku and Handsets already start on hd8.

### 3. Second-device ADB proxy (netcat / socat) — **works in theory; bad ops**

AFTVnews comment: on-device app connects to Pi/phone proxy; proxy opens “external” session to Fire adbd. Still requires a always-on external host. Strictly worse than Mac Handsets for this fleet.

### 4. Tailscale / mesh VPN — **does not unblock same-device**

Useful for Mac↔hd8 when LAN is messy. Does not make Termux→own adbd succeed (confirmed: LAN IP from Termux still offline).

### 5. Shizuku / `rish` as shell without Termux→adbd — **dead end on Fire for Termux**

Live on hd8 (deepened 2026-07-09):

| Step                                                             | Result                                                                  |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Start Shizuku via Mac/`libshizuku.so`                            | **OK** — `shizuku_server` as shell UID                                  |
| Add Termux uid `10310` to `/data/local/tmp/shizuku/shizuku.json` | Applied                                                                 |
| `pm grant com.termux moe.shizuku.manager.permission.API_V23`     | **Fails** — Termux does not declare that permission                     |
| `rish -c id` (dex from Shizuku APK)                              | **Request timeout** even with json grant + `MANAGER_APPLICATION_ID` set |

Termux is not a Shizuku client app (no binder handshake / no declared API perm). AutoJs6 _is_ granted and can use Shizuku APIs, but that does not give Termux a shell-UID `app_process` starter without going through AutoJs6 JS — and Shizuku itself still needs an **external** start every boot on Fire (“Start by connecting to a computer”).

**Do not** build the Fire Handsets path on `rish`. Peer ADB (below) is strictly better.

### 6. Hybrid: external start Handsets daemon + Termux wire client — **proven**

```
External shell UID:  adb shell CLASSPATH=…/hs.jar app_process … Main --port=N
Termux on hd8:       length-prefixed wire → 127.0.0.1:N
```

| Starter                                         | Wire `ping`    |
| ----------------------------------------------- | -------------- |
| Mac adb                                         | `pong` ~246 ms |
| **s24 Termux adb → hd8** (after one-time Allow) | `pong` ~238 ms |

### 7. Peer help (fleet device starts Handsets on hd8) — **proven; recommended for Mac-less self-heal**

#### Live proof (2026-07-09)

1. SSH mesh already works both ways: `hd8 → s24` and `s24 → hd8` via `id_ed25519_fleet` + known_hosts (Ansible `termux_userland` / `ssh_keys.yml`). No runtime script used it until now.
2. s24 `adb connect 192.168.1.157:5555` (and Tailscale `100.124.55.39:5555`) → initially `unauthorized`.
3. One-time `UsbDebuggingActivity` on hd8: check **Always allow** + **ALLOW** (Mac Handsets tapped it).
4. s24 then:
   ```bash
   adb -s 192.168.1.157:5555 shell \
     'CLASSPATH=/data/local/tmp/hs.jar nohup app_process /system/bin \
      --nice-name=hsd9018 dev.handsets.daemon.Main --port=9018 \
      >/data/local/tmp/hsd9018.log 2>&1 &'
   ```
5. hd8 Termux wire `ping` → `pong`.

Same short command can start Shizuku:
`LD_LIBRARY_PATH=<apk>/lib/arm64 <apk>/lib/arm64/libshizuku.so`.

#### Why peer ADB beats peer SSH-into-hd8

SSH into hd8 Termux only gets **app UID** — cannot start `app_process` as shell. The helper must speak **to hd8’s adbd from outside**. Flow:

```
hd8 Termux                    helper (s24 / p7a / Mac)
    |                              |
    |-- SSH: "start handsets" ---->|
    |                              |-- adb connect <hd8-ip>:5555
    |                              |-- adb shell app_process … Main --port=N
    |<-- (daemon on 127.0.0.1:N) --|
    |-- wire ping/dump_active ---->| (local loopback)
```

#### One-time ADB trust (ops)

Each helper has its own `~/.android/adbkey` today (Mac / s24 / p7a / hd8 all different). Fire stores accepted keys in `/data/misc/adb/adb_keys` (**not writable by shell**). Options:

| Approach                                           | Cost                                                                            |
| -------------------------------------------------- | ------------------------------------------------------------------------------- |
| **A. Accept each peer once** (“Always allow”)      | 2–3 taps per new helper; survives reboot                                        |
| **B. Shared fleet `adbkey`** on all Termux helpers | One Allow covers every phone; Ansible deploys identical keypair                 |
| **C. Mac-only helper**                             | Already trusted; device→Mac SSH via peerhelp ForceCommand + launchd `fire-help` |

Recommend **B** for phones + keep Mac as fallback when present.

#### Restricted SSH (`command=` / ForceCommand)

User recollection is right: OpenSSH `authorized_keys` can pin a key to one program:

```
command="/data/data/com.termux/files/home/.stayturgid/bin/stayturgid-peer-help",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAA… hd8-peer-help
```

Put that on **helpers** (s24/p7a), not on hd8. hd8’s dedicated `id_ed25519_peerhelp` can only invoke the helper script. Script accepts a small verb set (`handsets-start`, `shizuku-start`, `ping`) and target identity from env/argv — never a free shell.

In this fully-trusted lab, full mesh SSH is already deployed and acceptable;
ForceCommand is defense-in-depth. **Shipped:** Fire hosts generate
`id_ed25519_peerhelp`; helpers get `command=…/stayturgid-peer-help-force.sh`;
Mac gets `command=…/fire_peer_help.py`.

#### Discovery list (hd8 asks who can help)

Inventory already has Tailscale + LAN per host (`hosts.yml` / `devices.conf`). On-device sketch:

1. Read peer list from `~/.stayturgid/peers` (rendered by Ansible from inventory, exclude self).
2. For each peer (prefer LAN, then Tailscale): TCP probe `:8022` → SSH `BatchMode` → run `stayturgid-peer-help handsets-start --target <hd8-ts-or-lan>:5555 --port 9012`.
3. Local wire `ping`; on success stop. Else next peer. Else leave Handsets disabled / fall back to raw dump / wait for Mac.

Mac can be last in the list once device→Mac SSH is enabled (authorize fleet pubkeys on Mac sshd).

### 8. Root / downgrade / pre-CVE firmware — **out of scope**

Not for unrooted fleet policy.

### 9. Raw `uiautomator dump` on-device — **possible but slow**

Does not need shell UID. Already the Termux fallback when Handsets is disabled.

## Recommendation

| Option                                       | Use?                                                                                    |
| -------------------------------------------- | --------------------------------------------------------------------------------------- |
| Pure Termux→`localhost:5555` Handsets on hd8 | **No** — Amazon block                                                                   |
| Wireless Debugging self-pair                 | **No**                                                                                  |
| Tailscale for self-ADB                       | **No** — wrong problem                                                                  |
| Shizuku/`rish` to start Handsets from Termux | **No** on Fire (binder timeout); **rish still installed by default** for stock Android  |
| **Peer ADB bootstrap via SSH mesh**          | **Shipped** — `stayturgid_peer_bootstrap` + `stayturgid_peer_help`                      |
| Shared fleet `adbkey-fleet` + one Allow      | **Shipped** — `~/.stayturgid/adbkey-fleet` (does **not** overwrite `~/.android/adbkey`) |
| SSH `command=` restricted helper key         | **Shipped** — Fire `id_ed25519_peerhelp` → helpers/Mac ForceCommand                     |
| Hybrid wire client after peer start          | **Yes** — `stayturgid_handsets.py` uses peer start when `NO_LOCAL_ADB`                  |
| Mac Handsets when Mac present                | **Yes** — Mac last in `peers` + launchd `fire-help`                                     |

### Shipped pieces (2026-07-09)

| Piece                         | Path                                                                                    |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| rish install (default deploy) | `device/termux/py/stayturgid_rish.py` → `~/.stayturgid/bin/rish`                        |
| Shared fleet ADB key          | Mac `~/.config/stayturgid/adbkey` → device `~/.stayturgid/adbkey-fleet`                 |
| Helper (phones)               | `stayturgid_peer_help.py` (`ADB_VENDOR_KEYS=…/adbkey-fleet`)                            |
| Helper (Mac)                  | `control/bin/fire_peer_help.py`                                                         |
| Asker                         | `stayturgid_peer_bootstrap.py` + `~/.stayturgid/peers` (phones + Mac)                   |
| Keepalive (F1/F2)             | `stayturgid_peer_keepalive.py` from boot loop when `NO_LOCAL_ADB`                       |
| Mac launchd (F4)              | `com.stayturgid.fire-help` → `control/bin/fire_help_monitor.py`                         |
| ForceCommand (F5)             | `stayturgid-peer-help-force.sh` on helpers; Mac `authorized_keys` → `fire_peer_help.py` |
| Handsets integration          | `stayturgid_handsets.start()` peer path when `STAYTURGID_NO_LOCAL_ADB=1`                |

**Live E2E:** hd8 cold start → SSH s24 → `handsets-start` on `192.168.1.157:5555` → wire `pong`. Same fleet key works from p7a without a second Allow. Mac is last peer; launchd also helps if peers miss.

**One-time ops:** on each Fire (or new target), accept **Always allow** once when a helper first connects with `adbkey-fleet`. Mac **Remote Login** must be on for device→Mac SSH.

## Related

- `docs/research/handsets-under-termux.md` — s24 Termux Handsets; hd8 out of scope
- `docs/architecture/adr/001-ansible-boundary.md` — hd8 Mac adb only
- `STAYTURGID_NO_LOCAL_ADB=1` — presence / Handsets / shell helpers
