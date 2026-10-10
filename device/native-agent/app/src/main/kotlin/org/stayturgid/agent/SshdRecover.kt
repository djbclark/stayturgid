package org.stayturgid.agent

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.SystemClock
import android.util.Log
import java.io.IOException
import java.net.ConnectException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

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
        if (wedgeState(statusLine) == SshdWedge.FORCESTOPPED) {
            // The UserService (shell UID) just force-stopped a wedged Termux; relaunching sshd
            // needs the RUN_COMMAND holder, so it happens here, at once rather than after two
            // sshd=down probes a co-monitor interval apart.
            val sent = SshdRecoverIntent.send(context)
            CatastrophicRepair.appendLog("[agent] sshd-wedge relaunch $sent")
            SshdWedge.reprobeLater()
        }
        val state = sshdState(statusLine)
        if (!decision.shouldAttempt(state, SystemClock.elapsedRealtime())) return
        CatastrophicRepair.appendLog("[agent] sshd-recover ${SshdRecoverIntent.send(context)}")
    }

    /** "up"/"down" from a `[agent] STATUS ... sshd=<state> ...` line, else "unknown". */
    fun sshdState(statusLine: String): String =
        Regex("""\bsshd=(up|down)\b""").find(statusLine)?.groupValues?.get(1) ?: "unknown"

    /** The `sshd_wedge=<tag>` value from a STATUS line, else "skip" (see [SshdWedge.tag]). */
    fun wedgeState(statusLine: String): String =
        Regex("""\bsshd_wedge=([a-z]+)\b""").find(statusLine)?.groupValues?.get(1) ?: SshdWedge.SKIP
}

/** How the TCP connect to the sshd port ended. */
enum class SshdConnect {
    CONNECTED,
    TIMED_OUT,
    REFUSED,
    ERROR,
}

/** What one bounded connect-and-read probe of the Termux sshd concluded. */
enum class SshdBannerProbe {
    HEALTHY,

    /** Listening but not accepting: connect times out, or connects and sends no SSH banner. */
    WEDGED,

    /** Nothing listening: the sshd=down path owns that, not the wedge heal. */
    REFUSED,

    /** The probe itself was inconclusive; never a reason to act. */
    UNKNOWN,
}

/**
 * The wedge probe: an SSH server speaks first, so a banner within the read timeout is healthy. A
 * full accept queue (Recv-Q over the backlog, seen on t2e 2026-10-10) drops the SYN, so the connect
 * times out; a hung sshd connects through the kernel and never writes.
 *
 * Plain java.net, so [classify] and [connectOutcome] run in JVM unit tests.
 */
object SshdBanner {
    const val HOST = "127.0.0.1"
    const val PORT = 8022
    private const val CONNECT_TIMEOUT_MS = 3_000
    private const val READ_TIMEOUT_MS = 4_000
    private const val BANNER_BYTES = 64

    // The socket timeouts bound the probe already; this is the backstop if one ever misbehaves.
    private const val HARD_TIMEOUT_MS = 10_000L

    /** [banner]: the first bytes read; null when the read timed out, "" on an immediate EOF. */
    fun classify(connect: SshdConnect, banner: String? = null): SshdBannerProbe =
        when (connect) {
            SshdConnect.TIMED_OUT -> SshdBannerProbe.WEDGED
            SshdConnect.REFUSED -> SshdBannerProbe.REFUSED
            SshdConnect.ERROR -> SshdBannerProbe.UNKNOWN
            SshdConnect.CONNECTED ->
                when {
                    banner == null -> SshdBannerProbe.WEDGED
                    banner.startsWith("SSH-") -> SshdBannerProbe.HEALTHY
                    else -> SshdBannerProbe.UNKNOWN
                }
        }

    /** Maps the exception a failed connect threw. Android words refusals "ECONNREFUSED". */
    fun connectOutcome(e: IOException): SshdConnect {
        val m = (e.message ?: "").lowercase()
        return when {
            e is SocketTimeoutException || m.contains("etimedout") || m.contains("timed out") ->
                SshdConnect.TIMED_OUT
            e is ConnectException && (m.contains("econnrefused") || m.contains("refused")) ->
                SshdConnect.REFUSED
            else -> SshdConnect.ERROR
        }
    }

    /** One probe, hard-bounded: runs on a daemon thread so a stuck call cannot hang the caller. */
    fun probeOnce(): SshdBannerProbe {
        val result = AtomicReference(SshdBannerProbe.UNKNOWN)
        val socket = Socket()
        val worker =
            thread(isDaemon = true, name = "sshd-wedge-probe") {
                result.set(connectAndRead(socket))
            }
        worker.join(HARD_TIMEOUT_MS)
        if (worker.isAlive) {
            closeQuietly(socket)
            return SshdBannerProbe.UNKNOWN
        }
        return result.get()
    }

