package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * Pure stalePidsToReap() tests (#65) — the pidof/kill IO in reapStaleUserServices() itself isn't
 * unit-testable without shelling out, but the "which pids are stale" decision is pure and is what
 * actually matters for correctness.
 */
class ShizukuUserServiceTest {
    @Test
    fun excludesOwnPidFromMultiplePids() {
        assertEquals(
            listOf(101, 103),
            ShizukuUserService.stalePidsToReap("101 102 103", myPid = 102),
        )
    }

    @Test
    fun emptyPidofOutputYieldsNothingToReap() {
        assertTrue(ShizukuUserService.stalePidsToReap("", myPid = 42).isEmpty())
    }

    @Test
    fun onlySelfRunningYieldsNothingToReap() {
        assertTrue(ShizukuUserService.stalePidsToReap("42", myPid = 42).isEmpty())
    }

    @Test
    fun tabsAndNewlinesAreValidSeparators() {
        assertEquals(
            listOf(10, 20, 30),
            ShizukuUserService.stalePidsToReap("10\t20\n30", myPid = 999),
        )
    }

    @Test
    fun nonNumericTokensAreIgnored() {
        assertEquals(
            listOf(10, 20),
            ShizukuUserService.stalePidsToReap("10 notapid 20", myPid = 999),
        )
    }
}
