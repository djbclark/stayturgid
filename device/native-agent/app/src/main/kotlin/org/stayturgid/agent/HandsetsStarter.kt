package org.stayturgid.agent

import android.content.Context
import android.util.Log
import java.util.Base64
import org.stayturgid.agent.adb.AdbAuthPendingException
import org.stayturgid.agent.adb.AdbClient
import org.stayturgid.agent.adb.AdbKey

/**
 * Handsets-start: launch the Handsets UI-automation daemon (`hs.jar`) on a Fire-OS device over
 * external ADB, with no dependency on the Mac (issue #121).
 *
 * Same shape as [PeerStarter]'s Shizuku peer-start (issue #61) — connect to the target's `adbd`
 * with the agent's own embedded [AdbClient] + on-device [AdbKey], then drive the target purely over
 * `shell:` commands. The one genuinely new piece vs. Shizuku is the payload: `hs.jar` isn't already
 * installed on the target (Shizuku is, as an app), so it has to be transferred. The embedded
 * [AdbClient] only implements the `shell:` service (see its class doc — it never writes stdin to a
 * stream), not the `sync:` file-transfer service `adb push` uses, so the jar is written by piping
 * base64 chunks through `base64 -d` shell commands instead of a real sync-protocol push. `hs.jar`
 * itself ships as an APK asset (`app/src/main/assets/hs.jar`, MIT-licensed — see the companion
 * `hs.jar.LICENSE.txt` asset for the required attribution) so the agent never depends on the Mac
 * having a copy.
 *
 * The wire steps mirror `control/bin/fire_peer_help.py:cmd_handsets_start`: push `hs.jar` (skip if
 * already present), kill any existing `hsd<port>`-tagged process, launch `dev.handsets.daemon.Main`
 * via `app_process`, and poll the port for up to ~12s.
 */
object HandsetsStarter {
    private const val TAG = "StayTurgidHandsets"
    private const val ASSET_NAME = "hs.jar"

    /** Settle time after `pkill` before launching the replacement process. */
    private const val KILL_SETTLE_MS = 300L

    private const val POLL_INTERVAL_MS = 400L
    private const val POLL_TIMEOUT_MS = 12_000L

    private const val START_OUTPUT_LOG_CHARS = 400
    private const val FAILURE_DETAIL_CHARS = 300
    private const val ERROR_MESSAGE_CHARS = 200

    /**
     * Connect to [target]'s adbd, ensure `hs.jar` is present, and (re)start the daemon on [port].
     */
    @Suppress("TooGenericExceptionCaught")
    fun ensureHandsets(
        context: Context,
        target: PeerTarget,
        key: AdbKey,
        port: Int = HandsetsStartCommands.DEFAULT_PORT,
    ): PeerStarter.Result {
        return try {
            AdbClient(target.host, target.port, key).use { client ->
                client.connect()
                ensureHandsets(context, target, client, port)
            }
        } catch (t: AdbAuthPendingException) {
            authPending(target, t)
        } catch (t: java.io.IOException) {
            failed(target, t)
        } catch (t: IllegalStateException) {
            failed(target, t)
        }
    }

    /**
     * Reuse [PeerStarter]'s already-connected periodic-loop client. Delegates straight to the
     * shared implementation with a lazy jar loader, so the liveness poll runs exactly once and the
     * asset is only ever read on the confirmed not-up path — a healthy daemon must never pay for a
     * jar read, and a transient asset-read failure must never mark a healthy daemon FAILED.
     */
    internal fun ensureHandsets(
        context: Context,
        target: PeerTarget,
        client: AdbClient,
        port: Int = HandsetsStartCommands.DEFAULT_PORT,
    ): PeerStarter.Result = ensureHandsets(target, client, port) { loadJar(context) }

    /** Same as the [Context] overload, but with the jar bytes already loaded (unit-test seam). */
    @Suppress("TooGenericExceptionCaught")
    fun ensureHandsets(
        target: PeerTarget,
        key: AdbKey,
        jarBytes: ByteArray,
        port: Int = HandsetsStartCommands.DEFAULT_PORT,
    ): PeerStarter.Result {
        val name = target.toString()
        return try {
            AdbClient(target.host, target.port, key).use { client ->
                client.connect()
                ensureHandsets(target, client, port) { jarBytes }
            }
        } catch (t: AdbAuthPendingException) {
            authPending(target, t)
        } catch (t: java.io.IOException) {
            failed(target, t)
        } catch (t: IllegalStateException) {
            failed(target, t)
        }
    }

