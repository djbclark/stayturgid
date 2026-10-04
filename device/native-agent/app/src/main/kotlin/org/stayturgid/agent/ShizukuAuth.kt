package org.stayturgid.agent

/**
 * ShizukuTendCF's "ADB authorisation dialog went unanswered" contract, as unattended starters see
 * it. While the marker is set a plain HEADLESS_START answers result 4 / `AUTH_UNANSWERED` and
 * HEADLESS_STATUS data ends with ` AUTH_UNANSWERED`. Only an operator at the phone clears it (`--ez
 * force true`, i.e. "Attempt now"), so nothing here ever sends force and nothing falls back to the
 * starter binary. Builds that predate the contract never emit the marker, which reads as
 * "answered".
 */
object ShizukuAuth {
    const val MARKER = "AUTH_UNANSWERED"
    const val WITHHELD_MSG =
        "shizuku start withheld: ADB authorisation dialog unanswered; " +
            "operator: tap Attempt now on the phone"

    /** HEADLESS_STATUS on a target, by explicit receiver (implicit broadcasts are dropped). */
    const val STATUS_COMMAND =
        "am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS " +
            "-n moe.shizuku.privileged.api/af.shizuku.manager.receiver.HeadlessStartStopReceiver"

    private val START_RESULT_WITHHELD = Regex("""\bresult=4\b""")

    /** STATUS result codes are state ordinals (4 = CRASHED), so only the marker text counts. */
    fun statusUnanswered(statusOut: String?): Boolean = statusOut?.contains(MARKER) == true

    fun startWithheld(startOut: String?): Boolean =
        startOut != null &&
            (startOut.contains(MARKER) || START_RESULT_WITHHELD.containsMatchIn(startOut))

    /** Remembers the last state so a log line is written once per change, not every cycle. */
    class ChangeTracker(private var unanswered: Boolean = false) {
        /** Returns the line to log when [now] differs from the last observation, else null. */
        fun observe(now: Boolean): String? {
            if (now == unanswered) return null
            unanswered = now
            return if (now) {
                "WARNING: $WITHHELD_MSG"
            } else {
                "NOTICE: ADB authorisation answered; shizuku starts resume"
            }
        }
    }
}
