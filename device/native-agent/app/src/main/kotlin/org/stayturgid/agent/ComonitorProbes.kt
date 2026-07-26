package org.stayturgid.agent

import android.os.Process
import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Co-monitor probes run inside the UserService process (UID 2000).
 *
 * Prefer direct /proc and settings reads; shell is a last resort and must not be used for the
 * [ShizukuUserService.pingAwake] path.
 *
 * STATUS shape mirrors AutoJs6 comonitor so fleet scrapers can dual-read during dual-run (Phase 2).
 * Detection-only for a11y — never settings put.
 */
object ComonitorProbes {
    private const val TAG = "StayTurgidComo"
    private const val LOG_PATH = "/sdcard/stayturgid/logs/agent.log"
    private const val A11Y_AUTOJS6 =
        "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityService"
    private const val TAILSCALE_PACKAGE = "com.tailscale.ipn"
    private const val TAILSCALE_CONTROL_HOST = "controlplane.tailscale.com"

    data class Status(
        val port: String,
        val shizuku: String,
        val sshd: String,
        val a11y: String,
        val shell: String,
        val wifi: String,
        val tailscale: String,
        val tailscalePolicy: String,
        val reason: String,
    ) {
        fun line(ts: String): String =
            "[agent] STATUS port=$port shizuku=$shizuku sshd=$sshd a11y=$a11y shell=$shell wifi=$wifi tailscale=$tailscale tailscale_policy=$tailscalePolicy reason=$reason ts=$ts uid=${Process.myUid()}"
    }

    fun runAndLog(): String {
        val st = probe()
        val ts = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
        val line = st.line(ts)
        appendLog(line)
        Log.i(TAG, line)
        return line
    }

    fun probe(): Status {
        val sshd = if (pgrepMatch("sshd")) "up" else "down"
        // We are running as Shizuku UserService → binder path is up.
        val shizuku = "up"
        val a11y = probeA11yListed()
        val port5555 = probePort5555()
        val shell = if (port5555 == "open") "yes" else "no"
        val wifi = probeWifi()
        val tailscale = probeTailscale()
        val tailscalePolicy = probeTailscalePolicy()
        val reason = "agent-comonitor"
        return Status(
            port = port5555,
            shizuku = shizuku,
            sshd = sshd,
            a11y = a11y,
            shell = shell,
            wifi = wifi,
            tailscale = tailscale,
            tailscalePolicy = tailscalePolicy,
            reason = reason,
        )
    }

    private fun probeTailscale(): String {
        val installed = shellOut(arrayOf("pm", "path", TAILSCALE_PACKAGE), 4)
        if (installed.isNullOrBlank() || !installed.contains("package:")) return "skip"
        val netDev = readText("/proc/net/dev").orEmpty()
        val tunnelUp =
            netDev.lineSequence().any { line ->
                val iface = line.substringBefore(':').trim()
                iface == "tun0" || iface == "tailscale0"
            }
        val controlPlaneUp =
            commandOk(arrayOf("ping", "-c", "1", "-W", "2", TAILSCALE_CONTROL_HOST), 4)
        return if (tunnelUp && controlPlaneUp) "up" else "down"
    }

    private fun probeTailscalePolicy(): String {
        val installed = shellOut(arrayOf("pm", "path", TAILSCALE_PACKAGE), 4)
        if (installed.isNullOrBlank() || !installed.contains("package:")) return "skip"
        val app = settingsGet("secure", "always_on_vpn_app")?.trim()
        val lockdown = settingsGet("secure", "always_on_vpn_lockdown")?.trim()
        return if (app == TAILSCALE_PACKAGE && lockdown == "0") "up" else "down"
    }

    private fun probeA11yListed(): String {
        val list = settingsGet("secure", "enabled_accessibility_services")
        if (list.isNullOrBlank() || list == "null") return "down"
        return if (list.contains(A11Y_AUTOJS6) || list.contains("org.autojs.autojs6")) "up"
        else "down"
    }

    private fun probePort5555(): String {
        // service.adb.tcp.port or ss/netstat on 5555
        val prop = getprop("service.adb.tcp.port")
        if (prop == "5555") {
            return if (listeningOn(5555)) "open" else "CLOSED_NO_SHELL"
        }
        return if (listeningOn(5555)) "open" else "CLOSED_NO_SHELL"
    }

    private fun probeWifi(): String {
        // iw or dumpsys — keep light: check wlan0 sysfs operstate
        val oper = readText("/sys/class/net/wlan0/operstate")?.trim()
        return when (oper) {
            "up" -> "up"
            null,
            "" -> "skip"
            else -> "FAILED"
        }
    }

    private fun settingsGet(namespace: String, key: String): String? {
        // settings binary is fine under shell UID for co-monitor (not inject path).
        return shellOut(arrayOf("settings", "get", namespace, key), 4)
    }

