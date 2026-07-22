package org.stayturgid.agent

import android.util.Log
import java.util.concurrent.TimeUnit

/**
 * Phase 3: catastrophic path when port 5555 is closed / shell dead.
 *
 * // @heals: PORT5555-OPEN SHIZUKU-HEADLESS
 *
 * Mirrors AutoJs6 `lib/shizuku.ts` **shell-first** sequence (ADR 003):
 * 1. settings: development + adb + adb_wifi
 * 2. setprop service.adb.tcp.port 5555
 * 3. adb connect 127.0.0.1:5555 + verify uid 2000
 * 4. HEADLESS_START broadcast (thedjchi / stayturgid Shizuku fork)
 *
 * No Accessibility UI taps here — that remains AutoJs6-only until a fork
 * intent path is proven on all fleet ROMs.
 */
object CatastrophicRepair {
    private const val TAG = "StayTurgidCat"

    data class Result(
        val ok: Boolean,
        val detail: String,
    )

    fun repair(): Result {
        val steps = mutableListOf<String>()
        try {
            if (ComonitorProbes.probe().port == "open") {
                return Result(true, "already open")
            }
            steps += "shell_wireless"
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
        val bc = shellOut(arrayOf("am", "broadcast", "-a", "moe.shizuku.privileged.api.HEADLESS_STATUS"), 6)
        if (bc != null && bc.contains("result=1")) return true
        return ComonitorProbes.probe().shizuku == "up" && pgrepShizuku()
    }

    private fun pgrepShizuku(): Boolean {
        // Same /proc scan style as ComonitorProbes
        val proc = java.io.File("/proc")
        val dirs = proc.listFiles { f -> f.isDirectory && f.name.all { it.isDigit() } } ?: return false
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

    fun tryShellWirelessRepair(): Boolean {
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
        val uid =
            shellOut(
                arrayOf("adb", "-s", "localhost:5555", "shell", "id", "-u"),
                8,
            )?.trim()
        val ok = uid == "2000"
        Log.i(TAG, "tryShellWirelessRepair uid=$uid ok=$ok")
        return ok
    }

    fun headlessStart(): Boolean {
        shellOut(arrayOf("am", "broadcast", "-a", "moe.shizuku.privileged.api.HEADLESS_START"), 8)
        Thread.sleep(5000)
        return serverRunning()
    }

    private fun ensureSetting(
        namespace: String,
        key: String,
        want: String,
    ) {
        val cur = shellOut(arrayOf("settings", "get", namespace, key), 4)?.trim()
        if (cur != want) {
            shellOut(arrayOf("settings", "put", namespace, key, want), 4)
        }
    }

    private fun shellOut(
        cmd: Array<String>,
        timeoutSec: Long,
    ): String? {
        return try {
            val p =
                ProcessBuilder(*cmd)
                    .redirectErrorStream(true)
                    .start()
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
                java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US)
                    .format(java.util.Date())
            f.appendText("$ts $line\n")
        } catch (t: Throwable) {
            Log.w(TAG, "appendLog: ${t.message}")
        }
    }
}
