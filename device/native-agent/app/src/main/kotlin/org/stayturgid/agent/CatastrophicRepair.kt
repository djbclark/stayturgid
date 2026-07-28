package org.stayturgid.agent

import android.util.Log
import java.util.concurrent.TimeUnit

/**
 * Phase 3: catastrophic path when port 5555 is closed / shell dead.
 *
 * // @heals: PORT5555-OPEN SHIZUKU-HEADLESS TAILSCALE-VPN TAILSCALE-ALWAYSON
 *
 * Mirrors AutoJs6 `lib/shizuku.ts` **shell-first** sequence (ADR 003):
 * 1. settings: development + adb + adb_wifi
 * 2. setprop service.adb.tcp.port 5555
 * 3. adb connect 127.0.0.1:5555 + verify uid 2000
 * 4. HEADLESS_START broadcast (thedjchi / stayturgid Shizuku fork)
 *
 * No Accessibility UI taps here — that remains AutoJs6-only until a fork intent path is proven on
 * all fleet ROMs.
 */
object CatastrophicRepair {
    private const val TAG = "StayTurgidCat"
    private const val TAILSCALE_COMPONENT = "com.tailscale.ipn/com.tailscale.ipn.MainActivity"
    private const val TAILSCALE_RECEIVER = "com.tailscale.ipn/com.tailscale.ipn.IPNReceiver"
    private const val TAILSCALE_CONNECT_ACTION = "com.tailscale.ipn.CONNECT_VPN"

    data class Result(val ok: Boolean, val detail: String)

    fun repair(): Result {
        val steps = mutableListOf<String>()
        try {
            if (ComonitorProbes.probe().port == "open") {
                return Result(true, "already open")
            }
            // Fire OS adbd drops this step's loopback connect (#60); labeled distinctly
            // from a real failure so agent.log doesn't read as a mystery repeated failure.
            steps +=
                if (DeviceProfile.isPrivilegedShellExpected()) {
                    "shell_wireless"
                } else {
                    "shell_wireless_skip"
                }
            if (tryShellWirelessRepair()) {
                appendLog("[agent] catastrophic shell wireless OK")
                return Result(true, steps.joinToString("+") + ":ok")
            }
            steps += "headless_start"
            if (headlessStart()) {
                appendLog("[agent] catastrophic HEADLESS_START sent; rechecking shell")
                if (tryShellWirelessRepair()) {
                    return Result(true, steps.joinToString("+") + ":ok")
                }
                if (serverRunning()) {
                    return Result(true, steps.joinToString("+") + ":server_up_shell_unknown")
                }
            }
            appendLog("[agent] catastrophic FAILED steps=${steps.joinToString("+")}")
            return Result(false, steps.joinToString("+") + ":failed")
        } catch (t: Throwable) {
            Log.e(TAG, "repair failed", t)
            appendLog("[agent] catastrophic error=${t.message}")
            return Result(false, "error:${t.message}")
        }
    }

    fun serverRunning(): Boolean {
        val bc =
            shellOut(
                arrayOf(
                    "am",
                    "broadcast",
                    "--include-stopped-packages",
                    "-a",
                    "moe.shizuku.privileged.api.HEADLESS_STATUS",
                ),
                6,
            )
        if (bc != null && bc.contains("result=1")) return true
        return ComonitorProbes.probe().shizuku == "up" && pgrepShizuku()
    }

    private fun pgrepShizuku(): Boolean {
        // Same /proc scan style as ComonitorProbes
        val proc = java.io.File("/proc")
        val dirs =
            proc.listFiles { f -> f.isDirectory && f.name.all { it.isDigit() } } ?: return false
        for (d in dirs) {
            val cmdline =
                try {
                    java.io.File(d, "cmdline").readText().replace('\u0000', ' ')
                } catch (_: Throwable) {
                    continue
                }
            if (cmdline.contains("shizuku_server")) return true
        }
        return false
    }

    /**
     * Idempotently keep USB debugging enabled, independent of whether wireless ADB is currently
     * open. Some ROMs (confirmed: Fire OS) won't reopen the wireless TCP listener from a setprop
     * alone without an actual adbd restart, which this shell-privileged process cannot force
     * without root or an already-open transport — see [tryShellWirelessRepair] and
     * docs/operations/sessions/session-2026-07-25-k1-verification.md. Keeping adb_enabled on means
     * a physical USB reconnect always works immediately, with no manual Developer Options digging
     * required.
     */
    fun ensureAdbBaseline(): String {
        return try {
            ensureSetting("global", "development_settings_enabled", "1")
            ensureSetting("global", "adb_enabled", "1")
            "ok"
        } catch (t: Throwable) {
            Log.w(TAG, "ensureAdbBaseline: ${t.message}")
            "error:${t.message}"
        }
    }

