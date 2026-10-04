package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class ShizukuAuthTest {
    @Test
    fun startWithheldOnMarkerOrResultFour() {
        val withheld = "Broadcast completed: result=4, data=\"AUTH_UNANSWERED\""
        assertTrue(ShizukuAuth.startWithheld(withheld))
        assertTrue(ShizukuAuth.startWithheld("Broadcast completed: result=4"))
        assertFalse(ShizukuAuth.startWithheld("Broadcast completed: result=0"))
        assertFalse(ShizukuAuth.startWithheld("Broadcast completed: result=40"))
        assertFalse(ShizukuAuth.startWithheld(""))
        assertFalse(ShizukuAuth.startWithheld(null))
    }

    @Test
    fun trackerLogsOncePerStateChange() {
        val t = ShizukuAuth.ChangeTracker()
        assertNull(t.observe(false))
        assertEquals("WARNING: " + ShizukuAuth.WITHHELD_MSG, t.observe(true))
        assertNull(t.observe(true))
        assertTrue(t.observe(false)!!.startsWith("NOTICE:"))
        assertNull(t.observe(false))
    }

    @Test
    fun withheldMessageIsTheFleetWideText() {
        assertEquals(
            "shizuku start withheld: ADB authorisation dialog unanswered; " +
                "operator: tap Attempt now on the phone",
            ShizukuAuth.WITHHELD_MSG,
        )
    }
}
