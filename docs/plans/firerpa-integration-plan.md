# FIRERPA Integration Plan

**Created:** 2026-07-10
**Status:** IN PROGRESS — Step 1 (Spike) starting
**Author:** Hermes (AI) + Dan
**Prerequisite analysis:** [firerpa-lamda-analysis-2026-07-10.md](../history/firerpa-lamda-analysis-2026-07-10.md)

---

## Safety Principle

> **At each step's wrapup, zero regression in stayturgid functionality.**
> Every step has a CHECKPOINT section. If the checkpoint fails, execute
> the ROLLBACK for that step before doing anything else.

---

## Device Inventory (Baseline)

| Device | Alias | Model | Android | Arch | Storage Free | Shizuku | Root | Role |
|--------|-------|-------|---------|------|-------------|---------|------|------|
| s24 | `s24` | SM-S921U1 | 16 | arm64 | 73 GB | ✅ installed | ❌ | Daily driver, primary test |
| p7a | `p7a` | Pixel 7a | 16 | arm64 | 12 GB | ✅ installed | ❌ | Legacy device |
| hd8 | `hd8` | KFRASWI (Fire HD 8) | 11 | armv7a | 20 GB | ✅ installed | ❌ | Tablet |

**Tailscale IPs:** s24=`100.123.218.30`, p7a=`100.65.230.108`, hd8=`100.124.55.39`
**SSH port (all):** `8022`

---

## FIRERPA Release Assets (v10.0)

| Asset | Size | Use |
|-------|------|-----|
| `lamda-server-arm64-v8a.tar.gz` | 163 MB | Server binary for s24, p7a |
| `lamda-server-armeabi-v7a.tar.gz` | 134 MB | Server binary for hd8 |
| `lamda-magisk-module.zip` | 371 MB | Magisk module (NOT usable — no root) |
| `lamda-client-py-10.0.tar.gz` | <1 MB | Python client for Mac control node |
| `startmitm.exe` | 21 MB | Windows MITM tool (not needed) |

**⚠️ BLOCKER — No APK in GitHub releases.**
The README mentions "one-click APP (root or Shizuku)" but no APK is
distributed through GitHub releases. Options:
  1. The APK is on firerpa.com (currently DNS-unreachable)
  2. The APK is built from a private source repo
  3. The server binary can be run directly via Shizuku `rish` shell
  4. We contact the FIRERPA maintainer to request APK distribution

**Step 1 will determine which option works.**

---

## FIRERPA Server Binary — What It Needs

From README + code analysis:
- **No JVM, no Python, no extra runtime** — single native binary
- Listens on **port 65000** (configurable via INI)
- Multiplexes: gRPC + HTTP (WebUI/MCP) + remote desktop + built-in ADB + SSH
- Requires **root OR Shizuku** for system-level operations (SELinux, proxy,
  virtual displays, Frida, MITM). Basic UI automation works with just
  shell-level permissions.
- Config via INI file at `/data/local/tmp/firerpa.ini` (or auto-generated)
- TLS certificates auto-generated on first run

---

## Steps Overview

| # | Step | Risk | Devices | Est. Time | Gate |
|---|------|------|---------|-----------|------|
| 1 | Spike: Verify FIRERPA runs on s24 | LOW | s24 only | 1 day | API responds, no stayturgid regression |
| 2 | Create Ansible role `firerpa` | NONE | N/A | 1 day | Role passes `ansible-playbook --check` |
| 3 | Deploy FIRERPA to s24 via Ansible | LOW | s24 | 0.5 day | Service starts, health passes |
| 4 | Deploy to p7a + hd8 | LOW | p7a, hd8 | 0.5 day | All 3 devices healthy |
| 5 | Install Python client on Mac | NONE | Mac | 0.5 day | `Device("s24")` connects |
| 6 | MCP bridge extension | LOW | s24 | 2 days | Hermes can call MCP tools |
| 7 | WebRTC desktop test | LOW | hd8→s24 | 1 day | Browser remote desktop works |
| 8 | MITM-on-demand playbook | LOW | s24 | 1 day | Capture + restore works |
| 9 | Fleet-wide rollout + docs | NONE | all | 1 day | All devices have FIRERPA opt-in |