    private fun getprop(key: String): String? = shellOut(arrayOf("getprop", key), 3)

    private fun pgrepMatch(name: String): Boolean {
        // Avoid pgrep binary portability; scan /proc.
        val proc = File("/proc")
        val dirs =
            proc.listFiles { f -> f.isDirectory && f.name.all { it.isDigit() } } ?: return false
        for (d in dirs) {
            val cmdline = readText(File(d, "cmdline").path)?.replace('\u0000', ' ') ?: continue
            if (cmdline.contains(name)) return true
        }
        return false
    }

    // /proc/net/tcp local-address hex for 127.0.0.1 (little-endian 32-bit word).
    // Verified empirically against a live device's /proc/net/tcp.
    private const val LOOPBACK_V4_HEX = "0100007F"

    private fun listeningOn(port: Int): Boolean {
        // Parse /proc/net/tcp for local port in hex. A loopback-only bind is
        // NOT externally reachable — do not report it as "open". (Found via
        // live testing: adbd can be left listening on 127.0.0.1 only after
        // certain failure modes, which this probe previously treated as a
        // false-positive "open" state. See
        // docs/operations/sessions/session-2026-07-25-k1-verification.md.)
        val hex = "%04X".format(port)
        val tcp = readText("/proc/net/tcp") ?: return false
        for (line in tcp.lineSequence().drop(1)) {
            val parts = line.trim().split(Regex("\\s+"))
            if (parts.size < 4) continue
            val local =
                parts[1] // ip:port, hex, e.g. 0100007F:15B3 (127.0.0.1) or 00000000:15B3 (any)
            val st = parts[3] // 0A = LISTEN
            if (!local.endsWith(":$hex", ignoreCase = true) || !st.equals("0A", ignoreCase = true))
                continue
            if (local.substringBefore(":").equals(LOOPBACK_V4_HEX, ignoreCase = true)) continue
            return true
        }
        // IPv6 — not loopback-filtered (this fleet's ADB path is IPv4-only via
        // service.adb.tcp.port; a v6-loopback-only listener is not a case
        // observed in practice, so left as before rather than guessing at the
        // byte layout without a live example to verify against).
        val tcp6 = readText("/proc/net/tcp6") ?: return false
        for (line in tcp6.lineSequence().drop(1)) {
            val parts = line.trim().split(Regex("\\s+"))
            if (parts.size < 4) continue
            val local = parts[1]
            val st = parts[3]
            if (local.endsWith(":$hex", ignoreCase = true) && st.equals("0A", ignoreCase = true)) {
                return true
            }
        }
        // Fire OS can hide adbd's socket from /proc even for UID 2000 while
        // `ss -ltn` still reports the live listener. `ss` may emit a netlink
        // permission warning first, so match only LISTEN table addresses.
        // Exclude an explicit loopback address the same way as above; `*`
        // (any-interface) is fine and stays a match.
        val ss = shellOut(arrayOf("ss", "-ltn"), 4).orEmpty()
        val portPattern = Regex("""(?:^|\s)(\*|[0-9A-Fa-f:.]+):$port(?:\s|$)""")
        if (
            ss.lineSequence().any { line ->
                if (!line.contains("LISTEN")) return@any false
                val m = portPattern.find(line) ?: return@any false
                val addr = m.groupValues[1]
                addr != "127.0.0.1" && addr != "localhost"
            }
        ) {
            return true
        }
        return false
    }

    private fun shellOut(cmd: Array<String>, timeoutSec: Long): String? {
        return try {
            val p = ProcessBuilder(*cmd).redirectErrorStream(true).start()
            val ok = p.waitFor(timeoutSec, TimeUnit.SECONDS)
            if (!ok) {
                p.destroyForcibly()
                return null
            }
            p.inputStream.bufferedReader().readText().trim()
        } catch (t: Throwable) {
            Log.w(TAG, "shellOut ${cmd.joinToString(" ")}: ${t.message}")
            null
        }
    }

    private fun commandOk(cmd: Array<String>, timeoutSec: Long): Boolean {
        return try {
            val p = ProcessBuilder(*cmd).redirectErrorStream(true).start()
            val finished = p.waitFor(timeoutSec, TimeUnit.SECONDS)
            if (!finished) {
                p.destroyForcibly()
                false
            } else {
                p.exitValue() == 0
            }
        } catch (t: Throwable) {
            Log.w(TAG, "commandOk ${cmd.joinToString(" ")}: ${t.message}")
            false
        }
    }

    private fun readText(path: String): String? =
        try {
            File(path).takeIf { it.canRead() }?.readText()
        } catch (_: Throwable) {
            null
        }

    private fun appendLog(line: String) {
        try {
            val f = File(LOG_PATH)
            f.parentFile?.mkdirs()
            f.appendText(line + "\n")
        } catch (t: Throwable) {
            Log.w(TAG, "appendLog failed: ${t.message}")
        }
    }
}
