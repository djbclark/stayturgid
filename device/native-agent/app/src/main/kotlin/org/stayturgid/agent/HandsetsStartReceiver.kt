package org.stayturgid.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Headless trigger for a one-off handsets-start (issue #121) — lets ops/testing kick it **without
 * foregrounding the app UI**, mirroring [PeerStartReceiver]'s pattern for peer-start:
 * ```
 * adb shell am broadcast -a org.stayturgid.agent.action.HANDSETS_START_NOW \
 *   --es target_host <ip> --ei target_adb_port 5555 --ei handsets_port 9012 \
 *   -n <pkg>/org.stayturgid.agent.HandsetsStartReceiver
 * ```
 *
 * `target_adb_port` (the device's ADB port, [AdbClient] connects there) and `handsets_port` (the
 * daemon's own listen port once launched) are distinct — both default sensibly if omitted.
 *
 * Unlike peer-start (which iterates a fleet-wide config of assigned targets), handsets-start has no
 * config to load — it always targets whatever `target_host` the caller supplies, matching the
 * single-target, on-demand semantics of the original `fire_peer_help.py handsets-start --target ...
 * --port ...` CLI verb. It just forwards to [HostService.handsetsStartNow] (the already-running
 * FGS), so it never launches an activity.
 */
class HandsetsStartReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != HostService.ACTION_HANDSETS_START_NOW) return
        val host = intent.getStringExtra(HostService.EXTRA_TARGET_HOST)
        val adbPort =
            intent.getIntExtra(HostService.EXTRA_TARGET_ADB_PORT, PeerTarget.DEFAULT_ADB_PORT)
        val handsetsPort =
            intent.getIntExtra(HostService.EXTRA_HANDSETS_PORT, HandsetsStartCommands.DEFAULT_PORT)
        if (host.isNullOrBlank()) {
            Log.w(TAG, "handsets-start broadcast missing ${HostService.EXTRA_TARGET_HOST}")
            return
        }
        Log.i(
            TAG,
            "handsets-start broadcast received for $host:$adbPort (daemon port $handsetsPort)",
        )
        HostService.handsetsStartNow(context.applicationContext, host, adbPort, handsetsPort)
    }

    companion object {
        private const val TAG = "StayTurgidHandsetsRcv"
    }
}
