package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class ComonitorA11yTest {
    @Test
    fun uninstalledAutoJsIsRetired() {
        assertEquals("retired", ComonitorProbes.a11yListed(false, null))
        assertEquals("retired", ComonitorProbes.a11yListed(false, "org.autojs.autojs6/x"))
    }

    @Test
    fun installedAutoJsFollowsTheSettingsList() {
        assertEquals("down", ComonitorProbes.a11yListed(true, null))
        assertEquals("down", ComonitorProbes.a11yListed(true, "null"))
        assertEquals(
            "up",
            ComonitorProbes.a11yListed(
                true,
                "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityService",
            ),
        )
        assertEquals("down", ComonitorProbes.a11yListed(true, "com.other/.Service"))
    }

    @Test
    fun unknownInstallFallsThroughToTheList() {
        assertEquals("down", ComonitorProbes.a11yListed(null, ""))
        assertEquals("up", ComonitorProbes.a11yListed(null, "org.autojs.autojs6/anything"))
    }
}
