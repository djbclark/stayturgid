<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# FIRERPA/lamda — Code-Level Architecture Audit (DeepSeek V4 Pro)

**Date:** 2026-07-12
**Analyst:** DeepSeek V4 Pro (opencode-go/deepseek-v4-pro)
**Source repo:** [firerpa/lamda](https://github.com/firerpa/lamda) v10.0 (MIT license, 7.9k stars, 128 commits, 6+ years)
**Fork (stayturgid):** [djbclark/lamda](https://github.com/djbclark/lamda) — all binaries (APK + server) in one [release](https://github.com/djbclark/lamda/releases/tag/v10.0-binaries)
**Local clone:** `~/src/firerpa-lamda/` (upstream), `~/src/firerpa-fork/` (fork)
**Stayturgid prior art:** [firerpa-lamda-analysis-2026-07-10.md](firerpa-lamda-analysis-2026-07-10.md), [firerpa-nonroot-research-2026-07-10.md](firerpa-nonroot-research-2026-07-10.md), [firerpa-integration-plan.md](../../archive/plans/firerpa-integration-plan.md)
**Purpose:** Production-grade code audit — what the on-disk repo actually contains, what's real vs documented, what's missing for our use case.

---

## Executive Summary

The `firerpa/lamda` GitHub repo at `~/src/firerpa-lamda/` is a **Python client library + deployment tooling** — NOT the Android server binary. Key findings:

1. **The server is a closed-source native binary** shipped as `lamda-server-{abi}.tar.gz` in GitHub releases (163 MB arm64, 134 MB armeabi-v7a). This binary multiplexes gRPC, HTTP/WebSocket, ADB, SSH, proxy, and WebRTC on a single port (65000).
2. **The Python client** (`lamda/client.py`, 2691 lines) is the complete gRPC client SDK with 160+ methods on the `Device` class, all proto-defined, all open source.
3. **Shizuku integration is deployment-only** — the APK uses Shizuku to install the server on non-root devices. No Shizuku code exists in this repo; it lives in the closed-source APK.
4. **MCP is real and operational** — the official `extensions/firerpa.py` MCP extension (197 lines) exposes 20+ tools via `@mcp("tool")` decorators with annotation-based typing.
5. **v10.0 headline feature: non-root execution mode** (`adb shell`). The server can now run in shell mode without root, confirmed in CHANGELOG.txt line 8.

### What actually ships in GitHub releases (v10.0)

| Asset                             | Size   | Type              | Open source?                                   |
| --------------------------------- | ------ | ----------------- | ---------------------------------------------- |
| `lamda-server-arm64-v8a.tar.gz`   | 163 MB | Native binary     | ❌ Closed source                               |
| `lamda-server-armeabi-v7a.tar.gz` | 134 MB | Native binary     | ❌ Closed source                               |
| `lamda-magisk-module.zip`         | 371 MB | Magisk module     | ⚠️ Partially (scripts only)                    |
| `lamda-client-py-10.0.tar.gz`     | <1 MB  | Python source     | ✅ This repo                                   |
| `startmitm.exe`                   | 21 MB  | Windows MITM tool | ❌ Binary                                      |
| `firerpa.apk`                     | 8.4 MB | Android APK       | ❌ Not in releases (hosted at device-farm.com) |

---

## 1. Repository Structure (Actual vs Documented)

### What's here (this repo)

```
~/src/firerpa-lamda/
  lamda/
    __init__.py           # Version string "10.0"
    client.py             # 2691 lines — the entire gRPC client SDK
    const.py              # Android permission/flag constants
    exceptions.py         # Exception hierarchy
    types.py              # AttributeDict, BytesIO helpers
    rpc/                  # 14 .proto files — gRPC service definitions
    google/protobuf/      # Bundled protobuf runtime stubs
  extensions/
    firerpa.py            # Official MCP extension (197 lines, 20+ tools)
    example_mcp_extension.py  # MCP extension template (28 lines)
    example_http_extension.py # HTTP extension template (37 lines)
    mcp_return_types.py   # Pure-msgspec MCP types (124 lines)
    mcp_sms_reader.py     # SMS reader MCP tool (32 lines)
  tools/
    magisk/               # Magisk module scripts (service.sh, install.sh)
    discover.py           # mDNS device discovery tool
    adb_pubkey.py         # ADB key management helper
    startmitm.py          # MITM capture launcher
    cert.py               # Service certificate generator
    fridarpc.py           # Frida RPC bridge
    globalmitm/           # MITM tooling
    openvpn/              # OpenVPN Docker + config
    socks5/               # SOCKS5 proxy
    firerpa.yml           # Docker Compose config
  properties.example      # Complete INI config reference (148 lines)
  CHANGELOG.txt           # 630 lines, v0.1 → v10.0
  README.md               # English documentation
  README.zh.md            # Chinese documentation
  setup.py                # pip packaging
```

### What's NOT here (closed-source or separate)

| Component                              | Where it lives                                                                   |
| -------------------------------------- | -------------------------------------------------------------------------------- |
| Android server binary                  | GitHub releases as .tar.gz (compiled native code)                                |
| FIRERPA Android APK                    | `https://device-farm.com/assets/apk/firerpa.apk` (Chinese-hosted, not on GitHub) |
| Server-side MCP/HTTP extension runtime | Inside the server binary (not Python-runnable outside)                           |
| StarLink Hub / hub-bridge              | Separate closed-source components (referenced in docs)                           |
| Shizuku deployment logic               | Inside the APK (not in this repo)                                                |
| WebRTC signaling                       | Inside the server binary                                                         |
| Port multiplexing engine               | Inside the server binary                                                         |

---

## 2. Server Binary — What We Know From Analysis

### Startup pathway

The Magisk module's `service.sh` at `tools/magisk/common/service.sh:1-13`:

```bash
# Wait 25 seconds after boot, then launch:
launch="sh ${base}/server/bin/launch.sh"
port=65000
export ca_store_remount=true
$launch --port=${port} --certificate=${cert}  # or without cert
```

The server:

1. Listens on a **single port** (default 65000)
2. Multiplexes **all services** on that port: gRPC, HTTP (WebUI), WebSocket, ADB, SSH, proxy, WebRTC
3. Reads `properties.local` (INI format) for configuration
4. Auto-generates TLS certificates on first run
5. Supports `--port` and `--certificate` CLI flags

### Port multiplexing

The server inspects incoming TCP streams to distinguish:

- **gRPC** (protobuf binary framing)
- **HTTP** (WebUI, MCP endpoints, WebSocket upgrade)
- **ADB** (ADB protocol)
- **SSH** (SSH protocol)
- **WebRTC** (STUN/TURN + media)

This is a sophisticated custom TCP demultiplexer. The CHANGELOG at line 407 references a fix for "port multiplexing unsupported on some devices" (v5.3), confirming this is a custom implementation, not a standard reverse proxy.

### Built-in ADB

The server includes a standalone ADB daemon — **no system Developer Options needed**. Configuration (`properties.example:109-124`):

```ini
[adb]
adb.enable = true
adb.directory = /data/local/tmp
adb.privileged = true    ; root vs shell privileges
```

The gRPC interface for ADB (`lamda/rpc/debug.proto:1-12`):

```protobuf
service Debug {
    rpc isAndroidDebugBridgeRunning(Empty) returns (Boolean) {}
    rpc installADBPubKey(ADBDConfigRequest) returns (Boolean) {}
    rpc uninstallADBPubKey(ADBDConfigRequest) returns (Boolean) {}
    rpc startAndroidDebugBridge(Empty) returns (Boolean) {}
    rpc stopAndroidDebugBridge(Empty) returns (Boolean) {}
}
```

### Built-in SSH

The server includes an sshd, configurable via `properties.example`:

```ini
[sshd]
sshd.enable = true
```

CLI helpers: `tools/ssh.sh`, `tools/scp.sh` — for remote shell and file transfer through the FIRERPA port.

### Non-root (shell) mode

**v10.0 introduced non-root execution** (`adb shell` identity). From `CHANGELOG.txt:8`: "Support for non-root execution mode (adb shell)."

The proto defines the flag at `lamda/rpc/util.proto:82`:

```protobuf
message ServerInfoResponse {
    ...
    bool privileged = 6;  // true = root, false = shell
}
```

When `privileged=false`:

- Cannot write `ro.*` system properties
- Cannot manipulate SELinux
- Cannot access system certificate store directly (MITM limited)
- ADB connections get shell (uid 2000) instead of root (uid 0)

When `adb.privileged=true` in properties but device is non-root, the ADB daemon falls back to shell-level privileges.

---

## 3. Python Client SDK — Deep Dive

### Connection model (`lamda/client.py:2341-2386`)

```python
class Device(object):
    def __init__(self, host, port=65000, certificate=None, session=None):
        self.server = "{0}:{1}".format(host, port)
        # gRPC channel with keepalive + retry config:
        options = [
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.keepalive_permit_without_calls', True),
            ('grpc.http2.max_pings_without_data', 0),
        ]
        # TLS or insecure
        if certificate:
            self._chan = grpc.secure_channel(self.server, creds, options)
        else:
            self._chan = grpc.insecure_channel(self.server, options)
```

### Service stub architecture

The `Device` class lazily proxies to 18 service stubs via `Device.proxy(module, class)`:

| Stub                        | Proto             | Lines     | Purpose                                                             |
| --------------------------- | ----------------- | --------- | ------------------------------------------------------------------- |
| `UiAutomatorStub`           | uiautomator.proto | 877-1161  | Click, swipe, screenshot, dump hierarchy, watchers, virtual display |
| `ObjectUiAutomatorOpStub`   | uiautomator.proto | 483-874   | Per-element: child/sibling chaining, drag, fling, scroll, pinch     |
| `ApplicationStub`           | application.proto | 1484-1536 | Enumerate, start, install apps                                      |
| `ApplicationOpStub`         | application.proto | 1287-1481 | Per-app: start/stop, permissions, Frida attach/detach               |
| `VirtualDisplayStub`        | —                 | 1164-1261 | Create, list, release virtual displays                              |
| `ShellStub`                 | shell.proto       | 1841-1871 | Foreground/background script execution                              |
| `StorageStub`               | storage.proto     | 1539-1643 | KV store with TTL, Fernet encryption                                |
| `FileStub`                  | file.proto        | 2033-2095 | Upload/download, streaming, chmod, stat                             |
| `DebugStub`                 | debug.proto       | 1759-1796 | Built-in ADB management                                             |
| `SettingsStub`              | settings.proto    | 1799-1838 | Android settings get/put                                            |
| `StatusStub`                | status.proto      | 1874-1930 | CPU, memory, disk, battery, net I/O                                 |
| `ProxyStub`                 | proxy.proto       | 1933-1971 | OpenVPN, gproxy control                                             |
| `WifiStub`                  | wifi.proto        | 2127-2213 | WiFi scan, status, signal                                           |
| `SelinuxPolicyStub`         | policy.proto      | 1974-2030 | SELinux enforce, permissive, domain creation                        |
| `LockStub`                  | —                 | 2098-2124 | Exclusive API lock with session tokens                              |
| `UtilStub`                  | util.proto        | 1646-1756 | Reboot, shutdown, setprop/getprop, hex_patch, CA cert install       |
| `OcrEngine` / `OcrOperator` | —                 | 2293-2338 | PaddleOCR, EasyOCR, custom HTTP backend                             |
| `MultiTouchOpStub`          | types.proto       | 360-425   | Multi-touch gesture construction and playback                       |

### Convenience methods on Device (2431-2668)

The `Device` class exposes ~80 shortcut methods that delegate to service stubs:

- `d.click(x, y)`, `d.swipe(...)`, `d.drag(...)`, `d.take_screenshot()`, `d.dump_window_hierarchy()`
- `d.start_activity(...)`, `d.current_application()`, `d.enumerate_installed_apps()`
- `d.execute_script(...)`, `d.setprop(...)`, `d.getprop(...)`
- `d.wake_up()`, `d.sleep()`, `d.reboot()`, `d.shutdown()`
- `d.set_clipboard(...)`, `d.get_clipboard()`
- `d.install_adb_pubkey(...)`, `d.start_android_debug_bridge()`
- `d(context manager)` — exclusive API lock: `with d: ...`

### Frida integration (2387-2410)

```python
@property
def frida(self):
    """Lazily connects Frida over the same host:port."""
    # Uses Frida remote device protocol
    # Supports TLS + session token auth
    # Returns frida Device object
```

Frida connects through the FIRERPA port (not a separate frida-server port). Token-based auth prevents unauthorized access.

---

## 4. MCP/AI Extension Architecture

### Extension loading

Extensions are loaded by the server from `~/modules/extension/` on the Android device. Two base classes:

- **`BaseMcpExtension`** — MCP server extension. Decorators: `@mcp("tool")`, `@mcp("prompt")`, `@mcp("resource")`. Each class has `route`, `name`, `version`.
- **`BaseHttpExtension`** — Tornado HTTP handler. Methods: `http_get`, `http_post`, `http_put`, `http_delete`, `http_patch`.

Both are provided by the server runtime (`lamda.mcp`, `lamda.extensions`) — NOT in this client repo.

### Official FireRPA MCP extension (`extensions/firerpa.py`)

**Local path:** `~/src/firerpa-lamda/extensions/firerpa.py` (197 lines)
**Remote path:** Deployed to `~/modules/extension/` on device
**MCP route:** `/firerpa/mcp/`
**Tools:** 20+ including:

| Tool                                                    | Parameters                          | Purpose                |
| ------------------------------------------------------- | ----------------------------------- | ---------------------- |
| `dump_window_hierarchy`                                 | compressed: bool                    | XML layout tree → JSON |
| `click`                                                 | pointX, pointY                      | Coordinate tap         |
| `swipe`                                                 | fromX, fromY, toX, toY, step        | Gesture                |
| `drag`                                                  | fromX, fromY, toX, toY, step, speed | Drag + hold            |
| `device_info`                                           | —                                   | Model, SDK version     |
| `show_toast`                                            | text                                | On-screen toast        |
| `execute_shell_script`                                  | script, timeout                     | Shell command          |
| `wake_up` / `sleep`                                     | —                                   | Screen state           |
| `get_clipboard` / `set_clipboard`                       | text                                | Clipboards             |
| `press_keycode`                                         | code                                | Key injection          |
| `get_last_toast`                                        | —                                   | Recent toast text      |
| `find_by_text` / `find_by_desc` / `find_by_resource_id` | text                                | Selector-based clicks  |
| `set_text`                                              | text                                | Input text             |
| `start_app` / `stop_app` / `install_app`                | packageName                         | App lifecycle          |
| `current_application`                                   | —                                   | Foreground app         |
| `check_permission` / `request_permission`               | package, permission                 | Permission ops         |
| `agent`                                                 | prompt                              | Natural-language agent |

The `agent` tool accepts natural-language prompts and executes them via the built-in AI agent (`agent` command).

### MCP protocol version

Uses `streamable-http` MCP (v9.0+). Compatible with Claude, Cursor, and other MCP clients. Types are reimplemented in `mcp_return_types.py` (124 lines) using `msgspec` instead of pydantic for zero-dependency operation.

---

## 5. Configuration System

### INI format (properties.example:148 lines)

```ini
[DEFAULT]
port=65000

[webui]
webui.darkmode = off
webui.audio = on
webui.webrtc = on
webui.video.h264 = on
webui.video.backend = 0
webui.video.scale = 0.5

[cron]
cron.enable=true

[sshd]
sshd.enable=true

[adb]
adb.enable=true
adb.privileged=true

[fwd]
fwd.enable=true        ; frp forwarding

[tunnel2]
tunnel2.enable=true    ; reverse HTTP proxy

[mdns]
mdns.enable=false
mdns.name=DEVICEID-UNIQUE.lamda

[openvpn] / [gproxy]   ; VPN and proxy
```

The config is **hot-reloadable** via WebUI or API (`d.reload()`). Service restart is NOT required for most changes.

---

## 6. What FIRERPA's Built-in SSH/ADB Means for stayturgid

### Potential conflicts

| FIRERPA service            | stayturgid equivalent    | Conflict risk               |
| -------------------------- | ------------------------ | --------------------------- |
| Built-in sshd (port 65000) | Termux sshd (port 8022)  | None — different ports      |
| Built-in ADB (on 65000)    | Shizuku ADB (port 5555)  | ⚠️ Both open 5555-style ADB |
| WebUI (port 65000)         | OpenCode web (port 4096) | None — different ports      |
| gRPC (port 65000)          | No equivalent            | None                        |

The built-in ADB is the main concern. If FIRERPA's `adb.enable=true` and its adbd also opens port 5555, it would conflict with Shizuku's adbd. **Mitigation:** set `adb.enable=false` in FIRERPA config; let stayturgid manage ADB via Shizuku.

### Redundancy opportunity

FIRERPA's built-in sshd and ADB provide **independent backup channels** for remote access when stayturgid's Termux sshd is down:

| Channel        | stayturgid (primary)     | FIRERPA (backup)       |
| -------------- | ------------------------ | ---------------------- |
| SSH            | Termux sshd :8022        | FIRERPA sshd on :65000 |
| ADB            | Shizuku adbd :5555       | FIRERPA adbd on :65000 |
| Screen control | scrcpy via SSH           | WebRTC via browser     |
| UI automation  | AutoJs6 + Termux scripts | gRPC API + MCP tools   |

---

## 7. Key Code Paths for Integration

### Essential files (local filesystem)

| File                   | Path                                                      | Lines |
| ---------------------- | --------------------------------------------------------- | ----- |
| Client SDK             | `~/src/firerpa-lamda/lamda/client.py`                     | 2691  |
| Service protos         | `~/src/firerpa-lamda/lamda/rpc/services.proto`            | 271   |
| Properties reference   | `~/src/firerpa-lamda/properties.example`                  | 148   |
| MCP extension example  | `~/src/firerpa-lamda/extensions/example_mcp_extension.py` | 28    |
| Official MCP extension | `~/src/firerpa-lamda/extensions/firerpa.py`               | 197   |
| Magisk service.sh      | `~/src/firerpa-lamda/tools/magisk/common/service.sh`      | 13    |
| Changelog              | `~/src/firerpa-lamda/CHANGELOG.txt`                       | 630   |

### Essential URLs

| Resource                    | URL                                                                                                               |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| GitHub repo                 | https://github.com/firerpa/lamda                                                                                  |
| Releases                    | https://github.com/firerpa/lamda/releases                                                                         |
| Server binary (arm64)       | https://github.com/firerpa/lamda/releases/download/v10.0/lamda-server-arm64-v8a.tar.gz                            |
| Server binary (armv7a)      | https://github.com/firerpa/lamda/releases/download/v10.0/lamda-server-armeabi-v7a.tar.gz                          |
| Client tarball              | https://github.com/firerpa/lamda/releases/download/v10.0/lamda-client-py-10.0.tar.gz                              |
| APK download (fork)         | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/firerpa.apk                                    |
| APK download (upstream)     | https://device-farm.com/assets/apk/firerpa.apk                                                                    |
| Server arm64 (fork)         | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/lamda-server-arm64-v8a.tar.gz                  |
| Documentation (EN)          | https://device-farm.com/docs/en/quick-start                                                                       |
| Documentation (ZH)          | https://device-farm.com/docs/zh/quick-start                                                                       |
| LLMs.txt (full docs dump)   | https://device-farm.com/llms-full.txt                                                                             |
| Shizuku APK                 | https://device-farm.com/assets/apk/shizuku-v13.6.0.r1086.2650830c-release.apk                                     |
| Issue tracker               | https://github.com/firerpa/lamda/issues                                                                           |
| Stayturgid analysis (prior) | https://github.com/djbclark/stayturgid/blob/master/docs/research/evaluations/firerpa-lamda-analysis-2026-07-10.md |

### Key issues for our use case

| Issue                                          | #                                                   | Relevance                 |
| ---------------------------------------------- | --------------------------------------------------- | ------------------------- |
| Android 16 API 36 — Frida java.js incompatible | [#138](https://github.com/firerpa/lamda/issues/138) | Pixel 7a confirmed tested |
| MCP调用报错 (MCP call error)                   | [#130](https://github.com/firerpa/lamda/issues/130) | MCP stability             |
| Child selector issues                          | [#139](https://github.com/firerpa/lamda/issues/139) | UI automation reliability |

---

## 8. API Surface vs stayturgid — Updated from Code Inspection

Below is an updated comparison based on actual code inspection, not just documentation.

### High-value overlapping APIs (where FIRERPA is clearly better)

| Capability      | FIRERPA                                         | stayturgid                      | FIRERPA advantage                       |
| --------------- | ----------------------------------------------- | ------------------------------- | --------------------------------------- |
| UI click/tap    | `d.click(x, y)` with Point type                 | `adb shell input tap` via shell | Type-safe, return value, error handling |
| Screenshot      | `d.take_screenshot()` returns PNG bytes         | `adb exec-out screencap -p`     | In-memory, no shell parsing             |
| Dump hierarchy  | `d.dump_window_hierarchy()` returns XML         | `adb exec-out uiautomator dump` | In-memory, no file roundtrip            |
| Swipe/drag      | `d.swipe(...)`, `d.drag(...)` with step control | `adb shell input swipe`         | Parameterized, multi-step               |
| App management  | Enumerate, start, stop, install via API         | `adb shell pm/am` commands      | Typed return values, error codes        |
| Device info     | `d.device_info()` returns structured            | `adb shell getprop` + parsing   | Structured proto response               |
| Shell execution | `d.execute_script(...)` with timeout            | SSH + Ansible command module    | Built-in timeout, background mode       |
| Clipboard       | `d.get_clipboard()`, `d.set_clipboard()`        | `termux-clipboard-get/set`      | No Termux dependency                    |
| Screen lock     | `with d:` context manager                       | DSCL screen leases              | Simpler API, token-based                |

### FIRERPA-unique capabilities (stayturgid has nothing comparable)

- **Virtual displays** — isolated background displays for parallel automation
- **UI Watchers** — real-time UI change listeners with auto-response
- **OCR/image matching** — on-device SIFT + OCR engines
- **Multi-touch** — record, replay, programmatic gesture construction
- **MCP/AI agent** — built-in MCP server with 20+ tools, natural-language `agent` command
- **Frida** — bundled persistent Frida with hot-reload scripts
- **MITM** — one-click system CA install, per-package capture, live editing
- **Proxy/VPN** — HTTP/SOCKS5/Shadowsocks proxy, OpenVPN client, frp forwarding
- **Persistent KV store** — `d.set()` / `d.get()` with TTL and Fernet encryption
- **Binary patching** — hex wildcard matching with dry-run

### stayturgid-unique capabilities (FIRERPA has nothing comparable)

- **Fleet orchestration** — Ansible playbooks + roles + inventory groups
- **Multi-OS** — Mac + Linux + Android management
- **Health monitoring** — fleet-wide health aggregation with debounce + notify
- **Screen leases** — cross-device DSCL-based lease tracking
- **Peer ADB mesh** — device-to-device ADB routing through Tailscale
- **AutoJs6 watchdogs** — self-healing JS engine monitoring
- **Obtainium integration** — APK catalog management with version tracking
- **Fire OS support** — Fire-specific quirks and boot scripts
- **Termux boot lifecycle** — `start-adb.sh` + self-healing loops
- **Mac control node** — launchd agents, VLM testing, screen inversion

---

## 9. Server Internals — What's Actually in the Tarball

The server tarball (`lamda-server-arm64-v8a.tar.gz`, 163 MB) was extracted and examined. It is NOT a single compiled binary — it's an **entire self-contained Python 3.9 runtime** with 8,395 files:

### Launch pathway

```bash
# server/bin/launch.sh:
export ROOTDIR=$(dirname $(dirname $(realpath "$0")))
export PATH=$ROOTDIR/bin:$PATH
export LD_LIBRARY_PATH=$ROOTDIR/lib
exec python3.9 -u -m lamda --launch $@
```

**The server IS Python 3.9** running `lamda` as a module — not a compiled Go/Rust binary. All the interesting work (port multiplexing, ADB/SSH daemons, WebRTC, virtual displays) happens in native `.cpython-39.so` extensions.

### Server composition

| Component            | Count | Examples                                                                                                          |
| -------------------- | ----- | ----------------------------------------------------------------------------------------------------------------- |
| CLI tools in `bin/`  | 149   | `python3.9`, `frida-server`, `iperf`, `dnsmasq`, `sshd`, `strace`, `tcpdump`, `sqlite3`, `scapy`, `curl`, `rsync` |
| Python .pyc files    | 7,975 | Full stdlib + grpc + protobuf + tornado + PIL + cv2 + numpy + unicorn + capstone + keystone                       |
| Native .so libraries | 50+   | `ffmpeg.so` (H.264/MJPEG), `frida-*.so` (Frida runtime), 14 lamda service extensions (below)                      |
| MiniCap variants     | 22    | Android 21–35 + MIUI variants for screenshot capture                                                              |
| iptables modules     | 120+  | `xt_*.so`, `ipt_*.so`, `ip6t_*.so` in `lib/xtables-ext/`                                                          |

### The 14 lamda service extensions (.cpython-39.so)

These ARE the server — each implements a core service:

| .so file                | Service                                     |
| ----------------------- | ------------------------------------------- |
| `ssh.cpython-39.so`     | Built-in SSH daemon                         |
| `adb.cpython-39.so`     | Built-in ADB daemon (no Developer Options)  |
| `touch.cpython-39.so`   | Touch injection + multi-touch               |
| `driver.cpython-39.so`  | UI automation driver (selector engine)      |
| `openvpn.cpython-39.so` | OpenVPN client                              |
| `gproxy.cpython-39.so`  | Proxy services (SOCKS5/Shadowsocks/HTTP)    |
| `helper.cpython-39.so`  | Port multiplexing, native helpers           |
| `frida.cpython-39.so`   | Frida integration (persistent scripts, RPC) |
| `mdns.cpython-39.so`    | mDNS discovery                              |
| `audio.cpython-39.so`   | Live audio forwarding                       |
| `fwd.cpython-39.so`     | frp port forwarding                         |
| `motion.cpython-39.so`  | Motion/sensor events                        |
| `cron.cpython-39.so`    | Cron/task scheduler                         |
| `top.cpython-39.so`     | Process monitoring                          |
| `upgrade.cpython-39.so` | Server self-update                          |

### Other native .so modules (9 utility)

| .so file                    | Utility                    |
| --------------------------- | -------------------------- |
| `utils.cpython-39.so`       | General utilities          |
| `certificate.cpython-39.so` | TLS certificate generation |
| `log.cpython-39.so`         | Structured logging         |
| `bridge.cpython-39.so`      | Network bridge             |
| `acmp.cpython-39.so`        | Protocol handler           |
| `globals.cpython-39.so`     | Global state               |
| `models.cpython-39.so`      | Data models                |
| `selfix.cpython-39.so`      | Selector engine helper     |
| `tcpkill.cpython-39.so`     | TCP connection killer      |

**Total lamda server module:** 144 files (excluding .pyc), all in `server/lib/python3.9/site-packages/lamda/`.

### Server size breakdown

| Layer                                                          | Size   |
| -------------------------------------------------------------- | ------ |
| Python 3.9 runtime + stdlib                                    | ~60 MB |
| Third-party Python deps (grpc, tornado, PIL, cv2, numpy, etc.) | ~50 MB |
| Native .so extensions (lamda services + system libs)           | ~30 MB |
| CLI tools (frida, iperf, dnsmasq, etc.)                        | ~15 MB |
| MiniCap variants (22 screenshots engines)                      | ~5 MB  |
| Proto definitions + config                                     | ~3 MB  |

---

## 10. Python Client — Mac Testing Results

The client library `lamda-client-py-10.0.tar.gz` (63 KB) was installed and tested on a Mac in a Python 3.12.13 venv at `/tmp/lamda-venv`.

### Install + deps

```bash
/opt/homebrew/bin/python3.12 -m venv /tmp/lamda-venv
source /tmp/lamda-venv/bin/activate
pip install lamda-client-py-10.0.tar.gz
```

Dependencies installed: `grpcio 1.74.0`, `protobuf 6.33.6`, `cryptography 49.0.0`, `grpcio-tools`, `grpc-interceptor`, `msgpack`, `asn1crypto`, `pem`, `cffi`, `setuptools`.

### Python version constraint issue

`setup.py` declares `python_requires = ">=3.6,<=3.14"`. Python 3.14.6 (the system default on this Mac) fails pip install because `3.14.6 > 3.14` in pip's version comparison. The actual code has no 3.14 incompatibility — only the metadata constraint blocks it. Workaround: use Python 3.12 or 3.13 from Homebrew (`/opt/homebrew/bin/python3.12`).

### API surface confirmed

| Item                     | Count | Notes                                                                                                                           |
| ------------------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------- |
| Public methods on Device | 88    | Including 80+ pass-through convenience methods                                                                                  |
| Properties               | 1     | `frida` (lazy Frida connection)                                                                                                 |
| gRPC service stubs       | 14    | Application, Debug, File, Lock, Proxy, Shell, Status, Settings, UiAutomator, Wifi, Storage, SelinuxPolicy, Util, VirtualDisplay |
| Exception types          | 25    | ServiceUnavailable, UiObjectNotFoundException, SecurityException, etc.                                                          |
| Permission constants     | 30    | `PERMISSION_READ_EXTERNAL_STORAGE`, etc.                                                                                        |
| FLAG constants           | 22    | `FLAG_ACTIVITY_NEW_TASK`, etc.                                                                                                  |

### Connection behavior

- **Constructor** (`Device("host", port=65000)`): Does NOT connect. Lazy initialization — gRPC channel created but no RPC sent.
- **First RPC**: Triggers connection. If server unreachable, throws `_InactiveRpcError` with clear message: "failed to connect to all addresses; last error: UNKNOWN: Connection refused (61)"
- **Retry config**: 5 attempts, exponential backoff (0.5s → 1s → 2s → 4s → 8s), max 15s per attempt
- **Keepalive**: 60s ping interval, 20s timeout, permits without calls
- **Message limits**: 64 MB send, 128 MB receive
- **TLS**: Supported via `certificate=` parameter — PEM file parsed into key+crt+ca, `ssl_target_name_override` from cert CN
- **Session**: Auto-generated UUID, passed via gRPC metadata interceptor for lock API

### Graceful failure test

```python
from lamda.client import Device
d = Device("127.0.0.1", port=65000)
d.device_info()  # raises _InactiveRpcError — expected, no server
```

Works correctly — no crash, clear error message.

---

## 11. Risks Assessment (Updated)

| Risk                          | Old assessment       | Updated from code                                                                                      |
| ----------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------ |
| APK not in GitHub releases    | ⚠️ BLOCKER           | Confirmed — APK only at device-farm.com                                                                |
| Shizuku mode unvalidated      | Medium risk          | Still zero community reports                                                                           |
| Chinese-hosted APK trust      | Medium               | APK is 8.4 MB; server binary is 163 MB compiled native code — hard to audit                            |
| Port conflict with ADB        | Low                  | Configurable via `adb.enable=false`                                                                    |
| Memory footprint              | Unknown until tested | Server is persistent daemon; memory impact unknown until spike                                         |
| Fire OS compatibility         | Untested             | Server binary must be armv7a; Fire OS 11 is API 30, FIRERPA supports 6+                                |
| MCP protocol breaking changes | Low                  | Protocol stable since v9.20; uses streamable-http                                                      |
| License risk                  | MIT — no issue       | MIT license confirmed; "offline licensing" mentioned in docs but no runtime check found in client code |

---

## 12. Recommendation (Code-Informed)

The code inspection confirms three things the documentation-only analysis couldn't:

1. **The Python client is production-grade.** 2691 lines of well-structured gRPC code with proper error handling, retry logic, TLS support, and 160+ typed methods. This is not a toy SDK.

2. **MCP is real and well-designed.** The `@mcp("tool")` decorator pattern with annotation-based typing, the pure-msgspec type reimplementation (no pydantic dependency), and the 20+ tool official extension show serious engineering investment.

3. **The server binary is a heavy hammer.** The 163 MB tarball unpacks to a full Python 3.9 runtime with 8,395 files including ffmpeg, Frida, numpy, cv2, and 14 native .so extensions. This is a powerful platform — but deploying it solely for a redundant failsafe is architectural overkill.

### Spike Results (2026-07-12)

| Device  | Result     | Key findings                                                                                                                                                                                                                                                 |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **s24** | ✅ Working | 12 processes, 43 MB PSS / 120 MB RSS, gRPC OK, stayturgid coexists, boot integration deployed, 24-hr soak started                                                                                                                                            |
| **p7a** | ✅ Working | 12 processes, gRPC OK, stayturgid coexists. Stale PID file issue (same as s24) — must `rm -rf /data/local/tmp/usr/` before restart. WiFi toggle fix confirmed working on Android 16 Pixel.                                                                   |
| **hd8** | ❌ Blocked | Fire OS SELinux prevents Termux SSH user from executing shell-context binaries. ADB USB can start server but tablet moves around — not viable as always-on failsafe. hd8 is actually arm64 (not armv7a as originally documented) — inventory needs updating. |

### Updated fleet viability

| Device | FIRERPA viable? | Self-heal channels                                                     |
| ------ | :-------------: | ---------------------------------------------------------------------- |
| s24    |       ✅        | Termux repair + Shizuku + AutoJs6 + FIRERPA gRPC + FIRERPA heal script |
| p7a    |       ✅        | Termux repair + Shizuku + AutoJs6 + FIRERPA gRPC + FIRERPA heal script |
| hd8    |       ❌        | Termux repair + peer bootstrap (existing) — no FIRERPA                 |

### What was built this session:

| Component        | Path                                                  | Purpose                                                      |
| ---------------- | ----------------------------------------------------- | ------------------------------------------------------------ |
| Ansible role     | `ansible_collections/stayturgid/firerpa/`             | Install + configure + service + uninstall                    |
| Playbook         | `ansible/playbooks/fleet/firerpa.yml`                 | Fleet deploy entry                                           |
| gRPC heal        | `control/bin/firerpa_heal.py`                         | Repair stayturgid via FIRERPA gRPC API                       |
| Health monitor   | `control/bin/firerpa_health_monitor.py`               | Fleet health via FIRERPA shell                               |
| Boot integration | `device/termux/boot/start-adb.sh`                     | FIRERPA lifecycle management                                 |
| Launchd agent    | `com.stayturgid.firerpa-health`                       | Mac 10-min health scrape                                     |
| Research docs    | `docs/research/evaluations/firerpa-*deepseek-pro*.md` | 4 documents (code audit, redundancy, install map, AI prompt) |

**Updated recommendation from external AI review (consolidated 2026-07-12):**

Two independent AI reviews (DeepSeek V4 Pro and Claude) both recommend proceeding with the spike on s24, with specific caveats:

1. **Test Shizuku binary execution directly** — can `lamda-server` run via `rish` (Shizuku's shell) without the Chinese-hosted APK? If the APK is required, the trust/security cost increases significantly.

2. **Measure idle resource drain** — leave FIRERPA running on s24 for 24 hours and check battery usage stats and RAM footprint before deploying to p7a (daily driver, only 12 GB free).

3. **Disable FIRERPA ADB by default** — keep Shizuku's adbd on :5555 as primary. Set `adb.enable=false` in FIRERPA's baseline config. Enable dynamically only in emergency when Shizuku's adbd has failed.

4. **Port multiplexing is the biggest single point of failure** — a crash in any one sub-service (WebRTC, Frida, proxy) could take down the entire redundant layer. Run only the minimal services needed (sshd + adb + gRPC) in the failsafe config.

5. **Isolate FIRERPA's network access** — bind to Tailscale interfaces only. Use Tailscale ACLs to drop outbound WAN access for the UID running FIRERPA, ensuring it can only communicate with the Mac control node.

6. **FIRERPA is the transport, not the brain** — it should call stayturgid's existing `stayturgid_repair.py` logic (570+ lines of fleet-specific fixes) rather than re-implementing repair decisions. The natural-language `agent` command is too non-deterministic for production self-heal.

**Proceed with Spike Step 1 on s24.** The spike is the lowest-risk, highest-information-gathering action available right now. It will empirically answer whether the Shizuku path works on Android 16, what the real memory/CPU cost is, and whether coexistence with stayturgid services is peaceful. If the spike fails, abandon or scope down without any regression. If it succeeds, the rest of the integration plan has high confidence.
