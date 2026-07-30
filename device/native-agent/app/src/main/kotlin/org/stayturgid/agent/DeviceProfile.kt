package org.stayturgid.agent

import android.util.Log
import java.io.File

/**
 * Reads the fleet-provisioned on-device profile (`device.json`) that Termux/Ansible already consume
 * (`stayturgid_repair.py`, `stayturgid_shell.py`) so the Kotlin side can honor the same
 * `privilegedShellExpected` flag instead of guessing.
 *
 * Fire OS's `adbd` drops any ADB connection whose peer is local to the device (#60) — Termux's own
 * `localhost:5555` scripts are already gated off there via this flag (`privilegedShellExpected:
 * false` in the device's `device.json`). [CatastrophicRepair]'s wireless-shell repair step performs
 * the exact same loopback connect and needs the same gate.
 *
 * Regex extraction of a single known boolean field, not full JSON parsing — `org.json.JSONObject`
 * is an unconfigurable Android stub under plain JVM unit tests (matches the no-Android-deps
 * philosophy [PeerStartCommands] already documents for its own testable pure functions).
 */
object DeviceProfile {
    private const val TAG = "StayTurgidDeviceProfile"
    private const val PROFILE_PATH = "/sdcard/stayturgid/state/device.json"
    private val PRIVILEGED_SHELL_EXPECTED_FIELD =
        Regex(""""privilegedShellExpected"\s*:\s*(true|false)""")

    /** True unless the device's profile explicitly says otherwise (matches the Python default). */
    fun isPrivilegedShellExpected(): Boolean =
        try {
            val file = File(PROFILE_PATH)
            if (file.canRead()) parsePrivilegedShellExpected(file.readText()) else true
        } catch (e: java.io.IOException) {
            Log.w(TAG, "device profile read failed: ${e.message}")
            true
        }

    /** Pure parse, kept separate from file I/O so it is unit-testable off-device. */
    fun parsePrivilegedShellExpected(json: String): Boolean =
        PRIVILEGED_SHELL_EXPECTED_FIELD.find(json)?.groupValues?.get(1)?.toBooleanStrictOrNull()
            ?: true
}