    fun tryShellWirelessRepair(): Boolean {
        if (!DeviceProfile.isPrivilegedShellExpected()) {
            // Fire OS adbd drops this exact loopback connect (#60) — same gate Termux
            // already applies via `privilegedShellExpected` in device.json. Skip the
            // doomed attempt rather than eat the connect timeout every cycle.
            Log.i(TAG, "tryShellWirelessRepair skipped — privilegedShellExpected=false")
            return false
        }
        ensureSetting("global", "development_settings_enabled", "1")
        ensureSetting("global", "adb_enabled", "1")
        ensureSetting("global", "adb_wifi_enabled", "1")
        val cur = shellOut(arrayOf("getprop", "service.adb.tcp.port"), 3)?.trim()
        if (cur != "5555") {
            shellOut(arrayOf("setprop", "service.adb.tcp.port", "5555"), 3)
            Thread.sleep(1000)
        }
        Thread.sleep(1500)
        shellOut(arrayOf("adb", "connect", "127.0.0.1:5555"), 8)
        Thread.sleep(1000)
        val uid = shellOut(arrayOf("adb", "-s", "localhost:5555", "shell", "id", "-u"), 8)?.trim()
        val ok = uid == "2000"
        Log.i(TAG, "tryShellWirelessRepair uid=$uid ok=$ok")
        return ok
    }

    fun headlessStart(): Boolean {
        shellOut(
            arrayOf(
                "am",
                "broadcast",
                "--include-stopped-packages",
                "-a",
                "moe.shizuku.privileged.api.HEADLESS_START",
            ),
            8,
        )
        Thread.sleep(5000)
        return serverRunning()
    }

    fun repairTailscale(): Result {
        ensureSetting("secure", "always_on_vpn_app", "com.tailscale.ipn")
        ensureSetting("secure", "always_on_vpn_lockdown", "0")
        val initial = ComonitorProbes.probe()
        val policyOk = initial.tailscalePolicy == "up"
        if (initial.tailscale != "down") {
            val detail =
                if (policyOk) {
                    "tailscale up; always-on policy healthy"
                } else {
                    "tailscale up; always-on policy repair failed"
                }
            appendLog("[agent] $detail")
            return Result(policyOk, detail)
        }

        // Prefer Tailscale's exported, documented receiver. Some Fire OS /
        // WorkManager combinations reject its expedited StartVPNWorker, so
        // never treat successful broadcast delivery as successful repair.
        shellOut(
            arrayOf(
                "am",
                "broadcast",
                "--include-stopped-packages",
                "-a",
                TAILSCALE_CONNECT_ACTION,
                "-n",
                TAILSCALE_RECEIVER,
            ),
            8,
        )
        if (waitForTailscaleUp(attempts = 4)) {
            val detail =
                if (policyOk) {
                    "tailscale restored via CONNECT_VPN"
                } else {
                    "tailscale restored via CONNECT_VPN; always-on policy repair failed"
                }
            appendLog("[agent] $detail")
            return Result(policyOk, detail)
        }

        // Activity launch is a best-effort prompt/fallback. It requires an
        // unlocked screen and operator input. Never foreground the GUI if the
        // VPN tunnel interface is actually up (e.g. transient control-plane ping failure).
        if (ComonitorProbes.isTailscaleTunnelUp()) {
            val detail = "tailscale tunnel up; control-plane probe flaky (GUI launch suppressed)"
            appendLog("[agent] $detail")
            return Result(policyOk, detail)
        }

        shellOut(arrayOf("am", "start", "-n", TAILSCALE_COMPONENT), 8)
        val restored = waitForTailscaleUp(attempts = 3)
        val detail =
            if (restored && policyOk) {
                "tailscale restored after activity fallback"
            } else if (restored) {
                "tailscale restored after activity fallback; always-on policy repair failed"
            } else {
                "tailscale still down after CONNECT_VPN and activity fallback"
            }
        appendLog("[agent] $detail")
        return Result(restored && policyOk, detail)
    }

    private fun waitForTailscaleUp(attempts: Int): Boolean {
        repeat(attempts) {
            Thread.sleep(2000)
            if (ComonitorProbes.probe().tailscale == "up") return true
        }
        return false
    }

    private fun ensureSetting(namespace: String, key: String, want: String) {
        val cur = shellOut(arrayOf("settings", "get", namespace, key), 4)?.trim()
        if (cur != want) {
            shellOut(arrayOf("settings", "put", namespace, key, want), 4)
        }
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

    private fun appendLog(line: String) {
        try {
            val f = java.io.File("/sdcard/stayturgid/logs/agent.log")
            f.parentFile?.mkdirs()
            val ts =
                java.text
                    .SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US)
                    .format(java.util.Date())
            f.appendText("$ts $line\n")
        } catch (t: Throwable) {
            Log.w(TAG, "appendLog: ${t.message}")
        }
    }
}
