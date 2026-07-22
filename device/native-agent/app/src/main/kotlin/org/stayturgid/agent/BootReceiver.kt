package org.stayturgid.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Starts [HostService] after boot / package replace.
 * Shizuku may not be up yet; HostService rebinds when the binder appears.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(
        context: Context,
        intent: Intent?,
    ) {
        val action = intent?.action ?: return
        if (
            action == Intent.ACTION_BOOT_COMPLETED ||
            action == Intent.ACTION_MY_PACKAGE_REPLACED
        ) {
            Log.i(TAG, "starting host for $action")
            HostService.start(context.applicationContext)
        }
    }

    companion object {
        private const val TAG = "StayTurgidBoot"
    }
}
