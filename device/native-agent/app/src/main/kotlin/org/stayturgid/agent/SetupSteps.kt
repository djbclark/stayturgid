package org.stayturgid.agent

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import rikka.shizuku.Shizuku

/**
 * One outstanding-setup step, shown as a card on [SetupActivity] in this declaration order. Earlier
 * steps gate later ones — e.g. [GRANT_SHIZUKU_PERMISSION] never shows before [START_SHIZUKU] is
 * satisfied, since [Shizuku.requestPermission] needs a live binder.
 */
enum class SetupStep {
    START_SHIZUKU,
    GRANT_SHIZUKU_PERMISSION,
    ENABLE_NOTIFICATIONS,
    ENABLE_WIRELESS_DEBUGGING,
}

/**
 * Device-state inputs to [outstandingSetupSteps], gathered once per refresh so the actual
 * ordering/gating decision stays a pure, unit-testable function (see `SetupStepsTest`).
 */
data class SetupSignals(
    val shizukuBinderAlive: Boolean,
    val shizukuPermissionGranted: Boolean,
    val postNotificationsApplicable: Boolean,
    val postNotificationsGranted: Boolean,
    val wirelessDebuggingApplicable: Boolean,
    val wirelessDebuggingOn: Boolean,
) {
    companion object {
        private const val ADB_WIFI_ENABLED_KEY = "adb_wifi_enabled"
        private const val ADB_WIFI_ENABLED_ON = 1
        private const val ADB_WIFI_ENABLED_DEFAULT = 0
        private const val MIN_SDK_FOR_POST_NOTIFICATIONS = 33

        fun capture(context: Context): SetupSignals {
            val binderAlive = Shizuku.pingBinder()
            val permissionGranted = binderAlive && hasGrantedShizukuPermission()
            val notifApplicable = Build.VERSION.SDK_INT >= MIN_SDK_FOR_POST_NOTIFICATIONS
            val notifGranted =
                !notifApplicable ||
                    ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.POST_NOTIFICATIONS,
                    ) == PackageManager.PERMISSION_GRANTED
            // AuthorizeReminder marks this device as a peer-start *target* still awaiting the
            // wireless-debugging "Allow" dialog (issue #61) — the closest existing signal for
            // "this device needs ADB-over-WiFi on", since not every device in the fleet does.
            val wirelessApplicable = AuthorizeReminder.isPresent(context)
            val wirelessOn = isAdbWifiEnabled(context)
            return SetupSignals(
                shizukuBinderAlive = binderAlive,
                shizukuPermissionGranted = permissionGranted,
                postNotificationsApplicable = notifApplicable,
                postNotificationsGranted = notifGranted,
                wirelessDebuggingApplicable = wirelessApplicable,
                wirelessDebuggingOn = wirelessOn,
            )
        }

        /**
         * Best-effort read of the "Wireless debugging" toggle. `adb_wifi_enabled` isn't a
         * documented public Settings key and Fire OS in particular doesn't reliably expose it (see
         * memory/project_fireos8_adb_wireless_debugging.md) — any read failure is treated as "not
         * confirmed on" so the step still surfaces rather than silently hiding.
         */
        @Suppress("TooGenericExceptionCaught") // Settings.Global.getInt can throw depending on
        // provider state on OEM builds; any failure just means "not confirmed on".
        private fun isAdbWifiEnabled(context: Context): Boolean =
            try {
                val value =
                    Settings.Global.getInt(
                        context.contentResolver,
                        ADB_WIFI_ENABLED_KEY,
                        ADB_WIFI_ENABLED_DEFAULT,
                    )
                value == ADB_WIFI_ENABLED_ON
            } catch (_: Throwable) {
                false
            }

        @Suppress("TooGenericExceptionCaught") // Shizuku's binder call can throw when the daemon
        // dies mid-check — matches MainActivity.hasShizukuPermission()'s handling.
        private fun hasGrantedShizukuPermission(): Boolean =
            try {
                Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
            } catch (_: Throwable) {
                false
            }
    }
}

/**
 * Which [SetupStep]s are still outstanding, in the order they should be presented. Pure given
 * [signals] so this ordering/gating logic is unit-testable without an Android runtime.
 */
fun outstandingSetupSteps(signals: SetupSignals): List<SetupStep> = buildList {
    if (!signals.shizukuBinderAlive) add(SetupStep.START_SHIZUKU)
    if (signals.shizukuBinderAlive && !signals.shizukuPermissionGranted) {
        add(SetupStep.GRANT_SHIZUKU_PERMISSION)
    }
    if (signals.postNotificationsApplicable && !signals.postNotificationsGranted) {
        add(SetupStep.ENABLE_NOTIFICATIONS)
    }
    if (signals.wirelessDebuggingApplicable && !signals.wirelessDebuggingOn) {
        add(SetupStep.ENABLE_WIRELESS_DEBUGGING)
    }
}
