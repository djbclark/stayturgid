package org.stayturgid.agent

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** Pure /proc/net/dev parsing for the Tailscale tunnel probe — no Android deps. */
class ComonitorProbesTest {
    private val tun1NetDev =
        """
        Inter-|   Receive                                                |  Transmit
         face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
            lo: 7592867   32776    0    0    0     0          0         0  7592867   32776    0    0    0     0       0          0
         tunl0:       0       0    0    0    0     0          0         0        0       0    0    0    0     0       0          0
         wlan0: 27046635   64812    0    0    0     0          0         0 11349680   52068    0    0    0     0       0          0
          tun1:  416727    5987    0    0    0     0          0         0   450986    5923    0    0    0     0       0          0
        """
            .trimIndent()

    private val tun0NetDev =
        """
        Inter-|   Receive                                                |  Transmit
         face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
            lo: 7592867   32776    0    0    0     0          0         0  7592867   32776    0    0    0     0       0          0
          tun0:  416727    5987    0    0    0     0          0         0   450986    5923    0    0    0     0       0          0
        """
            .trimIndent()

    private val noTunnelNetDev =
        """
        Inter-|   Receive                                                |  Transmit
         face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
            lo: 7592867   32776    0    0    0     0          0         0  7592867   32776    0    0    0     0       0          0
         tunl0:       0       0    0    0    0     0          0         0        0       0    0    0    0     0       0          0
         wlan0: 27046635   64812    0    0    0     0          0         0 11349680   52068    0    0    0     0       0          0
        """
            .trimIndent()

    @Test
    fun recognizesTun1() {
        // Regression: s24 and t2e both allocate tun1, not tun0, for the
        // Tailscale VpnService — a hardcoded "tun0" check false-negatives here.
        assertTrue(ComonitorProbes.hasTunnelInterface(tun1NetDev))
    }

    @Test
    fun recognizesTun0() {
        assertTrue(ComonitorProbes.hasTunnelInterface(tun0NetDev))
    }

    @Test
    fun ignoresTunl0IpIpTunnelModule() {
        // tunl0 (IP-IP tunnel) is always present and never a VPN — must not
        // false-positive on its "tun" prefix.
        assertFalse(ComonitorProbes.hasTunnelInterface(noTunnelNetDev))
    }

    @Test
    fun recognizesTailscale0Name() {
        val netDev =
            """
            Inter-|   Receive                                                |  Transmit
             face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
            tailscale0:  416727    5987    0    0    0     0          0         0   450986    5923    0    0    0     0       0          0
            """
                .trimIndent()
        assertTrue(ComonitorProbes.hasTunnelInterface(netDev))
    }
}
