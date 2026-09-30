package org.stayturgid.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.core.app.NotificationCompat
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

/**
 * Tells the operator when a newer agent release exists: a notification from the service (checked
 * shortly after start, then every [CHECK_INTERVAL_MS]) and a line on the main screen.
 *
 * Source of truth is the public GitHub releases of djbclark/stayturgid: the newest non-draft,
 * non-prerelease `agent-vX.Y.Z` tag. Unauthenticated (60 requests/hour per IP), so the cadence is
 * deliberately slow. Nothing is installed from here — the fleet deploy (bootstrap_apks lock) and
 * Obtainium stay the install paths; this only points at the release page.
 */
object UpdateCheck {
    private const val TAG = "StayTurgidUpdate"
    private const val RELEASES_URL =
        "https://api.github.com/repos/djbclark/stayturgid/releases?per_page=50"
    private const val TAG_PREFIX = "agent-v"
    private const val CHANNEL_ID = "stayturgid_agent_update"
    private const val NOTIFICATION_ID = 7104
    private const val PREFS = "update_check"
    private const val KEY_LATEST = "latest_version"
    private const val KEY_URL = "latest_url"
    private const val KEY_CHECKED_MS = "checked_ms"
    private const val KEY_NOTIFIED = "notified_version"
    private const val TIMEOUT_MS = 15_000
    private const val FIRST_CHECK_DELAY_MS = 60_000L
    const val CHECK_INTERVAL_MS: Long = 12 * 60 * 60 * 1000L

    data class Release(val version: String, val url: String)

    /** Latest known release vs what's installed. [latest] is null until a check has succeeded. */
    data class Status(val installed: String, val latest: Release?, val checkedMs: Long) {
        val updateAvailable: Boolean
            get() = latest != null && isNewer(latest.version, installed)
    }

    private var executor: ScheduledExecutorService? = null

    /**
     * Numeric parts of a version or tag: "agent-v0.9.10" and "0.9.10-heartbeat-dedupe" -> [0,9,10].
     */
    fun parseVersion(raw: String): List<Int>? {
        val core = raw.removePrefix(TAG_PREFIX).substringBefore('-')
        val parts = core.split('.').map { it.toIntOrNull() ?: return null }
        return parts.takeIf { it.isNotEmpty() }
    }

    fun isNewer(candidate: String, installed: String): Boolean {
        val a = parseVersion(candidate) ?: return false
        val b = parseVersion(installed) ?: return false
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }
            val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    /** Newest agent release among (tag, url, draft, prerelease) rows; other tags are ignored. */
    fun newestAgentRelease(rows: List<ReleaseRow>): Release? =
        rows
            .filter { it.tag.startsWith(TAG_PREFIX) && !it.draft && !it.prerelease }
            .filter { parseVersion(it.tag) != null }
            .reduceOrNull { best, row -> if (isNewer(row.tag, best.tag)) row else best }
            ?.let { Release(it.tag.removePrefix(TAG_PREFIX), it.url) }

    data class ReleaseRow(
        val tag: String,
        val url: String,
        val draft: Boolean,
        val prerelease: Boolean,
    )

    fun cached(context: Context): Status {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val version = p.getString(KEY_LATEST, null)
        val url = p.getString(KEY_URL, null)
        val latest = if (version != null && url != null) Release(version, url) else null
        return Status(BuildConfig.VERSION_NAME, latest, p.getLong(KEY_CHECKED_MS, 0L))
    }

    /** Blocking network check; stores and returns the result, or the cached one on failure. */
    @Suppress("TooGenericExceptionCaught")
    fun checkNow(context: Context): Status {
        try {
            val release = newestAgentRelease(fetchRows())
            if (release != null) {
                context
                    .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit()
                    .putString(KEY_LATEST, release.version)
                    .putString(KEY_URL, release.url)
                    .putLong(KEY_CHECKED_MS, System.currentTimeMillis())
                    .apply()
            }
        } catch (t: Throwable) {
            // Network, rate limit, or JSON shape — try again next interval.
            Log.w(TAG, "update check failed: ${t.message}")
        }
        return cached(context)
    }

    @Synchronized
    fun start(context: Context) {
        if (executor != null) return
        val appContext = context.applicationContext
        val exec =
            Executors.newSingleThreadScheduledExecutor { r ->
                Thread(r, "stayturgid-update").apply { isDaemon = true }
            }
        executor = exec
        exec.scheduleWithFixedDelay(
            { notifyIfNewer(appContext) },
            FIRST_CHECK_DELAY_MS,
            CHECK_INTERVAL_MS,
            TimeUnit.MILLISECONDS,
        )
    }

    @Synchronized
    fun stop() {
        executor?.shutdownNow()
        executor = null
    }

    /** Intent that opens a release page in the browser. */
    fun openReleaseIntent(release: Release): Intent =
        Intent(Intent.ACTION_VIEW, Uri.parse(release.url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    // Runs on the executor thread; a throw would cancel every later run.
    @Suppress("TooGenericExceptionCaught")
    private fun notifyIfNewer(context: Context) {
        try {
            val status = checkNow(context)
            val nm = context.getSystemService(NotificationManager::class.java) ?: return
            val latest = status.latest
            if (latest == null || !status.updateAvailable) {
                nm.cancel(NOTIFICATION_ID)
                return
            }
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            if (prefs.getString(KEY_NOTIFIED, null) == latest.version) return
            ensureChannel(context, nm)
            nm.notify(NOTIFICATION_ID, buildNotification(context, status.installed, latest))
            prefs.edit().putString(KEY_NOTIFIED, latest.version).apply()
        } catch (t: Throwable) {
            Log.w(TAG, "update notify failed: ${t.message}")
        }
    }

    private fun fetchRows(): List<ReleaseRow> {
        val conn = URL(RELEASES_URL).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.setRequestProperty("Accept", "application/vnd.github+json")
            conn.setRequestProperty("User-Agent", "stayturgid-agent/${BuildConfig.VERSION_NAME}")
            check(conn.responseCode == HttpURLConnection.HTTP_OK) { "HTTP ${conn.responseCode}" }
            val array = org.json.JSONArray(conn.inputStream.bufferedReader().use { it.readText() })
            return (0 until array.length()).map { i ->
                val o = array.getJSONObject(i)
                ReleaseRow(
                    tag = o.optString("tag_name"),
                    url = o.optString("html_url"),
                    draft = o.optBoolean("draft"),
                    prerelease = o.optBoolean("prerelease"),
                )
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun ensureChannel(context: Context, nm: NotificationManager) {
        val name = context.getString(R.string.update_channel_name)
        val channel = NotificationChannel(CHANNEL_ID, name, NotificationManager.IMPORTANCE_DEFAULT)
        channel.description = context.getString(R.string.update_channel_desc)
        nm.createNotificationChannel(channel)
    }

    private fun buildNotification(
        context: Context,
        installed: String,
        latest: Release,
    ): Notification {
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val open =
            PendingIntent.getActivity(context, NOTIFICATION_ID, openReleaseIntent(latest), flags)
        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.update_title, latest.version))
            .setContentText(context.getString(R.string.update_text, installed))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
    }
}