**Total: ~8.5 days**

---

## Step 1 — Spike: Verify FIRERPA Runs on s24

**Goal:** Confirm FIRERPA server binary starts on s24, basic API
responds, and no stayturgid services are disrupted.

**Pre-conditions:**
- s24 online, SSH reachable (`ssh -p 8022 u0_a354@100.123.218.30`)
- Fleet health OK (`make health`)
- Shizuku running on s24

**Actions:**

1. **Download server binary** to Mac:
   ```
   curl -L -o /tmp/lamda-server.tar.gz \
     https://github.com/firerpa/lamda/releases/download/v10.0/lamda-server-arm64-v8a.tar.gz
   ```

2. **Record baseline** — snapshot what's running on s24 before changes:
   ```
   ssh s24 'ps -A | grep -E "termux|autojs|shizuku|adb" > /tmp/before-firerpa.txt'
   make health  # must say OK
   ```

3. **Investigate APK vs binary question:**
   - Try running the server binary directly via `rish` (Shizuku shell)
   - If that fails, check if the Magisk module zip contains an APK
     (download, `unzip -l`, look for `*.apk`)
   - If neither works, file a GitHub issue on firerpa/lamda asking how
     to install on non-root Shizuku devices without the APK

4. **Push binary to device** (if binary works directly):
   ```
   scp -P 8022 /tmp/lamda-server.tar.gz u0_a354@100.123.218.30:/data/local/tmp/
   ssh s24 'cd /data/local/tmp && tar xzf lamda-server.tar.gz && chmod +x lamda-server'
   ```

5. **Start FIRERPA** on s24 (minimal config, high port to avoid conflicts):
   ```
   ssh s24 '/data/local/tmp/lamda-server -p 65000 &'
   ```
   Or if it needs Shizuku: `rish -c '/data/local/tmp/lamda-server -p 65000 &'`

6. **Test basic API** from Mac:
   ```
   pip3 install lamda-client  # or use the tar.gz
   python3 -c "from lamda.client import Device; d = Device('100.123.218.30:65000'); print(d.device_info())"
   ```

7. **Verify no regression:**
   ```
   make health          # must say OK
   ssh s24 'ps -A | grep -E "termux|autojs|shizuku|adb" > /tmp/after-firerpa.txt'
   diff /tmp/before-firerpa.txt /tmp/after-firerpa.txt  # should be empty or FIRERPA-only diff
   ```

8. **Stop FIRERPA** (spike is temporary):
   ```
   ssh s24 'kill $(pgrep lamda-server) 2>/dev/null; pkill lamda-server'
   ```

**CHECKPOINT 1:**
- [ ] Server binary starts without crash
- [ ] Basic API call succeeds (device_info returns JSON)
- [ ] `make health` still says OK after start AND after stop
- [ ] No new processes besides FIRERPA itself
- [ ] APK question resolved (either found a way, or filed issue)

**ROLLBACK 1:** Kill FIRERPA process. Remove `/data/local/tmp/lamda-*`.
Run `make health`. Done — nothing persistent was changed.

**⚠️ DECISION GATE:** If APK is unavailable and binary doesn't work
via Shizuku, we cannot proceed to Step 2. File issue, wait for
response, or explore building from source.

---

## Step 2 — Create Ansible Role `firerpa`

**Goal:** Build `ansible/roles/firerpa/` so FIRERPA can be deployed
idempotently to any device. Default: disabled.

**Pre-conditions:**
- Step 1 checkpoint passed (we know how to install and run FIRERPA)
- Ansible control node functional

**Actions:**