    private fun closeQuietly(socket: Socket) {
        try {
            socket.close()
        } catch (_: IOException) {
            // Closing only unblocks a stuck probe; nothing to recover if it fails.
        }
    }

    private fun connectAndRead(socket: Socket): SshdBannerProbe =
        try {
            socket.use { probeOpen(it) }
        } catch (_: IOException) {
            SshdBannerProbe.UNKNOWN
        }

    private fun probeOpen(socket: Socket): SshdBannerProbe {
        val connect = connect(socket)
        if (connect != SshdConnect.CONNECTED) return classify(connect)
        socket.soTimeout = READ_TIMEOUT_MS
        return classify(connect, readBanner(socket))
    }

    private fun connect(socket: Socket): SshdConnect =
        try {
            socket.connect(InetSocketAddress(HOST, PORT), CONNECT_TIMEOUT_MS)
            SshdConnect.CONNECTED
        } catch (e: IOException) {
            connectOutcome(e)
        }

    /** The first bytes the server sent; null when the read timed out, "" on an immediate EOF. */
    private fun readBanner(socket: Socket): String? =
        try {
            val buf = ByteArray(BANNER_BYTES)
            val n = socket.getInputStream().read(buf)
            if (n < 0) "" else String(buf, 0, n, Charsets.ISO_8859_1)
        } catch (_: SocketTimeoutException) {
            null
        }
}

/**
 * Debounce and rate limit for the wedge heal: the probe must fail twice, [recheckDelayMs] apart,
 * before [Verdict.WEDGED_ACT], and a heal is allowed at most once per [cooldownMs]. Probe, sleep
 * and clock are injected so the decision is a pure function in tests. [now] is monotonic.
 */
class SshdWedgeGuard(
    private val probe: () -> SshdBannerProbe,
    private val sleep: (Long) -> Unit,
    private val now: () -> Long,
    private val recheckDelayMs: Long = DEFAULT_RECHECK_MS,
    private val cooldownMs: Long = TimeUnit.MINUTES.toMillis(DEFAULT_COOLDOWN_MINUTES),
) {
    enum class Verdict {
        HEALTHY,

        /** A probe failed or was inconclusive once, but the recheck (or the probe) cleared it. */
        NOT_WEDGED,
        WEDGED_ACT,
        WEDGED_COOLDOWN,
    }

    companion object {
        const val DEFAULT_RECHECK_MS = 8_000L
        const val DEFAULT_COOLDOWN_MINUTES = 10L
    }

    private var lastActMs: Long? = null

    @Synchronized
    fun check(): Verdict {
        val first = probe()
        return when {
            first == SshdBannerProbe.HEALTHY -> Verdict.HEALTHY
            first != SshdBannerProbe.WEDGED -> Verdict.NOT_WEDGED
            inCooldown() -> Verdict.WEDGED_COOLDOWN
            else -> confirmAfterRecheck()
        }
    }

    private fun inCooldown(): Boolean {
        val last = lastActMs
        return last != null && now() - last < cooldownMs
    }

    private fun confirmAfterRecheck(): Verdict {
        sleep(recheckDelayMs)
        if (probe() != SshdBannerProbe.WEDGED) return Verdict.NOT_WEDGED
        lastActMs = now()
        return Verdict.WEDGED_ACT
    }
}

/**
 * Evidence captured into agent.log just before the force-stop destroys it. The leading hypothesis
 * is Android's cached-app freezer suspending com.termux, which `dumpsys activity processes` shows
 * (isFrozen/procState) and `ps` shows as a stopped or sleeping sshd. Every command is time-bounded
 * and its output capped; any failure is ignored. Observation only: no unfreeze step.
 */
object SshdWedgeDiagnostics {
    private const val TAG = "StayTurgidWedgeDiag"
    private const val COMMAND_TIMEOUT_SEC = 6L
    private const val READ_JOIN_MS = 500L
    private const val MAX_OUTPUT_CHARS = 1_000_000
    private const val DRAIN_CHARS = 8_192
    private const val DUMPSYS_CONTEXT_LINES = 10
    private const val DEFAULT_MAX_LINES = 40
    private const val DEFAULT_MAX_LINE_CHARS = 200

    private class Probe(
        val name: String,
        val command: List<String>,
        val keep: Regex,
        val after: Int,
    )

