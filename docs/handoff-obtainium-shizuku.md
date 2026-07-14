# Handoff: Obtainium Shizuku installer — debugging history

**Goal:** Set Obtainium's installation method to "Shizuku" via headless fleet profile so APK updates use Shizuku silent install.

**Current state:** All attempts have failed. The fleet profile `{"installMethod": "shizuku"}` is written via `FleetProfileActivity` (Status: ok), but Obtainium's Settings → Installation still shows "System".

---

## What we know works

- **Shizuku side**: Obtainium is authorized in Shizuku. `shizuku.json` has `uid=10375 flags=2` (FLAG_ALLOWED). The Shizuku app → Application management shows Obtainium with the switch **ON**.
- **Shizuku server**: Running on s24 (PID 10980). HEADLESS_START/HEADLESS_STATUS work after one manual Start tap (Samsung process freezer issue).
- **AutoJs6 fleet profile**: Works correctly (23 keys applied). Same `FleetProfileActivity` pattern, different app.
- **Manual setting**: The user can manually change Settings → Installation to Shizuku and it works. The Shizuku permission dialog appears and "Allow all the time" grants it.

## What we tried that didn't work

### Attempt 1: `getSharedPreferences("FlutterSharedPreferences", ...)` — SharedPreferences XML

- **Fix:** Changed `FleetProfileApplier.kt` from `packageName + "_preferences"` to `"FlutterSharedPreferences"` (commit `aa05d6c`).
- **Result:** Still showed "System". Issue: the APK was built before the commit was pushed (timing issue), OR the `flutter.` prefix wasn't included.

### Attempt 2: DataStore (`preferencesDataStore("FlutterSharedPreferences")`)

- **Fix:** Replaced `SharedPreferences.Editor` with DataStore `runBlocking` + `fleetPreferencesDataStore.edit { ... }`.
- **Why:** Because `SharedPreferencesPlugin.kt` in `shared_preferences_android` 2.4.26 uses DataStore.
- **Result:** Still showed "System". Issue: Obtainium's `SettingsProvider` uses the **legacy** `SharedPreferences` class (line 85 of `settings_provider.dart`: `SharedPreferences.getInstance()`), NOT `SharedPreferencesAsync`. The legacy class reads from XML (`FlutterSharedPreferences.xml` via `LegacySharedPreferencesPlugin`), NOT DataStore (`FlutterSharedPreferences.preferences_pb`). These are different files.

### Attempt 3: `getSharedPreferences("FlutterSharedPreferences", ...)` — SharedPreferences XML (debug7)

- **Fix:** Reverted DataStore, went back to `SharedPreferences.Editor` with `"FlutterSharedPreferences"` name.
- **Result:** Still showed "System".

### Attempt 4: `flutter.` prefix (debug8)

- **Fix:** Added `"flutter."` prefix to all keys in the `putValue` function, matching Flutter's `SharedPreferences._prefix` default (line 22 of `shared_preferences_legacy.dart`: `static String _prefix = 'flutter.'`).
- **Why:** Flutter reads `flutter.installMethod` but the applier wrote `installMethod` — different keys.
- **Verified:** `classes.dex` now contains 282 `flutter.` strings.
- **Result:** Still shows "System".

---

## Current theory: `_getString` reads from in-memory cache, not disk

`SharedPreferences.getInstance()` at `settings_provider.dart:85` reads the XML file ONCE into `_preferenceCache`. The FleetProfileActivity writes to the XML file, but the in-memory cache is already populated from the previous read.

**Sequence that might be happening:**

1. User opens Obtainium → `init()` calls `getInstance()` → reads XML → caches `flutter.installMethod = null` or `"system"`
2. FleetProfileActivity runs → writes `flutter.installMethod = "shizuku"` to XML
3. User checks Settings → reads cached value → still shows old value

**But this should be fixed by force-stop:** Force-stop kills the process. Next open starts fresh → `getInstance()` reads fresh XML → should find `"shizuku"`.

