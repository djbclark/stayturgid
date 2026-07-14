# FIRERPA/lamda — AI Review Prompt (DeepSeek V4 Pro)

**Created:** 2026-07-12
**Source analyst:** DeepSeek V4 Pro (opencode-go/deepseek-v4-pro)
**Purpose:** Full-context prompt for getting an independent opinion from another AI (Claude, GPT, Gemini, etc.) on FIRERPA/lamda integration into the stayturgid project.
**How to use:** Copy this entire document and paste it into another AI tool as the initial prompt. It contains all the context, code snippets, and specific questions needed for a meaningful review.

---

# FULL CONTEXT

## About stayturgid

**Project:** stayturgid — keeps wireless ADB (port 5555), Shizuku, and SSH alive on unrooted Android phones across reboots, and makes them reachable over Tailscale via ADB + SSH.

**Repo:** https://github.com/djbclark/stayturgid (private; `master` branch)
**Version:** 2.7
**Fleet:** 3 unrooted Android devices:

- **s24** (Samsung Galaxy S24 SM-S921U1, Android 16, arm64, 73 GB free) — primary lab device
- **p7a** (Google Pixel 7a, Android 16, arm64, 12 GB free) — daily driver
- **hd8** (Amazon Kindle Fire HD 8 KFRASWI, Fire OS 11 / API 30, armv7a, 20 GB free) — tablet

All three run Shizuku (thedjchi fork, TCP mode, port 5555), Termux (GitHub-debug, sshd on :8022), AutoJs6 (v6.7.0 fleet-profile), Obtainium (app catalog), and Tailscale (always-on VPN).

**Access architecture:**

```
Mac Control Node ←─SSH :8022 (Tailscale)──→ Android Device
                 ←─ADB :5555 (Tailscale)──→ Android Device
                 ←─AutoJs6 a11y watchdogs──→ Android Device
```

**Self-heal system (what runs on each device):**

1. Termux:Boot `start-adb.sh` — starts sshd, then loops every 5 min:
   - Removes stale sshd `down` file (runit lockout fix)
   - Checks/repairs sshd, privileged shell :5555, Shizuku, a11y services
   - Ensures shell profile PATH (Mac leak fix), Termux mirror pinning
   - Re-applies fleet profiles (AutoJs6 + Shizuku)
   - Samsung wireless debug cosmetic skip (adb_wifi_enabled=0 but 5555 open)
   - Phone→Mac Eternal Terminal SSH config
2. AutoJs6 `main.js` — runs every 20 min:
   - Checks sshd + port 5555 liveness
   - If 5555 dead: accessibility-tap Shizuku "Start" button
   - Notifications on failures
3. Mac launchd agents: fleet-health (5 min), access-monitor (5 min), adb-reconnect (60 sec)

**Key recent failures (2026-07-12):**

- s24: sshd `down` file + Shizuku Samsung freezer + boot loop death → unreachable until USB ADB
- p7a: Mac PATH leaked into ~/.profile replacing Termux PATH → `pkg` not found
- Samsung wireless debug cosmetic flip-flop: repair sets `adb_wifi_enabled=1`, Samsung resets it every cycle

**Key repair scripts:**

- `~/stayturgid/device/termux/py/stayturgid_repair.py` (main self-heal, 570+ lines)
- `~/stayturgid/device/termux/boot/start-adb.sh` (Termux:Boot entry, 130+ lines)
- Deployed to devices via Ansible (`make deploy-termux HOSTS=<host>`)

## What We're Considering: FIRERPA/lamda

**Project:** FIRERPA/lamda — all-in-one Android device control platform
**Repo:** https://github.com/firerpa/lamda (MIT, 7.9k stars, 128 commits, 6+ years)
**Version:** v10.0 (June 2026)
**Local clone:** `~/src/firerpa-lamda/`

### What FIRERPA is

FIRERPA is a persistent on-device daemon that exposes 160+ APIs over gRPC+HTTP on a single port (default 65000). It includes:

