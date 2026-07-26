package org.stayturgid.agent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Pure host:port parsing — no Android deps. */
class PeerTargetTest {
    @Test
    fun parsesHostAndPort() {
        val t = PeerTarget.parseOrNull("100.124.55.39:5555")
        assertEquals(PeerTarget("100.124.55.39", 5555), t)
        assertEquals("100.124.55.39:5555", t.toString())
    }

    @Test
    fun bareHostDefaultsToAdbPort() {
        assertEquals(PeerTarget("100.124.55.39", 5555), PeerTarget.parseOrNull("100.124.55.39"))
    }

    @Test
    fun rejectsMalformedPort() {
        assertNull(PeerTarget.parseOrNull("host:notaport"))
    }

    @Test
    fun rejectsBlankMissingHostAndOutOfRange() {
        assertNull(PeerTarget.parseOrNull(""))
        assertNull(PeerTarget.parseOrNull("   "))
        assertNull(PeerTarget.parseOrNull(":5555"))
        assertNull(PeerTarget.parseOrNull("host:0"))
        assertNull(PeerTarget.parseOrNull("host:70000"))
    }

    @Test
    fun trimsWhitespace() {
        assertEquals(PeerTarget("10.0.0.1", 5555), PeerTarget.parseOrNull("  10.0.0.1:5555  "))
    }
}
