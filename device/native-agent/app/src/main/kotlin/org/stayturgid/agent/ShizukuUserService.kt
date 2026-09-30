package org.stayturgid.agent

import android.content.Context
import android.os.Process
import android.util.Log
import androidx.annotation.Keep
import java.util.concurrent.TimeUnit

/**
 * Runs as UID 2000 (shell) under Shizuku. No non-SDK restrictions.
 *
 * Never injects input events. [pingAwake] is a no-op liveness check.
 */
class ShizukuUserService : IStayTurgidService.Stub {
    private var appContext: Context? = null

    constructor() {
        Log.i(TAG, "constructor")
        reapStaleUserServices()
        ensureLogBufferSize()
    }

    /** Available from Shizuku API v13. */
    @Keep
    constructor(context: Context) {
        appContext = context.applicationContext ?: context
        Log.i(TAG, "constructor with Context: $context")
        reapStaleUserServices()
        ensureLogBufferSize()
    }

    override fun destroy() {
        Log.i(TAG, "destroy")
        System.exit(0)
    }

    /**
     * IPC liveness check only: the host calls this periodically and rebinds when it throws. It used
     * to inject a silent KEYCODE_UNKNOWN (AutoJs6-era keep-awake, plan goal G-A), which reset the
     * screen-off timer and kept phones awake indefinitely; removed 2026-09-29 — stayturgid no
     * longer sends key/input events of any kind.
     */
    override fun pingAwake() {
        Log.i(TAG, "pingAwake ok")
    }

    override fun runComonitor(): String {
        return try {
            ComonitorProbes.runAndLog()
        } catch (t: Throwable) {
            Log.e(TAG, "runComonitor failed", t)
            "[agent] STATUS error=${t.message}"
        }
    }

    override fun repairCatastrophic(): String {
        return try {
            val r = CatastrophicRepair.repair()
            Log.i(TAG, "repairCatastrophic ok=${r.ok} detail=${r.detail}")
            // Re-probe after repair so agent.log has a fresh STATUS.
            runComonitor()
            "ok=${r.ok} detail=${r.detail}"
        } catch (t: Throwable) {
            Log.e(TAG, "repairCatastrophic failed", t)
            "ok=false detail=${t.message}"
        }
    }

    override fun repairTailscale(): String {
        return try {
            val r = CatastrophicRepair.repairTailscale()
            Log.i(TAG, "repairTailscale ok=${r.ok} detail=${r.detail}")
            runComonitor()
            "ok=${r.ok} detail=${r.detail}"
        } catch (t: Throwable) {
            Log.e(TAG, "repairTailscale failed", t)
            "ok=false detail=${t.message}"
        }
    }

    override fun ensureAdbBaseline(): String {
        return try {
            CatastrophicRepair.ensureAdbBaseline()
        } catch (t: Throwable) {
            Log.e(TAG, "ensureAdbBaseline failed", t)
            "error:${t.message}"
        }
    }

    private fun reapStaleUserServices() {
        // Scope to BuildConfig.APPLICATION_ID only (this process's own build variant), not both
        // "org.stayturgid.agent" and "org.stayturgid.agent.debug" — debug builds use
        // applicationIdSuffix ".debug", so if both variants are ever installed at once, reaping
        // both packages would kill the OTHER variant's legitimate, live UserService as "stale."
        // BuildConfig is compiled per-variant, so this is always the correct package for
        // whichever variant this class was actually built into.
        val pkg = BuildConfig.APPLICATION_ID
        val myPid = Process.myPid()
        try {
            val stale = stalePidsToReap(runPidof(pkg), myPid)
            if (stale.isNotEmpty()) {
                Log.i(
                    TAG,
                    "Reaping ${stale.size} stale UserService pid(s): $stale (my pid: $myPid)",
                )
                killPids(stale)
            }
        } catch (t: Throwable) {
            Log.w(TAG, "reapStaleUserServices failed for $pkg: ${t.message}")
        }
    }

