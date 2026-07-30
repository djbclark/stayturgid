package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure parse tests — mirrors device.json's `privilegedShellExpected` semantics from #60. */
class DeviceProfileTest {
    @Test
    fun explicitFalseIsRespected() {
        val json = """{"id":"hd8","privilegedShellExpected":false}"""
        assertFalse(DeviceProfile.parsePrivilegedShellExpected(json))
    }

    @Test
    fun explicitTrueIsRespected() {
        val json = """{"id":"s24","privilegedShellExpected":true}"""
        assertTrue(DeviceProfile.parsePrivilegedShellExpected(json))
    }

    @Test
    fun missingFieldDefaultsToTrue() {
        assertTrue(DeviceProfile.parsePrivilegedShellExpected("""{"id":"s24"}"""))
    }

    @Test
    fun emptyObjectDefaultsToTrue() {
        assertTrue(DeviceProfile.parsePrivilegedShellExpected("{}"))
    }
}
