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
    fun statusUnansweredOnlyOnMarkerBecauseResultFourIsCrashed() {
        val unanswered = "Broadcast completed: result=3, data=\"STOPPED AUTH_UNANSWERED\""
        assertTrue(ShizukuAuth.statusUnanswered(unanswered))
        assertFalse(ShizukuAuth.statusUnanswered("Broadcast completed: result=4, data=\"CRASHED\""))
        assertFalse(ShizukuAuth.statusUnanswered("Broadcast completed: result=3"))
        assertFalse(ShizukuAuth.statusUnanswered(null))
    }

    @Test
    fun statusCommandTargetsExplicitReceiverWithoutForce() {
        assertTrue(ShizukuAuth.STATUS_COMMAND.contains("HEADLESS_STATUS"))
        assertTrue(ShizukuAuth.STATUS_COMMAND.contains("-n moe.shizuku.privileged.api/"))
        assertFalse(ShizukuAuth.STATUS_COMMAND.contains("force"))
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

    @Test
    fun peerAuthChangeLineOnlyOnTransitions() {
        val u = PeerStarter.Outcome.AUTH_UNANSWERED
        val line = PeerStartCommands.authChangeLine("10.0.0.5:5555", PeerStarter.Outcome.FAILED, u)
        assertEquals(
            "[agent] PEERSTART target=10.0.0.5:5555 WARNING: " + ShizukuAuth.WITHHELD_MSG,
            line,
        )
        assertNull(PeerStartCommands.authChangeLine("10.0.0.5:5555", u, u))
        val started = PeerStarter.Outcome.STARTED
        val cleared = PeerStartCommands.authChangeLine("10.0.0.5:5555", u, started)
        assertTrue(cleared!!.contains("NOTICE:"))
        assertNull(PeerStartCommands.authChangeLine("10.0.0.5:5555", null, started))
        assertNull(PeerStartCommands.authChangeLine("-", null, u))
        assertFalse(u.isSuccess())
    }
}
