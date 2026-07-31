package org.stayturgid.agent

import java.util.Base64
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.stayturgid.agent.adb.AdbProtocol.A_MAXDATA

/** Pure shell-command-builder tests — kept faithful to fire_peer_help.py's cmd_handsets_start. */
class HandsetsStartCommandsTest {
    @Test
    fun niceNameEmbedsPort() {
        assertEquals("hsd9012", HandsetsStartCommands.niceName(9012))
        assertEquals("hsd9013", HandsetsStartCommands.niceName(9013))
    }

    @Test
    fun jarExistsCheckTestsRemotePath() {
        val cmd = HandsetsStartCommands.jarExistsCheck()
        assertTrue(cmd.contains("test -f '${HandsetsStartCommands.REMOTE_JAR_PATH}'"))
        assertTrue(cmd.contains("echo present"))
        assertTrue(cmd.contains("echo absent"))
    }

    @Test
    fun jarPresentTrueOnlyWhenOutputSaysPresent() {
        assertTrue(HandsetsStartCommands.jarPresent("present\n"))
        assertTrue(!HandsetsStartCommands.jarPresent("absent\n"))
        assertTrue(!HandsetsStartCommands.jarPresent(""))
    }

    @Test
    fun base64ChunksEmptyForEmptyInput() {
        assertEquals(emptyList<String>(), HandsetsStartCommands.base64Chunks(ByteArray(0)))
    }

    @Test
    fun base64ChunksRoundTripsAndRespectsChunkSize() {
        val data = ByteArray(10_000) { (it % 251).toByte() }
        val chunks = HandsetsStartCommands.base64Chunks(data, chunkSize = 3_000)
        // ceil(10000 / 3000) = 4
        assertEquals(4, chunks.size)
        val decoded = chunks.flatMap { Base64.getDecoder().decode(it).toList() }
        assertEquals(data.toList(), decoded)
    }

    @Test
    fun base64ChunksSingleChunkWhenSmallerThanChunkSize() {
        val data = byteArrayOf(1, 2, 3)
        val chunks = HandsetsStartCommands.base64Chunks(data, chunkSize = 3_000)
        assertEquals(1, chunks.size)
        assertEquals(data.toList(), Base64.getDecoder().decode(chunks[0]).toList())
    }

    @Test
    fun base64ChunksRejectsNonPositiveChunkSize() {
        try {
            HandsetsStartCommands.base64Chunks(byteArrayOf(1), chunkSize = 0)
            throw AssertionError("expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
            // expected
        }
    }

    @Test
    fun defaultChunkSizeLeavesRealMarginAgainstAdbMaxData() {
        // AdbClient.command() sends the whole "shell:<cmd>" string as one unchunked A_OPEN
        // payload, and AdbMessage appends a trailing NUL byte — so the worst-case full command
        // (max-size chunk, "append" redirect, which is one char longer than the first chunk's)
        // must leave a comfortable margin against A_MAXDATA, not just be smaller than it. This
        // pins that invariant against the real protocol constant so a future change to
        // PUSH_CHUNK_BYTES or REMOTE_JAR_PATH can't silently shrink the margin back to nothing.
        val maxChunk = ByteArray(HandsetsStartCommands.PUSH_CHUNK_BYTES) { 0xFF.toByte() }
        val encoded = Base64.getEncoder().encodeToString(maxChunk)
        val cmd = HandsetsStartCommands.writeChunkCommand(encoded, append = true)
        val fullShellPayloadBytes =
            ("shell:$cmd").toByteArray(Charsets.UTF_8).size + 1 // NUL terminator
        val margin = A_MAXDATA - fullShellPayloadBytes
        assertTrue(
            margin >= 1_000,
            "push-chunk command only has $margin bytes of margin against A_MAXDATA " +
                "($A_MAXDATA) — was $fullShellPayloadBytes bytes; shrink PUSH_CHUNK_BYTES",
        )
    }

    @Test
    fun writeChunkCommandTruncatesFirstChunkAndAppendsRest() {
        val first = HandsetsStartCommands.writeChunkCommand("QUJD", append = false)
        val rest = HandsetsStartCommands.writeChunkCommand("REVG", append = true)
        assertTrue(first.contains("base64 -d > '${HandsetsStartCommands.REMOTE_JAR_PATH}'"))
        assertTrue(rest.contains("base64 -d >> '${HandsetsStartCommands.REMOTE_JAR_PATH}'"))
        assertTrue(first.contains("printf '%s' 'QUJD'"))
    }

    @Test
    fun killCommandTargetsNiceNameAndFullClassInvocation() {
        val cmd = HandsetsStartCommands.killCommand(9012)
        assertTrue(cmd.contains("pkill -f 'hsd9012'"))
        assertTrue(cmd.contains("pkill -f 'dev.handsets.daemon.Main --port=9012'"))
        assertTrue(cmd.trim().endsWith("true"))
    }

    @Test
    fun startCommandSetsClasspathNiceNameAndLogRedirect() {
        val cmd = HandsetsStartCommands.startCommand(9012)
        assertTrue(cmd.contains("CLASSPATH='${HandsetsStartCommands.REMOTE_JAR_PATH}'"))
        assertTrue(cmd.contains("--nice-name=hsd9012"))
        assertTrue(cmd.contains("dev.handsets.daemon.Main --port=9012"))
        assertTrue(cmd.contains(">/data/local/tmp/hsd9012.log 2>&1 &"))
    }

    @Test
    fun pollCommandChecksPortViaNcSsAndLogFallback() {
        val cmd = HandsetsStartCommands.pollCommand(9012)
        assertTrue(cmd.contains("nc -z 127.0.0.1 9012"))
        assertTrue(cmd.contains("ss -lntp"))
        assertTrue(cmd.contains("/data/local/tmp/hsd9012.log"))
        assertTrue(cmd.contains("echo up"))
        assertTrue(cmd.contains("echo down"))
    }

    @Test
    fun isUpTrueOnlyWhenOutputContainsUp() {
        assertTrue(HandsetsStartCommands.isUp("up\n"))
        assertTrue(!HandsetsStartCommands.isUp("down\n"))
        assertTrue(!HandsetsStartCommands.isUp(""))
    }

    @Test
    fun tailLogCommandUsesNiceNamedLogFile() {
        val cmd = HandsetsStartCommands.tailLogCommand(9012)
        assertEquals("tail -20 /data/local/tmp/hsd9012.log", cmd)
    }
}