- **WebRTC/H.264 remote desktop** — browser-based, multi-user, live audio, no client install
- **UI automation** — selector-based (text, resourceId, description), virtual displays, OCR, image matching, multi-touch, UI watchers
- **Built-in ADB** — standalone adbd, no Developer Options needed
- **Built-in SSH** — sshd on the same port via multiplexing
- **MCP/AI Agent** — built-in MCP server on `/mcp/` with 20+ tools, natural-language `agent` command
- **Frida** — bundled Frida with persistent scripts, RPC to Python/HTTP/Redis/MQTT
- **MITM** — one-click system CA install, per-package capture, live editing, QUIC downgrade
- **Proxy/VPN** — HTTP/SOCKS5/Shadowsocks, per-app proxy, OpenVPN, frp, tunnel2 reverse proxy
- **Persistent KV store** — `d.set()`/`d.get()` with TTL and Fernet encryption
- **Virtual displays** — isolated background displays for parallel automation

**v10.0 headline feature:** Non-root execution mode (`adb shell` identity) — the server can now run with `privileged=false`. This is critical for our use case since our devices are not rooted.

### What we've learned from code inspection (updated 2026-07-12)

The `firerpa/lamda` GitHub repo is a **Python client library + deployment tooling** — NOT the Android server binary. The server ships as a tarball in GitHub releases:

- `lamda-server-arm64-v8a.tar.gz` (163 MB) — for s24, p7a
- `lamda-server-armeabi-v7a.tar.gz` (135 MB) — for hd8

**Key finding from tarball extraction:** The server is NOT a compiled Go/Rust binary. It's an entire self-contained Python 3.9 runtime (8,395 files) with 14 native `.cpython-39.so` service extensions. Launches via:

```bash
# server/bin/launch.sh:
exec python3.9 -u -m lamda --launch --port=65000
```

**What we actually need (only 2 of 4 binaries):**

| Binary                            | Use | Reason                                                           |
| --------------------------------- | :-: | ---------------------------------------------------------------- |
| `lamda-server-arm64-v8a.tar.gz`   | ✅  | Both s24 + p7a are arm64 — same tarball                          |
| `lamda-client-py-10.0.tar.gz`     | ✅  | Mac talks to devices via gRPC                                    |
| `firerpa.apk`                     | ❌  | Manual deploy is the stayturgid way — no Chinese APK trust issue |
| `lamda-server-armeabi-v7a.tar.gz` | ❌  | Only for hd8 (Fire OS), skip for now                             |