    private val probes =
        listOf(
            Probe(
                "dumpsys",
                listOf("dumpsys", "activity", "processes"),
                Regex("""com\.termux"""),
                DUMPSYS_CONTEXT_LINES,
            ),
            Probe(
                "ps",
                listOf("ps", "-A", "-o", "PID,PPID,STAT,WCHAN,NAME"),
                Regex("""sshd|termux"""),
                0,
            ),
            Probe("ss", listOf("ss", "-ltn"), Regex(""":8022\b"""), 0),
        )

    /**
     * Keeps the lines of [text] matching [keep], each followed by [after] context lines, never more
     * than [maxLines] lines, each cut to [maxChars]. A line is kept once however many matches cover
     * it.
     */
    fun filterLines(
        text: String,
        keep: Regex,
        after: Int = 0,
        maxLines: Int = DEFAULT_MAX_LINES,
        maxChars: Int = DEFAULT_MAX_LINE_CHARS,
    ): List<String> {
        val out = mutableListOf<String>()
        var remaining = 0
        for (line in text.lineSequence()) {
            if (out.size >= maxLines) break
            if (keep.containsMatchIn(line)) {
                remaining = after
                out += line.take(maxChars)
            } else if (remaining > 0) {
                remaining--
                out += line.take(maxChars)
            }
        }
        return out
    }

    fun capture() {
        for (probe in probes) {
            val out = run(probe.command) ?: continue
            for (line in filterLines(out, probe.keep, probe.after)) {
                CatastrophicRepair.appendLog("[agent] sshd-wedge diag ${probe.name}: $line")
            }
        }
    }

    /** Output of [command], or null on failure. Never blocks past the timeout. */
    private fun run(command: List<String>): String? =
        try {
            val p = ProcessBuilder(command).redirectErrorStream(true).start()
            val sink = StringBuffer()
            // Drain concurrently: dumpsys output can exceed the pipe buffer.
            val reader = thread(isDaemon = true, name = "sshd-wedge-diag") { drain(p, sink) }
            if (!p.waitFor(COMMAND_TIMEOUT_SEC, TimeUnit.SECONDS)) p.destroyForcibly()
            reader.join(READ_JOIN_MS)
            sink.toString()
        } catch (e: IOException) {
            Log.w(TAG, "diag ${command.first()} failed: ${e.message}")
            null
        } catch (e: InterruptedException) {
            Log.w(TAG, "diag ${command.first()} interrupted: ${e.message}")
            Thread.currentThread().interrupt()
            null
        }

    private fun drain(p: Process, sink: StringBuffer) {
        try {
            p.inputStream.bufferedReader().use { r -> copyUpTo(r, sink) }
        } catch (_: IOException) {
            // The process was destroyed after the timeout; keep what was read.
        }
    }

    private fun copyUpTo(r: java.io.Reader, sink: StringBuffer) {
        val buf = CharArray(DRAIN_CHARS)
        var n = r.read(buf)
        while (n >= 0 && sink.length < MAX_OUTPUT_CHARS) {
            sink.append(buf, 0, n)
            n = r.read(buf)
        }
    }
}

/**
 * Heals a wedged Termux sshd from inside the agent. Runs in the Shizuku UserService (UID 2000) on
 * each co-monitor tick, because only that process may force-stop Termux. Termux's own
 * sshd-recover.sh is a no-op while `sv status sshd` reads "run", which is exactly what a wedged
 * sshd reports, so the only recovery is `am force-stop com.termux`; the relaunch then goes through
 * [SshdRecover.onStatus] on the app side (RUN_COMMAND), triggered by the `forcestopped` tag.
 *
 * Never touches ADB wireless settings.
 *
 * // @heals: SSHD-RUNNING
 */
object SshdWedge {
    private const val TAG = "StayTurgidWedge"
    private const val FORCE_STOP_TIMEOUT_SEC = 8L
    private const val SETTLE_MS = 2_000L
    private const val REPROBE_DELAY_MS = 30_000L

    const val SKIP = "skip"
    const val FORCESTOPPED = "forcestopped"

    val FORCE_STOP_COMMAND = listOf("am", "force-stop", "com.termux")

    private val guard =
        SshdWedgeGuard(
            probe = { SshdBanner.probeOnce() },
            sleep = { Thread.sleep(it) },
            now = { SystemClock.elapsedRealtime() },
        )

    /** Only a running sshd can be wedged; a dead one is the sshd=down path's. */
    fun shouldProbe(sshdState: String): Boolean = sshdState == "up"

    /** The STATUS `sshd_wedge=` value. */
    fun tag(verdict: SshdWedgeGuard.Verdict): String =
        when (verdict) {
            SshdWedgeGuard.Verdict.HEALTHY -> "ok"
            SshdWedgeGuard.Verdict.NOT_WEDGED -> "unconfirmed"
            SshdWedgeGuard.Verdict.WEDGED_ACT -> FORCESTOPPED
            SshdWedgeGuard.Verdict.WEDGED_COOLDOWN -> "cooldown"
        }

