package org.stayturgid.agent

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.SystemClock
import android.util.Log
import java.util.concurrent.TimeUnit

/**
 * When to fire the sshd recovery (OPTIONS #44): sshd down on 2 consecutive co-monitor probes, at
 * most once per cooldown. One probe can catch sshd mid-restart under runit, hence the second.
 *
 * No Android types, so it runs in plain JVM unit tests.
 *
 * // @heals: SSHD-RUNNING
 */
class SshdRecoverDecision(
    private val downsNeeded: Int = 2,
    private val cooldownMs: Long = TimeUnit.MINUTES.toMillis(COOLDOWN_MINUTES),
) {
    private companion object {
        const val COOLDOWN_MINUTES = 5L
    }

    private var consecutiveDown = 0
    private var lastAttemptMs: Long? = null

    /** [nowMs] is a monotonic clock (SystemClock.elapsedRealtime()). */
    @Synchronized
    fun shouldAttempt(sshdState: String, nowMs: Long): Boolean {
        if (sshdState != "down") {
            consecutiveDown = 0
            return false
        }
        consecutiveDown++
        if (consecutiveDown < downsNeeded) return false
        val last = lastAttemptMs
        if (last != null && nowMs - last < cooldownMs) return false
        lastAttemptMs = nowMs
        return true
    }
}

/** Co-monitor hook: feeds each STATUS line to the decision and fires the recovery when due. */
object SshdRecover {
    private val decision = SshdRecoverDecision()

    fun onStatus(context: Context, statusLine: String) {
        val state = sshdState(statusLine)
        if (!decision.shouldAttempt(state, SystemClock.elapsedRealtime())) return
        CatastrophicRepair.appendLog("[agent] sshd-recover ${SshdRecoverIntent.send(context)}")
    }

    /** "up"/"down" from a `[agent] STATUS ... sshd=<state> ...` line, else "unknown". */
    fun sshdState(statusLine: String): String =
        Regex("""\bsshd=(up|down)\b""").find(statusLine)?.groupValues?.get(1) ?: "unknown"
}

/**
 * Asks Termux to run sshd-recover.sh under its own UID via the RUN_COMMAND intent. The send needs
 * no adb or unlocked keyguard, so it still works after a permission-change GID-kill has taken down
 * every Termux process (detection still rides the Shizuku-bound co-monitor). The fleet grants
 * com.termux.permission.RUN_COMMAND over adb (control/lib/fleet_app_profiles.json); Termux also
 * needs allow-external-apps=true.
 */
object SshdRecoverIntent {
    private const val TAG = "StayTurgidSshdRec"
    private const val PERMISSION = "com.termux.permission.RUN_COMMAND"

    // The plain script, not sshd-recover-tasker.sh: that wrapper's marker must only move when
    // the Tasker path ran.
    private const val SCRIPT_PATH =
        "/data/data/com.termux/files/home/.termux/tasker/sshd-recover.sh"

    /** Returns the outcome for agent.log; failures contain "FAILED" for the Mac-side scraper. */
    fun send(context: Context): String {
        if (context.checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            return "FAILED $PERMISSION not granted"
        }
        val intent =
            Intent("com.termux.RUN_COMMAND").apply {
                component = ComponentName("com.termux", "com.termux.app.RunCommandService")
                putExtra("com.termux.RUN_COMMAND_PATH", SCRIPT_PATH)
                putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
            }
        return try {
            // Not startService: with every Termux process dead its app is background-idle, and
            // startService into such an app throws. RunCommandService calls startForeground
            // itself, which is what startForegroundService requires of it.
            context.startForegroundService(intent)
            "RUN_COMMAND sent"
        } catch (e: SecurityException) {
            failed(e)
        } catch (e: IllegalStateException) {
            // Includes ForegroundServiceStartNotAllowedException (API 31+).
            failed(e)
        }
    }

    private fun failed(e: Exception): String {
        Log.e(TAG, "RUN_COMMAND failed", e)
        return "FAILED ${e.javaClass.simpleName}: ${e.message}"
    }
}
