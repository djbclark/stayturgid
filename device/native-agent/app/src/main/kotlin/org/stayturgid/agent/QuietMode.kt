package org.stayturgid.agent

import android.content.Context
import java.time.Instant
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Quiet mode (2026-10-17): every stayturgid audio alert (the low-battery locate sound, the evening
 * warnings) stays off until a morning time, set from [MainActivity]'s buttons.
 *
 * The agent holds the state the launcher shows, refuses to play [LocateSound] while it lasts
 * (except an explicit ring), and hands the same deadline to Termux's `stayturgid_battery_alarm.py
 * quiet-until <epoch>`, which decides when the sounds start.
 */
object QuietMode {
    /** The usual sleeping window, the same hours as stayturgid_battery_alarm.py's quiet hours. */
    const val SLEEP_START_HOUR = 21
    const val SLEEP_END_HOUR = 9
    const val LATE_MORNING_HOUR = 10

    private const val PREFS = "quiet_mode"
    private const val KEY_UNTIL_MS = "until_epoch_ms"
    private val FORMAT = DateTimeFormatter.ofPattern("EEE HH:mm")

    /**
     * [hour]:00 on the morning that ends the current or next sleeping window: today before
     * [SLEEP_END_HOUR], else tomorrow: pressed at 01:00 it means this morning, at 14:00 tomorrow.
     */
    fun morningAfterSleep(now: LocalDateTime, hour: Int): LocalDateTime {
        val day =
            if (now.hour < SLEEP_END_HOUR) now.toLocalDate() else now.toLocalDate().plusDays(1)
        return day.atTime(LocalTime.of(hour, 0))
    }

    fun untilMs(context: Context, nowMs: Long = System.currentTimeMillis()): Long? {
        val until = prefs(context).getLong(KEY_UNTIL_MS, 0L)
        return until.takeIf { it > nowMs }
    }

    fun isQuiet(context: Context): Boolean = untilMs(context) != null

    /** Quiet until [hour]:00 after the next sleep; returns the deadline in epoch ms. */
    fun quietUntilMorning(context: Context, hour: Int): Long {
        val zone = ZoneId.systemDefault()
        val until =
            morningAfterSleep(LocalDateTime.now(zone), hour).atZone(zone).toInstant().toEpochMilli()
        prefs(context).edit().putLong(KEY_UNTIL_MS, until).apply()
        return until
    }

    fun clear(context: Context) {
        prefs(context).edit().remove(KEY_UNTIL_MS).apply()
    }

    fun describe(untilMs: Long?): String =
        if (untilMs == null) {
            "Audio alerts: ON"
        } else {
            val at = Instant.ofEpochMilli(untilMs).atZone(ZoneId.systemDefault())
            "Audio alerts: OFF until ${FORMAT.format(at)}"
        }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
