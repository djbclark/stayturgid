package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/** The quiet-mode deadline: a morning hour after the current or next sleeping window. */
class QuietModeTest {
    private fun at(day: Int, hour: Int, minute: Int = 0) =
        // Fully qualified: ktfmt sorts java.* first, detekt's ImportOrdering wants it last.
        java.time.LocalDateTime.of(2026, 10, day, hour, minute)

    @Test
    fun afternoonMeansTomorrowMorning() {
        assertEquals(at(18, 9), QuietMode.morningAfterSleep(at(17, 14, 30), 9))
        assertEquals(at(18, 10), QuietMode.morningAfterSleep(at(17, 14, 30), 10))
    }

    @Test
    fun lateEveningMeansTomorrowMorning() {
        assertEquals(at(18, 9), QuietMode.morningAfterSleep(at(17, 23, 59), 9))
    }

    @Test
    fun smallHoursMeanThisMorning() {
        assertEquals(at(17, 9), QuietMode.morningAfterSleep(at(17, 1, 0), 9))
        assertEquals(at(17, 10), QuietMode.morningAfterSleep(at(17, 8, 59), 10))
    }

    @Test
    fun afterTheWindowEndsItIsTheNextNight() {
        // 09:30: tonight's sleep is the next one, so even 10:00 means tomorrow.
        assertEquals(at(18, 9), QuietMode.morningAfterSleep(at(17, 9, 0), 9))
        assertEquals(at(18, 10), QuietMode.morningAfterSleep(at(17, 9, 30), 10))
    }
}