1. **Create role structure:**
   ```
   ansible/roles/firerpa/
   ├── tasks/
   │   ├── main.yml          # include_vars + dispatch
   │   ├── install.yml       # push binary, set permissions
   │   ├── configure.yml     # render INI from template
   │   ├── service.yml       # start/stop/restart
   │   └── uninstall.yml     # clean removal
   ├── templates/
   │   └── firerpa.ini.j2    # INI config template
   ├── defaults/
   │   └── main.yml          # all variables with sane defaults
   └── README.md
   ```

2. **Default variables** (`defaults/main.yml`):
   ```yaml
   firerpa_enabled: false            # OFF by default — safe
   firerpa_version: "10.0"
   firerpa_port: 65000
   firerpa_arch: "arm64"            # overridden per-device
   firerpa_install_dir: /data/local/tmp
   firerpa_webui: true
   firerpa_sshd: false              # don't conflict with Termux sshd
   firerpa_adb: false               # don't conflict with stayturgid ADB
   firerpa_mcp: true                # enable MCP server
   firerpa_mdns: true               # enable mDNS discovery
   ```

3. **Host_vars** for arch override:
   ```yaml
   # host_vars/hd8.yml
   firerpa_arch: "armeabi-v7a"
   ```

4. **Playbook** (`ansible/playbooks/firerpa.yml`):
   ```yaml
   - hosts: android
     become: true
     roles:
       - role: firerpa
         when: firerpa_enabled | default(false)
   ```

5. **Verify:** Run `ansible-playbook --check ansible/playbooks/firerpa.yml`
   (dry run — no changes applied).

**CHECKPOINT 2:**
- [ ] Role structure exists with all files
   ```
   ansible-playbook --syntax-check ansible/playbooks/firerpa.yml
   ansible-playbook --check ansible/playbooks/firerpa.yml -l s24
   ```
- [ ] Default is `firerpa_enabled: false` — no device gets FIRERPA
   unless explicitly opted in
- [ ] No existing playbooks or roles modified

**ROLLBACK 2:** Delete `ansible/roles/firerpa/` and
`ansible/playbooks/firerpa.yml`. Nothing was deployed.

---

## Step 3 — Deploy FIRERPA to s24 via Ansible

**Goal:** First real deployment. FIRERPA installed on s24 through
Ansible, coexisting with all existing services.

**Pre-conditions:**
- Step 2 checkpoint passed
- s24 online, fleet health OK

**Actions:**

1. **Record baseline:**
   ```
   make health
   ssh s24 'ps -A > /tmp/before-step3.txt; df -h /data | tail -1 > /tmp/disk-before.txt'
   ```

2. **Enable FIRERPA on s24** in inventory:
   ```yaml
   # host_vars/s24.yml (add)
   firerpa_enabled: true
   ```

3. **Deploy:**
   ```
   ansible-playbook ansible/playbooks/firerpa.yml -l s24 -v
   ```

4. **Verify service:**
   ```
   ssh s24 'curl -s http://localhost:65000/api/v1/device 2>/dev/null | head -c 200'
   # Should return JSON with device info
   ```

5. **Verify no regression:**
   ```
   make health                    # must say OK
   ssh s24 'diff <(ps -A) /tmp/before-step3.txt'  # only FIRERPA diff
   ssh s24 'df -h /data | tail -1'  # disk usage OK
   ```

6. **Verify existing services unaffected:**
   ```
   ssh s24 'pgrep -a autojs6'          # watchdog still running
   ssh s24 'pgrep -a "termux"'          # Termux services still running
   ssh s24 'ss -tlnp | grep 8022'       # SSH still on 8022
   ```

**CHECKPOINT 3:**
- [ ] `curl localhost:65000` returns FIRERPA device info JSON
- [ ] `make health` says OK
- [ ] AutoJs6 watchdog still running
- [ ] Termux SSH still on port 8022
- [ ] Disk usage delta < 200 MB (server binary + config)
- [ ] No process crashes in `logcat -d -s FIRERPA`