    /**
     * Reuse an already-authorized peer connection from [PeerStarter]'s periodic loop. The port poll
     * is deliberately before [jarBytesProvider] runs: a healthy daemon is ALREADY_UP, never
     * restarted on each loop iteration, and never pays for a jar read/asset-read failure.
     */
    internal fun ensureHandsets(
        target: PeerTarget,
        client: AdbClient,
        port: Int = HandsetsStartCommands.DEFAULT_PORT,
        jarBytesProvider: () -> ByteArray?,
    ): PeerStarter.Result {
        val name = target.toString()
        if (HandsetsStartCommands.isUp(exec(client, HandsetsStartCommands.pollCommand(port)))) {
            return PeerStarter.Result(name, PeerStarter.Outcome.ALREADY_UP)
        }
        val jarBytes = jarBytesProvider() ?: return assetFailure(target)
        pushJarIfNeeded(client, jarBytes)
        exec(client, HandsetsStartCommands.killCommand(port))
        Thread.sleep(KILL_SETTLE_MS)
        val startOut = exec(client, HandsetsStartCommands.startCommand(port))
        Log.i(
            TAG,
            "handsets-start output for $name: ${startOut.trim().take(START_OUTPUT_LOG_CHARS)}",
        )
        return if (pollUntilUp(client, port)) {
            PeerStarter.Result(name, PeerStarter.Outcome.STARTED)
        } else {
            val log = exec(client, HandsetsStartCommands.tailLogCommand(port))
            PeerStarter.Result(
                name,
                PeerStarter.Outcome.FAILED,
                log.trim().replace('\n', ' ').take(FAILURE_DETAIL_CHARS),
            )
        }
    }

    private fun authPending(target: PeerTarget, t: Throwable): PeerStarter.Result {
        Log.i(TAG, "handsets-start $target pending one-time approval: ${t.message}")
        return PeerStarter.Result(
            target.toString(),
            PeerStarter.Outcome.AUTH_PENDING,
            "awaiting Always-allow on target",
        )
    }

    private fun loadJar(context: Context): ByteArray? =
        try {
            context.assets.open(ASSET_NAME).use { it.readBytes() }
        } catch (t: java.io.IOException) {
            Log.e(TAG, "hs.jar asset read failed", t)
            null
        }

    private fun assetFailure(target: PeerTarget): PeerStarter.Result =
        PeerStarter.Result(target.toString(), PeerStarter.Outcome.FAILED, "asset:read failed")

    private fun failed(target: PeerTarget, t: Throwable): PeerStarter.Result {
        Log.w(TAG, "handsets-start $target failed", t)
        return PeerStarter.Result(
            target.toString(),
            PeerStarter.Outcome.FAILED,
            (t.message ?: t.javaClass.simpleName).take(ERROR_MESSAGE_CHARS),
        )
    }

    private fun pushJarIfNeeded(client: AdbClient, jarBytes: ByteArray) {
        val present =
            HandsetsStartCommands.jarPresent(exec(client, HandsetsStartCommands.jarExistsCheck()))
        if (present) return
        HandsetsStartCommands.base64Chunks(jarBytes).forEachIndexed { i, chunk ->
            exec(client, HandsetsStartCommands.writeChunkCommand(chunk, append = i > 0))
        }
    }

    private fun pollUntilUp(client: AdbClient, port: Int): Boolean {
        val deadline = System.currentTimeMillis() + POLL_TIMEOUT_MS
        do {
            if (HandsetsStartCommands.isUp(exec(client, HandsetsStartCommands.pollCommand(port)))) {
                return true
            }
            Thread.sleep(POLL_INTERVAL_MS)
        } while (System.currentTimeMillis() < deadline)
        return false
    }

    /** Run one `shell:` command to completion and return its aggregated stdout. */
    private fun exec(client: AdbClient, shellCmd: String): String {
        val sb = StringBuilder()
        client.command("shell:$shellCmd") { sb.append(String(it)) }
        return sb.toString()
    }
}

/**
 * Pure shell-command builders for the handsets-start wire steps — no Android or socket
 * dependencies, so they are unit-testable off-device. Kept faithful to
 * `control/bin/fire_peer_help.py:cmd_handsets_start`.
 */
object HandsetsStartCommands {
    const val REMOTE_JAR_PATH = "/data/local/tmp/hs.jar"

