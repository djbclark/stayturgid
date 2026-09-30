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
        assertEquals(listOf(0, 9, 10), UpdateCheck.parseVersion("agent-v0.9.10"))
        assertEquals(listOf(0, 9, 10), UpdateCheck.parseVersion("0.9.10-heartbeat-dedupe"))
        assertNull(UpdateCheck.parseVersion("ops-v1.3.26x"))
    }

    @Test
    fun comparesNumericallyNotLexically() {
        assertTrue(UpdateCheck.isNewer("0.9.10", "0.9.9-bind-self-heal"))
        assertFalse(UpdateCheck.isNewer("0.9.9", "0.9.10-heartbeat-dedupe"))
        assertFalse(UpdateCheck.isNewer("0.9.10", "0.9.10-heartbeat-dedupe"))
        assertTrue(UpdateCheck.isNewer("1.0", "0.9.10"))
    }

    @Test
    fun newestAgentReleaseIgnoresOtherTagsDraftsAndPrereleases() {
        val rows =
            listOf(
                row("ops-v9.9.9"),
                row("agent-v0.9.12", prerelease = true),
                row("agent-v0.9.13", draft = true),
                row("agent-v0.9.9"),
                row("agent-v0.9.11"),
                row("agent-v0.9.10"),
            )
        assertEquals(
            UpdateCheck.Release("0.9.11", "https://example/agent-v0.9.11"),
            UpdateCheck.newestAgentRelease(rows),
        )
        assertNull(UpdateCheck.newestAgentRelease(listOf(row("ops-v1.0.0"))))
    }
}