**ROLLBACK 3:**
```
ansible-playbook ansible/playbooks/firerpa.yml -l s24 -e "firerpa_enabled=false" --tags uninstall
# OR manually:
ssh s24 'kill $(pgrep lamda-server); rm -f /data/local/tmp/lamda-* /data/local/tmp/firerpa.ini'
make health
```

---

## Step 4 — Deploy to p7a and hd8

**Goal:** Extend FIRERPA to remaining devices. All three devices
running FIRERPA, all stayturgid services intact.

**Pre-conditions:**
- Step 3 checkpoint passed
- p7a and hd8 online, fleet health OK

**⚠️ Special considerations:**
- **p7a** has only 12 GB free. FIRERPA binary is ~163 MB. Acceptable
  but monitor disk closely.
- **hd8** is armv7a (not arm64). Needs `lamda-server-armeabi-v7a.tar.gz`
  (134 MB). Also Fire OS 11 — test that FIRERPA runs on Fire OS.
- **hd8** is the daily-driver tablet — extra caution.

**Actions:**

1. **Deploy to p7a** (lower risk, not daily driver):
   ```
   make health
   ssh p7a 'df -h /data | tail -1'          # confirm 12 GB free
   # Enable in host_vars:
   # host_vars/p7a.yml: firerpa_enabled: true
   ansible-playbook ansible/playbooks/firerpa.yml -l p7a -v
   # Verify:
   ssh p7a 'curl -s http://localhost:65000/api/v1/device | head -c 200'
   make health
   ```

2. **Deploy to hd8** (highest caution — daily driver tablet):
   ```
   make health
   # hd8 already has firerpa_arch: "armeabi-v7a" in host_vars
   # Enable: host_vars/hd8.yml: firerpa_enabled: true
   ansible-playbook ansible/playbooks/firerpa.yml -l hd8 -v
   # Verify:
   ssh hd8 'curl -s http://localhost:65000/api/v1/device | head -c 200'
   make health
   # Manually verify tablet still works:
   # - AutoJs6 watchdog running?
   # - Screen still accessible via scrcpy?
   # - Termux boot scripts still starting?
   ```

3. **Full fleet verification:**
   ```
   make health   # all 3 OK
   for h in s24 p7a hd8; do
     echo "=== $h ==="
     ssh $h 'curl -s http://localhost:65000/api/v1/device | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(\"model\",\"?\"))" 2>/dev/null || echo "NOT RUNNING"'
   done
   ```

**CHECKPOINT 4:**
- [ ] All 3 devices: `curl localhost:65000` returns device info
- [ ] `make health` says OK for all 3
- [ ] p7a disk still has > 10 GB free after install
- [ ] hd8: AutoJs6 watchdog running, screen accessible, Termux boot OK
- [ ] No device has FIRERPA conflicting with existing services

**ROLLBACK 4:**
```
# Disable on all devices:
# Set firerpa_enabled: false in all host_vars
ansible-playbook ansible/playbooks/firerpa.yml -l "p7a,hd8" --tags uninstall
# If playbook rollback fails, manual cleanup:
for h in p7a hd8; do
  ssh $h 'kill $(pgrep lamda-server); rm -f /data/local/tmp/lamda-* /data/local/tmp/firerpa.ini'
done
make health
```

---

## Step 5 — Install Python Client on Mac

**Goal:** Mac control node can connect to any FIRERPA device via
the Python `lamda` client. This unlocks scripted API access.

**Pre-conditions:**
- Step 4 checkpoint passed (FIRERPA running on devices)
- Mac has Python 3.14 + venv

**Actions:**

1. **Install client in stayturgid venv:**
   ```
   cd ~/stayturgid-hermes
   source .venv/bin/activate
   pip install lamda-client
   # OR from downloaded tar.gz:
   # pip install /tmp/lamda-client-py-10.0.tar.gz
   ```

2. **Test connection to s24:**
   ```
   python3 -c "
   from lamda.client import Device
   d = Device('100.123.218.30:65000')
   info = d.device_info()
   print(f'Model: {info.model}')
   print(f'Android: {info.sdkVersion}')
   print('FIRERPA client OK')
   "
   ```

