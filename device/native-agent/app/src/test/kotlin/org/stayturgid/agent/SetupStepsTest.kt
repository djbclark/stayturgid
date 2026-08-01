package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure outstandingSetupSteps() ordering/gating tests — no Android runtime involved. */
class SetupStepsTest {
    private fun signals(
        shizukuBinderAlive: Boolean = true,
        shizukuPermissionGranted: Boolean = true,
        postNotificationsApplicable: Boolean = false,
        postNotificationsGranted: Boolean = true,
        wirelessDebuggingApplicable: Boolean = false,
        wirelessDebuggingOn: Boolean = true,
    ) =
        SetupSignals(
            shizukuBinderAlive = shizukuBinderAlive,
            shizukuPermissionGranted = shizukuPermissionGranted,
            postNotificationsApplicable = postNotificationsApplicable,
            postNotificationsGranted = postNotificationsGranted,
            wirelessDebuggingApplicable = wirelessDebuggingApplicable,
            wirelessDebuggingOn = wirelessDebuggingOn,
        )

    @Test
    fun allSatisfiedYieldsNoSteps() {
        assertTrue(outstandingSetupSteps(signals()).isEmpty())
    }

    @Test
    fun binderDeadOnlyShowsStartShizuku() {
        assertEquals(
            listOf(SetupStep.START_SHIZUKU),
            outstandingSetupSteps(
                signals(shizukuBinderAlive = false, shizukuPermissionGranted = false)
            ),
        )
    }

    @Test
    fun permissionStepNeverShowsBeforeBinderIsAlive() {
        val steps =
            outstandingSetupSteps(
                signals(shizukuBinderAlive = false, shizukuPermissionGranted = false)
            )
        assertTrue(SetupStep.GRANT_SHIZUKU_PERMISSION !in steps)
    }

    @Test
    fun permissionStepShowsOnceBinderIsAliveButUngranted() {
        assertEquals(
            listOf(SetupStep.GRANT_SHIZUKU_PERMISSION),
            outstandingSetupSteps(signals(shizukuPermissionGranted = false)),
        )
    }

    @Test
    fun notificationsStepOnlyShowsWhenApplicableAndUngranted() {
        val notApplicable =
            signals(postNotificationsApplicable = false, postNotificationsGranted = false)
        assertTrue(outstandingSetupSteps(notApplicable).isEmpty())
        assertEquals(
            listOf(SetupStep.ENABLE_NOTIFICATIONS),
            outstandingSetupSteps(
                signals(postNotificationsApplicable = true, postNotificationsGranted = false)
            ),
        )
    }

    @Test
    fun wirelessDebuggingStepOnlyShowsWhenApplicableAndOff() {
        val notApplicable =
            signals(wirelessDebuggingApplicable = false, wirelessDebuggingOn = false)
        assertTrue(outstandingSetupSteps(notApplicable).isEmpty())
        assertEquals(
            listOf(SetupStep.ENABLE_WIRELESS_DEBUGGING),
            outstandingSetupSteps(
                signals(wirelessDebuggingApplicable = true, wirelessDebuggingOn = false)
            ),
        )
    }

    @Test
    fun everythingOutstandingPreservesDisplayOrder() {
        assertEquals(
            listOf(
                SetupStep.START_SHIZUKU,
                SetupStep.ENABLE_NOTIFICATIONS,
                SetupStep.ENABLE_WIRELESS_DEBUGGING,
            ),
            outstandingSetupSteps(
                signals(
                    shizukuBinderAlive = false,
                    shizukuPermissionGranted = false,
                    postNotificationsApplicable = true,
                    postNotificationsGranted = false,
                    wirelessDebuggingApplicable = true,
                    wirelessDebuggingOn = false,
                )
            ),
        )
    }
}
