package org.stayturgid.agent

import android.content.Context
import android.provider.Settings

/**
 * Per-device phase stagger for the agent's periodic loops (ADR-006).
 *
 * Every device runs the same fixed-interval loops (co-monitor, peer-start). If
 * they all fire at the same wall-clock instant (e.g. after a fleet-wide boot or
 * a Doze maintenance window that batches wakeups) they cause a coincident burst
 * of network/radio spinup. A stable per-device offset in `[0, interval)` shifts
 * each device's steady-state phase so the runs spread out.
 *
 * The offset is applied **once, after the first (prompt) iteration** — never to
 * the first post-boot check — so recovery latency is unaffected.
 */
object AgentSchedule {
    /**
     * Deterministic fraction in `[0, 1)` for a device id — stable across process
     * restarts (Java `String.hashCode` is fixed), 0.0 for a missing id so the
     * loop just isn't staggered rather than crashing.
     */
    fun fractionForId(id: String?): Double {
        if (id.isNullOrBlank()) return 0.0
        val h = id.hashCode().toLong() and 0x7FFFFFFFL
        return (h % 1_000_000L) / 1_000_000.0
    }

    fun staggerFraction(context: Context): Double =
        fractionForId(
            runCatching {
                Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            }.getOrNull(),
        )

    /** One-time phase offset in `[0, windowMs)` for this device. */
    fun staggerMs(
        context: Context,
        windowMs: Long,
    ): Long = (staggerFraction(context) * windowMs).toLong()
}
