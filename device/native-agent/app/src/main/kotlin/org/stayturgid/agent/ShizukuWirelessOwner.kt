package org.stayturgid.agent

/**
 * Revision parser for a ShizukuTendCF versionName. Writers do not use [appOwnsWirelessRestore] to
 * skip `adb_wifi_enabled`: a running server answers HEADLESS_START with "Already running" and
 * leaves the toggle off. The prompt limit is a short burst, not one prompt for the whole boot.
 */
object ShizukuWirelessOwner {
    /**
     * Historical r2842 threshold. The Termux repair and the agent no longer skip `adb_wifi_enabled`
     * from this revision; [appOwnsWirelessRestore] remains for the parser tests.
     */
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
