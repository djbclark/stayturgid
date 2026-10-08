package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Mirrors tests/python/test_wireless_debug_handoff.py. */
class ShizukuWirelessOwnerTest {
    @Test
    fun parsesTheRevisionOfAShizukuTendCfVersionName() {
        assertEquals(
            2842,
            ShizukuWirelessOwner.parseRevision("    versionName=ShizukuTendCF 13.7.0.r2842\n"),
        )
        assertEquals(
            2850,
            ShizukuWirelessOwner.parseRevision("vShizukuTendCF 13.7.0.r2850) AUTH_UNANSWERED"),
        )
    }

    @Test
    fun otherBuildsHaveNoRevision() {
        assertNull(ShizukuWirelessOwner.parseRevision("    versionName=13.7.0.r2900\n"))
        assertNull(ShizukuWirelessOwner.parseRevision("    versionName=ShizukuPlus 13.7.0\n"))
        assertNull(ShizukuWirelessOwner.parseRevision(""))
        assertNull(ShizukuWirelessOwner.parseRevision(null))
    }

    @Test
    fun theAppOwnsTheRestoreFromR2842() {
        assertTrue(ShizukuWirelessOwner.appOwnsWirelessRestore(2842))
        assertTrue(ShizukuWirelessOwner.appOwnsWirelessRestore(2900))
        assertFalse(ShizukuWirelessOwner.appOwnsWirelessRestore(2841))
        assertFalse(ShizukuWirelessOwner.appOwnsWirelessRestore(null))
    }

    @Test
    fun versionNameCommandNamesThePackage() {
        val command = ShizukuWirelessOwner.versionNameCommand("moe.shizuku.privileged.api")
        assertTrue(command.startsWith("dumpsys package moe.shizuku.privileged.api"))
    }
}
