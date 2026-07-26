package org.stayturgid.agent

import android.content.Context
import androidx.core.content.edit

/**
 * Latest peer-start outcome per target, persisted so the GUI + notification can
 * reflect "authorization pending" across restarts (issue #61 activation UX).
 *
 * The nag is driven by live state, not a sticky flag: a target needs the
 * one-time approval iff its most recent outcome is [PeerStarter.Outcome.AUTH_PENDING].
 * A later `ALREADY_UP`/`STARTED` clears it automatically; an `UNREACHABLE`
 * (offline, never reached auth) is not an authorization problem and does not nag.
 */
object PeerStartState {
    private const val PREFS = "stayturgid_peerstart_state"
    private const val KEY_LATEST = "latest" // "target=OUTCOME;target=OUTCOME"

    fun update(
        context: Context,
        results: List<PeerStarter.Result>,
    ) {
        val map = load(context).toMutableMap()
        for (r in results) {
            if (r.target == "-") continue // NO_TARGETS / key-init sentinels
            map[r.target] = r.outcome
        }
        prefs(context).edit {
            putString(KEY_LATEST, map.entries.joinToString(";") { "${it.key}=${it.value.name}" })
        }
    }

    /** Targets whose latest outcome is AUTH_PENDING (need the one-time approval). */
    fun pendingTargets(context: Context): List<String> = load(context).filterValues { it == PeerStarter.Outcome.AUTH_PENDING }.keys.toList()

    fun anyAuthPending(context: Context): Boolean = pendingTargets(context).isNotEmpty()

    private fun load(context: Context): Map<String, PeerStarter.Outcome> {
        val raw = prefs(context).getString(KEY_LATEST, "").orEmpty()
        if (raw.isBlank()) return emptyMap()
        return raw.split(";").mapNotNull { entry ->
            val idx = entry.lastIndexOf('=')
            if (idx <= 0) return@mapNotNull null
            val target = entry.substring(0, idx)
            val outcome = runCatching { PeerStarter.Outcome.valueOf(entry.substring(idx + 1)) }.getOrNull()
            if (outcome == null) null else target to outcome
        }.toMap()
    }

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
