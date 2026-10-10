package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
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

/**
 * A Termux sshd can WEDGE: listening on 8022 with a full accept queue, so every connect times out
 * or connects and never gets a banner (t2e 2026-10-10, s24 2026-10-08).
 */
class SshdBannerProbeClassifyTest {
    private fun classify(outcome: SshdConnect, banner: String? = null) =
        SshdBanner.classify(outcome, banner)

    @Test
    fun sshBannerIsHealthy() {
        assertEquals(
            SshdBannerProbe.HEALTHY,
            classify(SshdConnect.CONNECTED, "SSH-2.0-OpenSSH_9.9"),
        )
    }

    @Test
    fun connectedButNoBannerBeforeTheReadTimeoutIsWedged() {
        assertEquals(SshdBannerProbe.WEDGED, classify(SshdConnect.CONNECTED, null))
    }

    @Test
    fun connectTimeoutIsWedged() {
        // A full accept queue drops the SYN, so the connect never completes.
        assertEquals(SshdBannerProbe.WEDGED, classify(SshdConnect.TIMED_OUT))
    }

    @Test
    fun refusedIsDownNotWedged() {
        // Nothing listening: the existing sshd=down path owns that case.
        assertEquals(SshdBannerProbe.REFUSED, classify(SshdConnect.REFUSED))
    }

    @Test
    fun otherSocketErrorIsUnknown() {
        assertEquals(SshdBannerProbe.UNKNOWN, classify(SshdConnect.ERROR))
    }

    @Test
    fun immediateEofIsUnknownNotWedged() {
        assertEquals(SshdBannerProbe.UNKNOWN, classify(SshdConnect.CONNECTED, ""))
    }

    @Test
    fun aNonSshBannerIsUnknownNotWedged() {
        assertEquals(SshdBannerProbe.UNKNOWN, classify(SshdConnect.CONNECTED, "HTTP/1.1 400"))
    }
}

class SshdConnectOutcomeTest {
    @Test
    fun socketTimeoutIsATimeout() {
        assertEquals(
            SshdConnect.TIMED_OUT,
            SshdBanner.connectOutcome(java.net.SocketTimeoutException("connect timed out")),
        )
    }

    @Test
    fun androidWordedRefusalIsRefused() {
        val msg = "failed to connect to /127.0.0.1 (port 8022): ECONNREFUSED (Connection refused)"
        val e = java.net.ConnectException(msg)
        assertEquals(SshdConnect.REFUSED, SshdBanner.connectOutcome(e))
    }

    @Test
    fun etimedoutConnectExceptionIsATimeout() {
        val e = java.net.ConnectException("isConnected failed: ETIMEDOUT (Connection timed out)")
        assertEquals(SshdConnect.TIMED_OUT, SshdBanner.connectOutcome(e))
    }

    @Test
    fun anythingElseIsAnError() {
        assertEquals(
            SshdConnect.ERROR,
            SshdBanner.connectOutcome(java.io.IOException("ENETUNREACH (Network is unreachable)")),
        )
    }
}

class SshdWedgeGuardTest {
    private val cooldownMs = 600_000L
    private val recheckMs = 5_000L
    private var clock = 1_000L
    private val sleeps = mutableListOf<Long>()
    private var probes = ArrayDeque<SshdBannerProbe>()

    private fun guard() =
        SshdWedgeGuard(
            probe = { probes.removeFirst() },
            sleep = {
                sleeps += it
                clock += it
            },
            now = { clock },
            recheckDelayMs = recheckMs,
            cooldownMs = cooldownMs,
        )

    private fun queue(vararg p: SshdBannerProbe) {
        probes = ArrayDeque(p.toList())
    }

    @Test
    fun healthyFirstProbeNeedsNoRecheck() {
        queue(SshdBannerProbe.HEALTHY)
        assertEquals(SshdWedgeGuard.Verdict.HEALTHY, guard().check())
        assertTrue(sleeps.isEmpty())
    }

