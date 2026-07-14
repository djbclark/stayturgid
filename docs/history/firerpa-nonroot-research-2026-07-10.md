# FIRERPA/lamda Non-Root Viability Research

**Date:** 2026-07-10
**Context:** Evaluating FIRERPA/lamda for integration into stayturgid.
Our devices (s24, p7a, hd8) are NOT rooted. Previous analysis assumed
Shizuku mode would work. This research tests that assumption.

## Findings

### 1. Non-root IS officially supported

The README badge says `root/non--root-mode`. Documentation describes a
Shizuku installation path:

1. Install `firerpa.apk` (8.4 MB)
2. Install `Shizuku.apk`
3. Configure Shizuku, authorize FIRERPA, start service

**The APK exists** at `device-farm.com/assets/apk/firerpa.apk` (HTTP 200,
updated July 10, 2026). It is NOT in GitHub releases — only the server
binary tar.gz and Magisk module are on GitHub.

### 2. But the community is overwhelmingly rooted

**ZERO mentions** of Shizuku / non-root / rootless in 100+ GitHub issues.
The Magisk module is the most-downloaded artifact in every release.
The project targets Chinese phone farms and rooted power users.
Only 42 issues for 7.9k stars — most users engage via QQ/Telegram.

### 3. What works without root (per docs)

- Remote desktop (WebRTC/H.264)
- UI automation (clicks, swipes, text input)
- Virtual displays
- Watchers (UI change listeners)
- OCR, image matching, multi-touch
- MCP/AI agent server
- Built-in terminal, SSH, ADB
- Python client APIs (160+ functions)

### 4. What needs root

- `setprop` (write to `ro.*` system properties)
- SELinux manipulation
- System-level CA certificate install (full MITM)
- Frida hooks (may partially work via Shizuku)
- Auto-start on boot (easier with Magisk)
- `strace`, `tcpdump` at system level

### 5. Known issues

- **GitHub issue #138:** Android 16 (API 36) on Pixel 7a — Frida
  incompatibility. Confirms FIRERPA has been tested on our exact device.
- **No community reports** of Shizuku mode working or broken.
- **APK trust:** The APK is hosted on a Chinese domain (device-farm.com),
  not on GitHub. Users must trust a third-party binary.

### 6. Deployment reality

Ranked by community usage:

1. Magisk module (root) — production path
2. APK in root mode — quick setup
3. APK in Shizuku mode — documented alternative
4. Manual server tarball extraction — Docker/emulator
5. ROM integration — device farms

## Assessment

**Non-root FIRERPA is viable for core automation but clearly the secondary
path.** The entire userbase appears to be rooted Android power users. The
Shizuku path is a legitimate fallback, but:

1. Zero community validation (good or bad)
2. Known limitations on system-level features
3. APK requires trusting a Chinese-hosted binary
4. Our use case (personal devices, not phone farms) is different from
   the project's target audience

**For our specific needs** (remote desktop, UI automation, MCP bridge),
non-root mode covers the important features. MITM and Frida are nice-to-haves
that would require root.

## Recommendation

The integration idea is NOT a mistake, but the scope should be narrower:

- **DO:** WebRTC remote desktop (could solve tablet-control-phone)
- **DO:** MCP bridge (AI device control)
- **DO:** Basic UI automation APIs
- **SKIP:** MITM (needs root, we have alternatives)
- **SKIP:** Frida (needs root, not our use case)
- **SKIP:** SELinux/system properties (needs root)

**Alternative to evaluate:** scrcpy v4.0 (MITM-free, no root needed)
for remote desktop only, without FIRERPA's full stack.

---

## Bonus Finding: p7a Notification Permission Bug

**Problem:** On p7a (Android 16 / SDK 36), `pm grant com.termux.api
android.permission.POST_NOTIFICATIONS` returns exit 0 but does NOT
actually grant the permission if the app has never been launched
(stopped state). User had to manually open Termux:API and respond to
the system permission toast.

**Root cause:** Android 13+ requires the permission controller to
initialize before `pm grant` takes effect for POST_NOTIFICATIONS. If
the app is in stopped state (never launched since install or last
force-stop), the grant is a no-op.

**Impact:** `stayturgid_battery_alarm.py` fires `termux-notification`
which silently fails without POST_NOTIFICATIONS — the 30% alert never
appears.

**Fix needed:** In `android_app_privileges` role, force-start apps
before granting POST_NOTIFICATIONS:

```
adb shell monkey -p <package> -c android.intent.category.LAUNCHER 1
sleep 2
pm grant <package> android.permission.POST_NOTIFICATIONS
```

**Secondary issue:** `dumpsys package` shows TWO permission entries
per app (user 0 + Island/Private Space). The `parse_ungranted_runtime`
function may see the non-user-0 entry's `granted=false` and report
false negatives.
