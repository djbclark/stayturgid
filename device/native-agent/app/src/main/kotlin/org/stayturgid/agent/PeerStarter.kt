package org.stayturgid.agent

import android.content.Context
import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.stayturgid.agent.adb.AdbAuthPendingException
import org.stayturgid.agent.adb.AdbClient
import org.stayturgid.agent.adb.AdbKey
import org.stayturgid.agent.adb.PreferenceAdbKeyStore

/**
 * Peer-start: bring Shizuku up on a Fire-OS device from a healthy peer over external ADB, with no
 * dependency on the Mac (issue #61).
 *
 * Fire OS `adbd` drops device-local (loopback) connections, so Shizuku can't self-start there; a
 * connection from *another host* is accepted (proven in #60). This runs entirely in the agent's app
 * process — the peer does **not** need Shizuku itself, only the embedded [AdbClient] + its own
 * on-device [AdbKey] (authorized once on the target's adbd via "Always allow").
 *
 * The wire steps mirror `control/bin/fire_peer_help.py` (`shizuku-start`), which proved the path
 * this session: `pm path` → `<apkdir>/lib/arm64/libshizuku.so` under `LD_LIBRARY_PATH`, falling
 * back to the app's `start.sh`.
 */
object PeerStarter {
    private const val TAG = "StayTurgidPeer"

    /**
     * Peer-start runs in the **app** process (no local Shizuku), which under scoped storage cannot
     * write the shared UID-2000 `agent.log`. Durable results go to the app-writable external files
     * dir instead; every result is also emitted to logcat.
     */
    private const val LOG_FILE_NAME = "peerstart.log"
    private const val ADB_KEY_PREFS = "stayturgid_adb_key"
    private const val ADB_KEY_NAME = "stayturgid-agent"

    /** Time for the just-launched daemon to register before we re-probe. */
    private const val START_SETTLE_MS = 1_800L

    enum class Outcome {
        ALREADY_UP,
        STARTED,
        /**
         * Target reachable + auth-challenged, but the one-time "Always allow" hasn't been granted
         * yet.
         */
        AUTH_PENDING,
        FAILED,
        UNREACHABLE,
        NOT_INSTALLED,
        NO_TARGETS;

        /** Shizuku confirmed running via an authorized connection. */
        fun isSuccess(): Boolean = this == ALREADY_UP || this == STARTED
    }

    data class Result(val target: String, val outcome: Outcome, val detail: String = "") {
        fun line(ts: String): String =
            "[agent] PEERSTART target=$target outcome=$outcome detail=$detail ts=$ts"
    }

    /** Load config and ensure Shizuku on every assigned target. */
    fun startAll(context: Context): List<Result> {
        val config = PeerConfig.load(context)
        if (config.targets.isEmpty()) {
            val r = Result("-", Outcome.NO_TARGETS)
            record(context, r)
            return listOf(r)
        }
        val key =
            try {
                loadKey(context)
            } catch (t: Throwable) {
                Log.e(TAG, "adb key init failed", t)
                val r = Result("-", Outcome.FAILED, "adb_key:${t.message}")
                record(context, r)
                return listOf(r)
            }
        val results =
            config.targets.map { target ->
                ensurePeerServices(context, target, config.shizukuPkg, key)
            }
        results.forEach { result ->
            record(context, result.shizuku)
            record(context, result.handsets)
        }
        val shizukuResults = results.map { it.shizuku }
        PeerStartState.update(context, shizukuResults)
        return shizukuResults
    }

    /**
     * Visible to [HostService] so [HandsetsStarter]'s manual trigger can reuse the same identity.
     */
    internal fun loadKey(context: Context): AdbKey {
        val prefs = context.getSharedPreferences(ADB_KEY_PREFS, Context.MODE_PRIVATE)
        return AdbKey(PreferenceAdbKeyStore(prefs), ADB_KEY_NAME)
    }

    /** Connect to [target]'s adbd; start Shizuku only if it is not already up. */
    fun ensureShizuku(target: PeerTarget, shizukuPkg: String, key: AdbKey): Result {
        val name = target.toString()
        return try {
            AdbClient(target.host, target.port, key).use { client ->
                client.connect()

                // Reaching here means the key is authorized — clear any stale
                // "approve on the target" reminder we set on the target device.
                clearTargetReminder(client)

                ensureShizuku(target, shizukuPkg, client)
            }
        } catch (t: AdbAuthPendingException) {
            Log.i(TAG, "peer-start $name pending one-time approval")
            Result(name, Outcome.AUTH_PENDING, "awaiting Always-allow on target")
        } catch (t: Throwable) {
            Log.w(TAG, "peer-start $name failed", t)
            val msg = t.message ?: t.javaClass.simpleName
            val outcome = if (isUnreachable(t)) Outcome.UNREACHABLE else Outcome.FAILED
            Result(name, outcome, msg.take(200))
        }
    }

    private data class PeerServicesResult(val shizuku: Result, val handsets: Result)