    /** Probes, and force-stops Termux when confirmed wedged. Returns the STATUS tag. */
    @Synchronized
    @Suppress("TooGenericExceptionCaught") // Runs on a binder thread: must never break STATUS.
    fun check(sshdState: String): String {
        if (!shouldProbe(sshdState)) return SKIP
        return try {
            val verdict = guard.check()
            // The force-stop destroys the evidence (e.g. a frozen Termux), so record it first.
            if (verdict == SshdWedgeGuard.Verdict.WEDGED_ACT) SshdWedgeDiagnostics.capture()
            logVerdict(verdict)
            tag(verdict)
        } catch (t: Throwable) {
            Log.w(TAG, "wedge check failed: ${t.message}")
            "error"
        }
    }

    private fun logVerdict(verdict: SshdWedgeGuard.Verdict) {
        val line =
            when (verdict) {
                SshdWedgeGuard.Verdict.WEDGED_ACT ->
                    "wedged twice on 127.0.0.1:${SshdBanner.PORT}; force-stop com.termux " +
                        forceStopTermux()
                SshdWedgeGuard.Verdict.WEDGED_COOLDOWN ->
                    "still wedged inside the recovery cooldown; not acting"
                SshdWedgeGuard.Verdict.NOT_WEDGED ->
                    "probe failed once, recheck did not confirm; not acting"
                SshdWedgeGuard.Verdict.HEALTHY -> return
            }
        CatastrophicRepair.appendLog("[agent] sshd-wedge $line")
    }

    private fun forceStopTermux(): String =
        try {
            val p = ProcessBuilder(FORCE_STOP_COMMAND).redirectErrorStream(true).start()
            if (!p.waitFor(FORCE_STOP_TIMEOUT_SEC, TimeUnit.SECONDS)) {
                p.destroyForcibly()
                "rc=timeout"
            } else {
                // Let the kill land before the app relaunches sshd.
                Thread.sleep(SETTLE_MS)
                "rc=${p.exitValue()}"
            }
        } catch (e: IOException) {
            Log.w(TAG, "force-stop failed: ${e.message}")
            "rc=error:${e.message}"
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
            "rc=interrupted"
        }

    /**
     * Probes once more after the relaunch and records the result next to the other repairs. A
     * daemon thread, so the main-thread caller is not held for [REPROBE_DELAY_MS].
     */
    fun reprobeLater() {
        thread(isDaemon = true, name = "sshd-wedge-reprobe") {
            try {
                Thread.sleep(REPROBE_DELAY_MS)
                val after = SshdBanner.probeOnce()
                CatastrophicRepair.appendLog("[agent] sshd-wedge post-recovery probe=$after")
            } catch (_: InterruptedException) {
                // Process is going away; skip the probe.
            }
        }
    }
}

/**
 * Asks Termux to run sshd-recover.sh under its own UID via the RUN_COMMAND intent. The send needs
 * no adb or unlocked keyguard, so it still works after a permission-change GID-kill has taken down
 * every Termux process (detection still rides the Shizuku-bound co-monitor).
 */
object SshdRecoverIntent {
    // The plain script, not sshd-recover-tasker.sh: that wrapper's marker must only move when
    // the Tasker path ran.
    private const val SCRIPT_PATH =
        "/data/data/com.termux/files/home/.termux/tasker/sshd-recover.sh"

    /** Returns the outcome for agent.log; failures contain "FAILED" for the Mac-side scraper. */
    fun send(context: Context): String = TermuxRunCommand.send(context, SCRIPT_PATH)
}

/**
 * Runs a command in Termux under its own UID via the RUN_COMMAND intent. The fleet grants
 * com.termux.permission.RUN_COMMAND over adb (control/lib/fleet_app_profiles.json); Termux also
 * needs allow-external-apps=true.
 */
object TermuxRunCommand {
    private const val TAG = "StayTurgidTermuxRun"
    private const val PERMISSION = "com.termux.permission.RUN_COMMAND"
    const val PYTHON = "/data/data/com.termux/files/usr/bin/python"
    const val HOME = "/data/data/com.termux/files/home"

    /** Returns the outcome; failures start with "FAILED". */
    fun send(context: Context, path: String, vararg args: String): String {
        if (context.checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            return "FAILED $PERMISSION not granted"
        }
        val intent =
            Intent("com.termux.RUN_COMMAND").apply {
                component = ComponentName("com.termux", "com.termux.app.RunCommandService")
                putExtra("com.termux.RUN_COMMAND_PATH", path)
                if (args.isNotEmpty()) putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf(*args))
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