3. **Test from stayturgid codebase** (import check):
   ```
   cd ~/stayturgid-hermes
   python3 -c "from lamda.client import Device; print('import OK')"
   ```

**CHECKPOINT 5:**
- [ ] `pip install lamda-client` succeeds in stayturgid venv
- [ ] `Device('100.123.218.30:65000').device_info()` returns JSON
- [ ] Import works from stayturgid-hermes directory
- [ ] No existing Python dependencies broken

**ROLLBACK 5:**
```
pip uninstall lamda-client
```
Client is purely a library — no device-side changes.

---

## Step 6 — MCP Bridge Extension

**Goal:** Write a custom FIRERPA MCP extension that exposes
stayturgid-aware operations (health, leases, watchdog status)
as MCP tools. Hermes can then control devices through FIRERPA's
MCP server using the standard Model Context Protocol.

**Pre-conditions:**
- Steps 4-5 checkpoint passed
- FIRERPA MCP server enabled on at least s24
- Understanding of `BaseMcpExtension` API (from `/tmp/lamda/extensions/`)

**Actions:**

1. **Design MCP tools** the extension exposes:
   | Tool | Description |
   |------|-------------|
   | `stayturgid_health` | Get fleet health status for this device |
   | `stayturgid_lease_status` | Check who holds the screen lease |
   | `stayturgid_lease_acquire` | Acquire screen lease for automation |
   | `stayturgid_lease_release` | Release screen lease |
   | `stayturgid_watchdog_status` | Check AutoJs6 watchdog health |
   | `stayturgid_watchdog_restart` | Restart AutoJs6 watchdog |
   | `stayturgid_fleet_info` | Get device inventory info |

2. **Write extension** (`extensions/stayturgid_bridge.py`):
   - Uses `BaseMcpExtension` decorator pattern
   - Calls back to stayturgid's SSH/API layer for data
   - Deployed to device via Ansible

3. **Deploy extension to s24** (via Ansible role update):
   ```
   ansible-playbook ansible/playbooks/firerpa.yml -l s24 --tags configure -v
   ```

4. **Test MCP tools** from Mac:
   ```
   # Using FIRERPA's MCP endpoint:
   curl -X POST http://100.123.218.30:65000/mcp/ \
     -H "Content-Type: application/json" \
     -d '{"method": "tools/list"}'
   # Should list stayturgid_* tools
   ```

5. **Test from Hermes** (if MCP client is configured):
   Connect Hermes to FIRERPA's MCP server and call
   `stayturgid_health` tool.

**CHECKPOINT 6:**
- [ ] Extension file deployed to s24
- [ ] `tools/list` returns stayturgid_* tools
- [ ] `stayturgid_health` returns device health data
- [ ] `stayturgid_watchdog_status` returns watchdog state
- [ ] Existing stayturgid services unaffected

**ROLLBACK 6:**
Remove extension file from device:
```
ssh s24 'rm -f /data/local/tmp/firerpa/extensions/stayturgid_bridge.py'
ssh s24 'kill -HUP $(pgrep lamda-server)'  # restart to unload extension
```
Extension is additive — removing it restores previous state.

---

## Step 7 — WebRTC Desktop Test (tablet-control-phone)

**Goal:** Test FIRERPA's browser-based WebRTC remote desktop as a
potential replacement for scrcpy-in-Termux for the tablet-control-phone
incubator proposal.

**Pre-conditions:**
- Step 4 checkpoint passed (FIRERPA on all devices)
- hd8 Silk browser or any browser available

**Actions:**

1. **Open FIRERPA WebUI** on s24 from hd8's browser:
   ```
   # On hd8, open Silk browser:
   http://100.123.218.30:65000
   ```
   Or from Mac: `http://100.123.218.30:65000`

