package org.stayturgid.agent

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File

/**
 * Static peer-start assignment: which Fire-OS devices *this* device is
 * responsible for starting Shizuku on, over external ADB (issue #61).
 *
 * The fleet is small, so assignment is static config rather than dynamic
 * discovery. The config is app-readable (never a secret — just `host:port`
 * targets) and is provisioned out of band (ansible / adb). Search order:
 *   1. internal `filesDir/peer.json`          (provisioned via `run-as … cp`)
 *   2. external `getExternalFilesDir/peer.json` (provisioned via `adb push`)
 * First file found wins. Absent/empty ⇒ empty target list ⇒ the peer-start
 * loop is a no-op (hd8 itself carries no config; s24/p7a list hd8).
 *
 * Schema:
 * ```json
 * { "targets": ["100.124.55.39:5555"], "shizuku_pkg": "moe.shizuku.privileged.api" }
 * ```
 */
data class PeerConfig(
    val targets: List<PeerTarget>,
    val shizukuPkg: String,
) {
    companion object {
        private const val TAG = "StayTurgidPeerCfg"
        const val FILE_NAME = "peer.json"
        const val DEFAULT_SHIZUKU_PKG = "moe.shizuku.privileged.api"

        fun candidatePaths(context: Context): List<File> =
            buildList {
                add(File(context.filesDir, FILE_NAME))
                context.getExternalFilesDir(null)?.let { add(File(it, FILE_NAME)) }
            }

        fun load(context: Context): PeerConfig {
            for (file in candidatePaths(context)) {
                if (!file.canRead()) continue
                try {
                    return parse(file.readText())
                } catch (t: Throwable) {
                    Log.w(TAG, "peer config parse failed at ${file.path}: ${t.message}")
                }
            }
            return PeerConfig(emptyList(), DEFAULT_SHIZUKU_PKG)
        }

        fun parse(json: String): PeerConfig {
            val obj = JSONObject(json)
            val arr = obj.optJSONArray("targets")
            val targets =
                buildList {
                    if (arr != null) {
                        for (i in 0 until arr.length()) {
                            PeerTarget.parseOrNull(arr.getString(i))?.let { add(it) }
                        }
                    }
                }
            val pkg = obj.optString("shizuku_pkg", DEFAULT_SHIZUKU_PKG).ifBlank { DEFAULT_SHIZUKU_PKG }
            return PeerConfig(targets, pkg)
        }
    }
}

data class PeerTarget(val host: String, val port: Int) {
    override fun toString(): String = "$host:$port"

    companion object {
        const val DEFAULT_ADB_PORT = 5555

        /** Parse `host:port` or bare `host` (default port 5555). Null if unusable. */
        fun parseOrNull(raw: String): PeerTarget? {
            val s = raw.trim()
            if (s.isEmpty()) return null
            val idx = s.lastIndexOf(':')
            if (idx < 0) return PeerTarget(s, DEFAULT_ADB_PORT)
            if (idx == 0) return null // ":5555" — no host
            val host = s.substring(0, idx)
            val port = s.substring(idx + 1).toIntOrNull() ?: return null // malformed port
            if (host.isBlank() || port !in 1..65535) return null
            return PeerTarget(host, port)
        }
    }
}
