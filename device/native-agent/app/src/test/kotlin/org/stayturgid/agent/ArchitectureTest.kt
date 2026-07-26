package org.stayturgid.agent

import com.lemonappdev.konsist.api.Konsist
import com.lemonappdev.konsist.api.ext.list.withNameEndingWith
import com.lemonappdev.konsist.api.verify.assertTrue
import org.junit.jupiter.api.Test

/**
 * Architectural consistency checks enforced as unit tests via Konsist.
 *
 * These ensure the codebase structure stays predictable as new code is added. Add new rules here
 * whenever a structural convention is established.
 */
class ArchitectureTest {

    /**
     * All BroadcastReceivers must live in the agent package root (not sub-packages) and have names
     * ending with "Receiver".
     */
    @Test
    fun `classes ending with Receiver should reside in the agent package`() {
        Konsist.scopeFromProject().classes().withNameEndingWith("Receiver").assertTrue {
            it.resideInPackage("org.stayturgid.agent")
        }
    }

    /**
     * ADB protocol classes must be scoped to the adb sub-package — they should not leak into the
     * top-level agent package.
     */
    @Test
    fun `adb classes should reside in the adb sub-package`() {
        Konsist.scopeFromProject().classes().withNameEndingWith("Adb").assertTrue {
            it.resideInPackage("org.stayturgid.agent.adb..")
        }
    }

    /**
     * No source file should exceed a reasonable line count — a signal that the class should be
     * split.
     */
    @Test
    fun `no source file should exceed 800 lines`() {
        Konsist.scopeFromProject()
            .files
            .assertTrue { it.text.lines().size < 800 }
    }
}
