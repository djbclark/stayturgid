# Inferno in Termux for Distributed Android Fleet Control

**Document for Coding AI**  
**Date:** 2026-07-09  
**Author:** Grok (based on conversation with user)  
**Goal:** Enable a fleet of non-rooted Android devices to act as a single distributed entity using Inferno's namespace and Styx model, with virtual filesystems for privileged control (app permissions + system settings) via Shizuku.

---

## 1. Executive Summary & End Goals

**Primary Objective**  
Run **hosted Inferno** inside Termux on multiple Android devices so they can form a unified distributed system. Devices should be able to:

- Export and mount namespaces across the fleet via Styx (9P).
- Create **synthetic/virtual files** that allow reading and modifying app permissions and system settings.
- Achieve the closest possible "root-like" privileged access **without rooting** the devices.

**Key Constraints**

- No actual root on devices.
- Use **Shizuku** (or equivalent) for elevated privileges.
- Everything must run in Termux (user-space, no custom ROMs or invasive changes).
- Focus on virtual filesystems as the control interface (Plan 9/Inferno philosophy).

**Why Inferno (hosted) instead of plan9port?**

- Superior native support for synthetic files (`file2chan`).
- Designed from the ground up as a distributed operating system.
- Cleaner integration of Styx, namespaces, auth, and remote execution.
- Better conceptual match for "fleet as one entity".

---

## 2. Research Findings

### 2.1 Inferno Hosted on Linux/Termux

- Inferno can be built as a **hosted** application (`emu` binary) on Linux.
- Standard build process (from reliable sources like bluishcoder.co.nz and inferno-os repo):
  1. Clone repo.
  2. Edit `mkconfig` → `SYSHOST=Linux`, `OBJTYPE=386` (even on 64-bit hosts in most cases).
  3. Run `makemk.sh`, set PATH, `mk nuke`, `mk install`.
- `emu` is the runtime. It can be started with flags to set root directory and JIT.
- Challenges in Termux:
  - Termux is 64-bit ARM on modern devices. Traditional `emu` is 32-bit (386).
  - Possible solutions: Use 32-bit support in Termux or a 64-bit fork (e.g., `inferno64` experiments exist).
  - Storage: Termux has its own home; Scoped Storage limits broad Android FS access.
- No recent public reports of Inferno + Termux + Shizuku combination (this is novel work).

### 2.2 Shizuku for Privileged Access (Non-Root)

- Shizuku allows apps to use privileged Android APIs without root by using ADB or wireless debugging.
- In Termux: Use the `rish` wrapper (exported from Shizuku app) to run commands with elevated privileges.
- Common pattern:
  ```bash
  rish -c "settings put global ..."
  rish -c "appops set <package> ..."
  ```
- This enables control over many system settings and some permission-related operations (`appops`, package manager queries, etc.).
- Limitations: Not full root. Cannot access arbitrary protected files or perform all system-level changes.

### 2.3 Virtual/Synthetic Filesystems in Inferno

- Core primitive: `file2chan` in Limbo.
- Allows creation of virtual files whose read/write behavior is implemented in Limbo code.
- Perfect for control interfaces:
  - `/ctl/permissions/com.example.app` → read current state, write "grant" or "revoke".
  - `/ctl/settings/global/always_on_display` → control settings.
- These can be exported via Styx and mounted on other devices.

### 2.4 Distributed Fleet Architecture

- Each device runs its own Inferno instance in Termux.
- Use Styx listeners to export control namespaces.
- Mount remote namespaces (`mount -k tcp!deviceIP ...` with auth).
- Result: Unified view across devices (e.g. `/n/phone2/ctl/...`).

### 2.5 Key Limitations (Honest Assessment)

- **No true root**: Shizuku + virtual files get you significantly closer than a normal app, but many deep system operations remain restricted.
- **Background execution**: Android will kill Termux/Inferno processes. Requires wake locks + foreground services.
- **Scoped Storage**: Accessing broad Android storage from Termux/Inferno is restricted.
- **Build complexity**: 32-bit vs 64-bit `emu` may require troubleshooting.
- **No prior art**: This specific combination (Inferno + Termux + Shizuku + virtual permission control) has no public tutorials.

---

## 3. High-Level Architecture

```
Device 1 (Coordinator or any device)
├── Termux
│   ├── Shizuku (rish wrapper)
│   └── Inferno (emu)
│       ├── Control Namespace (synthetic files via file2chan)
│       │   ├── /ctl/permissions/...
│       │   └── /ctl/settings/...
│       └── Styx listener (exports control namespace)

Device 2, 3, ... (fleet members)
├── Same structure as Device 1
└── Mounts from other devices into local namespace

Result: Any device can see/control others via paths like:
/n/device2/ctl/permissions/com.example.app
```

**Data Flow Example**

1. User (or script) on Device 1 writes to `/n/device2/ctl/permissions/com.foo.app`.
2. Inferno on Device 2 receives the write via Styx.
3. Limbo `file2chan` handler executes elevated command via `rish`.
4. Permission or setting is changed on Device 2.

---

## 4. Step-by-Step Implementation Plan

### Phase 0: Prerequisites on All Devices

- Install **Termux** (F-Droid recommended).
- Install **Shizuku** from Play Store.
- Enable Wireless Debugging or pair Shizuku via ADB.
- In Shizuku app → "Use Shizuku in terminal apps" → Export `rish` and `rish_shizuku.dex`.
- In Termux:
  ```bash
  termux-setup-storage
  mv ~/storage/shared/rish/rish /data/data/com.termux/files/usr/bin/
  mv ~/storage/shared/rish/rish_shizuku.dex /data/data/com.termux/files/usr/bin/
  chmod +x /data/data/com.termux/files/usr/bin/rish
  ```
