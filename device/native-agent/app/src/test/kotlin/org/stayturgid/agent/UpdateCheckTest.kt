package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class UpdateCheckTest {
    private fun row(tag: String, draft: Boolean = false, prerelease: Boolean = false) =
        UpdateCheck.ReleaseRow(tag, "https://example/$tag", draft, prerelease)

    @Test
    fun parsesTagsAndSuffixedVersionNames() {
        assertEquals(listOf(102), UpdateCheck.parseVersion("agent-r102"))
        assertEquals(listOf(0, 9, 10), UpdateCheck.parseVersion("0.9.10-heartbeat-dedupe"))
        assertEquals(listOf(0, 9, 102), UpdateCheck.parseVersion("0.9.102+ab12cd34"))
        assertNull(UpdateCheck.parseVersion("ops-v1.3.26x"))
    }

    @Test
    fun comparesNumericallyNotLexically() {
        assertTrue(UpdateCheck.isNewer("0.9.10", "0.9.9-bind-self-heal"))
        assertFalse(UpdateCheck.isNewer("0.9.9", "0.9.10-heartbeat-dedupe"))
        assertFalse(UpdateCheck.isNewer("0.9.10", "0.9.10-heartbeat-dedupe"))
        assertTrue(UpdateCheck.isNewer("1.0", "0.9.10"))
        assertTrue(UpdateCheck.isNewer("agent-r102", "99"))
        assertFalse(UpdateCheck.isNewer("agent-r102", "102"))
    }

    @Test
    fun updateIsAvailableOnlyForAHigherVersionCode() {
        val release = UpdateCheck.Release("102", "https://example/agent-r102")
        assertTrue(UpdateCheck.Status("0.9.101+ab12cd34", release, 0L, 101).updateAvailable)
        assertFalse(UpdateCheck.Status("0.9.102+ab12cd34", release, 0L, 102).updateAvailable)
        assertFalse(UpdateCheck.Status("0.9.103+ab12cd34", release, 0L, 103).updateAvailable)
        assertFalse(UpdateCheck.Status("0.9.19", null, 0L, 37).updateAvailable)
    }

    @Test
    fun newestAgentReleaseIgnoresOtherTagsDraftsAndPrereleases() {
        val rows =
            listOf(
                row("ops-v9.9.9"),
                row("agent-v0.9.19"),
                row("agent-ci-0.9.19-cdd76c47", prerelease = true),
                row("agent-r105", prerelease = true),
                row("agent-r106", draft = true),
                row("agent-r99"),
                row("agent-r103"),
                row("agent-r101"),
            )
        assertEquals(
            UpdateCheck.Release("103", "https://example/agent-r103"),
            UpdateCheck.newestAgentRelease(rows),
        )
        assertNull(UpdateCheck.newestAgentRelease(listOf(row("ops-v1.0.0"))))
    }
}
