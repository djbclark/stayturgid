package org.stayturgid.agent

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import java.io.BufferedWriter
import java.io.IOException
import java.io.OutputStreamWriter
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Durable, Shizuku-independent liveness heartbeat (#86).
 *
 * Ticks on its own dedicated single-thread executor — never the coroutine scope HostService uses
 * for Shizuku/UserService work — so a hung Shizuku binder call can never delay or block a tick.
 * "Top of the heartbeat tick" in the same loop as co-monitor was explicitly ruled out during
 * review: a wedged `runComonitor()` call would stall that loop's next iteration and silently stop
 * the heartbeat too, recreating the exact blind spot #86 exists to fix.
 *
 * Writes to the MediaStore Downloads collection so Termux (unprivileged app uid, no Shizuku, no
 * adb) can read it as a plain file with no new permission grant. HostService cannot write
 * `/sdcard/stayturgid/...` directly without `MANAGE_EXTERNAL_STORAGE` — only the Shizuku-bound
 * UserService (uid 2000) can, and that coupling is exactly the "trap" #86 routes around. A
 * ContentProvider (the plan's first-choice transport) was tried and dropped: the real fleet's
 * Termux has no `content` binary (only am/pm/settings — confirmed live via SSH on hd8), so a
 * `content query` probe is not reachable from the CFEngine side. MediaStore is the plan's own
 * documented fallback and needs no new on-device package.
 *
 * Lands at /sdcard/Download/[FILE_NAME] (the .txt is MediaStore's own doing — see the constant's
 * comment). File format is a single plain-text line, `ts_sec=<epoch> seq=<n>`, parsed on the read
 * side with a plain `grep -oE 'ts_sec=[0-9]+'` (see device/termux/cfengine/policy/stayturgid.cf and
 * control/lib/fleet_health.py) — keep [formatLine], [FILE_NAME], and that shell contract in sync.
 */
object HeartbeatWriter {
    private const val TAG = "StayTurgidHeartbeat"

    // MediaStore enforces MIME_TYPE <-> extension agreement and silently appends the extension if
    // DISPLAY_NAME lacks one — verified live on hd8: a "text/plain" insert with DISPLAY_NAME
    // "stayturgid-agent.heartbeat" actually landed at .../Download/stayturgid-agent.heartbeat.txt.
    // Naming it explicitly here keeps the constant truthful instead of fighting that behavior.
    const val FILE_NAME = "stayturgid-agent.heartbeat.txt"
    private const val MIME_TYPE = "text/plain"

    /**
     * Tick cadence. Must stay well under the freshness threshold on the reader side (420s in
     * stayturgid.cf / fleet_health.py — see those files for the full "2-3x + jitter" rationale).
     */
    const val HEARTBEAT_INTERVAL_MS: Long = 120_000L

    private val seq = AtomicLong(0)
    private var cachedUri: Uri? = null
    private var executor: ScheduledExecutorService? = null
    private var loggedUnsupported = false

    /** Pure formatting — no Android runtime — so the shell-parsing contract is unit-testable. */
    fun formatLine(nowEpochSec: Long, seqValue: Long): String =
        "ts_sec=$nowEpochSec seq=$seqValue\n"

    @Synchronized
    fun start(context: Context) {
        if (executor != null) return
        val appContext = context.applicationContext
        val exec =
            Executors.newSingleThreadScheduledExecutor { r ->
                Thread(r, "stayturgid-heartbeat").apply { isDaemon = true }
            }
        executor = exec
        exec.scheduleWithFixedDelay(
            { tickSafely(appContext) },
            0L,
            HEARTBEAT_INTERVAL_MS,
            TimeUnit.MILLISECONDS,
        )
    }

    @Synchronized
    fun stop() {
        executor?.shutdownNow()
        executor = null
    }

    // A periodic executor task must survive literally anything thrown inside it (see comment
    // below) — that is a deliberate boundary, not an oversight, so the generic catch stays.
    @Suppress("TooGenericExceptionCaught")
    private fun tickSafely(context: Context) {
        try {
            tick(context)
        } catch (t: Throwable) {
            // A ScheduledExecutorService silently drops all future runs of a periodic task after
            // an uncaught exception — never let that happen here, or this reintroduces the same
            // silent blind spot #86 exists to fix.
            Log.w(TAG, "heartbeat tick failed: ${t.message}")
        }
    }

    // MediaStore/ParcelFileDescriptor I/O can throw several undocumented runtime exception types
    // across OEMs; any of them must fall back to "re-resolve next tick", not propagate (tickSafely
    // is the last-resort net, but this catch keeps a single flaky write from dropping the cache
    // unnecessarily — see the catch body below).
    @Suppress("TooGenericExceptionCaught")
    private fun tick(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            if (!loggedUnsupported) {
                Log.w(
                    TAG,
                    "heartbeat needs API 29+ (MediaStore.Downloads); skipping on ${Build.VERSION.SDK_INT}",
                )
                loggedUnsupported = true
            }
            return
        }
        val nowSec = System.currentTimeMillis() / 1000L
        val body = formatLine(nowSec, seq.incrementAndGet())
        val resolver = context.contentResolver
        val uri = cachedUri ?: resolveOrCreate(context) ?: return
        try {
            val stream =
                resolver.openOutputStream(uri, "wt") ?: throw IOException("openOutputStream null")
            stream.use { out -> BufferedWriter(OutputStreamWriter(out)).use { it.write(body) } }
            cachedUri = uri
        } catch (t: Throwable) {
            // The cached row may have been invalidated (e.g. the user cleared Downloads) — drop
            // the cache so the next tick re-resolves (query-or-insert) instead of failing forever.
            Log.w(TAG, "heartbeat write failed, will re-resolve: ${t.message}")
            cachedUri = null
        }
    }

    // Same rationale as tick() above: MediaStore query/insert failure modes vary by OEM and must
    // degrade to "return null, try again next tick" rather than propagate.
    @Suppress("TooGenericExceptionCaught")
    private fun resolveOrCreate(context: Context): Uri? {
        val resolver = context.contentResolver
        val collection = MediaStore.Downloads.EXTERNAL_CONTENT_URI
        val relativePath = Environment.DIRECTORY_DOWNLOADS + "/"
        val projection = arrayOf(MediaStore.MediaColumns._ID)
        val selection =
            "${MediaStore.MediaColumns.DISPLAY_NAME} = ? AND " +
                "${MediaStore.MediaColumns.RELATIVE_PATH} = ?"
        try {
            resolver
                .query(collection, projection, selection, arrayOf(FILE_NAME, relativePath), null)
                ?.use { c ->
                    if (c.moveToFirst()) {
                        val id = c.getLong(c.getColumnIndexOrThrow(MediaStore.MediaColumns._ID))
                        return ContentUris.withAppendedId(collection, id)
                    }
                }
        } catch (t: Throwable) {
            Log.w(TAG, "heartbeat query failed: ${t.message}")
        }
        val values =
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, FILE_NAME)
                put(MediaStore.MediaColumns.MIME_TYPE, MIME_TYPE)
                put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            }
        return try {
            resolver.insert(collection, values)
        } catch (t: Throwable) {
            Log.w(TAG, "heartbeat insert failed: ${t.message}")
            null
        }
    }
}
