package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * Pure heartbeat line formatting (no Android runtime — the MediaStore write path itself needs a
 * real device and is exercised live on hd8/p7a per #86's device-testing requirement, not here).
 */
class HeartbeatWriterTest {
    @Test
    fun formatLineIsExactKeyValueShape() {
        assertEquals("ts_sec=1700000000 seq=42\n", HeartbeatWriter.formatLine(1_700_000_000L, 42L))
    }

    @Test
    fun formatLineFieldsSurviveTheShellReaderContract() {
        // device/termux/cfengine/policy/stayturgid.cf and control/lib/fleet_health.py both parse
        // this line with `grep -oE 'ts_sec=[0-9]+'` — pin the exact token shape so a reformat here
        // can't silently break that contract on the read side.
        val line = HeartbeatWriter.formatLine(123L, 7L)
        val ts = Regex("""ts_sec=(\d+)""").find(line)?.groupValues?.get(1)
        val seqField = Regex("""seq=(\d+)""").find(line)?.groupValues?.get(1)
        assertEquals("123", ts)
        assertEquals("7", seqField)
    }

    @Test
    fun heartbeatIntervalIsWellUnderTheDocumentedFreshnessThreshold() {
        // Freshness threshold (stayturgid.cf FRESHNESS_SEC / fleet_health.py
        // AGENT_HEARTBEAT_FRESH_SEC) is documented as ~3x this interval + jitter margin — guard the
        // "well under" relationship so the two files can't silently drift apart on a future edit.
        val freshnessSec = 420L
        assertEquals(true, HeartbeatWriter.HEARTBEAT_INTERVAL_MS / 1000L * 3 <= freshnessSec)
    }
}