2. **Test remote desktop features:**
   - [ ] MJPEG stream loads
   - [ ] H.264 stream loads (if WebRTC supported)
   - [ ] Click/touch input works (control s24 from browser)
   - [ ] Clipboard sharing works
   - [ ] Latency acceptable (<200ms for touch response)

3. **Compare with scrcpy approach** from tablet-control-phone.md:
   | Criterion | FIRERPA WebRTC | scrcpy in Termux |
   |-----------|---------------|------------------|
   | Browser-based | ✅ Yes | ❌ Needs X11 |
   | Install complexity | APK + config | Termux:X11 + scrcpy compile |
   | Multi-user | ✅ Built-in | ❌ Single user |
   | Audio forwarding | ✅ Android 10+ | ❌ Limited |
   | Touch injection | ✅ Native API | ⚠️ scrcpy relay |
   | Fire OS compat | ⚠️ Untested | ⚠️ Untested |

4. **Decision:** Does FIRERPA WebRTC solve tablet-control-phone?
   - If YES: Update tablet-control-phone.md with recommendation
   - If NO: Continue with scrcpy plan, keep FIRERPA as supplementary

**CHECKPOINT 7:**
- [ ] WebUI accessible from hd8 browser
   ```
   # From Mac (verify WebUI serves):
   curl -s http://100.123.218.30:65000/ | head -c 100
   ```
- [ ] Remote desktop stream works
- [ ] Touch input functional
- [ ] `make health` still OK on all devices

**ROLLBACK 7:** No persistent changes. WebRTC is built into FIRERPA
server — just stop using it. If we decide not to use this feature,
set `firerpa_webui: false` in host_vars and redeploy.

---

## Step 8 — MITM-on-Demand Playbook

**Goal:** Create an Ansible playbook that enables FIRERPA's MITM
capture on a target device, captures traffic, and cleanly restores.
One-shot debug capability for fleet devices.

**Pre-conditions:**
- Steps 4-5 checkpoint passed
- `startmitm.py` tool available (from lamda-client or separate download)

**Actions:**

1. **Create playbook** (`ansible/playbooks/firerpa-mitm.yml`):
   ```yaml
   - hosts: "{{ target }}"
     tasks:
       - name: Install mitmproxy on control node
         local_action: pip install mitmproxy
         run_once: true

       - name: Start FIRERPA MITM capture
         command: >
           python3 -m lamda.tools.startmitm
           --host {{ firerpa_host }}:{{ firerpa_port }}
           --output /tmp/mitm-{{ target }}.flow
           --timeout {{ capture_duration | default(300) }}
   ```

2. **Test on s24** (short capture):
   ```
   ansible-playbook ansible/playbooks/firerpa-mitm.yml \
     -l s24 -e "capture_duration=30"
   ```

3. **Verify clean restore:**
   ```
   ssh s24 'settings get global http_proxy'  # should be empty/null
   ssh s24 'curl -s https://example.com -o /dev/null -w "%{http_code}"'  # should be 200
   ```

**CHECKPOINT 8:**
- [ ] MITM capture starts and produces .flow file
- [ ] Capture stops after timeout
- [ ] Device proxy settings restored to default
- [ ] HTTPS traffic works normally after capture
- [ ] `make health` OK

**ROLLBACK 8:**
```
# Force-restore proxy settings:
ssh s24 'settings put global http_proxy :0'
ssh s24 'settings put global global_http_proxy_host ""'
ssh s24 'settings put global global_http_proxy_port ""'
make health
```

---

## Step 9 — Fleet Rollout + Documentation

**Goal:** Finalize integration. Update documentation, ensure all
devices are configured, and record decisions.

**Pre-conditions:**
- Steps 1-8 all checkpointed
- All devices healthy

**Actions:**

1. **Update device inventory** with FIRERPA info:
   ```yaml
   # devices.conf comment block:
   # FIRERPA: v10.0, port 65000, MCP enabled, Shizuku mode
   ```