**Fork:** [djbclark/lamda](https://github.com/djbclark/lamda) mirrors all 4 binaries in one GitHub-hosted [release](https://github.com/djbclark/lamda/releases/tag/v10.0-binaries).

**Mac testing results:** Client installed + tested in Python 3.12 venv at `/tmp/lamda-venv`. 88 Device methods, 14 gRPC service stubs, 25 exception types. Graceful failure on no-server (clear `_InactiveRpcError`). Python version constraint (`<=3.14` in setup.py) blocks pip on 3.14.6 — code works fine, only metadata blocks it. Retry: 5 attempts, exponential backoff 0.5s–15s. TLS: PEM cert parsing with `ssl_target_name_override`.

**Server service extensions (14 native .so):** sshd, adb, touch, driver (UI automation), openvpn, gproxy, helper (port multiplexing), frida, mdns, audio, fwd, motion, cron, top.

**Key code paths from the repo (for reference):**

1. **Device class** (`lamda/client.py:2341-2386`):

```python
class Device(object):
    def __init__(self, host, port=65000, certificate=None, session=None):
        self.certificate = certificate
        self.server = "{0}:{1}".format(host, port)
        # gRPC retry: 5 attempts, exponential backoff 0.5s → 1s → 2s → 4s → 8s
        policy = {"maxAttempts": 5, "retryableStatusCodes": ["UNAVAILABLE"],
                  "backoffMultiplier": 2, "initialBackoff": "0.5s", "maxBackoff": "15s"}
        # gRPC keepalive: 60s ping, 20s timeout, permit without calls
        option = {"grpc.keepalive_time_ms": 60000, "grpc.keepalive_timeout_ms": 20000,
                  "grpc.keepalive_permit_without_calls": True,
                  "grpc.max_send_message_length": 67108864,
                  "grpc.max_receive_message_length": 134217728}
        # TLS: PEM → key+crt+ca, ssl_target_name_override from cert CN
        if certificate is not None:
            with open(certificate, "rb") as fd:
                key, crt, ca = self._parse_certdata(fd.read())
            creds = grpc.ssl_channel_credentials(root_certificates=ca,
                        certificate_chain=crt, private_key=key)
            self._chan = grpc.secure_channel(self.server, creds, options)
        else:
            self._chan = grpc.insecure_channel(self.server, options)
        # Session: auto-generated UUID for lock API
        session = session or uuid.uuid4().hex
        # 3 interceptors: session metadata, gRPC→typed exception translation, logging
        self.channel = grpc.intercept_channel(self._chan, *interceptors)
```

2. **Service stub architecture** — 18 service stubs proxied through Device:

```python
# Device proxies to stubs:
d = Device("100.123.218.30:65000")
d.click(x=500, y=1000)                              # UiAutomatorStub
d.start_activity("com.android.settings")             # ApplicationStub
d.take_screenshot()                                  # UiAutomatorStub
d.execute_script("ls -la")                           # ShellStub
d.device_info()                                      # StatusStub
d.start_android_debug_bridge()                       # DebugStub (ADB)
# Context manager for exclusive lock:
with d:
    d.swipe(100,500, 900,500)  # locked session
```

3. **MCP extension pattern** (`extensions/firerpa.py:36-50`):

```python
class FireRpaMcpExtension(BaseMcpExtension):
    route = "/firerpa/mcp/"
    name = "firerpa"
    version = "1.0"
    @mcp("tool", description="Perform a click at arbitrary coordinates.")
    def click(self, ctx, pointX: Annotated[int, "X coordinate"],
                               pointY: Annotated[int, "Y coordinate"]):
        result = self.device.click(Point(x=pointX, y=pointY))
        return str(result).lower()
```

4. **Properties config** (`properties.example:1-148` — INI format):

```ini
[DEFAULT]
port=65000
[adb]
adb.enable=true
adb.privileged=false   # false = shell mode for non-root
[sshd]
sshd.enable=true
[cron]
cron.enable=true
```

5. **Server startup** (`tools/magisk/common/service.sh:1-13`):

```bash
port=65000
sleep 25   # wait for boot
$launch --port=${port} --certificate=${cert}
```

6. **Non-root support** (`CHANGELOG.txt:8`):

```
* Support for non-root execution mode (adb shell)
```

Proto: `ServerInfoResponse.privileged` (bool) — false = shell, true = root

### How FIRERPA could complement stayturgid

**Redundant failsafe layers:**

| Layer | What                                         | Current | With FIRERPA |
| ----- | -------------------------------------------- | ------- | ------------ |
| 1     | Termux sshd :8022                            | ✅      | ✅           |
| 2     | Shizuku adbd :5555                           | ✅      | ✅           |
| 3     | AutoJs6 watchdog                             | ✅      | ✅           |
| 4     | **FIRERPA sshd on :65000**                   | ❌      | ✅ NEW       |
| 5     | **FIRERPA adbd on :65000**                   | ❌      | ✅ NEW       |
| 6     | **FIRERPA UI automation taps Shizuku Start** | ❌      | ✅ NEW       |
| 7     | **Mac→FIRERPA health monitor**               | ❌      | ✅ NEW       |

**Mutual repair pair:** Termux repairs FIRERPA (start/stop via shell), FIRERPA repairs Termux (remove down file, restart sshd via API). Each monitors the other.

**Self-heal via FIRERPA (conceptual):**

```python
# Runs on FIRERPA (not Termux). Repairs stayturgid when primary channels are down.
def repair_sshd():
    down = "/data/data/com.termux/files/usr/var/service/sshd/down"
    if file_exists(down): delete_file(down)
    if not is_sshd_alive():
        execute_script("/data/data/com.termux/files/usr/bin/sshd")

def repair_shizuku():
    if is_port_5555_alive(): return
    execute_script("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START")
    sleep(3)
    if not is_port_5555_alive():
        start_app("moe.shizuku.privileged.api")
        sleep(2)
        d(text="Start").click()   # UI automation via FIRERPA's selector API
```

---

## QUESTIONS FOR THE REVIEWING AI

### Architecture & Design

1. **Is FIRERPA the right choice for a redundant failsafe layer?** Given stayturgid's architecture (Termux sshd + Shizuku adbd + AutoJs6 watchdog + Ansible fleet orchestration), does adding a separate native daemon (FIRERPA on port 65000) actually improve reliability, or does it add a new single point of failure (the server binary itself)?

2. **What's the right deployment model for non-root devices?** The options are:
   - A) Shizuku APK install (one-click, auto-start on boot, but Chinese-hosted APK)
   - B) Manual server binary + Ansible deploy (GitHub-hosted binary, fully auditable, no auto-start)
   - C) stayturgid boot integration (start-adb.sh manages FIRERPA lifecycle)
     Which do you recommend and why?