    // logcat's ring buffers default to 256 KiB, which rotates out in seconds under normal
    // SELinux avc-audit volume (each subprocess spawn logs several "granted" lines) — too small
    // to catch the sequence around a boot/repair event by the time a human or a Mac-side script
    // goes looking. `logcat -G` needs shell/root (a plain app UID cannot resize logd's buffers),
    // so this can only run here, inside the Shizuku-bound UserService — and since Shizuku itself
    // has to be up before this constructor runs, this is the earliest point in the boot sequence
    // this process can reach with the privilege to do it. Idempotent: resizing to the same size
    // again is a cheap no-op, so this runs unconditionally on every UserService (re)start rather
    // than tracking a "did we already do this" flag.
    private fun ensureLogBufferSize() {
        // Fully qualified: android.os.Process (imported above for Process.myPid()/myUid()) would
        // otherwise shadow java.lang.Process here.
        var p: java.lang.Process? = null
        try {
            p =
                ProcessBuilder("logcat", "-b", "all", "-G", LOG_BUFFER_SIZE)
                    .redirectErrorStream(true)
                    .start()
            if (!p.waitFor(LOG_BUFFER_RESIZE_TIMEOUT_SEC, TimeUnit.SECONDS)) {
                p.destroyForcibly()
                p.waitFor()
                Log.w(TAG, "logcat -G timed out")
                return
            }
            if (p.exitValue() != 0) {
                val out = p.inputStream.bufferedReader().use { it.readText().trim() }
                Log.w(TAG, "logcat -G exited ${p.exitValue()}: $out")
            }
        } catch (t: Throwable) {
            Log.w(TAG, "ensureLogBufferSize failed: ${t.message}")
        } finally {
            // Explicit close rather than try-with-resources: destroyForcibly() above already
            // tears the process down on the timeout path, but its streams (stdin/stdout, merged
            // stderr) still need closing on every path — success, non-zero exit, or timeout — to
            // avoid leaking file descriptors from an unread/unclosed stream.
            p?.inputStream?.close()
            p?.outputStream?.close()
        }
    }

    private fun runPidof(pkg: String): String {
        val p = ProcessBuilder("pidof", "$pkg:userservice").redirectErrorStream(true).start()
        if (!p.waitFor(2, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            Log.w(TAG, "pidof timed out for $pkg")
            return ""
        }
        val out = p.inputStream.bufferedReader().use { it.readText().trim() }
        // Android/toybox pidof exits 0 (match found) or 1 (no match) as routine,
        // expected outcomes. Anything else is a real failure worth logging so a
        // broken pidof doesn't silently skip stale-service cleanup.
        if (p.exitValue() != 0 && p.exitValue() != 1) {
            Log.w(TAG, "pidof exited ${p.exitValue()} for $pkg: $out")
        }
        return out
    }

    private fun killPids(pids: List<Int>) {
        val p = ProcessBuilder(listOf("kill") + pids.map { it.toString() }).start()
        if (!p.waitFor(2, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            Log.w(TAG, "kill did not exit within timeout for pids=$pids")
            return
        }
        if (p.exitValue() != 0) {
            Log.w(TAG, "kill exited ${p.exitValue()} for pids=$pids")
        }
    }

    companion object {
        private const val TAG = "StayTurgidUS"

        // Requested size per buffer (main/system/crash/kernel) — comfortably outlasts a
        // boot+repair sequence even under hd8's heavy avc-audit log volume. logd enforces its own
        // device-specific hard cap and silently clamps down to it (verified live: hd8 accepts the
        // full 8M, s24's cap is only 5M) — that's a benign, expected outcome, not a failure.
        private const val LOG_BUFFER_SIZE = "8M"
        private const val LOG_BUFFER_RESIZE_TIMEOUT_SEC = 5L

        /** Pure: pidof output -> pids that are stale (not this process) and should be reaped. */
        internal fun stalePidsToReap(pidofOutput: String, myPid: Int): List<Int> =
            pidofOutput.split(Regex("\\s+")).mapNotNull { it.toIntOrNull() }.filter { it != myPid }
    }
}
