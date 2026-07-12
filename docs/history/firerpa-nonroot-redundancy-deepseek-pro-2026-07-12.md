# FIRERPA/lamda — Non-Root Viability + Redundant Failsafe Architecture (DeepSeek V4 Pro)

**Date:** 2026-07-12
**Analyst:** DeepSeek V4 Pro (opencode-go/deepseek-v4-pro)
**Prior art:** [firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md](firerpa-lamda-code-audit-deepseek-pro-2026-07-12.md), [firerpa-nonroot-research-2026-07-10.md](firerpa-nonroot-research-2026-07-10.md)
**Stayturgid repo:** `~/stayturgid/` — [GitHub](https://github.com/djbclark/stayturgid)
**FIRERPA repo:** `~/src/firerpa-lamda/` (upstream), `~/src/firerpa-fork/` (fork) — [djbclark/lamda](https://github.com/djbclark/lamda) with all binaries at [releases](https://github.com/djbclark/lamda/releases/tag/v10.0-binaries)
**Purpose:** Evaluate FIRERPA's non-root viability on stayturgid's fleet (s24, p7a, hd8) and design a multi-layered redundant failsafe architecture for maintaining remote system access.

---

## Executive Summary

FIRERPA v10.0 introduced **official non-root execution mode** (`adb shell`). This is a headline feature — line 8 of CHANGELOG.txt. The server can now run with `privileged=false` (shell UID 2000) vs `privileged=true` (root UID 0). For stayturgid's purposes, this means:

1. **Core features work without root:** remote desktop (WebRTC), UI automation, MCP server, 160+ APIs, virtual displays, OCR, image matching, multi-touch, watchers, app management, shell execution, file I/O, clipboard, device status.
2. **System features need root:** MITM (system CA cert install), Frida hooks at system level, SELinux manipulation, writing `ro.*` properties, `strace`/`tcpdump` at system level.
3. **stayturgid's key needs are all in the core set** — remote desktop, UI automation, and MCP bridge don't require root.

Most importantly, FIRERPA can serve as a **2nd/3rd line of redundant failsafe** for remote access and self-heal execution when stayturgid's primary channels (Termux sshd, Shizuku adbd) are down. This document maps out that architecture.

---

## 1. Current stayturgid Remote Access Architecture

### What we actually need — only 2 of 4 binaries

FIRERPA distributes 4 binaries. For stayturgid's fleet, we only need 2:

| Binary | Use? | Reason |
|--------|:----:|--------|
| `lamda-server-arm64-v8a.tar.gz` (163 MB) | ✅ **Needed** | Both s24 and p7a are arm64 — same tarball for both phones |
| `lamda-client-py-10.0.tar.gz` (63 KB) | ✅ **Needed** | Mac control node talks to device servers via gRPC |
| `firerpa.apk` (8 MB) | ❌ Skip | We already have Shizuku. Manual tar + Ansible deploy is the stayturgid way — version-controlled, idempotent, no Chinese APK trust issue. The APK is pure Dalvik/Java (14.7 MB dex, no native libs) — its only job is downloading and extracting the server tarball. |
| `lamda-server-armeabi-v7a.tar.gz` (135 MB) | ❌ Skip | Only needed for the hd8 Fire tablet. Fire OS 11 has no localhost:5555, blocks background broadcasts, and FIRERPA has no Fire-specific code. The peer-bootstrap architecture already handles hd8. If we ever want FIRERPA on hd8, add it later. |

**Effective install:** one server tarball for the two arm64 phones, one pip package for the Mac. 163 MB on each phone, 63 KB on the Mac.

### What the server actually is

The tarball is an **entire self-contained Python 3.9 runtime** (8,395 files) — not a single compiled Go/Rust binary. It contains:

- **149 CLI tools** in `server/bin/` — `python3.9`, `frida-server`, `sshd`, `iperf`, `dnsmasq`, `strace`, `tcpdump`, `sqlite3`, etc.
- **7,975 Python .pyc files** — full stdlib + grpc + protobuf + tornado (WebUI) + PIL + cv2 + numpy + unicorn + capstone + keystone
- **14 native .so service extensions** — sshd, adb, touch, driver (UI automation), openvpn, gproxy, helper (port multiplexing), frida, mdns, audio, fwd, motion, cron, top
- **22 MiniCap screenshot engines** — one per Android version 21–35 plus MIUI variants
- **120+ iptables modules** — for proxy/VPN/firewall features

The server launches via: `exec python3.9 -u -m lamda --launch --port=65000`

### Minimal failsafe config — just backup SSH + ADB

If deploying only as a redundant backup channel (no automation, no MCP, no Frida), the config is 3 lines:

```ini
port=65000
[sshd]
sshd.enable=true
[adb]
adb.enable=true
adb.privileged=false
```

This gives you SSH backup on :65000 and ADB backup on :65000. No APK, no Shizuku interaction, no conflicts with stayturgid's :8022 (SSH) or :5555 (ADB).

### Primary channels (fleet-maintained)

| Layer | Channel | Port | Initiated by | Failure modes |
|-------|---------|------|-------------|---------------|
| 1 | **Termux sshd** | 8022 | Termux:Boot `start-adb.sh` | `down` file lockout, sshd crash, Termux force-stop |
| 2 | **Shizuku adbd** | 5555 | Shizuku TCP mode + `ensure_wireless_debugging()` | Shizuku crash, Samsung process freezer, wireless debug toggle off |
| 3 | **AutoJs6 watchdog** | N/A | `start-autojs6-watchdog.sh` → main.js | a11y drift, AutoJs6 crash, Fire OS zombie instance |
| 4 | **Termux repair loop** | N/A | `start-adb.sh` (5-min cycle) | Boot loop death, `run-as` PATH poisoning |

### What these channels repair

```
┌─────────────┐     ┌─────────────┐     ┌───────────┐     ┌──────────┐
│ Termux sshd │────▶│ Shizuku adbd│────▶│ AutoJs6   │────▶│ Termux   │
│  :8022      │     │  :5555      │     │ a11y      │     │ repair    │
└──────┬──────┘     └──────┬──────┘     └─────┬─────┘     └────┬─────┘
       │                   │                  │                 │
       ▼                   ▼                  ▼                 ▼
  SSH to device     ADB to device      UI-tap Shizuku     Self-heal
  Restart sshd      Restart Termux     Start buttons      sshd + ADB
  Deploy scripts    Install apps       Dismiss dialogs    A11y merge
```

### The problem: all channels share one dependency

Every channel ultimately depends on **at least one** of sshd:8022 or adbd:5555 being alive. If both die simultaneously (Shizuku crash + sshd `down` file), the device is **unreachable** until:
1. The user physically interacts (open Shizuku app, tap "Start")
2. The device reboots (Shizuku auto-starts)
3. USB ADB is plugged in

This happens. On 2026-07-12, the s24 had both failures simultaneously — sshd `down` file + Shizuku frozen — and the boot loop was dead, preventing self-heal. Recovery required USB ADB.

---

## 2. FIRERPA as Additional Redundant Channels

### New channel: FIRERPA remote desktop (WebRTC)

FIRERPA's WebRTC remote desktop provides a **browser-based UI channel** that doesn't depend on ADB or SSH at all. It runs entirely within FIRERPA's own server process on port 65000, with its own touch injection, clipboard, and terminal.

- **Access:** Open `http://<tailscale-ip>:65000` in any browser
- **What it survives:** Termux force-stop, Shizuku crash, sshd down, ADB dead
- **What kills it:** FIRERPA server crash (mitigated by launchd/Magisk auto-restart)

### New channel: FIRERPA SSH (built-in sshd)

FIRERPA includes a built-in sshd on port 65000 (same port, multiplexed). This provides a **second SSH path** independent of Termux.

- **Access:** `ssh -p 65000 <tailscale-ip>` (if FIRERPA sshd enabled)
- **What it survives:** Termux force-stop, Termux sshd crash, `down` file
- **What kills it:** FIRERPA server crash

### New channel: FIRERPA ADB (built-in adbd)

FIRERPA includes a standalone ADB daemon — no Developer Options or Shizuku needed. This provides a **third ADB path**.

- **Access:** `adb connect <tailscale-ip>:65000` (if FIRERPA ADB enabled)
- **What it survives:** Shizuku crash, wireless debugging toggle off, Samsung process freezer
- **What kills it:** FIRERPA server crash, `adb.enable=false` in config

### New channel: FIRERPA MCP/AI agent

FIRERPA's built-in MCP server and `agent` command allow AI-driven device control via standard MCP protocol. This is a **programmatic channel** for self-heal scripts.

- **Access:** POST to `http://<tailscale-ip>:65000/mcp/` with MCP JSON-RPC
- **What it can do:** Click "Start" in Shizuku via UI automation, restart Termux services, check system state
- **What kills it:** FIRERPA server crash, MCP extension failure

---

## 3. Redundant Failsafe Architecture

### Layer 1: stayturgid repair (current — everyday self-heal)

```
┌──────────────────────────────────────────────────┐
│ EVERY 5 MINUTES (boot loop)                       │
│                                                    │
│  1. ensure_sshd_down_file()  ← NEW (2026-07-12)  │
│  2. sshd_up() → restart if down                   │
│  3. ensure_wireless_debugging() ← Samsung-aware   │
│  4. privileged_shell() → 5555 repair              │
│  5. ensure_shell_profile_path()  ← NEW            │
│  6. ensure_termux_mirror()       ← NEW            │
│  7. ensure_control_et_ssh_config()                │
│  8. Re-apply fleet profiles                       │
│                                                    │
│ RAN BY: Termux boot loop (start-adb.sh → repair)  │
│ REQUIRES: Termux alive, boot loop alive           │
└──────────────────────────────────────────────────┘
```

### Layer 2: AutoJs6 watchdog (current — catastrophic recovery)

```
┌──────────────────────────────────────────────────┐
│ EVERY 20 MINUTES (AutoJs6 main.js)                │
│                                                    │
│  1. Check sshd + port 5555 liveness               │
│  2. If 5555 dead: accessibility-tap Shizuku Start │
│  3. Termux probe (Tailscale connectivity)          │
│  4. Notification if anything still broken          │
│                                                    │
│ RAN BY: AutoJs6 engine (a11y service)             │
│ REQUIRES: AutoJs6 a11y service enabled            │
│ FAILS ON: Fire OS (zombie instance), a11y drift    │
└──────────────────────────────────────────────────┘
```

### Layer 3: FIRERPA health check + self-heal (proposed — new redundant path)

```
┌──────────────────────────────────────────────────┐
│ EVERY 5-10 MINUTES (FIRERPA cron or external)     │
│                                                    │
│  1. Check stayturgid sshd :8022 liveness          │
│  2. If dead: FIRERPA's SSH/API repairs it:         │
│     a. Remove sshd down file via file API          │
│     b. Start Termux sshd via shell API             │
│     c. Or: touch repair_now via file API            │
│  3. Check Shizuku adbd :5555 liveness              │
│  4. If dead: FIRERPA's UI automation taps Start:   │
│     a. Launch Shizuku activity via app API         │
│     b. Click "Start" button via selector API       │
│     c. Or: FIRERPA ADB runs HEADLESS_START          │
│  5. Report status to Mac control node              │
│                                                    │
│ RAN BY: FIRERPA cron or Mac launchd agent          │
│ REQUIRES: FIRERPA server alive                    │
│ SURVIVES: Termux crash, sshd down, Shizuku crash   │
└──────────────────────────────────────────────────┘
```

### Layer 4: Mac→FIRERPA health monitor (proposed — fleet-level safety net)

```
┌──────────────────────────────────────────────────┐
│ EVERY 5 MINUTES (Mac launchd agent)               │
│                                                    │
│  1. For each device:                              │
│     a. Try stayturgid SSH :8022 → if OK, skip     │
│     b. If SSH dead: try FIRERPA gRPC :65000       │
│     c. If FIRERPA alive: run self-heal script      │
│        via FIRERPA's shell API:                    │
│        - Remove sshd down file                     │
│        - Kill + restart sshd                       │
│        - Start Shizuku via app API                 │
│     d. If both dead: escalate to operator          │
│  2. Log + notify (same pattern as fleet_health)    │
│                                                    │
│ RAN BY: Mac launchd (com.stayturgid.firerpa-health)│
│ REQUIRES: FIRERPA server reachable                 │
│ SURVIVES: Termux + Shizuku both dead               │
└──────────────────────────────────────────────────┘
```

### Failure matrix: what survives what

| Failure | stayturgid repair | AutoJs6 | FIRERPA repair | Mac→FIRERPA |
|---------|:---:|:---:|:---:|:---:|
| sshd down file | ✅ NEW | ❌ | ✅ | ✅ |
| sshd crash | ✅ | ❌ | ✅ | ✅ |
| Boot loop dead | ❌ | ✅ | ✅ | ✅ |
| Shizuku crash | ✅ | ✅ | ✅ | ✅ |
| Samsung freezer | ✅ NEW | ❌ | ✅ | ✅ |
| Wireless debug off | ✅ | ❌ | ✅ | ✅ |
| a11y drift | ✅ | ❌ | ✅ | ✅ |
| AutoJs6 dead | ✅ | N/A | ✅ | ✅ |
| Termux force-stop | ❌ | ✅ | ✅ | ✅ |
| FIRERPA crash | N/A | N/A | ❌ | ❌ |
| Tailscale down | ❌ | ❌ | ❌ | ❌ |
| Battery dead | ❌ | ❌ | ❌ | ❌ |

**Result:** With FIRERPA as layer 3/4, every single-device failure mode has at least one recovery path that doesn't require physical access. The only failures that still need human intervention are FIRERPA crash + stayturgid crash simultaneously, Tailscale outage, or power loss.

---

## 4. Non-Root Deployment Paths

### Option A: Shizuku APK install (recommended)

```
1. Download firerpa.apk from device-farm.com
2. Install on device (adb install or Obtainium)
3. Open FIRERPA app → Shizuku authorizes → one-click download+install+start
4. Server binary extracted to /data/local/tmp/
5. Started with privileged=false (shell mode)
```

**Pros:** One-click, auto-generates certs, auto-start on boot via APP
**Cons:** APK hosted on Chinese domain, Shizuku path untested by community

### Option B: Manual server binary + Ansible deploy

```
1. Download lamda-server-arm64-v8a.tar.gz from GitHub releases
2. Extract to /data/local/tmp/firerpa/
3. Create properties.local with port=65000, adb.privileged=false
4. Start via: nohup /data/local/tmp/firerpa/lamda-server --port=65000 &
5. Ansible role manages install, config, start, stop
```

**Pros:** No APK trust issue, GitHub-hosted binary, fully Ansible-managed
**Cons:** Manual cert setup, no auto-start on boot without additional scripting

### Option C: FIRERPA + stayturgid boot integration (best fit)

```
1. FIRERPA server deployed via Ansible (Option B)
2. start-adb.sh extended to also start FIRERPA server
3. FIRERPA runs as a peer of sshd in the boot loop
4. FIRERPA's own crash recovery: boot loop restarts it
5. Mutually-repairing pair: Termux repairs FIRERPA, FIRERPA repairs Termux
```

This creates a **co-dependent recovery pair** — each monitors and repairs the other. External AI review flagged specific failure modes and mitigations:

| Risk | Mitigation |
|------|------------|
| **Restart storm:** Both sides see the other as "down" simultaneously, triggering mutual restarts in a loop | Health checks must be functional (real gRPC call, actual sshd process check), not just port-based. Exponential backoff + max retries. |
| **OOM thrashing:** System-level OOM killer takes both down; FIRERPA repeatedly trying to restart Termux could thrash CPU and drain battery | Shared state file in `~/.stayturgid/run/` to coordinate. Only one side has authority to restart at a time. |
| **One side's repair kills the other:** e.g., Termux restart via `pkill` could accidentally kill FIRERPA's Python process | Use PID files and precise process management. Never `pkill -f` with overly broad patterns. |
| **Port 65000 multiplexing single point of failure:** A crash in one sub-service (WebRTC, Frida) takes down the entire redundant layer | Run only minimal services (sshd + adb + gRPC) in the failsafe config. Disable WebUI, Frida, cron, proxy in `properties.local`. |

**Architecture principle:** FIRERPA should be the **transport** (the hand that clicks the UI, the shell that removes the `down` file), not the **brain** (the logic that decides what needs fixing). It should call stayturgid's existing `stayturgid_repair.py` (570+ lines of fleet-specific fixes: Samsung cosmetic skip, Mac PATH leak, mirror pinning) rather than re-implementing repair decisions. The natural-language `agent` command is too non-deterministic for production self-heal — use deterministic gRPC/selector API calls for repair automation.

**Network isolation:** Bind FIRERPA to Tailscale interfaces only. Use Tailscale ACLs to drop outbound WAN access for the UID running FIRERPA, ensuring it can only communicate with the Mac control node. This mitigates the risk of the closed-source server binary phoning home.

```bash
# In start-adb.sh (addition):
FIRERPA_DIR=/data/local/tmp/firerpa
FIRERPA_PID_FILE="$STG/run/firerpa.pid"

start_firerpa() {
    if [ -x "$FIRERPA_DIR/lamda-server" ]; then
        nohup "$FIRERPA_DIR/lamda-server" --port=65000 > "$STG/logs/firerpa.log" 2>&1 &
        echo $! > "$FIRERPA_PID_FILE"
    fi
}

# Boot loop addition (every cycle):
# Check if FIRERPA is alive; restart if dead
if [ -f "$FIRERPA_PID_FILE" ]; then
    pid=$(cat "$FIRERPA_PID_FILE")
    if ! kill -0 "$pid" 2>/dev/null; then
        start_firerpa
    fi
fi
```

---

## 5. FIRERPA Self-Heal Script (On-Device)

A self-heal script that FIRERPA runs (via cron or external trigger) to repair stayturgid services:

```python
# ~/stayturgid/device/termux/py/stayturgid_firerpa_heal.py
# Runs ON FIRERPA (not Termux) via FIRERPA's MCP or RPC trigger.
# Repairs stayturgid when the primary channels are down.

SSHD_DOWN = "/data/data/com.termux/files/usr/var/service/sshd/down"
TERMUX_SSHD = "/data/data/com.termux/files/usr/bin/sshd"
SHIZUKU_PKG = "moe.shizuku.privileged.api"

def is_sshd_alive():
    """Check if stayturgid sshd is running on port 8022."""
    result = shell("ss -tlnp | grep ':8022 '")
    return ":8022" in (result or "")

def is_port_5555_alive():
    """Check if Shizuku's adbd is running on port 5555."""
    result = shell("ss -tlnp | grep ':5555 '")
    return ":5555" in (result or "")

def repair_sshd():
    """Repair stayturgid sshd via FIRERPA's shell access."""
    # 1. Remove stale down file
    if file_exists(SSHD_DOWN):
        delete_file(SSHD_DOWN)
        log("removed sshd down file via FIRERPA")

    # 2. Start sshd if not running
    if not is_sshd_alive():
        execute_script(TERMUX_SSHD)
        sleep(2)
        if is_sshd_alive():
            log("sshd restarted via FIRERPA -> OK")

    # 3. Restart boot loop if dead
    boot_pid = read_file("/data/data/com.termux/files/home/.stayturgid/run/bootloop.pid")
    if boot_pid and not is_process_alive(int(boot_pid)):
        execute_script(
            "setsid /data/data/com.termux/files/home/.termux/boot/start-adb.sh "
            ">/dev/null 2>&1 < /dev/null &"
        )
        log("boot loop restarted via FIRERPA")

def repair_shizuku():
    """Repair Shizuku via FIRERPA's UI automation."""
    if is_port_5555_alive():
        return

    # 1. Try HEADLESS_START via FIRERPA's shell
    execute_script("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START")
    sleep(3)

    if is_port_5555_alive():
        log("Shizuku started via HEADLESS_START from FIRERPA")
        return

    # 2. UI automation fallback: tap Start button
    start_app(SHIZUKU_PKG)
    sleep(2)
    # Tap the "Start" button — coordinates depend on Shizuku version
    # Better: use selector-based click
    d = get_device()
    d(text="Start").click()
    sleep(3)

    if is_port_5555_alive():
        log("Shizuku started via UI tap from FIRERPA")

def main():
    log("FIRERPA heal cycle start")
    if not is_sshd_alive():
        repair_sshd()
    if not is_port_5555_alive():
        repair_shizuku()
    log("FIRERPA heal cycle done")
```

**Trigger mechanisms:**
1. **FIRERPA cron** (`[cron] cron.enable=true` in properties) — periodic Python scripts
2. **Mac launchd agent** — SSH into FIRERPA → run heal script
3. **stayturgid boot loop** — call FIRERPA's API to trigger heal if FIRERPA is down

---

## 6. MCP as Self-Heal Trigger

FIRERPA's MCP server can be used as a **standardized interface** for self-heal. An MCP tool can be written that wraps the heal logic:

```python
# extensions/stayturgid_heal.py
# Deploy to FIRERPA's ~/modules/extension/

from lamda.mcp import *
from lamda.extensions import BaseMcpExtension

class StayturgidHealExtension(BaseMcpExtension):
    route = "/stayturgid/heal/"
    name = "stayturgid-heal"
    version = "1.0"

    @mcp("tool", description="Run stayturgid self-heal on this device.")
    def heal(self, ctx,
             target: Annotated[str, "What to repair: sshd, shizuku, all"]):

        results = []
        if target in ("sshd", "all"):
            results.append(self._repair_sshd())
        if target in ("shizuku", "all"):
            results.append(self._repair_shizuku())
        return TextContent(text="\n".join(results))

    @mcp("tool", description="Check stayturgid service health.")
    def health(self, ctx):
        sshd_ok = "ss -tlnp | grep ':8022 '"
        adb_ok = "ss -tlnp | grep ':5555 '"
        return TextContent(text=f"sshd: {sshd_ok}, adbd: {adb_ok}")
```

Then from the Mac control node or any MCP client:

```bash
# Trigger heal via MCP
curl -X POST http://100.123.218.30:65000/stayturgid/heal/ \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "heal", "arguments": {"target": "all"}}}'
```

---

## 7. Deployment Order — From 0 to 4 Layers

| Phase | What | Effort | Adds |
|-------|------|--------|------|
| **0 (current)** | stayturgid repair + AutoJs6 | Already done | Layers 1-2 |
| **1 — FIRERPA spike** | Install FIRERPA on s24 (Shizuku mode) | 1 day | Verify FIRERPA coexists |
| **2 — FIRERPA Ansible** | `ansible/roles/firerpa/` — install, config, start | 1 day | Deployable to fleet |
| **3 — FIRERPA self-heal** | `stayturgid_firerpa_heal.py` + MCP extension | 1 day | Layer 3 (on-device) |
| **4 — Mac monitor** | `com.stayturgid.firerpa-health` launchd agent | 0.5 day | Layer 4 (fleet-level) |
| **5 — Boot integration** | `start-adb.sh` manages FIRERPA lifecycle | 0.5 day | Mutual repair pair |

**Total: ~4 days to full 4-layer redundant architecture.**

---

## 8. Prior Art and References

| Resource | URL | Relevance |
|----------|-----|-----------|
| FIRERPA v10.0 release | https://github.com/firerpa/lamda/releases/tag/v10.0 | v10.0 added non-root mode (shell identity) |
| FIRERPA docs (EN) | https://device-farm.com/docs/en/quick-start | Deployment instructions |
| FIRERPA docs (ZH) | https://device-farm.com/docs/zh/quick-start | Shizuku-mode deployment |
| FIRERPA full docs dump | https://device-farm.com/llms-full.txt | AI-readable full documentation |
| FIRERPA APK | https://device-farm.com/assets/apk/firerpa.apk | 8.4 MB, Shizuku-compatible |
| Shizuku APK (FIRERPA-hosted) | https://device-farm.com/assets/apk/shizuku-v13.6.0.r1086.2650830c-release.apk | Recommended Shizuku version |
| Shizuku docs | https://shizuku.rikka.app/guide/setup/ | Official Shizuku setup guide |
| FIRERPA MCP extension (code) | ~/src/firerpa-lamda/extensions/firerpa.py | 20+ MCP tools |
| FIRERPA MCP extension (web) | https://github.com/firerpa/lamda/blob/10/extensions/firerpa.py | Same, via GitHub |
| stayturgid repair script | ~/stayturgid/device/termux/py/stayturgid_repair.py | Current self-heal |
| stayturgid repair (web) | https://github.com/djbclark/stayturgid/blob/master/device/termux/py/stayturgid_repair.py | Same, via GitHub |
| stayturgid boot script | ~/stayturgid/device/termux/boot/start-adb.sh | Termux:Boot entry |
| stayturgid handoff doc | ~/stayturgid/docs/handoff.md | Fleet architecture reference |
| stayturgid CA doc | ~/stayturgid/ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml | SSH CA integration |
| Frida issue #138 (Android 16) | https://github.com/firerpa/lamda/issues/138 | p7a confirmed tested on FIRERPA |
| stayturgid options (FIRERPA) | ~/stayturgid/docs/options.md#L141-L152 | Parked integration work |

---

## 9. Key Questions for Spike (Updated from External Review 2026-07-12)

1. **Does the non-root mode actually work on Shizuku?** The APK installs via Shizuku. But more critically: can the server binary be executed directly via `rish` (Shizuku's shell) WITHOUT the Chinese-hosted APK? If the binary requires the APK, the trust/security cost increases significantly and the integration becomes much heavier.

2. **What's the idle resource drain?** Leave FIRERPA running on s24 for 24 hours. Measure battery usage stats and RAM footprint (via `dumpsys meminfo` and FIRERPA's own StatusStub). The p7a is a daily driver — a daemon that prevents deep sleep or consumes 200+ MB RAM may be unacceptable.

3. **Can FIRERPA coexist with stayturgid's boot loop?** Two persistent daemons on the same device. Do they fight for resources? Does FIRERPA's built-in ADB conflict with Shizuku's adbd on port 5555? The spike should measure for at least 24 hours with both running.

4. **What happens when the server binary crashes?** Does it auto-restart? Does the boot loop need to handle FIRERPA crashes? Test: `kill -9` the `python3.9` process and observe.

5. **Is the WebRTC remote desktop viable?** Test immediately in the spike. If it's laggy or crashes, the overall value proposition drops. This is the feature that could solve the tablet-control-phone incubator proposal without Termux:X11/scrcpy compilation pain.

6. **Does the APK add anything we can't get from the binary alone?** The APK handles: TLS cert generation, auto-boot via Android app lifecycle, Shizuku auth flow, server download. We can replicate all of these with Ansible + `rish` + launch.sh. But if the binary refuses to run without APK-produced artifacts, we need to know.

7. **Can we limit FIRERPA to Tailscale-only networking?** Use `iptables` or Tailscale ACLs to ensure the closed-source binary only talks to the Mac control node. This is a key mitigation for the trust risk.
