# FIRERPA — Install Map: What Goes Where, Required vs Optional, Duplicative Functions

**Date:** 2026-07-12
**Context:** stayturgid fleet (Mac + s24 + p7a + hd8), all unrooted, Shizuku + Termux + Tailscale.

---

## 1. What Gets Installed Where

```
┌─────────────────────────────────────────────────────────────────────┐
│ MAC (Control Node)                                                  │
│                                                                     │
│  REQUIRED:                                                          │
│    lamda-client-py-10.0.tar.gz  ── pip install (63 KB + deps)      │
│    ├─ lamda.client.Device       ── gRPC client to talk to servers   │
│    ├─ lamda.const               ── 30 Android permission constants   │
│    └─ lamda.rpc.*               ── 14 proto service definitions      │
│                                                                     │
│  NOT ON MAC:                                                        │
│    firerpa.apk                 ── Android-only APK                  │
│    lamda-server-*.tar.gz       ── Android-only native server         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ s24 + p7a (arm64 Android 16)                                        │
│                                                                     │
│  ONE OF THESE (server runtime):                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ PATH A: firerpa.apk (8 MB) — GUI installer                  │   │
│  │   Install via Obtainium or adb install                       │   │
│  │   Opens app → Shizuku authorizes → downloads + extracts      │   │
│  │   auto server tarball → one-click Start                     │   │
│  │   Handles: TLS certs, auto-boot, server lifecycle            │   │
│  │                                                              │   │
│  │ PATH B: lamda-server-arm64-v8a.tar.gz (163 MB) — manual     │   │
│  │   tar xzf → /data/local/tmp/firerpa/server/                 │   │
│  │   Write properties.local (port, adb, sshd, cron)             │   │
│  │   nohup server/bin/launch.sh --port=65000 &                  │   │
│  │   Handled by: Ansible role or start-adb.sh boot integration  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  The server IS (163 MB extracted):                                   │
│    server/bin/python3.9           ── embedded Python 3.9 (ELF arm64) │
│    server/bin/launch.sh           ── entry: python3.9 -m lamda      │
│    server/bin/python3.9 -m lamda  ── starts all services below      │
│    server/bin/sshd                ── built-in SSH server            │
│    server/bin/frida-server        ── bundled Frida                  │
│    server/lib/ffmpeg.so           ── H.264/MJPEG encoding           │
│    server/lib/.../lamda/services/ ── 14 native .so service modules  │
│    server/lib/python3.9/...       ── 7975 Python .pyc files          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ hd8 (armv7a Fire OS 11)                                             │
│                                                                     │
│  Same as s24/p7a but uses:                                          │
│    lamda-server-armeabi-v7a.tar.gz (135 MB) — 32-bit ARM           │
│    firerpa.apk — same APK, auto-detects arch                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Required vs Optional

### Critical install note — SELinux context

The server files MUST be extracted with the correct SELinux context. Two methods work:

| Method                     | Context                              | Works on                                | Start via                                                          |
| -------------------------- | ------------------------------------ | --------------------------------------- | ------------------------------------------------------------------ |
| `run-as com.termux cat ... | tar xz`                              | Termux app (`u:object_r:app_data_file`) | `adb shell` (only way — shell UID has broader context permissions) |
| `adb push ... && tar xzf`  | shell (`u:object_r:shell_data_file`) | ADB directly                            | `adb shell`                                                        |

**Do NOT `chmod -R 755`** after extraction — this breaks execute permissions for security-sensitive files. The tarball preserves correct permissions.

**hd8 (Fire OS) is blocked for always-on:** The Termux SSH user lacks SELinux execute permission for shell-context binaries. Only ADB USB can start the server. The server works fine when started via USB (11 processes, gRPC + WebUI OK, UIAutomator fails as expected on Fire OS). Since hd8 is a tablet without always-on USB, FIRERPA is not viable as an always-on failsafe there. It CAN be started on-demand when USB is connected.

**Stale PID issue:** On restart, `pkill -9 lamda` may miss processes (different ADB session groups). Always run `rm -rf /data/local/tmp/usr/` before restarting to clear lamda.pid and lamda.db files.

### 🔴 Required — can't operate without

| Component                                   | Why                                                                                                                                                                                 |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **lamda-server-\*.tar.gz** (server runtime) | The actual FIRERPA daemon. Contains Python 3.9, 14 service modules, ffmpeg, Frida, SSH, ADB, WebUI. Nothing works without it.                                                       |
| **lamda-client-py-10.0.tar.gz** (Mac only)  | To call the server API programmatically from Ansible, health monitors, or self-heal scripts. You _could_ use only the WebUI in a browser, but programmatic access needs the client. |

### 🟡 Optional — choose one path

| Component                       | Why optional                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **firerpa.apk** (GUI installer) | You need the server runtime. The APK is one way to install it. The manual `tar xzf` + launch.sh is another. They're mutually exclusive — you only need ONE install path. The APK adds: GUI buttons, Shizuku auth handling, auto-boot via Android app, auto-updates. The manual path adds: Ansible idempotency, Git-tracked config, boot loop integration. |

### 🟢 Deploy-only — needed for install, not runtime

| Component                 | Why                                                                                          |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| **firerpa.apk** (if used) | Installed once, needed to download + start server. After that the server runs independently. |

---

## 3. Duplicative Functions — You Only Need One

Every service FIRERPA provides has an existing stayturgid equivalent. Choose per device based on which layer you trust most for each function.

### Connectivity — pick your remote access channel

| Function           | stayturgid            | FIRERPA                   | Recommendation                                                                                                                                                           |
| ------------------ | --------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **SSH to device**  | Termux sshd on :8022  | FIRERPA sshd on :65000    | **Primary: Termux** (battle-tested, self-healed, CA-signed). FIRERPA SSH is the backup — enable it so you can still get in when Termux is down.                          |
| **ADB to device**  | Shizuku adbd on :5555 | FIRERPA adbd on :65000    | **Primary: Shizuku** (TCP mode, `ensure_wireless_debugging()` self-heals). FIRERPA ADB is the backup — no Developer Options needed, survives Shizuku crashes.            |
| **Remote desktop** | scrcpy via Mac ↔ SSH  | FIRERPA WebRTC in browser | **Primary: scrcpy** (lower latency, harder to set up on Fire). FIRERPA WebRTC is the backup — browser-based, no client install, works on hd8's Silk browser, multi-user. |

### Automation — pick your automation engine

| Function           | stayturgid                                                    | FIRERPA                                                      | Recommendation                                                                                                                                                                        |
| ------------------ | ------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **UI automation**  | AutoJs6 (JS, a11y-based) + `adb shell input`                  | FIRERPA gRPC API (Python, selector + coordinate)             | **Primary: AutoJs6** (watchdog loops, notifications, fleet-profile). FIRERPA is the backup for when AutoJs6 is dead, or for advanced operations (virtual displays, OCR, multi-touch). |
| **Self-heal loop** | `start-adb.sh` → `stayturgid_repair.py` (5-min cycle, Termux) | FIRERPA cron → self-heal script (5-min cycle, server daemon) | **Primary: stayturgid repair** (570+ lines, fleet-specific fixes). FIRERPA self-heal is the backup — repairs stayturgid when Termux itself is broken. They monitor each other.        |
| **App management** | Ansible + `adb shell pm/am`                                   | FIRERPA `ApplicationStub` (gRPC)                             | Either is fine. FIRERPA is more granular (permissions, silent grant, launch non-exported activities). stayturgid is fleet-integrated.                                                 |

### Monitoring — pick your health check

| Function          | stayturgid                                         | FIRERPA                                                      | Recommendation                                                                                                                                             |
| ----------------- | -------------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Device health** | `fleet_health_monitor.py` (Mac launchd, SSH-based) | FIRERPA `StatusStub` (CPU/mem/disk/battery/net I/O via gRPC) | **Both.** stayturgid for fleet-wide aggregation + notifications. FIRERPA for richer per-device metrics. Feed FIRERPA metrics into stayturgid's health log. |
| **Screen leases** | DSCL cross-device leases                           | FIRERPA API exclusive lock (`with d:`)                       | **Primary: stayturgid DSCL** (cross-device awareness). FIRERPA lock is simpler but single-device only.                                                     |

### AI / MCP — pick your agent platform

| Function       | stayturgid                                         | FIRERPA                                                    | Recommendation                                                                                                                                                        |
| -------------- | -------------------------------------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AI agent**   | Hermes (Telegram gateway, OpenCode API, Mac-based) | FIRERPA MCP server (on-device, 20+ tools, `agent` command) | **Complementary.** Hermes for fleet orchestration + user interaction. FIRERPA MCP for direct device control. Hermes can call FIRERPA MCP tools for on-device actions. |
| **MCP server** | Hermes MCP (if configured)                         | FIRERPA `/mcp/` endpoint (streamable-http)                 | **FIRERPA is better for device MCP.** Hermes is better for fleet MCP. Bridge them: Hermes → FIRERPA MCP for device ops.                                               |

### Services that DON'T overlap — use both

| Function                     | stayturgid                                                                 | FIRERPA                                                       |
| ---------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Fleet inventory + deploy** | Ansible playbooks, hosts.yml, group_vars                                   | ❌ No fleet layer                                             |
| **Tailscale mesh**           | always-on VPN, Tailscale IPs in inventory                                  | ❌ No Tailscale integration (has frp/OpenVPN as alternatives) |
| **Fire OS quirks**           | Fire-specific boot scripts, `STAYTURGID_NO_LOCAL_ADB`, `fire_help_monitor` | ❌ No Fire-specific code                                      |
| **Obtainium catalog**        | APK catalog management with version tracking                               | ❌ No app catalog (has its own APK distro)                    |
| **Mac control node**         | launchd agents, VLM, screen inversion                                      | ❌ Android-only                                               |
| **Virtual displays**         | ❌ Not available                                                           | ✅ Isolated background displays, full API parity              |
| **OCR / image matching**     | ❌ Not available (VLM alternative)                                         | ✅ On-device SIFT + PaddleOCR/EasyOCR                         |
| **Multi-touch**              | ❌ Basic adb input only                                                    | ✅ Record, replay, programmatic, pressure                     |
| **MITM capture**             | ❌ Not available                                                           | ✅ One-click system CA, per-package, live editing             |
| **Frida hooks**              | ❌ Not available                                                           | ✅ Bundled, persistent scripts, RPC                           |
| **Persistent KV store**      | ❌ File-based configs only                                                 | ✅ `d.set()/get()` with TTL, Fernet encryption                |
| **Proxy/VPN**                | ❌ Tailscale only                                                          | ✅ HTTP/SOCKS5/Shadowsocks, OpenVPN, frp, tunnel2             |

---

## 4. Minimal Install (Just the Redundant Failsafe)

If you only want FIRERPA as a **backup remote-access channel** (no automation, no MCP, no Frida):

| Device        | Install                                   | Configure                                                                   |
| ------------- | ----------------------------------------- | --------------------------------------------------------------------------- |
| **s24 + p7a** | `tar xzf lamda-server-arm64-v8a.tar.gz`   | `port=65000`, `adb.enable=true`, `adb.privileged=false`, `sshd.enable=true` |
| **hd8**       | `tar xzf lamda-server-armeabi-v7a.tar.gz` | Same config                                                                 |
| **Mac**       | `pip install lamda-client-py-10.0.tar.gz` | Used by health monitor to check liveness                                    |

**Minimal properties.local:**

```ini
port=65000
[sshd]
sshd.enable=true
[adb]
adb.enable=true
adb.privileged=false
```

This gives you: SSH backup on :65000, ADB backup on :65000, remote desktop via browser — all without the APK, without Shizuku interaction, and without conflicting with existing stayturgid services.

---

## 5. Full Install (All Feature Overlap Disabled)

If you want everything FIRERPA offers but disable what stayturgid already does:

```ini
port=65000

[sshd]
sshd.enable=true           # Backup SSH — keep enabled

[adb]
adb.enable=true            # Backup ADB — keep enabled
adb.privileged=false       # Shell mode on non-root

[webui]
webui.darkmode = on
webui.webrtc = on          # Backup remote desktop

[cron]
cron.enable=true           # Self-heal trigger

[fwd]                      # frp — optional, Tailscale works fine
fwd.enable=false

[mdns]
mdns.enable=false          # Tailscale handles discovery

[tunnel2]
tunnel2.enable=false       # Keep Tailscale as primary VPN
```

The services stayturgid already provides (primary SSH, ADB, VPN, health monitoring) are left to stayturgid. FIRERPA runs alongside as the backup for when any of those fail.
