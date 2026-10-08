package org.stayturgid.agent

/**
 * From ShizukuTendCF r2842 the app restores its own ADB TCP port through wireless debugging, with
 * at most one "Allow wireless debugging on this network?" prompt per boot. Wireless-debugging trust
 * is per BSSID, so our own `adb_wifi_enabled=1` writes re-raise that prompt outside the limit. Pure
 * helpers for the gate; mirrors `app_owns_wireless_restore` in
 * `device/termux/py/stayturgid_repair.py` (and `fire_help_monitor.py`).
 */
object ShizukuWirelessOwner {
    /** Keep equal to `SHIZUKU_OWNS_WIFI_RESTORE_REVISION` in the Python repair. */
    const val OWNS_WIFI_RESTORE_REVISION = 2842

    // versionName is "ShizukuTendCF <upstream>.r<commit count>". Upstream Shizuku also has an
    // ".rNNNN" in its versionName, so the ShizukuTendCF prefix is required.
    private val VERSION_RE = Regex("""ShizukuTendCF\s+\d+(?:\.\d+)*\.r(\d+)\b""")

    /** `dumpsys` line carrying the installed versionName of [pkg]. */
    fun versionNameCommand(pkg: String): String =
        "dumpsys package $pkg 2>/dev/null | grep versionName="

    /** The rNNNN of a ShizukuTendCF versionName in [text], or null (unknown, not ShizukuTendCF). */
    fun parseRevision(text: String?): Int? =
        text?.let { VERSION_RE.find(it)?.groupValues?.get(1)?.toIntOrNull() }

    fun appOwnsWirelessRestore(revision: Int?): Boolean =
        revision != null && revision >= OWNS_WIFI_RESTORE_REVISION
}