3. **Co-dependent recovery pair — sound architecture or fragile coupling?** If Termux monitors FIRERPA and FIRERPA monitors Termux, both restarting each other, what are the failure modes? Is there a risk of restart loops?

4. **Port multiplexing on 65000 — risk or feature?** FIRERPA runs gRPC, HTTP, WebSocket, ADB, SSH, proxy, and WebRTC all on a single port. What are the security implications? What happens if one sub-service crashes?

### Integration & Execution

5. **How should we prioritize the 9-step integration plan?** Steps: (1) Spike, (2) Ansible role, (3) Deploy to s24, (4) Fleet rollout, (5) Python client, (6) MCP bridge, (7) WebRTC test, (8) MITM playbook, (9) Docs. Which steps deliver the most value earliest?

6. **Can the MCP agent reliably automate repair?** The FIRERPA MCP extension has an `agent` command that accepts natural-language prompts. Could we literally tell it "open Shizuku, tap Start, wait 3 seconds" and have it work? Or is the agent unreliable for repair automation?

7. **Should we use FIRERPA's built-in ADB or keep Shizuku's?** FIRERPA's adbd runs on port 65000 without Developer Options. Shizuku's runs on port 5555 with wireless debugging. If we run both, do they conflict? Which should be the primary ADB channel?

### Risks & Mitigations

8. **What are the risks of the server binary being closed-source?** The 163 MB native binary is not auditable. What's the worst case — does it phone home? Could it have a backdoor? How would we monitor its network traffic?

9. **Is the Shizuku deployment path actually tested?** The README says "root or Shizuku" but zero GitHub issues mention Shizuku. The entire community appears rooted (Magisk module is the most-downloaded artifact). Is Shizuku mode a real feature or a checkbox feature?

10. **What's the failure mode if FIRERPA goes unmaintained?** The project has 6+ years of development but a single maintainer (rev1si0n). If the project dies, our redundant layer is dead on all devices simultaneously. How do we mitigate this — pin version? Fork the client? Have an uninstall path?

### Specific to Our Fleet

11. **Fire OS (hd8) compatibility?** FIRERPA claims Android 6.0+ support. Fire OS 11 is API 30. But Fire OS blocks background broadcasts and has no Termux→localhost:5555 loopback. Will FIRERPA's server binary even run on Fire OS?

12. **Memory/CPU concern on p7a (12 GB free)?** The server is a persistent daemon. What's the expected RAM usage at idle? Could it impact the daily-driver experience on p7a?

13. **Stayturgid's existing self-heal vs FIRERPA's — overlap or complement?** stayturgid's repair script is 570+ lines of Python with specific fixes for our exact failures (down file, Samsung wireless debug, Mac PATH leak, mirror pinning). Does FIRERPA's automation replace this, or complement it?

### Future-proofing

14. **If we integrate FIRERPA, what's the migration path if we later remove it?** We need a clean uninstall that doesn't leave artifacts and doesn't create a dependency. Can the entire integration be behind a single Ansible boolean (`firerpa_enabled: false`)?

15. **What's the killer feature that makes FIRERPA worth the integration cost?** Is it the redundant failsafe? The WebRTC remote desktop (for tablet-control-phone)? The MCP bridge (AI-driven device control)? Or does the combination of all three justify the effort?

---

## RELEVANT CODE AND DOCUMENTS

### Local filesystem paths (on the Mac)