2. **Update documentation:**
   - `docs/handoff.md` — add FIRERPA section
   - `docs/plans/firerpa-integration-plan.md` — mark all steps complete
   - `docs/history/firerpa-lamda-analysis-2026-07-10.md` — cross-reference
   - `docs/incubator/tablet-control-phone.md` — update with FIRERPA findings

3. **Update options menu** (`docs/options.md`):
   Add FIRERPA integration as completed work item.

4. **Final fleet verification:**
   ```
   make health
   # Verify FIRERPA on all opted-in devices
   # Verify all stayturgid services running
   # Verify no port conflicts
   # Verify disk usage acceptable
   ```

5. **Commit and push:**
   ```
   git add -A
   git commit -m "feat: FIRERPA integration — Ansible role, MCP bridge, MITM playbook"
   git push origin HEAD:master
   ```

**CHECKPOINT 9:**
- [ ] All documentation updated
- [ ] `make health` OK across fleet
- [ ] FIRERPA accessible on all opted-in devices
- [ ] All changes committed and pushed to origin/master
- [ ] ~/stayturgid synced (`git pull --ff-only`)

**ROLLBACK 9:** At this point, FIRERPA is deployed and integrated.
Full rollback = set `firerpa_enabled: false` everywhere and redeploy.
All stayturgid services are independent and unaffected.

---

## Global Rollback (Abort Entire Integration)

If anything goes wrong at any point and we need to fully undo:

```
1. Stop FIRERPA on all devices:
   for h in s24 p7a hd8; do
     ssh $h 'kill $(pgrep lamda-server) 2>/dev/null'
   done

2. Remove FIRERPA binaries and config:
   for h in s24 p7a hd8; do
     ssh $h 'rm -f /data/local/tmp/lamda-* /data/local/tmp/firerpa.ini'
   done

3. Disable in Ansible:
   # Set firerpa_enabled: false in all host_vars
   # Remove ansible/roles/firerpa/ and ansible/playbooks/firerpa*.yml

4. Uninstall Python client:
   pip uninstall lamda-client

5. Revert git:
   git log --oneline  # find commit before FIRERPA work
   git revert <commit>
   git push origin HEAD:master

6. Verify:
   make health   # all OK
   # All services running as before
```

**stayturgid regression risk: ZERO.** FIRERPA is purely additive.
It runs on its own port (65000), uses its own binary, and doesn't
modify any stayturgid files, configs, or services.

---

## Decision Log

Record decisions as they're made during implementation.

| Date | Step | Decision | Rationale |
|------|------|----------|-----------|
| | | | |

---

## Open Questions

1. **APK availability:** FIRERPA's "one-click APP" APK is not in GitHub
   releases. Step 1 will determine if the server binary works via
   Shizuku's `rish` shell, or if we need the APK.

2. **Port 65000 conflicts:** Verify no existing service uses this port
   on any device. If conflicts exist, change `firerpa_port` in defaults.

3. **Memory footprint:** FIRERPA server is a persistent daemon. On
   constrained devices (p7a with 12 GB), monitor RAM usage after deploy.

4. **Fire OS compatibility:** FIRERPA lists "Android 6.0+" but Fire OS
   is a fork. Step 4 tests this on hd8.

5. **MCP protocol version:** FIRERPA uses streamable-http MCP (v9.0+).
   Ensure Hermes MCP client is compatible.

---

## Phase Dependencies

```
Step 1 (Spike) ──────────────────────────────────┐
                                                  │
Step 2 (Ansible role) ── Step 3 (Deploy s24) ── Step 4 (Deploy all)
                                                     │
Step 5 (Python client) ──────────────────────────────┤
                                                     │
Step 6 (MCP bridge) ─────────────────────────────────┤
                                                     │
Step 7 (WebRTC test) ────────────────────────────────┤
                                                     │
Step 8 (MITM playbook) ──────────────────────────────┤
                                                     │
Step 9 (Rollout + docs) ◄────────────────────────────┘
```

Steps 5-8 can run in parallel after Step 4 completes.