    /** Matches `docs/hacking.md`'s fireos-device Handsets port. */
    const val DEFAULT_PORT = 9012

    /**
     * Raw bytes per push chunk. The embedded [AdbClient] has no `sync:` (file-transfer) support, so
     * `hs.jar` is written via `base64 -d` shell commands instead, and [AdbClient.command] sends the
     * whole shell string as a single unchunked `A_OPEN` payload (see its implementation) — so this
     * has to leave real margin against the wire protocol's
     * [org.stayturgid.agent.adb.AdbProtocol.A_MAXDATA] (4096), not just be "smaller than it". 3000
     * raw bytes base64-encodes to exactly 4000 chars, and with the surrounding `printf '%s' '...' |
     * base64 -d >> '<path>'` wrapper plus [AdbMessage]'s trailing NUL terminator, the actual
     * command was only ~35 bytes under the 4096 cap — a single-character change to
     * [REMOTE_JAR_PATH] could have silently broken this. 2000 raw bytes leaves >1300 bytes of real
     * margin; see [HandsetsStartCommandsTest] for a test that pins this invariant against the
     * actual protocol constant so it can't silently drift back to a razor's edge.
     */
    const val PUSH_CHUNK_BYTES = 2000

    fun niceName(port: Int): String = "hsd$port"

    /** Shell probe for whether `hs.jar` is already on the target (mac's `_push_jar` skip case). */
    fun jarExistsCheck(remoteJar: String = REMOTE_JAR_PATH): String =
        "test -f '$remoteJar' && echo present || echo absent"

    fun jarPresent(output: String): Boolean = output.contains("present")

    /** Split [jarBytes] into base64-encoded chunks of at most [chunkSize] raw bytes each. */
    fun base64Chunks(jarBytes: ByteArray, chunkSize: Int = PUSH_CHUNK_BYTES): List<String> {
        require(chunkSize > 0) { "chunkSize must be positive" }
        if (jarBytes.isEmpty()) return emptyList()
        val encoder = Base64.getEncoder()
        val chunks = mutableListOf<String>()
        var offset = 0
        while (offset < jarBytes.size) {
            val end = minOf(offset + chunkSize, jarBytes.size)
            chunks.add(encoder.encodeToString(jarBytes.copyOfRange(offset, end)))
            offset = end
        }
        return chunks
    }

    /**
     * Decode one base64 [chunk] onto the target at [remoteJar] — truncating on the first chunk,
     * appending on the rest, so the sequence of calls reassembles the whole file in order.
     */
    fun writeChunkCommand(
        chunk: String,
        append: Boolean,
        remoteJar: String = REMOTE_JAR_PATH,
    ): String {
        val redirect = if (append) ">>" else ">"
        return "printf '%s' '$chunk' | base64 -d $redirect '$remoteJar'"
    }

    /** Kill any previous `hsd<port>`-tagged process (mac's unconditional restart semantics). */
    fun killCommand(port: Int): String {
        val nice = niceName(port)
        return "pkill -f '$nice' 2>/dev/null; pkill -f 'dev.handsets.daemon.Main --port=$port' 2>/dev/null; true"
    }

    /** Launch the daemon via `app_process`, nice-named so [killCommand] can find it next time. */
    fun startCommand(port: Int, remoteJar: String = REMOTE_JAR_PATH): String {
        val nice = niceName(port)
        return "CLASSPATH='$remoteJar' nohup app_process /system/bin --nice-name=$nice " +
            "dev.handsets.daemon.Main --port=$port >/data/local/tmp/$nice.log 2>&1 &"
    }

    /** One port probe: `nc` first, falling back to `ss`, falling back to the daemon's own log. */
    fun pollCommand(port: Int): String {
        val nice = niceName(port)
        return "toybox nc -z 127.0.0.1 $port >/dev/null 2>&1 && echo up || " +
            "(ss -lntp 2>/dev/null | grep -q ':$port' && echo up || " +
            "grep -q 'listening' /data/local/tmp/$nice.log 2>/dev/null && echo up || echo down)"
    }

    fun isUp(pollOutput: String): Boolean = pollOutput.contains("up")

    /** Tail of the daemon's own log, for a `FAILED` result's detail message. */
    fun tailLogCommand(port: Int, lines: Int = 20): String =
        "tail -$lines /data/local/tmp/${niceName(port)}.log"
}
