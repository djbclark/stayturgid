# Research — Fire OS sideloaded Google Play (hd8)

Date: 2026-07-09. Device: Fire HD 8 (`KFRASWI`), Fire OS 8 / Android 11.

## Symptom

Repeated dialog: **Google Services Framework has stopped** (App info / Close app).

Logcat shows the real crash in **`com.google.android.gms.persistent`**:

```
SecurityException: Permission Denial: com.google.android.c2dm.intent.RECEIVE
  … requires android.permission.CHANGE_DEVICE_IDLE_TEMP_WHITELIST
```

## Cause

hd8 has sideloaded Google Play (Account Manager, GSF, GMS, Play Store). **Play
Store auto-updated Google Play Services** to **26.24.34** (2026-07-05). That
build expects stock Android sysconfig (`/system/etc/sysconfig/google.xml`) and
signature permissions Fire OS does not grant sideloaded GMS.

This is a known Fire-tablet failure mode when GMS/Play Store drift too new.
Doze whitelist alone does **not** fix the broadcast permission crash.

## Fix (tested 2026-07-09)

1. **Pin GMS + Play Store** to Fire-Tools / APKMirror bundles known to work on
   Fire OS 8:
   - Google Play Services **24.35.30** (040400 arm64)
   - Google Play Store **42.6.23**
2. **Doze whitelist** GMS + GSF: `cmd deviceidle whitelist +com.google.android.gms`
3. **Disable Play Store auto-updates** (UI): Play Store → Settings → Network
   preferences → Auto-update apps → **Don't auto-update apps**

Fleet automation:

```bash
./mac/fix_hd8_google_stack.py hd8
# or: make fix-hd8-google
```

Downloads [Fire-Tools](https://github.com/mrhaydendp/Fire-Tools) GApps once to
`~/.cache/stayturgid/fire-tools/`, reinstalls pinned splits, applies whitelist.

Mac launchd (`fleet_health_monitor.py`) rate-limits the same repair when hd8 GMS
`versionCode` exceeds **250000000** (26.x line).

## Prevention

| Action | Why |
|--------|-----|
| Don't auto-update in Play Store | Stops GMS/Play self-updating past Fire-compatible builds |
| Re-run `fix_hd8_google_stack.py` after manual Play use | Play may still push GMS in background until auto-update is off |
| Avoid Fire OS OTA without checking | Amazon OTAs can break sideloaded Play; may need re-pin |

GMS **cannot** be fully frozen without root (Google pushes critical updates).
The practical Fire-tablet approach is **pin + disable Play auto-update**, not
latest GMS.

## Not fleet scope

stayturgid core stack (Termux, AutoJs6, Obtainium, Shizuku) does **not**
require Google Play. This doc is for the operator's personal Google apps on hd8.

## References

- [How-To Geek — Play Store on Fire tablet](https://www.howtogeek.com/232726/how-to-install-the-google-play-store-on-your-amazon-fire-tablet/)
- [Fire-Tools GApps bundles](https://github.com/mrhaydendp/Fire-Tools/tree/main/Fire-Tools/Gapps)
- AOSP/DeviceIdle `CHANGE_DEVICE_IDLE_TEMP_WHITELIST` — GMS crash on custom ROMs without `google.xml`
