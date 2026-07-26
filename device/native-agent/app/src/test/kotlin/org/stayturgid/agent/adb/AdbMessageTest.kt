package org.stayturgid.agent.adb

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Pure wire-framing tests — no Android/socket dependencies. */
class AdbMessageTest {
    @Test
    fun magicIsCommandXorMinusOne() {
        val m = AdbMessage(AdbProtocol.A_OPEN, 1, 0, null as ByteArray?)
        assertEquals(AdbProtocol.A_OPEN xor -0x1, m.magic)
        assertTrue(m.validate())
    }

    @Test
    fun headerRoundTripsLittleEndian() {
        val m = AdbMessage(AdbProtocol.A_CNXN, AdbProtocol.A_VERSION, AdbProtocol.A_MAXDATA, "host::")
        val bytes = m.toByteArray()

        val buf = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(AdbProtocol.A_CNXN, buf.int)
        assertEquals(AdbProtocol.A_VERSION, buf.int)
        assertEquals(AdbProtocol.A_MAXDATA, buf.int)
        // data_length includes the trailing NUL the String ctor appends.
        assertEquals("host::".length + 1, buf.int)
    }

    @Test
    fun stringConstructorNullTerminates() {
        val m = AdbMessage(AdbProtocol.A_OPEN, 1, 0, "shell:id")
        val data = m.data!!
        assertEquals("shell:id".length + 1, data.size)
        assertEquals(0.toByte(), data.last())
    }

    @Test
    fun crc32IsUnsignedByteSum() {
        // Two bytes whose signed values are negative (0xFF each) must sum as 255+255.
        val payload = byteArrayOf(0xFF.toByte(), 0xFF.toByte())
        val m = AdbMessage(AdbProtocol.A_WRTE, 1, 1, payload)
        assertEquals(510, m.data_crc32)
        assertTrue(m.validate())
    }

    @Test
    fun tamperedCrcFailsValidation() {
        val good = AdbMessage(AdbProtocol.A_WRTE, 1, 1, byteArrayOf(1, 2, 3))
        val bad = AdbMessage(good.command, good.arg0, good.arg1, good.data_length, good.data_crc32 + 1, good.magic, good.data)
        assertFalse(bad.validate())
    }

    @Test
    fun payloadAppendedAfterHeader() {
        val payload = byteArrayOf(10, 20, 30)
        val m = AdbMessage(AdbProtocol.A_WRTE, 2, 3, payload)
        val bytes = m.toByteArray()
        assertEquals(AdbMessage.HEADER_LENGTH + payload.size, bytes.size)
        assertArrayEquals(payload, bytes.copyOfRange(AdbMessage.HEADER_LENGTH, bytes.size))
    }
}
