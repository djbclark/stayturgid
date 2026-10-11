package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure shell-command-builder tests — kept faithful to fire_peer_help.py. */
class PeerStartCommandsTest {
    @Test
    fun parsesApkPathFromPmOutput() {
        val out = "package:/data/app/~~aB1cD==/moe.shizuku.privileged.api-xY9==/base.apk\r\n"
        assertEquals(
            "/data/app/~~aB1cD==/moe.shizuku.privileged.api-xY9==/base.apk",
            PeerStartCommands.parseApkPath(out),
        )
    }

    @Test
    fun parseApkPathTakesFirstPackageLine() {
        val out =
            "package:/data/app/A/base.apk\n" + "package:/data/app/A/split_config.arm64_v8a.apk\n"
        assertEquals("/data/app/A/base.apk", PeerStartCommands.parseApkPath(out))
    }

    @Test
    fun parseApkPathNullWhenNotInstalled() {
        assertNull(PeerStartCommands.parseApkPath(""))
        assertNull(PeerStartCommands.parseApkPath("cmd: Failure\n"))
    }

    @Test
    fun apkDirIsParentOfBaseApk() {
        assertEquals(
            "/data/app/~~aB==/moe.shizuku.privileged.api-xY==",
            PeerStartCommands.apkDirFor("/data/app/~~aB==/moe.shizuku.privileged.api-xY==/base.apk"),
        )
    }

    @Test
    fun starterCommandResolvesLibDirWithoutStartShFallback() {
        val apkDir = "/data/app/~~aB==/moe.shizuku.privileged.api-xY=="
        val cmd = PeerStartCommands.starterCommand(apkDir)
        assertTrue(cmd.startsWith("d='$apkDir'; "))
        assertTrue(cmd.contains("getprop ro.product.cpu.abi"))
        assertTrue(cmd.contains("lib/*/libshizuku.so"))
        assertTrue(cmd.contains("LD_LIBRARY_PATH=\$libdir \"\$libdir/libshizuku.so\""))
        assertFalse(cmd.contains("lib/arm64"))
        assertFalse(cmd.contains("start.sh"))
    }

    @Test
    fun runningCheckUsesBracketTrickAndEmitsUpDown() {
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("[s]hizuku_(plus_)?server"))
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("echo up"))
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("echo down"))
    }
}
