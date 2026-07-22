package org.stayturgid.agent

import android.app.Application
import android.util.Log

class AgentApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "AgentApplication onCreate ${BuildConfig.VERSION_NAME}")
    }

    companion object {
        private const val TAG = "StayTurgidApp"
    }
}
