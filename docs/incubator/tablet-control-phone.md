# Proposal — Control phone from tablet (hd8 → s24) at tablet native resolution

**Status:** parked proposal (do **not** implement unless the operator asks to revive)  
**Date:** 2026-07-10  
**Direction:** **hd8** (client / glass) controls **s24** (target)  
**Primary stack (external research):** Termux:X11 + scrcpy (virtual display) on the tablet  
**stayturgid fit:** peer ADB mesh already exists; this is a **human UX** layer, not a replacement for Mac Handsets / `ScreenControlSession`

---

## 1. Goal

Use the Fire HD 8’s **native panel** (≈ **800×1280**, portrait) as the full-screen controller for the Galaxy S24: see and drive s24 from hd8 without Mac, without cloud, and without being stuck at the phone’s tall aspect ratio in a letterboxed window.

Success looks like:

1. On **hd8**, open a session that fills the tablet glass (or a near-fullscreen Termux:X11 window).
2. That session shows **s24** content at a resolution/aspect chosen for the tablet (ideally **virtual display** sized to the tablet, not a stretched phone framebuffer).
3. Touch on hd8 maps to taps/swipes on s24 with acceptable latency over fleet ADB (USB preferred; Tailscale/LAN wireless as fallback).
4. Optional: s24’s physical screen stays on launcher / locked / other work while the virtual display is driven (scrcpy `--new-display`).
5. Coexists with stayturgid: does not break sshd/watchdog/Shizuku; respects **screen leases** if agents also touch s24.

Non-goals (v1):

- Replacing Mac-side Handsets / UI automation.
- Driving **hd8** from s24 (reverse direction) — different product.
- Root, Magisk, or commercial “remote desktop” SaaS.
- Guaranteeing 60 fps / game-quality latency on Fire SoC.

---

## 2. External research (condensed)

Operator research summary (Termux:X11 + scrcpy):

| Piece | Role |
|-------|------|
| **Termux + Termux:X11** on tablet | X11 server + Direct Touch so scrcpy’s window is usable with fingers |
| **scrcpy 2+/3+** inside that session | Mirror + inject input over ADB; **virtual display** (`--new-display=WxH[/dpi]`) decouples mirror size from phone panel |
| **Native tablet res** | Prefer `--new-display` matching tablet WxH (and DPI), not only `--max-size` on the phone’s physical display |
| **Install sketch** | `pkg install x11-repo termux-x11-nightly android-tools scrcpy` then `termux-x11 :0` + `DISPLAY=:0 scrcpy …` |

Useful flags called out in research: `--max-size`, `--new-display`, `--crop`, bitrate/FPS caps, fullscreen, optional `GALLIUM_DRIVER=virpipe`.

**stayturgid mapping of that research:**

- Tablet = **hd8** (Fire OS 8 / Android 11).
- Phone = **s24** (inventory alias; Tailscale + wireless ADB already fleet-standard).
- ADB auth already shared via fleet mesh keys / `localhost:5555` on phones; Fire uses Mac or peer help for some paths — **peer ADB hd8→s24** must be validated as a first-class path (see §4).

---

## 3. Architecture options (proposal)

### Option A — Pure tablet client (recommended v1)

```
┌──────────────── hd8 (client) ────────────────┐
│  Termux:X11  :0                               │
│       └── scrcpy  --new-display=800x1280/…    │
│                │  ADB (wireless / USB)         │
└────────────────┼──────────────────────────────┘
                 ▼
┌──────────────── s24 (target) ─────────────────┐
│  adbd :5555  +  virtual display (scrcpy)       │
│  physical panel: independent / optional        │
└────────────────────────────────────────────────┘
```

- All UX packages live on **hd8** Termux.
- s24 only needs ADB up (stayturgid already owns that).
- Launch: one wrapper script on hd8 (see §6).

### Option B — Mac bridge (fallback / lab)

hd8 does **not** run scrcpy; Mac runs `scrcpy -s s24` and streams to something hd8 views (e.g. VNC into Mac). Rejected for primary design: more latency, Mac must be awake, weaker “tablet as controller” story. Keep as debug escape hatch only.

### Option C — On-phone soft KVM (no X11)

Apps like “scrcpy android client” forks or WebRTC mirrors. Higher risk (untrusted APKs, Play/signature), less aligned with Termux FOSS stack. Park unless A fails hard on Fire GPU/X11.

**Recommendation:** implement **Option A** as an opt-in module; document B as troubleshooting.

