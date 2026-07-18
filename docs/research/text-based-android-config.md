<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# Best Practices: Text-Based Configuration for Android Apps

This document is based on the experience of adding fleet/headless text-based configuration support to AutoJs6 ([SuperMonster003/AutoJs6#553](https://github.com/SuperMonster003/AutoJs6/issues/553)). The goal is to turn fragile GUI automation into a single, repeatable, reviewable JSON (or similar) file that can be pushed to a device and applied without tapping through screens.

---

## 1. Why this matters for fleet automation

| GUI automation                                                          | Text-based configuration                                      |
| ----------------------------------------------------------------------- | ------------------------------------------------------------- |
| Breaks when layouts, themes, or translations change                     | Stable across app versions as long as the schema is supported |
| Requires unlocked screen, exact timing, and coordinate/label heuristics | Can run headless, via `adb`, Termux, or a boot script         |
| Hard to review, diff, or version-control                                | Lives in git, can be templated per device, and audited        |
| Difficult to reproduce across devices with different DPI/languages      | Identical input produces identical output on every device     |

For a fleet of Android devices (phones, tablets, Fire TV sticks), the same configuration must be applied repeatedly. Text-based config is the difference between "works on my device" and "works on every device every boot."

---

## 2. The pattern we used in AutoJs6

The AutoJs6 implementation introduced three main pieces:

1. **A centralized applier** (`FleetProfileApplier`) — reads a JSON profile and applies every setting through the app's internal preference APIs, exactly the same way the GUI does.
2. **An exported entry point** (`FleetProfileActivity`) — an `android:exported="true"` activity that accepts an `Intent` with a profile path or URI, applies it, and reports success/failure.
3. **A bundled reference profile** (`fleet_profile_default.json`) — ships with the app so users can copy and edit it.

The key insight: **do not bypass the app's preference system**. Instead, feed the text profile into the same helper methods that the GUI already uses. This guarantees that the resulting app state is identical to a human tapping through the settings, and it avoids duplicating logic.

---

## 3. Design best practices

### 3.1 Mirror the GUI mental model

Use the same section/key names that appear in the GUI. If users see a toggle called "Enable accessibility service," the profile key should be `enableAccessibilityService` or similar. The profile should read like a human-readable checklist of the settings screen.

### 3.2 Support a single file per device

A fleet wants one artifact per device. Bundle all relevant settings into one profile file. Avoid forcing the operator to run multiple commands or manage multiple files for one device.

### 3.3 Provide a no-op/dry-run mode

Add a mode that validates the profile without changing state. This lets CI or deploy scripts catch typos, unsupported keys, or missing values before touching the device.

### 3.4 Report errors clearly

If a key is unknown, a value is invalid, or a permission is missing, the applier should return a structured error that names the offending key. Silent failures are the enemy of fleet automation.

### 3.5 Keep backward compatibility

The GUI must keep working exactly as before. The text profile is an additional input path, not a replacement. Old preference files or databases should not be migrated or reset unless the profile explicitly asks for it.

### 3.6 Make the schema versioned

Include a `version` field in the profile. The applier can warn or reject profiles that are newer than the build understands, which prevents half-applied configurations.

---

## 4. Implementation best practices

### 4.1 One applier, not many scripts

```
FleetProfileApplier.apply(context, profile)
```

Call this from:

- The exported activity (for external automation)
- A GUI import screen (for manual users)
- A test harness (for CI)

### 4.2 Use the existing preference/storage layer

In AutoJs6 this meant calling `Pref.getDefaultPrefInstance().putString(...)` and similar helpers rather than writing to `SharedPreferences` directly. Using the app's abstraction layer ensures notifications, migrations, and side effects happen correctly.

### 4.3 Register the entry point in the manifest

```xml
<activity
    android:name=".core.pref.fleet.FleetProfileActivity"
    android:exported="true"
    android:theme="@android:style/Theme.NoDisplay"
    android:excludeFromRecents="true"
    android:launchMode="singleInstance"
    android:permission="android.permission.WRITE_EXTERNAL_STORAGE" />
```

Make it as lightweight as possible: no UI, no history entry, single-instance. The activity should finish immediately after applying the profile.

### 4.4 Accept the profile by path or by content

- **Path**: `intent.putExtra("path", "/sdcard/stayturgid/fleet_profile.json")` — useful for files already on the device.
- **Content**: `intent.setDataAndType(uri, "application/json")` — useful for `adb shell am start` with a content URI or for future cloud provisioning.

Support both.

### 4.5 Ship a default reference profile

Include `assets/fleet_profile_default.json` in the APK. It serves as:

- A documented schema example
- A copy-paste starting point for operators
- A built-in test fixture

### 4.6 Guard dangerous operations

If a profile can enable accessibility services, grant permissions, or toggle wireless debugging, make those sections explicit. Require boolean flags like `enableAccessibilityService: true` rather than applying them silently. This prevents a stale or accidentally-shared profile from changing security-sensitive state.

---

## 5. Build and release best practices

### 5.1 Fix the build first

Before adding any new public API, make sure the upstream project compiles cleanly. In the AutoJs6 branch we had to fix pre-existing issues (`LogBottomSheet` Kotlin access, missing color resources) before the feature could even be verified. If the upstream build is broken, the maintainers will not merge the PR.

### 5.2 Build a test APK and run it

A debug build proves the feature links and runs. Use the test build to:

- Confirm the activity resolves the intent
- Verify the profile applies without crashing
- Check that the GUI still works after applying a profile

### 5.3 Publish the test binaries on your fork

Create a GitHub release on your fork (not the upstream repo) with a clear, fork-specific naming convention. For example:

```
autojs6-v6.7.0-fleet-profile-553-debug-arm64-v8a.apk
```

This avoids confusion with official upstream releases and makes it easy for testers to find the exact build.

### 5.4 Document the exact invocation

Provide the `adb` or `am start` command that applies the profile. Do not make testers reverse-engineer the intent extras.

```bash
adb shell am start -n org.autojs.autojs6/.core.pref.fleet.FleetProfileActivity \
    -e path /sdcard/stayturgid/autojs6/fleet_profile.json
```

---

## 6. Upstreaming best practices

### 6.1 Open an issue before the PR

Explain the problem: "Fleet operators need to apply the same settings to many devices without GUI automation." Describe the proposed solution, the schema, and the entry point. Ask for feedback on naming and security.

### 6.2 Keep the PR focused

The PR should add one thing: text-based configuration. Do not bundle unrelated refactors, build fixes, or new features. If you need to fix the build to verify your change, put those fixes in the same PR only if they are tiny; otherwise split them.

### 6.3 Include tests and documentation

- Unit tests for the applier (pure logic, no Android runtime needed)
- An instrumentation test that launches the activity with a profile
- A markdown doc explaining the schema and how to invoke it

### 6.4 Offer to maintain the feature

Let upstream maintainers know you are running the test build on real devices and will report back. This reduces the perceived maintenance burden and increases the chance of merging.

---

## 7. Candidate apps in the stayturgid ecosystem

The following apps are part of the stayturgid stack and currently rely on GUI automation or manual setup that could be replaced by text-based configuration. All are open source unless noted.

### 7.1 Shizuku (the `thedjchi` fork)

|                 |                                                                                                                                                                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package         | `moe.shizuku.privileged.api`                                                                                                                                                                                                          |
| Current pain    | `tapStartButton()` in `device/autojs6/lib/shizuku.js` opens the Shizuku manager and taps the **Start** button by text matching or blind coordinates. It needs an unlocked screen and can fail when the UI language or layout changes. |
| What to ask for | A broadcast receiver or a service command that starts the Shizuku server directly when the app is already authorized, e.g. `am startservice -n moe.shizuku.privileged.api/.ServerService`.                                            |
| Upstream status | The `thedjchi` fork is maintained on GitHub. The change is small and security-sensitive, so it should be paired with a manifest permission or a `android:permission` on the receiver.                                                 |
| Impact          | High — removes the most fragile, screen-on dependency in the whole catastrophic-repair path.                                                                                                                                          |

### 7.2 Obtainium

|                 |                                                                                                                                                                                                                                               |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package         | `dev.imranr.obtainium`                                                                                                                                                                                                                        |
| Current pain    | Two UI automation flows: `apply_updates.py` taps fixed coordinates to bulk-install updates, and `enable_shizuku_installer.py` scrolls through settings to toggle the Shizuku installer switch.                                                |
| What to ask for | (1) A broadcast or shortcut to trigger the "Update all apps" flow without coordinate taps. (2) A `pm grant`-compatible way to enable the Shizuku installer, or a content-provider/config flag that can be set with `settings put` / `appops`. |
| Upstream status | Active open-source project on GitHub. The maintainer is receptive to automation-friendly features.                                                                                                                                            |
| Impact          | Medium-High — makes the default update path fully unattended and removes the need for `ScreenControlSession` during updates.                                                                                                                  |

### 7.3 Aurora Store

|                 |                                                                                                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package         | `com.aurora.store`                                                                                                                                                     |
| Current pain    | `control/tools/play/configure_aurora.py` walks through the first-run carousel, selects anonymous session, and toggles installer/update settings via UI parsing.        |
| What to ask for | A "setup complete" file or shared-preferences flag that can be seeded before first launch, plus a programmatic way to set the installer and update-filter preferences. |
| Upstream status | Open source on GitLab/GitHub. Currently **parked** in stayturgid, so this is lower priority unless Play-sourced APKs are re-enabled.                                   |
| Impact          | Medium — only valuable if the Play/Aurora module is re-enabled.                                                                                                        |

### 7.4 Neo Store

|                 |                                                                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package         | `com.machiav3lli.fdroid`                                                                                                                          |
| Current pain    | Historically needed UI automation to grant Shizuku installer permission; stayturgid now patches `shizuku.json` directly via Ansible.              |
| What to ask for | A documented intent or provider API for setting the default installer (Shizuku/Dhizuku/Sui) so the JSON patch can be replaced by a supported API. |
| Upstream status | Open source on GitHub. Currently **parked** alongside Aurora.                                                                                     |
| Impact          | Low-Medium — the current Ansible workaround is already functional.                                                                                |

### 7.5 Tailscale

|                 |                                                                                                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package         | `com.tailscale.ipn`                                                                                                                                                                                   |
| Current pain    | `device/autojs6/lib/tailscale.js` already relaunches Tailscale via `am start` to recover a dead tun0, but there is no programmatic way to force a re-auth or choose a tailnet without opening the UI. |
| What to ask for | Documented intents for `start`, `stop`, and `status`, plus a way to seed the login server and auth key via a file (already partially supported on some platforms).                                    |
| Upstream status | Open source on GitHub. Tailscale already has rich platform support; Android intents are the main gap.                                                                                                 |
| Impact          | Medium — would make tailnet onboarding and recovery more reliable.                                                                                                                                    |

### 7.6 AutoJs6

|              |                                                                                                                                                                                                                                                                                                          |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Package      | `org.autojs.autojs6`                                                                                                                                                                                                                                                                                     |
| Current pain | Before the fleet-profile feature, AutoJs6 required GUI automation to grant storage, Shizuku, notification, and battery permissions.                                                                                                                                                                      |
| Status       | **Already addressed** by `FleetProfileActivity` + `FleetProfileApplier` in [djbclark/AutoJs6#feature/fleet-profile-553](https://github.com/djbclark/AutoJs6/tree/feature/fleet-profile-553). The upstream issue is [SuperMonster003/AutoJs6#553](https://github.com/SuperMonster003/AutoJs6/issues/553). |
| Impact       | This is the proof of concept for the whole pattern described above.                                                                                                                                                                                                                                      |

---

## 8. Recommended priority order

If you are going to upstream changes, tackle them in this order:

1. **Shizuku** — highest impact, smallest surface, and the change is security-auditable.
2. **Obtainium** — removes the most active UI automation in the default stack.
3. **Tailscale** — nice-to-have for onboarding, but already mostly stable.
4. **Aurora Store** — only if the Play/Aurora module is re-enabled.
5. **Neo Store** — lowest priority because the current workaround is solid.

---

## 9. Quick reference: AutoJs6 fleet profile invocation

```bash
# Push profile
adb push device/autojs6/fleet_profile.json /sdcard/stayturgid/autojs6/fleet_profile.json

# Apply
adb shell am start -n org.autojs.autojs6/.core.pref.fleet.FleetProfileActivity \
    -e path /sdcard/stayturgid/autojs6/fleet_profile.json
```

Test build binaries are published at:
https://github.com/djbclark/AutoJs6/releases/tag/v6.7.0-fleet-profile-553-debug

---

_Last updated: 2026-07-11_