- Test: `rish -c "id"` (should show elevated context).

### Phase 1: Build Hosted Inferno in Termux

```bash
pkg update && pkg install clang make git
git clone https://github.com/inferno-os/inferno-os.git ~/inferno
cd ~/inferno

# Edit mkconfig
sed -i 's/SYSHOST=.*/SYSHOST=Linux/' mkconfig
sed -i 's/OBJTYPE=.*/OBJTYPE=386/' mkconfig
sed -i "s|ROOT=.*|ROOT=$PWD|" mkconfig

sh makemk.sh
export PATH=$PWD/Linux/386/bin:$PATH
mk nuke
mk install
```

**Run test**:

```bash
export EMU="-r$PWD -c1"
emu
# Inside emu:
; ls
; wm/wm   # optional GUI test (may need X11 or headless)
```

**Note on 32-bit vs 64-bit**: If `emu` fails due to architecture, investigate 64-bit forks or Termux multiarch support.

### Phase 2: Basic Inferno Environment + Styx

- Create a startup script that sets up a clean namespace.
- Start a Styx listener on a known port exporting a control directory.

### Phase 3: Create Virtual Control Files (Limbo)

Example skeleton for a permission control file (`/appl/ctl/permissions.b`):

```limbo
implement Permissions;

include "sys.m"; sys: Sys;
include "draw.m";
include "file2chan.m"; file2chan: File2chan;

Permissions: module {
    init: fn(ctxt: ref Draw->Context, args: list of string);
};

init(ctxt: ref Draw->Context, args: list of string) {
    sys = load Sys Sys->PATH;
    file2chan = load File2chan File2chan->PATH;

    # Create synthetic file
    (c1, c2) := file2chan->file2chan("/ctl/permissions/com.example.app", nil);

    for(;;) {
        alt {
        (nil, data, fid, rc) := <-c1.read =>
            if(rc != nil) {
                # Read current permission state (via rish)
                state := sys->fd2data(sys->open("/dev/null", Sys->OREAD)); # placeholder
                rc <-= (state, nil);
            }
        (nil, data, fid, wc) := <-c1.write =>
            if(wc != nil) {
                cmd := string data;
                if(cmd == "grant\n") {
                    # Execute via Shizuku
                    sys->pipe(...); # or use os->exec with rish wrapper
                    # Example: rish -c "appops set com.example.app ..."
                }
                wc <-= (len data, nil);
            }
        }
    }
}
```

**Next**: Make the handler call a shell script that uses `rish` for actual privileged commands.

### Phase 4: Integrate Shizuku Elevation

- Create a small shell script `elevated.sh` that Termux/Inferno can call:
  ```bash
  #!/data/data/com.termux/files/usr/bin/sh
  rish -c "$*"
  ```
- From Limbo, use `os->exec` or pipe to run commands through this script when virtual files are written.

### Phase 5: Distributed Namespace Setup

On each device, start a Styx server exporting the control tree.

Example (in Inferno shell or startup script):

```rc
styxlisten -A tcp!*!styx {export /ctl &}
```

On coordinator:

```rc
mount -k tcp!192.168.1.XX!styx /n/phone2
# Now /n/phone2/ctl/permissions/... is available
```

Use Inferno's auth mechanisms (`getauthinfo`, keyring) for security.

### Phase 6: Background Operation & Fleet Deployment

- Use `termux-wake-lock`.
- Run Inferno via Termux boot scripts or a foreground service wrapper.
- For production fleet: Create a simple startup Limbo program or rc script that auto-exports the control namespace and optionally auto-mounts known peers.

### Phase 7: Testing & Hardening

- Test permission changes from one device affecting another.
- Add error handling and logging in Limbo handlers.
- Implement basic discovery (manual IP list or simple mDNS if possible).

---

## 5. Challenges & Mitigations

| Challenge                            | Mitigation                                              | Status |
| ------------------------------------ | ------------------------------------------------------- | ------ |
| 32-bit emu on 64-bit Termux          | Use 386 target; test thoroughly or explore 64-bit forks | Medium |
| Background killing                   | termux-wake-lock + foreground notification              | High   |
| Scoped Storage                       | Work within Termux home + app-specific dirs             | Medium |
| Shizuku command execution from Limbo | Wrapper script + os->exec or pipes                      | High   |
| No prior tutorials                   | Build incrementally; test each layer                    | —      |
| Security of virtual control          | Use Inferno auth + restrict exported namespaces         | High   |

---

## 6. Open Questions for Further Research

1. Best way to reliably run 32-bit `emu` on modern 64-bit Termux/ARM devices?
2. Most reliable way to call `rish` from inside Limbo (pipes vs `os` module vs external script)?
3. Can we expose more powerful controls (e.g., via `pm grant` with Shizuku)?
4. Discovery mechanism for dynamic fleets (instead of static IPs)?
5. Performance impact of running full Inferno + Styx listeners continuously?

---

## 7. Key Resources

- Inferno sources: https://github.com/inferno-os/inferno-os
- Hosted Inferno guide: https://bluishcoder.co.nz/2014/12/31/using-inferno-os-on-linux/
- Shizuku + Termux setup: Search for recent "Shizuku Termux rish" guides (2025+)
- `file2chan` examples: Inferno documentation and old cluster tutorials (debu.gs)
- Plan 9 / Inferno distributed examples: 9fans archives, inferno-os Google Group

---

**This document is ready for a coding AI to follow or expand upon.**  
It balances the elegant Inferno distributed model with the practical realities of modern non-rooted Android + Shizuku.

Next recommended action for the AI: Start with **Phase 0 + Phase 1** (Termux + Shizuku + basic Inferno build) and report back on any build issues specific to the user's device architecture.