---

## 4. Fleet prerequisites (stayturgid-specific)

| Need | Today | Gap for this feature |
|------|--------|----------------------|
| s24 ADB wireless | Yes (TAP / health) | Stable when tablet initiates connect |
| hd8 ADB client | Termux `android-tools` may already be installed | Must **`adb connect` s24** from Fire Termux (not only Mac→device) |
| Auth | Fleet ADB key / “Always allow” | Ensure **hd8’s adbkey** is authorized on s24 (or reuse shared fleet adbkey already deployed to Termux) |
| Network | Tailscale IPs in inventory | Prefer LAN if both on same Wi‑Fi for lower latency; Tailscale OK |
| Screen lease | DSCL on Mac | Tablet sessions should **acquire/release** a lease for `s24` if we add a Mac-visible marker, or at least document “human hold” so agents don’t fight glass |
| Fire OS | Termux userland, no localhost:5555 | X11 + GPU may be weaker than on stock Android tablets — **spike required** |

Peer ADB is the critical unknown: confirm `ssh hd8 'adb connect <s24_ts>:5555 && adb -s … shell id'` works with the deployed fleet adbkey.

---

## 5. Resolution strategy (native **hd8** glass)

Inventory note: hd8 is documented as **800×1280**. s24 physical is much taller (≈1080×2340 class).

| Approach | Command idea | Pros | Cons |
|----------|--------------|------|------|
| **A. Virtual display = tablet** | `scrcpy -s $S24 --new-display=800x1280/213` (DPI TBD) | Phone UI lays out for tablet aspect; true “native tablet” control surface | Needs scrcpy 3+ / Android version support on s24; some apps hate unusual sizes |
| **B. Max-size only** | `scrcpy -s $S24 --max-size=1280 --fullscreen` | Simple | Still phone aspect → letterbox or crop on tablet |
| **C. Crop phone to tablet AR** | `--crop=W:H:x:y` | Uses physical phone buffer | Loses edges of phone UI; brittle |
| **D. Match tablet DPI in X11** | `termux-x11 -dpi …` + scrcpy fullscreen | Sharp touch targets | Tuning only |

**Proposed default:** **A** (virtual display sized to hd8), with **B** as fallback if `--new-display` fails on the installed scrcpy/Android combo.

Config should be inventory-driven, not hard-coded only for this pair:

```yaml
# e.g. host_vars / group_vars sketch (not shipping yet)
stayturgid_tablet_control:
  client: hd8
  target: s24
  display: "800x1280"
  dpi: 213          # measure; Fire HD 8 density ~213–240
  max_fps: 30
  video_bit_rate: "6M"
  prefer_lan: true
```

---

## 6. Proposed stayturgid surface (when implemented)

Keep it **modular and opt-in** — same philosophy as Obtainium-only / control-only consumers.

| Artifact | Purpose |
|----------|---------|
| `docs/modules/tablet-control.md` | Operator module README (install, launch, troubleshoot) |
| `device/termux/` packages list or role flag | Optional pkgs: `scrcpy`, `termux-x11-nightly`, `x11-repo` — **only** on client hosts (`stayturgid_tablet_control_client: true`) |
| `device/termux/bin` or `~/.stayturgid/bin/stayturgid-control-phone` | Wrapper: resolve target from peers.json / devices.conf, adb connect, set `DISPLAY`, run scrcpy with inventory flags |
| `catalogs/obtainium/` optional | Termux:X11 APK / scrcpy if not fully in `pkg` (prefer pkg) |
| Ansible | Tag `tablet-control` on termux_userland or tiny role; default **off** |
| Mac | Optional: `make tablet-control-check HOSTS=hd8` — SSH and dry-run `adb devices` from tablet toward target |
| Leases | Wrapper records purpose `tablet-control` in DSCL for `s24` if Mac lease tools are reachable; else log-only |

**Suggested CLI (tablet Termux):**

```bash
# Conceptual — not shipped
stayturgid-control-phone          # default target from device.json / peers
stayturgid-control-phone s24      # explicit
stayturgid-control-phone --physical-display   # fallback without --new-display
```

**Suggested scrcpy core (research + our flags):**

```bash
export DISPLAY=:0
# after termux-x11 :0 is up and Direct Touch enabled in the app
scrcpy -s "${TARGET_SERIAL}" \
  --new-display="${W}x${H}/${DPI}" \
  --video-bit-rate 6M \
  --max-fps 30 \
  --fullscreen
```

