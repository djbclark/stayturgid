package org.stayturgid.agent

import android.content.Context
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * Makes sure the flashlight is off when an alarm ends (2026-10-17). Termux's torch pulses go
 * through Termux:API, where an on/off pair can race or a call can be lost, so the light could stay
 * on after the alarm. The agent turns the torch off directly, then watches the real torch state for
 * [WATCH_MS] and turns off any flash that still reports on. No permission is needed for this.
 */
object Torch {
    private const val TAG = "StayTurgidTorch"
    private const val WATCH_MS = 3000L

    fun off(context: Context) {
        val cm = context.getSystemService(CameraManager::class.java) ?: return
        val flashes =
            try {
                cm.cameraIdList.filter { hasFlash(cm, it) }
            } catch (e: CameraAccessException) {
                Log.w(TAG, "camera list", e)
                return
            }
        flashes.forEach { setOff(cm, it) }
        // The callback reports every flash's current state on registration, then any change.
        val handler = Handler(Looper.getMainLooper())
        val callback =
            object : CameraManager.TorchCallback() {
                override fun onTorchModeChanged(cameraId: String, enabled: Boolean) {
                    if (enabled) {
                        Log.i(TAG, "torch $cameraId still on after the alarm; turning it off")
                        setOff(cm, cameraId)
                    }
                }
            }
        cm.registerTorchCallback(callback, handler)
        handler.postDelayed({ cm.unregisterTorchCallback(callback) }, WATCH_MS)
    }

    private fun hasFlash(cm: CameraManager, id: String): Boolean =
        cm.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true

    private fun setOff(cm: CameraManager, id: String) {
        try {
            cm.setTorchMode(id, false)
        } catch (e: CameraAccessException) {
            Log.w(TAG, "setTorchMode($id, false)", e)
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "setTorchMode($id, false)", e)
        }
    }
}