Unless the `_preferenceCache` is persistent across restarts (e.g., Flutter's `shared_preferences` caches in native memory that survives process death?). This is unlikely — `getInstance()` reads from disk every time.

## Ideas to try

### Idea A: Write the key directly via `adb shell` and verify

Instead of the FleetProfileActivity, write to the XML file directly:

```bash
echo '<?xml version="1.0" encoding="utf-8"?>
<map>
<string name="flutter.installMethod">shizuku</string>
</map>' > FlutterSharedPreferences.xml && ...
```

But we can't access the file on Android 16 (`run-as` restricted).

### Idea B: Use Flutter's own method channel to set the value

The Flutter `shared_preferences` plugin listens on the `"shared_preferences"` method channel. Send a `setString` message via `am broadcast` or through the binary messenger. This would use the SAME code path that the Dart side uses.

```python
# Use adb shell to send a platform channel message
# This is complex and requires knowing the exact pigeon API format
```

### Idea C: Check if the file is actually being written

On a rooted device or emulator, check `/data/data/dev.imranr.obtainium/shared_prefs/FlutterSharedPreferences.xml` after the FleetProfileActivity runs. If the file has `flutter.installMethod`, the applier works. If not, the write is failing silently.

### Idea D: Add logging to the FleetProfileApplier

The `FleetProfileActivity` currently suppresses the Toast with `-e silent true`. Without it, a Toast shows the result. The user should run WITHOUT `-e silent` and see if a Toast appears at all.

### Idea E: Check if Obtainium uses a custom prefix

Search the Obtainium codebase for `SharedPreferences.setPrefix('')` or `setPrefix`. If Obtainium sets an empty prefix, the `flutter.` prefix would be wrong and keys should be written WITHOUT it.

### Idea F: Use `dumpsys` to read the SharedPreferences

On Android 16, try:

```bash
adb shell dumpsys device_policy
```

Or use `content` provider to read preferences.

### Idea G: Check the `_normalizeInstallPreference` migration

At `settings_provider.dart:122-131`:

```dart
void _normalizeInstallPreference() {
    if (_getString('installMethod') != null) return;
    final shizukuFlag = _getBool('useShizuku');
    ...
}
```

If `_getString('installMethod')` uses the in-memory cache and returns null (because the cache was populated before the fleet profile ran), it triggers the migration. But the migration uses `prefs?.setString('installMethod', 'system')` which writes `flutter.installMethod = "system"` — OVERRIDING our `"shizuku"`!

So the sequence might be:

1. FleetProfileActivity writes `flutter.installMethod = "shizuku"`
2. `_normalizeInstallPreference()` runs during init
3. It calls `_getString('installMethod')` which reads from... the in-memory cache? Or from disk?
4. If from disk, it finds `"shizuku"` and returns early (no migration)
5. If from cache, it returns null, and the migration writes `"system"` over our value

But `getInstance()` was called BEFORE the migration in `init()`. So the cache IS populated. `_getString('installMethod')` reads from cache. If the cache was populated from the XML file that the FleetProfileActivity wrote to, the cache should have `"shizuku"`.

Unless `getInstance()` was called BEFORE the FleetProfileActivity ran. This could happen if:

1. The FleetProfileActivity and Obtainium's MainActivity share the same process
2. When the user opens Obtainium, `getInstance()` fires, caching the old value
3. Then the FleetProfileActivity runs, writing a new value to disk but not updating the cache

But in our test sequence, force-stop kills the process. Then FleetProfileActivity runs in a FRESH process, writes to XML. Then the user opens Obtainium in ANOTHER fresh process, where `getInstance()` reads the fresh XML.

## Key files to examine

- `lib/providers/settings_provider.dart` — the `_normalizeInstallPreference()` and how `prefs` is initialized
- `android/app/src/main/kotlin/dev/imranr/obtainium/FleetProfileApplier.kt` — the applier
- `android/app/src/main/kotlin/dev/imranr/obtainium/FleetProfileActivity.kt` — the activity
- `pubspec.lock` — `shared_preferences` version (currently 2.5.5)
