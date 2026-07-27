package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure command-string + outcome tests (no Android runtime). */
class AuthorizeReminderTest {
    @Test
    fun clearCommandRemovesBothAgentBuildsMarkers() {
        val cmd = AuthorizeReminder.clearCommand()
        assertTrue(cmd.contains("run-as org.stayturgid.agent rm -f files/authorize_reminder"))
        assertTrue(cmd.contains("run-as org.stayturgid.agent.debug rm -f files/authorize_reminder"))
        assertTrue(
            cmd.contains("/sdcard/Android/data/org.stayturgid.agent/files/authorize_reminder")
        )
        assertTrue(
            cmd.contains("/sdcard/Android/data/org.stayturgid.agent.debug/files/authorize_reminder")
        )
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
