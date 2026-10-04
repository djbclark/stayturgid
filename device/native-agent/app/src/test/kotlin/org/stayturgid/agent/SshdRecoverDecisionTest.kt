package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class SshdRecoverDecisionTest {
    private val cooldownMs = 300_000L
    private val decision = SshdRecoverDecision(downsNeeded = 2, cooldownMs = cooldownMs)

    @Test
    fun singleDownDoesNotTrigger() {
        assertFalse(decision.shouldAttempt("down", 1_000))
    }

    @Test
    fun secondConsecutiveDownTriggersEvenRightAfterBoot() {
        // elapsedRealtime is small after a reboot; "never attempted" must not read as "in
        // cooldown".
        assertFalse(decision.shouldAttempt("down", 1_000))
        assertTrue(decision.shouldAttempt("down", 2_000))
    }

    @Test
    fun upResetsTheCount() {
        assertFalse(decision.shouldAttempt("down", 1_000))
        assertFalse(decision.shouldAttempt("up", 2_000))
        assertFalse(decision.shouldAttempt("down", 3_000))
        assertTrue(decision.shouldAttempt("down", 4_000))
    }

    @Test
    fun unknownStateResetsTheCount() {
        assertFalse(decision.shouldAttempt("down", 1_000))
        assertFalse(decision.shouldAttempt("unknown", 2_000))
        assertFalse(decision.shouldAttempt("down", 3_000))
        assertTrue(decision.shouldAttempt("down", 4_000))
    }

    @Test
    fun stillDownRetriesOnlyAfterTheCooldown() {
        assertFalse(decision.shouldAttempt("down", 1_000))
        assertTrue(decision.shouldAttempt("down", 2_000))
        assertFalse(decision.shouldAttempt("down", 3_000))
        assertFalse(decision.shouldAttempt("down", 2_000 + cooldownMs - 1))
        assertTrue(decision.shouldAttempt("down", 2_000 + cooldownMs))
    }

    @Test
    fun recoveryThenNewOutageInsideCooldownWaits() {
        assertFalse(decision.shouldAttempt("down", 1_000))
        assertTrue(decision.shouldAttempt("down", 2_000))
        assertFalse(decision.shouldAttempt("up", 3_000))
        assertFalse(decision.shouldAttempt("down", 4_000))
        assertFalse(decision.shouldAttempt("down", 5_000))
        assertTrue(decision.shouldAttempt("down", 2_000 + cooldownMs))
    }
}

class SshdRecoverStatusParseTest {
    @Test
    fun readsSshdStateFromAStatusLine() {
        val line = "[agent] STATUS port=5555 shizuku=running sshd=down a11y=ok shell=ok"
        org.junit.jupiter.api.Assertions.assertEquals("down", SshdRecover.sshdState(line))
        org.junit.jupiter.api.Assertions.assertEquals(
            "up",
            SshdRecover.sshdState(line.replace("sshd=down", "sshd=up")),
        )
        org.junit.jupiter.api.Assertions.assertEquals(
            "unknown",
            SshdRecover.sshdState("[agent] STATUS port=5555"),
        )
    }
}