| File                                 | Path                                                                                    |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| stayturgid repair script             | `~/stayturgid/device/termux/py/stayturgid_repair.py`                                    |
| stayturgid boot script               | `~/stayturgid/device/termux/boot/start-adb.sh`                                          |
| stayturgid handoff doc               | `~/stayturgid/docs/handoff.md`                                                          |
| FIRERPA analysis (original)          | `~/stayturgid/docs/history/firerpa-lamda-analysis-2026-07-10.md`                        |
| FIRERPA non-root research (original) | `~/stayturgid/docs/history/firerpa-nonroot-research-2026-07-10.md`                      |
| FIRERPA integration plan             | `~/stayturgid/docs/plans/firerpa-integration-plan.md`                                   |
| FIRERPA code audit (DEEPSEEK-PRO)    | `~/stayturgid/docs/history/firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md`         |
| FIRERPA redundancy (DEEPSEEK-PRO)    | `~/stayturgid/docs/history/firerpa-nonroot-redundancy-deepseek-pro-2026-07-12.md`       |
| FIRERPA install map                  | `~/stayturgid/docs/history/firerpa-install-map-2026-07-12.md`                           |
| FIRERPA client SDK                   | `~/src/firerpa-lamda/lamda/client.py`                                                   |
| FIRERPA fork (local)                 | `~/src/firerpa-fork/`                                                                   |
| FIRERPA binaries (local)             | `~/src/firerpa-binaries/` (all 4 downloaded)                                            |
| FIRERPA MCP extension                | `~/src/firerpa-lamda/extensions/firerpa.py`                                             |
| FIRERPA properties config            | `~/src/firerpa-lamda/properties.example`                                                |
| FIRERPA CHANGELOG                    | `~/src/firerpa-lamda/CHANGELOG.txt`                                                     |
| FIRERPA Magisk service.sh            | `~/src/firerpa-lamda/tools/magisk/common/service.sh`                                    |
| stayturgid SSH CA                    | `~/stayturgid/ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml` |
| stayturgid fleet inventory           | `~/stayturgid/ansible/inventory/hosts.yml`                                              |

### URLs

| Resource                                 | URL                                                                                                |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| FIRERPA GitHub (upstream)                | https://github.com/firerpa/lamda                                                                   |
| FIRERPA fork (stayturgid)                | https://github.com/djbclark/lamda                                                                  |
| FIRERPA fork release (all 4 binaries)    | https://github.com/djbclark/lamda/releases/tag/v10.0-binaries                                      |
| FIRERPA APK (fork)                       | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/firerpa.apk                     |
| FIRERPA server arm64 (fork)              | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/lamda-server-arm64-v8a.tar.gz   |
| FIRERPA server armv7a (fork)             | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/lamda-server-armeabi-v7a.tar.gz |
| FIRERPA client (fork)                    | https://github.com/djbclark/lamda/releases/download/v10.0-binaries/lamda-client-py-10.0.tar.gz     |
| FIRERPA v10.0 release                    | https://github.com/firerpa/lamda/releases/tag/v10.0                                                |
| FIRERPA docs (EN)                        | https://device-farm.com/docs/en/quick-start                                                        |
| FIRERPA full docs dump                   | https://device-farm.com/llms-full.txt                                                              |
| FIRERPA APK                              | https://device-farm.com/assets/apk/firerpa.apk                                                     |
| Shizuku docs                             | https://shizuku.rikka.app/guide/setup/                                                             |
| stayturgid GitHub                        | https://github.com/djbclark/stayturgid                                                             |
| FIRERPA issue #138 (Android 16/Pixel 7a) | https://github.com/firerpa/lamda/issues/138                                                        |
| scrcpy (alternative remote desktop)      | https://github.com/Genymobile/scrcpy                                                               |
| AutoJs6 (stayturgid watchdog)            | https://github.com/djbclark/AutoJs6                                                                |
| Shizuku (fork used by stayturgid)        | https://github.com/djbclark/Shizuku                                                                |
| Obtainium (app catalog)                  | https://github.com/djbclark/Obtainium                                                              |
| Hermes Agent (control-node gateway)      | https://github.com/anomalyco/hermes-agent                                                          |
| OpenCode (AI coding agent)               | https://github.com/anomalyco/opencode                                                              |

### Key code snippets for context

**stayturgid repair — sshd down file fix (2026-07-12):**

```python
# ~/stayturgid/device/termux/py/stayturgid_repair.py
SSHD_SERVICE_DIR = PREFIX + "/var/service/sshd"

def ensure_sshd_down_file():
    down = os.path.join(SSHD_SERVICE_DIR, "down")
    if not os.path.isfile(down):
        return "up"
    try:
        os.unlink(down)
        log("removed stale sshd down file")
        return "repaired"
    except OSError:
        return "FAILED"
```

**stayturgid repair — Samsung wireless debug cosmetic skip:**

