package org.stayturgid.agent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Pure command-string + outcome tests (no Android runtime). */
class AuthorizeReminderTest {
    @Test
    fun clearCommandRemovesBothAgentBuildsMarkers() {
        val cmd = AuthorizeReminder.clearCommand()
        assertTrue(cmd.startsWith("rm -f "))
        assertTrue(cmd.contains("/sdcard/Android/data/org.stayturgid.agent/files/authorize_reminder"))
        assertTrue(cmd.contains("/sdcard/Android/data/org.stayturgid.agent.debug/files/authorize_reminder"))
    }

    @Test
    fun onlySuccessOutcomesCountAsSuccess() {
        assertTrue(PeerStarter.Outcome.ALREADY_UP.isSuccess())
        assertTrue(PeerStarter.Outcome.STARTED.isSuccess())
        assertFalse(PeerStarter.Outcome.AUTH_PENDING.isSuccess())
        assertFalse(PeerStarter.Outcome.FAILED.isSuccess())
        assertFalse(PeerStarter.Outcome.UNREACHABLE.isSuccess())
        assertFalse(PeerStarter.Outcome.NOT_INSTALLED.isSuccess())
        assertFalse(PeerStarter.Outcome.NO_TARGETS.isSuccess())
    }
}
