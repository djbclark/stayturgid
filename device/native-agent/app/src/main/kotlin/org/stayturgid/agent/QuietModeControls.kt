package org.stayturgid.agent

import android.app.Activity
import android.graphics.Typeface
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.util.concurrent.TimeUnit

/**
 * [MainActivity]'s quiet-mode block: the "Audio alerts: ON/OFF until ..." indicator and its three
 * buttons. A quiet button stops a locate sound that is playing, makes sure the flashlight is off,
 * and hands the deadline to Termux's battery alarm (`quiet-until <epoch seconds>`).
 */
class QuietModeControls(private val activity: Activity) {
    private val status =
        TextView(activity).apply {
            textSize = STATUS_TEXT_SP
            setTypeface(null, Typeface.BOLD)
            setPadding(0, STATUS_PAD_TOP, 0, STATUS_PAD_BOTTOM)
        }

    fun addTo(root: LinearLayout) {
        val untilMorning = quietButton(R.string.main_quiet_until_morning, QuietMode.SLEEP_END_HOUR)
        val untilLate = quietButton(R.string.main_quiet_until_late, QuietMode.LATE_MORNING_HOUR)
        val alertsOn =
            Button(activity).apply {
                text = activity.getString(R.string.main_quiet_off)
                setOnClickListener {
                    QuietMode.clear(activity)
                    sendToTermux("quiet-off")
                    refresh()
                }
            }
        listOf(status, untilMorning, untilLate, alertsOn).forEach(root::addView)
        refresh()
    }

    fun refresh() {
        status.text = QuietMode.describe(QuietMode.untilMs(activity))
    }

    /** [label] is a string resource formatted with [hour]. */
    private fun quietButton(label: Int, hour: Int): Button =
        Button(activity).apply {
            text = activity.getString(label, hour)
            setOnClickListener {
                val untilMs = QuietMode.quietUntilMorning(activity, hour)
                LocateSound.stop()
                Torch.off(activity)
                sendToTermux("quiet-until", TimeUnit.MILLISECONDS.toSeconds(untilMs).toString())
                refresh()
            }
        }

    private fun sendToTermux(vararg args: String) {
        val result =
            TermuxRunCommand.send(
                activity,
                TermuxRunCommand.PYTHON,
                "${TermuxRunCommand.HOME}/.stayturgid/bin/stayturgid_battery_alarm.py",
                *args,
            )
        val state = QuietMode.describe(QuietMode.untilMs(activity))
        val msg = if (result.startsWith("FAILED")) "$state, but Termux: $result" else state
        Toast.makeText(activity, msg, Toast.LENGTH_LONG).show()
    }

    private companion object {
        const val STATUS_TEXT_SP = 18f
        const val STATUS_PAD_TOP = 24
        const val STATUS_PAD_BOTTOM = 8
    }
}