    /** One external-ADB connection per target and periodic iteration. */
    private fun ensurePeerServices(
        context: Context,
        target: PeerTarget,
        shizukuPkg: String,
        key: AdbKey,
    ): PeerServicesResult {
        return try {
            AdbClient(target.host, target.port, key).use { client ->
                client.connect()
                // This only preserves the toggle when adbd is already reachable and authorized;
                // it cannot restore adbd or port 5555 after they are fully dead.
                exec(client, PeerStartCommands.ADB_WIFI_ENABLED_REASSERT)
                clearTargetReminder(client)
                val shizuku = ensureShizuku(target, shizukuPkg, client)
                val handsets = HandsetsStarter.ensureHandsets(context, target, client)
                PeerServicesResult(shizuku, handsets)
            }
        } catch (t: AdbAuthPendingException) {
            val pending =
                Result(target.toString(), Outcome.AUTH_PENDING, "awaiting Always-allow on target")
            PeerServicesResult(pending, pending)
        } catch (t: Throwable) {
            Log.w(TAG, "peer services $target failed", t)
            val detail = (t.message ?: t.javaClass.simpleName).take(200)
            val outcome = if (isUnreachable(t)) Outcome.UNREACHABLE else Outcome.FAILED
            val failed = Result(target.toString(), outcome, detail)
            PeerServicesResult(failed, failed)
        }
    }

    private fun ensureShizuku(target: PeerTarget, shizukuPkg: String, client: AdbClient): Result {
        val name = target.toString()
        if (isShizukuUp(client)) return Result(name, Outcome.ALREADY_UP)
        val apkPath =
            PeerStartCommands.parseApkPath(exec(client, PeerStartCommands.pmPath(shizukuPkg)))
                ?: return Result(name, Outcome.NOT_INSTALLED, "pkg=$shizukuPkg")
        val out =
            exec(
                client,
                PeerStartCommands.starterCommand(PeerStartCommands.libDirFor(apkPath), shizukuPkg),
            )
        Log.i(TAG, "starter output for $name: ${out.trim().take(400)}")
        Thread.sleep(START_SETTLE_MS)
        return if (isShizukuUp(client)) {
            Result(name, Outcome.STARTED)
        } else {
            Result(name, Outcome.FAILED, out.trim().replace('\n', ' ').take(300))
        }
    }

    /**
     * Best-effort removal of the "approve on the target" reminder marker on the target device, over
     * the now-authorized connection. Package-independent (covers debug + release agent ids);
     * failures are ignored.
     */
    private fun clearTargetReminder(client: AdbClient) {
        try {
            exec(client, AuthorizeReminder.clearCommand())
        } catch (t: Throwable) {
            Log.w(TAG, "clear target reminder failed: ${t.message}")
        }
    }

    private fun isShizukuUp(client: AdbClient): Boolean =
        exec(client, PeerStartCommands.SHIZUKU_RUNNING_CHECK).contains("up")

    private fun isUnreachable(t: Throwable): Boolean {
        val m = (t.message ?: "").lowercase()
        return t is java.net.ConnectException ||
            t is java.net.SocketTimeoutException ||
            t is java.net.NoRouteToHostException ||
            m.contains("econnrefused") ||
            m.contains("timed out") ||
            m.contains("unreachable")
    }

    /** Run one `shell:` command to completion and return its aggregated stdout. */
    private fun exec(client: AdbClient, shellCmd: String): String {
        val sb = StringBuilder()
        client.command("shell:$shellCmd") { sb.append(String(it)) }
        return sb.toString()
    }

    private fun record(context: Context, result: Result) {
        val ts = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val line = result.line(ts)
        Log.i(TAG, line)
        try {
            val dir = context.getExternalFilesDir(null) ?: context.filesDir
            File(dir, LOG_FILE_NAME).appendText("$line\n")
        } catch (t: Throwable) {
            Log.w(TAG, "peerstart log write failed: ${t.message}")
        }
    }
}

/**
 * Pure shell-command builders for the peer-start wire steps — no Android or socket dependencies, so
 * they are unit-testable off-device. Kept faithful to
 * `control/bin/fire_peer_help.py:cmd_shizuku_start`.
 */
object PeerStartCommands {
    /** Preserve wireless debugging over an already-authorized peer ADB session. */
    const val ADB_WIFI_ENABLED_REASSERT = "settings put global adb_wifi_enabled 1"

    /**
     * `[s]hizuku_server` (bracket trick) so the pgrep pattern never matches its own process. Emits
     * `up`/`down` so the reader is unambiguous.
     */
    const val SHIZUKU_RUNNING_CHECK =
        "pgrep -f '[s]hizuku_server' >/dev/null 2>&1 && echo up || echo down"

    fun pmPath(pkg: String): String = "pm path $pkg"

    /** First `package:<path>` line from `pm path` output, or null if absent. */
    fun parseApkPath(pmOutput: String): String? {
        for (raw in pmOutput.lineSequence()) {
            val line = raw.trim().removeSuffix("\r")
            if (line.startsWith("package:")) {
                val path = line.substringAfter("package:").trim()
                if (path.isNotEmpty()) return path
            }
        }
        return null
    }

    /** `<apkdir>/lib/arm64` — where extractNativeLibs=true puts `libshizuku.so`. */
    fun libDirFor(apkPath: String): String = apkPath.substringBeforeLast('/') + "/lib/arm64"

    /**
     * Run the extracted `libshizuku.so` under `LD_LIBRARY_PATH`, falling back to the app's bundled
     * `start.sh`. Paths single-quoted — install dirs contain `~~`/`==` (Android randomized app
     * dirs) that must stay literal.
     */
    fun starterCommand(libDir: String, shizukuPkg: String): String =
        "test -x '$libDir/libshizuku.so' && " +
            "LD_LIBRARY_PATH='$libDir' '$libDir/libshizuku.so' || " +
            "sh /storage/emulated/0/Android/data/$shizukuPkg/start.sh"
}
