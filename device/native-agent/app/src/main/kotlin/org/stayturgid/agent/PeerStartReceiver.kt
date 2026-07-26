package org.stayturgid.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Headless trigger for a peer-start (issue #61) — lets ops/testing kick a
 * peer-start **without foregrounding the app UI**:
 *
 * ```
 * adb shell am broadcast -a org.stayturgid.agent.action.PEER_START_NOW \
 *   -n <pkg>/org.stayturgid.agent.PeerStartReceiver
 * ```
 *
 * The steady-state trigger is the in-process loop in [HostService]; this is only
 * a manual kick. It just forwards to [HostService.peerStartNow] (the already-
 * running FGS), so it never launches an activity. The action is idempotent and
 * benign (at worst it attempts to start Shizuku on already-assigned targets),
 * so an exported receiver is acceptable for this fleet.
 */
class PeerStartReceiver : BroadcastReceiver() {
    override fun onReceive(
        context: Context,
        intent: Intent?,
    ) {
        if (intent?.action != HostService.ACTION_PEER_START_NOW) return
        Log.i(TAG, "peer-start broadcast received")
        HostService.peerStartNow(context.applicationContext)
    }

    companion object {
        private const val TAG = "StayTurgidPeerRcv"
    }
}
