package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure per-device stagger fraction (no Android runtime). */
class AgentScheduleTest {
    @Test
    fun fractionInUnitInterval() {
        for (id in listOf("abc123", "0000ffff", "deadbeefcafef00d", "z")) {
            val f = AgentSchedule.fractionForId(id)
            assertTrue(f >= 0.0 && f < 1.0, "$id -> $f")
        }
    }

    @Test
    fun deterministicForSameId() {
        assertEquals(
            AgentSchedule.fractionForId("deadbeef"),
            AgentSchedule.fractionForId("deadbeef"),
            0.0,
        )
    }

    @Test
    fun differsAcrossDevices() {
        // Distinct ids should generally map to distinct phases (spreads the fleet).
        assertNotEquals(
            AgentSchedule.fractionForId("device-a"),
            AgentSchedule.fractionForId("device-b"),
        )
    }

    @Test
    fun missingIdIsUnstaggered() {
        assertEquals(0.0, AgentSchedule.fractionForId(null), 0.0)
        assertEquals(0.0, AgentSchedule.fractionForId(""), 0.0)
        assertEquals(0.0, AgentSchedule.fractionForId("   "), 0.0)
    }
}