    @Test
    fun oneWedgedProbeThenHealthyDoesNotAct() {
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.HEALTHY)
        assertEquals(SshdWedgeGuard.Verdict.NOT_WEDGED, guard().check())
        assertEquals(listOf(recheckMs), sleeps)
    }

    @Test
    fun oneWedgedProbeThenUnknownDoesNotAct() {
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.UNKNOWN)
        assertEquals(SshdWedgeGuard.Verdict.NOT_WEDGED, guard().check())
    }

    @Test
    fun refusedFirstProbeDoesNotRecheckOrAct() {
        queue(SshdBannerProbe.REFUSED)
        assertEquals(SshdWedgeGuard.Verdict.NOT_WEDGED, guard().check())
        assertTrue(sleeps.isEmpty())
    }

    @Test
    fun twoWedgedProbesApartActOnce() {
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, guard().check())
        assertEquals(listOf(recheckMs), sleeps)
    }

    @Test
    fun aSecondWedgeInsideTheCooldownDoesNotActAgain() {
        val g = guard()
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, g.check())
        clock += 60_000
        queue(SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_COOLDOWN, g.check())
    }

    @Test
    fun actsAgainOnceTheCooldownHasPassed() {
        val g = guard()
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, g.check())
        clock += cooldownMs
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, g.check())
    }

    @Test
    fun neverActedMustNotReadAsInCooldownRightAfterBoot() {
        // elapsedRealtime is tiny after a reboot.
        clock = 10L
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, guard().check())
    }

    @Test
    fun healthyBetweenWedgesDoesNotRearmTheCooldown() {
        val g = guard()
        queue(SshdBannerProbe.WEDGED, SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_ACT, g.check())
        clock += 60_000
        queue(SshdBannerProbe.HEALTHY)
        assertEquals(SshdWedgeGuard.Verdict.HEALTHY, g.check())
        clock += 60_000
        queue(SshdBannerProbe.WEDGED)
        assertEquals(SshdWedgeGuard.Verdict.WEDGED_COOLDOWN, g.check())
    }
}

class SshdWedgeDiagnosticsTest {
    private val text =
        listOf("a", "com.termux x", "isFrozen=true", "procState=7", "b", "c").joinToString("\n")

    @Test
    fun keepsOnlyMatchingLines() {
        val out = SshdWedgeDiagnostics.filterLines(text, Regex("termux"))
        assertEquals(listOf("com.termux x"), out)
    }

    @Test
    fun keepsTheContextLinesAfterAMatch() {
        val out = SshdWedgeDiagnostics.filterLines(text, Regex("termux"), after = 2)
        assertEquals(listOf("com.termux x", "isFrozen=true", "procState=7"), out)
    }

    @Test
    fun overlappingContextKeepsEachLineOnce() {
        val out = SshdWedgeDiagnostics.filterLines("m1\nm2\nx\ny", Regex("m"), after = 2)
        assertEquals(listOf("m1", "m2", "x", "y"), out)
    }

    @Test
    fun capsTheNumberOfLines() {
        val many = (1..100).joinToString("\n") { "sshd $it" }
        assertEquals(5, SshdWedgeDiagnostics.filterLines(many, Regex("sshd"), maxLines = 5).size)
    }

    @Test
    fun cutsLongLines() {
        val out = SshdWedgeDiagnostics.filterLines("x".repeat(500), Regex("x"), maxChars = 50)
        assertEquals(50, out.single().length)
    }

    @Test
    fun noMatchGivesNothing() {
        assertTrue(SshdWedgeDiagnostics.filterLines(text, Regex("zzz")).isEmpty())
    }
}

class SshdWedgeStatusTest {
    @Test
    fun verdictsMapToStatusTags() {
        assertEquals("ok", SshdWedge.tag(SshdWedgeGuard.Verdict.HEALTHY))
        assertEquals("unconfirmed", SshdWedge.tag(SshdWedgeGuard.Verdict.NOT_WEDGED))
        assertEquals("forcestopped", SshdWedge.tag(SshdWedgeGuard.Verdict.WEDGED_ACT))
        assertEquals("cooldown", SshdWedge.tag(SshdWedgeGuard.Verdict.WEDGED_COOLDOWN))
    }

    @Test
    fun readsTheWedgeTagFromAStatusLine() {
        val line = "[agent] STATUS port=open sshd=up sshd_wedge=forcestopped reason=x"
        assertEquals("forcestopped", SshdRecover.wedgeState(line))
        assertEquals("skip", SshdRecover.wedgeState("[agent] STATUS port=open sshd=up"))
    }

    @Test
    fun onlyAnSshdThatIsRunningIsProbed() {
        assertTrue(SshdWedge.shouldProbe("up"))
        assertFalse(SshdWedge.shouldProbe("down"))
        assertFalse(SshdWedge.shouldProbe("unknown"))
    }

    @Test
    fun forceStopCommandTargetsOnlyTermux() {
        assertEquals(
            listOf("am", "force-stop", "com.termux"),
            SshdWedge.FORCE_STOP_COMMAND.toList(),
        )
    }
}