```python
def ensure_wireless_debugging():
    _rc, raw = sh_adb("settings get global adb_wifi_enabled")
    wifi = raw.strip()
    if wifi in ("1", "true"):
        return "up"
    # Cosmetic false on Samsung — shell works, toggle shows 0
    if wifi == "0" and _rc == 0:
        return "up"
    # Actually off — try to enable
    ...
```

**stayturgid repair — shell profile path fix:**

```python
MAC_PATH_KEYWORDS = ("/Users/", "/opt/homebrew/", "/Library/Apple/",
                     "/System/Cryptexes/")

def ensure_shell_profile_path():
    for rel in [".profile", ".bashrc", ".bash_profile"]:
        # Check for Mac-style PATH lines, replace with Termux PATH
        ...
```

**stayturgid Ansible inventory (hosts.yml):**

```yaml
s24:
  ansible_host: 100.123.218.30 # Tailscale IP
  device_usb_serial: RFCX219CHKA
  device_lan_ip: 192.168.68.54
  device_label: Galaxy S24
p7a:
  ansible_host: 100.65.230.108
  device_usb_serial: 35261JEHN12374
  device_lan_ip: 192.168.68.60
  device_label: Pixel 7a
hd8:
  ansible_host: 100.124.55.39
  device_usb_serial: GN43T503430603PS
  device_lan_ip: 192.168.1.157
  device_label: Kindle Fire HD 8
```

---

## INSTRUCTIONS FOR THE REVIEWING AI

1. Read this entire prompt first. The context is dense but complete.
2. Answer the 15 questions in the order listed. Be specific and cite evidence where possible.
3. If you need more detail about any specific code file, ask for it rather than guessing.
4. Feel free to challenge assumptions — if you think FIRERPA integration is a bad idea, say so and explain why.
5. The key decision we need your help with: **Should we proceed with the spike (Step 1 of the integration plan), or is there a fundamentally better approach we're missing?**

---

## CONSOLIDATED EXTERNAL REVIEWS (2026-07-12)

Two independent AI reviews were received. Both recommend proceeding with the spike on s24. Key areas of agreement and divergence:

### Areas of Agreement

| Point                                 | Consensus                                                                          |
| ------------------------------------- | ---------------------------------------------------------------------------------- |
| **Proceed with spike**                | Both recommend it — lowest risk, highest information                               |
| **Deployment model**                  | Both prefer boot integration (Option C) over APK                                   |
| **Keep Shizuku ADB primary**          | Both say disable FIRERPA ADB by default, enable only in emergency                  |
| **Don't use agent for self-heal**     | Both say natural-language agent is non-deterministic; use deterministic gRPC calls |
| **hd8 skip for now**                  | Both say prove on s24 first; Fire OS is too uncertain                              |
| **Measure idle drain in spike**       | Both say battery/RAM impact on p7a is a critical unknown                           |
| **Clean uninstall path**              | Both agree the `firerpa_enabled: false` toggle is well-designed                    |
| **FIRERPA + stayturgid = complement** | Both see FIRERPA as transport (UI hand), stayturgid as brain (repair logic)        |

### Areas of Divergence

| Point                      | Reviewer 1                         | Reviewer 2 (Claude)                                                                 |
| -------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------- |
| **Port multiplexing**      | Net feature with manageable risks  | Significant architectural risk — single point of failure for entire redundant layer |
| **Co-dependent recovery**  | Sound with backoff + health checks | Fragile — restart storms, OOM thrashing need shared state + unilateral authority    |
| **Prioritize WebRTC test** | Not mentioned specifically         | Move up to right after spike — if it works, it justifies the rest                   |
| **Network isolation**      | Not mentioned specifically         | Critical — bind to Tailscale only, drop WAN access for FIRERPA UID                  |
| **Closed-source trust**    | Monitor outbound + pin version     | More aggressive — iptables/Tailscale ACLs to enforce network isolation              |

### Decision

**Spike on s24 with constrained scope:**

1. Prove Shizuku binary execution via `rish` without APK
2. Measure 24-hour idle drain (battery + RAM)
3. Test WebRTC remote desktop immediately
4. Disable FIRERPA ADB by default
5. Configure minimal services only (sshd + adb + gRPC)
6. If any of these fail: abandon or scope down without regression
7. If all succeed: proceed to Ansible role + Python client integration
