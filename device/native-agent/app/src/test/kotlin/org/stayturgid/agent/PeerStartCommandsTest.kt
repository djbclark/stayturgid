package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
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
    fun libDirIsArm64UnderApkDir() {
        assertEquals(
            "/data/app/~~aB==/moe.shizuku.privileged.api-xY==/lib/arm64",
            PeerStartCommands.libDirFor("/data/app/~~aB==/moe.shizuku.privileged.api-xY==/base.apk"),
        )
    }

    @Test
    fun starterCommandQuotesLibDirAndFallsBack() {
        val libDir = "/data/app/~~aB==/moe.shizuku.privileged.api-xY==/lib/arm64"
        val cmd = PeerStartCommands.starterCommand(libDir, "moe.shizuku.privileged.api")
        assertTrue(cmd.contains("LD_LIBRARY_PATH='$libDir' '$libDir/libshizuku.so'"))
        assertTrue(cmd.contains("test -x '$libDir/libshizuku.so'"))
        assertTrue(
            cmd.contains("sh /storage/emulated/0/Android/data/moe.shizuku.privileged.api/start.sh")
        )
    }

    @Test
    fun runningCheckUsesBracketTrickAndEmitsUpDown() {
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("[s]hizuku_server"))
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("echo up"))
        assertTrue(PeerStartCommands.SHIZUKU_RUNNING_CHECK.contains("echo down"))
    }
}