Install path on hd8 (from research, adapted):

```bash
pkg update && pkg upgrade -y
pkg install x11-repo
pkg install termux-x11-nightly android-tools scrcpy
# Open Termux:X11 app once; enable Direct Touch
termux-x11 :0 & sleep 2
export DISPLAY=:0
```

---

## 7. Implementation phases

| Phase | Work | Exit criteria |
|-------|------|----------------|
| **0 — Spike (manual)** | On hd8: install X11+scrcpy; adb connect s24; one successful scrcpy session (physical display). Measure latency / FPS / heat | Notes in this file or research/ |
| **1 — Virtual display** | `--new-display=800x1280/…` on s24; fullscreen on hd8; tune DPI | Operator says “usable for daily tasks” |
| **2 — stayturgid wrapper** | `stayturgid-control-phone` + peers/inventory resolution + package opt-in | Idempotent deploy of client packages; one-command start |
| **3 — Polish** | Autostart docs, bitrate profiles (wifi vs USB), lease integration, fail messages if target busy | Optional OPTIONS item closed |
| **4 — Stretch** | Multi-target menu; reverse direction; audio; desktop WM (XFCE) | Only if asked |

Do **not** start phase 2 until phase 0–1 are operator-accepted on **this** hd8+s24 pair (Fire GPU is the risk).

---

## 8. Risks and interactions

| Risk | Mitigation |
|------|------------|
| Fire OS Termux:X11 flaky / slow | Spike early; fallback to physical-display scrcpy or Mac bridge |
| scrcpy in Termux older than 3.x | Pin termux-x11-nightly / check `scrcpy --help` for `--new-display` |
| ADB from Fire not authorized on s24 | Reuse fleet adbkey; document one “Allow” on s24 |
| Battery / heat on both devices | Cap FPS/bitrate; don’t auto-start at boot by default |
| Fights agent automation on s24 | Use virtual display when possible; document human lease; optional DSCL |
| `--new-display` breaks some bank/apps | Fallback `--physical-display` profile |
| Screen control inversion on s24 | Tablet path is human UX — agents still use Mac `ScreenControlSession`; don’t invert for scrcpy sessions unless requested |
| Security | ADB = full control of s24 from hd8; same trust model as fleet mesh |

---

## 9. Relation to existing stayturgid pieces

| Existing | Relation |
|----------|----------|
| Mac Handsets / `ui_driver.py` | Orthogonal: agents vs human tablet controller |
| `ScreenControlSession` | Agents only; tablet scrcpy is not inversion-gated unless we later choose to |
| Peer Handsets / fire-help | Different direction (Mac/phone help Fire); may share ADB connectivity lessons |
| `peers.json` / devices.conf | Natural source for target IP/serial on the tablet |
| Obtainium | Optional APK delivery for Termux:X11 if pkg lags |
| Incubator on-device LLM | Unrelated; do not couple |

---

## 10. Open questions (for operator / spike)

1. Prefer **virtual display** (apps re-layout to 800×1280) or **scaled phone UI** (familiar layout, letterboxing)?
2. Is **USB OTG** hd8↔s24 available for lowest latency, or Tailscale-only?
3. Acceptable max latency for “daily driver control” (e.g. &lt;100 ms vs “good enough for settings”)?
4. Should s24 **screen stay off** while controlled (privacy / battery)?
5. Auto-start on hd8 boot, or explicit launch only?

---

## 11. Verdict (stayturgid)

| | |
|--|--|
| **Worth exploring?** | Yes — matches fleet mesh ADB and multi-device lifestyle; FOSS-aligned |
| **In production path now?** | **No** — park until phases 0–1 succeed on Fire hd8 |
| **Where it would land** | Opt-in Termux client module + thin wrapper; **not** default `make deploy` |
| **Revive command** | Operator: “implement tablet-control / hd8 control s24” |

---

## 12. Source research (operator-provided)

Preserved intent from external conversation (Termux:X11 + scrcpy, native tablet resolution, virtual display, Direct Touch, bitrate/FPS flags). This proposal **adapts** that research to inventory hosts **hd8 → s24** and stayturgid deploy/lease constraints; it is not a commitment to ship every research flag as-is.

---

## 13. One-line OPTIONS candidate (if ever promoted)

> **Tablet control:** hd8 Termux:X11 + scrcpy virtual display → s24 at 800×1280; opt-in packages + `stayturgid-control-phone` wrapper.
