package org.stayturgid.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationAttributes
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log

/**
 * Battery locate sound (2026-10-08). Termux's `stayturgid_battery_alarm.py` decides when the sound
 * plays and renews a lease every clip while it should:
 * ```
 * am broadcast -a org.stayturgid.agent.action.LOCATE_SOUND --ei secs 15 \
 *   -n org.stayturgid.agent/.LocateSoundReceiver
 * ```
 *
 * `secs` > 0 plays (or keeps playing) until that many seconds after the last renewal, so a dead
 * Termux can't leave it on; `secs` 0 stops at once. The agent plays it rather than
 * termux-media-player because only an app can pin the output to the built-in speaker (never a
 * connected Bluetooth device) and vibrate alongside. Exported like [PeerStartReceiver]: the worst a
 * stranger can do is ring the phone for [MAX_LEASE_SEC].
 */
class LocateSoundReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != ACTION_LOCATE_SOUND) return
        val secs = intent.getIntExtra(EXTRA_SECS, 0).coerceIn(0, MAX_LEASE_SEC)
        if (secs > 0) LocateSound.play(context.applicationContext, secs) else LocateSound.stop()
    }

    companion object {
        const val ACTION_LOCATE_SOUND = "org.stayturgid.agent.action.LOCATE_SOUND"
        const val EXTRA_SECS = "secs"
        const val MAX_LEASE_SEC = 120
    }
}

/** The player: alarm usage at full alarm volume, on the built-in speaker, vibrating throughout. */
object LocateSound {
    private const val TAG = "StayTurgidLocate"
    private const val MS_PER_SEC = 1000L
    private val VIBRATE_PATTERN = longArrayOf(0, 700, 300)
    private val ALARM =
        AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()

    // Touched only on the main thread (onReceive and the handler), so no locking.
    private val handler = Handler(Looper.getMainLooper())
    private val stopRunnable = Runnable { stop() }
    private var player: MediaPlayer? = null
    private var vibrator: Vibrator? = null
    private var restore: (() -> Unit)? = null

    fun play(context: Context, secs: Int) {
        handler.removeCallbacks(stopRunnable)
        handler.postDelayed(stopRunnable, secs * MS_PER_SEC)
        if (player != null) return
        val audio = context.getSystemService(AudioManager::class.java)
        val before = audio.getStreamVolume(AudioManager.STREAM_ALARM)
        audio.setStreamVolume(
            AudioManager.STREAM_ALARM,
            audio.getStreamMaxVolume(AudioManager.STREAM_ALARM),
            0,
        )
        restore = { audio.setStreamVolume(AudioManager.STREAM_ALARM, before, 0) }
        val mp = MediaPlayer.create(context, R.raw.locate, ALARM, audio.generateAudioSessionId())
        if (mp == null) {
            Log.w(TAG, "could not load the locate sound")
            stop()
            return
        }
        // Explicit routing wins over the alarm strategy, which would also play on Bluetooth.
        val speaker =
            audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).firstOrNull {
                it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
            }
        if (speaker != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            mp.setPreferredDevice(speaker)
        }
        mp.isLooping = true
        mp.start()
        player = mp
        vibrator = vibrator(context).also { vibrate(it) }
        Log.i(TAG, "playing for ${secs}s (speaker=${speaker != null})")
    }

    fun stop() {
        handler.removeCallbacks(stopRunnable)
        player?.run {
            stop()
            release()
        }
        player = null
        vibrator?.cancel()
        vibrator = null
        restore?.invoke()
        restore = null
    }

    private fun vibrator(context: Context): Vibrator =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java).defaultVibrator
        } else {
            context.getSystemService(Vibrator::class.java)
        }

    @Suppress("DEPRECATION") // vibrate(effect, AudioAttributes) before API 33
    private fun vibrate(v: Vibrator) {
        val effect = VibrationEffect.createWaveform(VIBRATE_PATTERN, 0)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            v.vibrate(effect, VibrationAttributes.createForUsage(VibrationAttributes.USAGE_ALARM))
        } else {
            v.vibrate(effect, ALARM)
        }
    }
}
