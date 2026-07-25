package org.stayturgid.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.ServiceConnection
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.RemoteException
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import rikka.shizuku.Shizuku
import java.util.concurrent.atomic.AtomicReference

/**
 * Lightweight FGS host: screen on/off → bind UserService → ping every [PING_INTERVAL_MS].
 *
 * Keeps the binder open while the screen is on so we do not rebind every tick.
 * UserServiceArgs.daemon(true) + explicit unbind on screen-off (plan refinement).
 */
class HostService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var pingJob: Job? = null
    private var heartbeatJob: Job? = null
    private val serviceRef = AtomicReference<IStayTurgidService?>(null)
    private var bound = false
    private var screenOn = false

    private val userServiceArgs: Shizuku.UserServiceArgs by lazy {
        Shizuku.UserServiceArgs(
            ComponentName(packageName, ShizukuUserService::class.java.name),
        )
            .daemon(true)
            .processNameSuffix("userservice")
            .debuggable(BuildConfig.DEBUG)
            .version(BuildConfig.VERSION_CODE)
            .tag("stayturgid-agent")
    }

    private val connection =
        object : ServiceConnection {
            override fun onServiceConnected(
                name: ComponentName?,
                binder: IBinder?,
            ) {
                if (binder != null && binder.pingBinder()) {
                    serviceRef.set(IStayTurgidService.Stub.asInterface(binder))
                    bound = true
                    Log.i(TAG, "UserService connected")
                    updateNotification(bound = true)
                    if (screenOn) startPingLoop()
                } else {
                    Log.w(TAG, "invalid binder from $name")
                    serviceRef.set(null)
                    bound = false
                }
            }

            override fun onServiceDisconnected(name: ComponentName?) {
                Log.w(TAG, "UserService disconnected")
                serviceRef.set(null)
                bound = false
                stopPingLoop()
                updateNotification(bound = false)
            }
        }

    private val screenReceiver =
        object : BroadcastReceiver() {
            override fun onReceive(
                context: Context?,
                intent: Intent?,
            ) {
                when (intent?.action) {
                    Intent.ACTION_SCREEN_ON -> onScreenOn()
                    Intent.ACTION_SCREEN_OFF -> onScreenOff()
                }
            }
        }

    private val binderReceivedListener =
        Shizuku.OnBinderReceivedListener {
            Log.i(TAG, "Shizuku binder received")
            if (screenOn) ensureBound()
        }

    private val binderDeadListener =
        Shizuku.OnBinderDeadListener {
            Log.w(TAG, "Shizuku binder dead")
            serviceRef.set(null)
            bound = false
            stopPingLoop()
            updateNotification(bound = false)
        }

    private val permissionResultListener =
        Shizuku.OnRequestPermissionResultListener { requestCode, grantResult ->
            Log.i(TAG, "permission result code=$requestCode grant=$grantResult")
            if (grantResult == android.content.pm.PackageManager.PERMISSION_GRANTED && screenOn) {
                ensureBound()
            } else {
                updateNotification(bound = false, needPermission = true)
            }
        }

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startAsForeground(bound = false)
        val filter =
            IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
            }
        ContextCompat.registerReceiver(
            this,
            screenReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        Shizuku.addBinderReceivedListenerSticky(binderReceivedListener)
        Shizuku.addBinderDeadListener(binderDeadListener)
        Shizuku.addRequestPermissionResultListener(permissionResultListener)

        val pm = getSystemService(PowerManager::class.java)
        screenOn = pm?.isInteractive == true
        // Co-monitor always (screen-independent); inject only while interactive.
        startHeartbeatLoop()
        if (screenOn) onScreenOn() else ensureBound()
        Log.i(TAG, "HostService created screenOn=$screenOn")
    }

    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int,
    ): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_PING_NOW -> {
                scope.launch {
                    callPingAwake()
                    callComonitor()
                }
            }
            ACTION_REPAIR_NOW -> {
                scope.launch { callRepairCatastrophic() }
            }
            else -> {
                // ensure FGS + bind path
                startAsForeground(bound = bound)
                if (screenOn) ensureBound()
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopPingLoop()
        heartbeatJob?.cancel()
        heartbeatJob = null
        unbindUserService(remove = true)
        try {
            unregisterReceiver(screenReceiver)
        } catch (_: IllegalArgumentException) {
            // already unregistered
        }
        Shizuku.removeBinderReceivedListener(binderReceivedListener)
        Shizuku.removeBinderDeadListener(binderDeadListener)
        Shizuku.removeRequestPermissionResultListener(permissionResultListener)
        scope.cancel()
        Log.i(TAG, "HostService destroyed")
        super.onDestroy()
    }

    private fun onScreenOn() {
        screenOn = true
        Log.i(TAG, "SCREEN_ON")
        ensureBound()
        if (bound) startPingLoop()
    }

    private fun onScreenOff() {
        screenOn = false
        Log.i(TAG, "SCREEN_OFF")
        // Stop inject timer only. Keep UserService bound for co-monitor heartbeats
        // so agent_age stays fresh overnight (fleet dual-run).
        stopPingLoop()
    }

    private fun ensureBound() {
        if (!Shizuku.pingBinder()) {
            Log.w(TAG, "Shizuku not running")
            updateNotification(bound = false, needPermission = true)
            return
        }
        if (Shizuku.checkSelfPermission() != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "Shizuku permission not granted")
            updateNotification(bound = false, needPermission = true)
            // Permission UI must run from an Activity; MainActivity requests it.
            return
        }
        if (bound && serviceRef.get() != null) return
        try {
            if (Shizuku.getVersion() < 10) {
                Log.e(TAG, "Shizuku API ${Shizuku.getVersion()} < 10")
                return
            }
            Shizuku.bindUserService(userServiceArgs, connection)
            Log.i(TAG, "bindUserService requested")
        } catch (t: Throwable) {
            Log.e(TAG, "bindUserService failed", t)
        }
    }

    private fun unbindUserService(remove: Boolean) {
        try {
            if (Shizuku.pingBinder() && Shizuku.getVersion() >= 10) {
                Shizuku.unbindUserService(userServiceArgs, connection, remove)
            }
        } catch (t: Throwable) {
            Log.e(TAG, "unbindUserService failed", t)
        }
        serviceRef.set(null)
        bound = false
        updateNotification(bound = false)
    }

    private fun startPingLoop() {
        if (pingJob?.isActive == true) return
        pingJob =
            scope.launch {
                // Inject only while interactive (Phase 1 keep-awake proof / G-A).
                callPingAwake()
                while (isActive && screenOn) {
                    delay(PING_INTERVAL_MS)
                    if (!screenOn) break
                    callPingAwake()
                }
            }
    }

    private fun stopPingLoop() {
        pingJob?.cancel()
        pingJob = null
    }

    /** Screen-independent co-monitor + catastrophic shell path. */
    private fun startHeartbeatLoop() {
        if (heartbeatJob?.isActive == true) return
        heartbeatJob =
            scope.launch {
                // Retry the initial bind for up to INITIAL_BIND_RETRY_MS instead of
                // a single fixed-delay attempt — a lost race here previously meant
                // no CLOSED_NO_SHELL detection for a full COMONTOR_INTERVAL_MS after
                // every real reboot.
                var waited = 0L
                while (isActive && serviceRef.get() == null && waited < INITIAL_BIND_RETRY_MS) {
                    ensureBound()
                    if (serviceRef.get() != null) break
                    delay(INITIAL_BIND_POLL_MS)
                    waited += INITIAL_BIND_POLL_MS
                }
                callComonitor()
                while (isActive) {
                    delay(COMONTOR_INTERVAL_MS)
                    ensureBound()
                    callComonitor()
                }
            }
    }

    private fun callPingAwake() {
        if (!screenOn) return
        val svc = serviceRef.get()
        if (svc == null) {
            Log.w(TAG, "ping skipped — not bound")
            ensureBound()
            return
        }
        try {
            svc.pingAwake()
            Log.i(TAG, "pingAwake IPC ok")
        } catch (e: RemoteException) {
            Log.e(TAG, "pingAwake IPC failed", e)
            serviceRef.set(null)
            bound = false
            ensureBound()
        }
    }

    private fun callComonitor() {
        var svc = serviceRef.get()
        if (svc == null) {
            ensureBound()
            // Binder connect is async; skip this tick if not ready yet.
            svc = serviceRef.get()
            if (svc == null) {
                Log.w(TAG, "comonitor skipped — not bound")
                return
            }
        }
        try {
            val line = svc.runComonitor()
            Log.i(TAG, "comonitor: $line")
            // Keep USB debugging enabled unconditionally, independent of
            // port state — physical USB recovery should never require
            // manual Developer Options changes. Cheap/idempotent.
            try {
                svc.ensureAdbBaseline()
            } catch (e: RemoteException) {
                Log.e(TAG, "ensureAdbBaseline IPC failed", e)
            }
            // Phase 3: if agent STATUS says CLOSED_NO_SHELL, try shell-first repair
            // (no a11y). AutoJs6 still owns UI fallback until cutover.
            if (line.contains("port=CLOSED_NO_SHELL") || line.contains("port=closed")) {
                Log.w(TAG, "CLOSED_NO_SHELL — invoking repairCatastrophic")
                try {
                    val r = svc.repairCatastrophic()
                    Log.i(TAG, "repairCatastrophic: $r")
                } catch (e: RemoteException) {
                    Log.e(TAG, "repairCatastrophic IPC failed", e)
                }
            }
            if (line.contains("tailscale=down") || line.contains("tailscale_policy=down")) {
                Log.w(TAG, "Tailscale runtime or always-on policy down — repairing")
                try {
                    val r = svc.repairTailscale()
                    Log.i(TAG, "repairTailscale: $r")
                } catch (e: RemoteException) {
                    Log.e(TAG, "repairTailscale IPC failed", e)
                }
            }
        } catch (e: RemoteException) {
            Log.e(TAG, "runComonitor IPC failed", e)
            serviceRef.set(null)
            bound = false
        }
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java) ?: return
        val channel =
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.notification_channel_desc)
                setShowBadge(false)
            }
        nm.createNotificationChannel(channel)
    }

    private fun startAsForeground(
        bound: Boolean,
        needPermission: Boolean = false,
    ) {
        val notification = buildNotification(bound, needPermission)
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification(
        bound: Boolean,
        needPermission: Boolean = false,
    ) {
        val nm = getSystemService(NotificationManager::class.java) ?: return
        nm.notify(NOTIFICATION_ID, buildNotification(bound, needPermission))
    }

    private fun buildNotification(
        bound: Boolean,
        needPermission: Boolean,
    ): Notification {
        val open =
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        val text =
            when {
                needPermission -> getString(R.string.notification_text_no_shizuku)
                bound ->
                    getString(
                        R.string.notification_text_bound,
                        (PING_INTERVAL_MS / 60_000L).toInt().coerceAtLeast(1),
                    )
                else -> getString(R.string.notification_text_idle)
            }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    companion object {
        private const val TAG = "StayTurgidHost"
        private const val CHANNEL_ID = "stayturgid_agent_host"
        private const val NOTIFICATION_ID = 7101
        /** 5 minutes; override later via config if needed. */
        const val PING_INTERVAL_MS: Long = 5 * 60 * 1000L

        /** Co-monitor cadence while screen on (Phase 2). */
        const val COMONTOR_INTERVAL_MS: Long = 20 * 60 * 1000L

        /**
         * Poll interval while retrying the initial post-boot Shizuku bind.
         * Boot-time bind is async and can take longer than a single fixed
         * delay under full-boot system load (observed 2.5s+ on real device
         * boots — see docs/operations/sessions/session-2026-07-25-k1-verification.md).
         */
        const val INITIAL_BIND_POLL_MS: Long = 2_000L

        /**
         * Total time to keep retrying the initial bind before falling back
         * to the steady-state [COMONTOR_INTERVAL_MS] loop. Without this, a
         * lost race on the fixed 2s delay used to mean losing an entire
         * comonitor cycle (20 minutes) with zero CLOSED_NO_SHELL detection.
         */
        const val INITIAL_BIND_RETRY_MS: Long = 20_000L

        const val ACTION_STOP = "org.stayturgid.agent.action.STOP"
        const val ACTION_PING_NOW = "org.stayturgid.agent.action.PING_NOW"
        const val ACTION_REPAIR_NOW = "org.stayturgid.agent.action.REPAIR_NOW"

        fun start(context: Context) {
            val intent = Intent(context, HostService::class.java)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            val intent =
                Intent(context, HostService::class.java).apply {
                    action = ACTION_STOP
                }
            context.startService(intent)
        }

        fun pingNow(context: Context) {
            val intent =
                Intent(context, HostService::class.java).apply {
                    action = ACTION_PING_NOW
                }
            ContextCompat.startForegroundService(context, intent)
        }

        fun repairNow(context: Context) {
            val intent =
                Intent(context, HostService::class.java).apply {
                    action = ACTION_REPAIR_NOW
                }
            ContextCompat.startForegroundService(context, intent)
        }
    }

    private fun callRepairCatastrophic() {
        val svc = serviceRef.get()
        if (svc == null) {
            Log.w(TAG, "repair skipped — not bound")
            ensureBound()
            return
        }
        try {
            val r = svc.repairCatastrophic()
            Log.i(TAG, "repairCatastrophic: $r")
        } catch (e: RemoteException) {
            Log.e(TAG, "repairCatastrophic IPC failed", e)
        }
    }
}
