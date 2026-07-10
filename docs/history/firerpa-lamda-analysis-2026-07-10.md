# FIRERPA/lamda vs stayturgid — Integration Analysis

**Date:** 2026-07-10  
**Analyst:** Hermes (AI)  
**Source:** [firerpa/lamda](https://github.com/firerpa/lamda) v10.0 (MIT license, 7.8k★, 6+ years active)  
**Purpose:** Evaluate overlap, unique capabilities, and integration/replacement feasibility

---

## Executive Summary

FIRERPA/lamda is an **all-in-one Android device control platform** — a persistent on-device daemon exposing a gRPC+HTTP API on a single port. It covers remote desktop, UI automation, packet capture, Frida hooking, VPN/proxy, MCP/AI agents, and system-level control. It is the most feature-rich open-source Android automation framework we've found.

**Key finding:** FIRERPA and stayturgid are **complementary, not competing**. They solve different layers of the same problem:

| Layer | FIRERPA | stayturgid |
|-------|---------|------------|
| **On-device capabilities** | 160+ APIs, Frida, MITM, VPN, OCR, virtual displays | SSH + Termux + AutoJs6 watchdogs |
| **Fleet orchestration** | StarLink Hub (proprietary-ish) | Ansible + peer ADB mesh |
| **Configuration management** | INI file + API reload | Ansible playbooks + roles |
| **Device inventory** | mDNS/UDP broadcast | peers.json + devices.conf |
| **Human UX** | WebRTC remote desktop (browser) | scrcpy + Handsets |
| **AI integration** | Native MCP server + agent command | Hermes (external) |
| **Multi-OS support** | Android only | Android + Mac + Linux |
| **Deployment** | APK/Magisk/ROM | SSH + Ansible |

**Recommendation:** Do NOT replace stayturgid with FIRERPA. Instead, **integrate FIRERPA as an optional on-device capability** deployed via Ansible, giving stayturgid-managed devices access to FIRERPA's rich API surface when needed.

---

## 1. Overlap — What Both Projects Do

| Capability | FIRERPA approach | stayturgid approach | Better? |
|------------|-----------------|---------------------|---------|
| **ADB management** | Built-in ADB (no Dev Options needed) + wireless | Fleet mesh ADB keys + `localhost:5555` | stayturgid (mesh-wide) |
| **SSH access** | Built-in SSH server on device | Termux sshd via Ansible | Comparable |
| **Screen control** | WebRTC/H.264 browser remote desktop | scrcpy via Mac Handsets or Termux | FIRERPA (browser, no client) |
| **UI automation** | Full selector-based API (40+ methods) | AutoJs6 + uiautomator2 scripts | FIRERPA (richer, more stable) |
| **Touch input** | Multi-touch recording/replay/programmatic | `adb shell input` / AutoJs6 gestures | FIRERPA (much richer) |
| **App management** | Launch, install, uninstall, permissions, ops | `adb install` / Ansible tasks | FIRERPA (more granular) |
| **Device status** | Battery, CPU, disk, memory, network I/O | `make health` + fleet_health_monitor | stayturgid (fleet-wide aggregation) |
| **Screen lock/session** | API exclusive lock | Screen leases via DSCL | stayturgid (cross-device awareness) |
| **Clipboard** | Bidirectional, live in remote desktop | `termux-clipboard-set/get` | FIRERPA (richer) |
| **File transfer** | Upload/download/delete/chmod via API | `adb push/pull` + rsync over SSH | Comparable |
| **Shell execution** | Built-in terminal with strace/tcpdump/etc. | `ssh` + Ansible command module | stayturgid (orchestration) |
| **Key-value storage** | Persistent KV with TTL/expire | File-based configs | FIRERPA (structured) |
| **Wi-Fi management** | 13 Wi-Fi APIs (scan, connect, config) | `nmcli` via Ansible | FIRERPA (richer) |
| **Virtual displays** | Create isolated displays, full API parity | scrcpy `--new-display` (planned) | FIRERPA (native, richer) |

**Overlap is ~40%** — both can do ADB, SSH, screen control, UI automation, app management. But FIRERPA's on-device API is orders of magnitude richer for single-device control, while stayturgid's strength is fleet-wide orchestration.

---

## 2. What FIRERPA Does That stayturgid Doesn't

### HIGH relevance to stayturgid

| Feature | What it does | Why it matters |
|---------|-------------|----------------|
| **MITM/Packet capture** | One-click system CA install, per-package capture, live editing, QUIC downgrade. Docker + API. | Debug app network behavior on fleet devices. Verify proxy configs. Audit phone-home traffic. |
| **MCP/AI Agent** | Built-in MCP server (`/mcp/`) on streamable-http. 30+ MCP tools. `agent` command for natural-language device control via OpenAI-compatible API. | **Biggest gap.** Would let Hermes/Claude directly control devices via standard MCP protocol. Turns every fleet device into an AI-controllable endpoint. |
| **Frida hooking** | Bundled Frida (no separate server). Persistent scripts, YAML hot-reload, detection evasion. RPC to Python/HTTP/Redis/MQTT. | Dynamic analysis of apps. SSL pinning bypass. Runtime behavior inspection. Research capability. |
| **WebRTC remote desktop** | Browser-based, multi-user, H.264/MJPEG, live audio, TLS. Works in Silk browser on Fire HD. | Could replace scrcpy for tablet-control-phone (the incubator proposal). No client install needed. |
| **Virtual displays** | Create isolated background displays. Full API parity with main display. Watchers scoped to display. | Run automation on virtual display while human uses physical screen. Exactly what tablet-control-phone wants. |

### MEDIUM relevance

| Feature | What it does | Why it matters |
|---------|-------------|----------------|
| **OCR/Image matching** | PaddleOCR, EasyOCR, custom HTTP backends. On-device SIFT template matching. | Automate apps without accessibility nodes (games, custom UI). |
| **Visual layout inspection** | Highlights UI elements, Tab traversal, coordinates/RGB, XML export in WebUI. | Debug AutoJs6 scripts. Validate selectors. |
| **Multi-touch recording** | Record, replay, programmatic construction, binary persistence. Pressure + multi-finger. | Complex gesture automation (pinch, zoom, multi-finger swipes). |
| **SELinux control** | `allow()`, `disallow()`, `permissive()`, `create_domain()`. | System-level policy manipulation for advanced debugging. |
| **OpenVPN/frp client** | Built-in VPN with auto-connect. frp for NAT traversal. | Alternative to Tailscale for specific use cases. |
| **Proxy stack** | HTTP/HTTPS/SOCKS5/Shadowsocks, per-app proxy, DNS proxy, UDP proxy. | Route device traffic through specific proxies for geo-testing. |
| **Built-in ADB** | Wireless ADB without enabling Developer Options. Auto-authorized via Magisk. | Useful when apps detect dev mode. |
| **On-device ML** | tflite-runtime with hardware acceleration. | Edge inference without cloud dependency. |
| **Virtual Debian** | Full Debian with apt inside Android. | Compile BPF, install arbitrary packages. Niche but powerful. |

### LOW relevance

| Feature | What it does |
|---------|-------------|
| **Binary patching** | Hex wildcard matching, glob paths, dry-run. |
| **Script encryption** | Encrypted automation scripts. |
| **Hexedit command** | On-device hex editor. |

---

## 3. What stayturgid Does That FIRERPA Doesn't

| Feature | What it does | Why FIRERPA can't replace it |
|---------|-------------|------------------------------|
| **Fleet orchestration** | Ansible playbooks, roles, inventory groups. Deploy to N devices in parallel. | FIRERPA's StarLink Hub is proprietary and cloud-dependent. Ansible is self-hosted, auditable, idempotent. |
| **Multi-OS support** | Mac + Linux + Android devices. SSH into anything. | FIRERPA is Android-only. stayturgid manages Macs (control nodes) and Linux hosts too. |
| **Device health monitoring** | `fleet_health_monitor.py`, `access_monitor.py`, watchdog loops. Fleet-wide health aggregation. | FIRERPA has device status APIs but no fleet-wide monitoring daemon. |
| **Screen leases** | DSCL-based cross-device lease tracking. Prevents agent/human contention. | FIRERPA has API exclusive lock (single device) but no cross-device awareness. |
| **Peer ADB mesh** | hd8↔s24, Mac→device, device→device ADB routing through Tailscale. | FIRERPA has frp/OpenVPN but not the same mesh model. |
| **AutoJs6 watchdogs** | Self-healing AutoJs6 engine monitoring with termux-api notifications. | FIRERPA has its own automation but not the AutoJs6 ecosystem. |
| **Obtainium integration** | APK catalog management with version tracking. | FIRERPA has its own APK distribution but not a general-purpose catalog. |
| **Fire OS / Fire tablet support** | Specific handling of Fire OS quirks, boot scripts, battery optimization. | FIRERPA supports Android 6+ but has no Fire-specific adaptations documented. |
| **Termux boot lifecycle** | `start-adb.sh`, `start-autojs6-watchdog.sh`, self-healing loops. | FIRERPA has its own autostart but doesn't manage Termux services. |
| **Mac control node** | Ansible controller, VLM testing, screen control inversion. | FIRERPA has no Mac component. |

**stayturgid's unique value is fleet orchestration, multi-OS support, and the Ansible deployment model.** These are precisely the things FIRERPA cannot provide.

---

## 4. Could We Switch to FIRERPA?

### Verdict: **No, and we shouldn't try.**

| Criterion | Assessment |
|-----------|------------|
| **Feature coverage** | FIRERPA covers ~65% of what we need on-device, but 0% of fleet orchestration |
| **Deployment model** | APK/Magisk install is simpler than Ansible, but loses idempotency, auditability, and multi-OS support |
| **Inventory management** | mDNS/UDP broadcast is nice for discovery but doesn't replace structured inventory with host_vars |
| **Configuration management** | INI file + API reload vs Ansible playbooks — Ansible wins for reproducibility and version control |
| **Multi-device coordination** | StarLink Hub is proprietary; we'd trade self-hosted Ansible for a cloud dependency |
| **Mac support** | FIRERPA is Android-only. We manage Macs. Dead end. |
| **Fire OS** | No documented Fire tablet support. Our Fire-specific boot scripts and battery optimization have no FIRERPA equivalent |
| **Screen leases** | No cross-device lease system. Agent contention management would need to be rebuilt |
| **Custom automation** | AutoJs6 scripts, termux-api notifications, watchdog loops — all custom to our stack |
| **Licensing** | MIT license ✓ — no legal barrier, but architectural barrier is decisive |

**Bottom line:** Switching would mean rebuilding fleet orchestration, losing Mac support, losing Fire OS adaptations, and depending on a third-party project for core infrastructure. The on-device API is tempting but doesn't justify the loss.

---

## 5. Could We Integrate FIRERPA Under Ansible Control?

### Verdict: **Yes, and this is the right approach.**

FIRERPA's deployment model (APK install + Shizuku or root) maps cleanly to Ansible:

```yaml
# Conceptual Ansible role structure
roles/
  firerpa/
    tasks/
      main.yml          # Install FIRERPA APK, configure, start
      configure.yml     # Push INI config, certs, MCP extensions
      mcp.yml           # Deploy custom MCP extensions
    templates/
      firerpa.ini.j2    # Device-specific INI config
    files/
      extensions/       # Custom MCP extensions for stayturgid
```

### Integration points

| Integration | How | Value |
|-------------|-----|-------|
| **Deploy FIRERPA to devices** | Ansible role: download APK, `adb install`, push config, enable autostart | One-command deployment to fleet |
| **MCP bridge** | Custom MCP extension on device that exposes stayturgid-aware operations (health check, lease acquire, watchdog status) | Hermes can control devices via FIRERPA's MCP server |
| **WebRTC remote desktop** | FIRERPA's browser-based remote desktop replaces scrcpy for tablet-control-phone | Solves the incubator proposal without Termux:X11 compilation |
| **MITM on demand** | Ansible playbook that enables FIRERPA MITM, captures traffic, disables | Debug network issues on any fleet device |
| **Frida on demand** | Ansible playbook that injects persistent Frida scripts | Dynamic analysis without manual setup |
| **OCR/Image as fallback** | Use FIRERPA's OCR when AutoJs6 selectors fail on non-standard UI | Better automation coverage |
| **Health enrichment** | FIRERPA's device status API feeds into fleet_health_monitor | Richer health data (CPU, memory, network I/O) |

### Deployment options for FIRERPA on fleet devices

| Device | Root? | Deployment method | Notes |
|--------|-------|-------------------|-------|
| **s24** | No | Shizuku mode APK | Shizuku already installed (watchdog uses it) |
| **p7a** | No | Shizuku mode APK | Same — Shizuku already present |
| **hd8** | No | Shizuku mode APK | Fire OS — need to test APK install via ADB |
| **Mac** | N/A | Not applicable | FIRERPA is Android-only |

### Risks of integration

| Risk | Mitigation |
|------|------------|
| FIRERPA server runs as persistent daemon — memory/CPU overhead on constrained devices | Make it opt-in (`stayturgid_firerpa_enabled: false` by default). Only deploy to devices that need specific FIRERPA features. |
| FIRERPA's built-in ADB may conflict with stayturgid's ADB mesh | Disable FIRERPA's built-in ADB (`adb=off` in INI). Let stayturgid manage ADB. |
| FIRERPA's port 65000 may conflict with other services | Make port configurable in Ansible template. |
| FIRERPA updates may break MCP extensions | Pin version in Ansible. Test updates on one device before fleet rollout. |
| FIRERPA is a large binary — may not fit on constrained devices | Check APK size vs available storage. Make deployment conditional. |
| Licensing: FIRERPA is MIT but has "offline licensing" mentioned | Verify no runtime license check in the open-source build. |

---

## 6. Recommended Integration Roadmap

| Phase | Work | Effort | Value |
|-------|------|--------|-------|
| **0 — Spike** | Install FIRERPA APK on s24 via Shizuku. Test basic API (`Device("s24_ts:65000")`). Verify coexistence with stayturgid sshd/watchdog. | 1 day | Prove coexistence |
| **1 — Ansible role** | Create `roles/firerpa/` with tasks for install, config, start. Default disabled. | 2 days | Repeatable deployment |
| **2 — MCP bridge** | Write custom MCP extension that exposes stayturgid health/lease/watchdog status. Hermes connects via FIRERPA MCP. | 3 days | AI can control fleet via MCP |
| **3 — WebRTC desktop** | Test FIRERPA's browser remote desktop on hd8→s24 (tablet-control-phone incubator). Compare with scrcpy-in-Termux. | 2 days | May solve incubator proposal |
| **4 — MITM on demand** | Ansible playbook: enable FIRERPA MITM → capture → disable. | 1 day | Debug capability |
| **5 — Selective rollout** | Enable FIRERPA only on devices that need specific features (OCR, Frida, MITM). | Ongoing | Targeted capability boost |

**Total estimated effort: ~9 days for full integration, with immediate value from phase 0.**

---

## 7. API Surface Comparison (Summary)

### FIRERPA Device class: ~130+ methods across 23 categories

| Category | # Methods | stayturgid coverage |
|----------|-----------|---------------------|
| Connection & Core | 7 | 0% |
| UI Automation | 12 | 30% |
| Selector Operations | 40+ | 10% |
| Touch/Multitouch | 10+ | 0% |
| Display & Screen | 12 | 25% |
| Virtual Display | 7 | 0% |
| Application Management | 20+ | 25% |
| Frida/Scripting | 5 | 0% |
| System Properties | 10 | 20% |
| CA Certificates | 3 | 0% |
| Android Settings | 6 | 50% |
| Shell Execution | 4 | 25% |
| File Operations | 7 | 40% |
| Lock/Session | 5 | 80% |
| Wi-Fi | 13 | 15% |
| VPN/Proxy | 6 | 0% |
| ADB Management | 5 | 40% |
| SELinux | 8 | 0% |
| Device Status | 9 | 40% |
| Key-Value Storage | 11 | 0% |
| Watcher System | 13 | 0% |
| OCR Engine | 7 | VLM alternative |

**stayturgid covers ~35% of FIRERPA's on-device API surface** — mostly in areas that overlap (session lock, device status, ADB, settings, shell, files). The 65% gap is in specialized capabilities (Frida, selectors, virtual displays, VPN, OCR, watchers) that stayturgid doesn't need for fleet management but would benefit from having available.

---

## 8. Key Architecture Differences

```
FIRERPA model:
  [Android Device] ←gRPC/HTTP→ [Python Client / Web Browser / MCP Client]
  - Persistent on-device daemon
  - Single multiplexed port (65000)
  - Rich on-device API
  - No fleet orchestration

stayturgid model:
  [Mac Control Node] ←SSH→ [Android Device (Termux sshd)]
  - Ephemeral SSH sessions via Ansible
  - Per-device playbooks + roles
  - Fleet-wide inventory + health
  - Multi-OS support
```

**The models are complementary.** FIRERPA gives each device a rich API. stayturgid orchestrates across devices. Integration means: stayturgid deploys FIRERPA → FIRERPA exposes device API → stayturgid (or Hermes via MCP) uses that API for advanced operations.

---

## 9. Conclusion

| Question | Answer |
|----------|--------|
| Do we overlap? | ~40% on basic device operations (ADB, SSH, screen, apps) |
| What does FIRERPA do that we don't? | MCP/AI agent, MITM, Frida, virtual displays, WebRTC desktop, OCR, multi-touch, SELinux, VPN/proxy, 160+ APIs |
| What do we do that FIRERPA doesn't? | Fleet orchestration, Ansible, multi-OS, health monitoring, screen leases, peer ADB mesh, Fire OS support, AutoJs6 watchdogs |
| Should we switch? | **No.** Would lose fleet orchestration, Mac support, and Fire OS adaptations. |
| Should we integrate? | **Yes.** Deploy FIRERPA via Ansible as an optional on-device capability. Use its MCP server for AI integration. Use its WebRTC desktop for tablet-control-phone. Use its MITM/Frida on demand. |
| Effort? | ~9 days for full integration, with immediate value from spike. |

**FIRERPA is the best on-device Android control platform we've found. stayturgid is the best fleet orchestration layer for it. Together, they'd be formidable.**
