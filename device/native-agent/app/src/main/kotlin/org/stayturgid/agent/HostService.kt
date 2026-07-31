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
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import rikka.shizuku.Shizuku

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
    private var peerStartJob: Job? = null
    private val serviceRef = AtomicReference<IStayTurgidService?>(null)
    private var bound = false
    private var screenOn = false

    private val userServiceArgs: Shizuku.UserServiceArgs by lazy {
        Shizuku.UserServiceArgs(ComponentName(packageName, ShizukuUserService::class.java.name))
            .daemon(true)
            .processNameSuffix("userservice")
            .debuggable(BuildConfig.DEBUG)
            // Pin version to 1 so Shizuku dedupes the daemon service across app upgrades (#65)
            .version(1)
            .tag("stayturgid-agent")
    }

    private val connection =
        object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
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
            override fun onReceive(context: Context?, intent: Intent?) {
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
        // Durable liveness heartbeat (#86): its own dedicated thread, started
        // before anything Shizuku-related so it never depends on — or can be
        // blocked by — the co-monitor bind/IPC below.
        HeartbeatWriter.start(applicationContext)
        // Co-monitor always (screen-independent); inject only while interactive.
        startHeartbeatLoop()
        // Peer-start (issue #61): screen-independent, app-process (no local
        // Shizuku needed). No-op unless this device has assigned Fire targets.
        startPeerStartLoop()
        if (screenOn) onScreenOn() else ensureBound()
        Log.i(TAG, "HostService created screenOn=$screenOn")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
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
            ACTION_PEER_START_NOW -> {
                startAsForeground(bound = bound)
                scope.launch { runPeerStart() }
            }
            ACTION_HANDSETS_START_NOW -> {
                startAsForeground(bound = bound)
                val host = intent.getStringExtra(EXTRA_TARGET_HOST)
                val adbPort = intent.getIntExtra(EXTRA_TARGET_ADB_PORT, PeerTarget.DEFAULT_ADB_PORT)
                val handsetsPort =
                    intent.getIntExtra(EXTRA_HANDSETS_PORT, HandsetsStartCommands.DEFAULT_PORT)
                if (host.isNullOrBlank()) {
                    Log.w(TAG, "handsets-start broadcast missing $EXTRA_TARGET_HOST")
                } else {
                    scope.launch { runHandsetsStart(host, adbPort, handsetsPort) }
                }
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
        HeartbeatWriter.stop()
        heartbeatJob?.cancel()
        heartbeatJob = null
        peerStartJob?.cancel()
        peerStartJob = null
        getSystemService(NotificationManager::class.java)?.apply {
            cancel(PEER_NAG_NOTIFICATION_ID)
            cancel(TARGET_REMINDER_NOTIFICATION_ID)
        }
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
                // One-time per-device phase stagger (ADR-006) so fleet devices
                // don't all run co-monitor at the same instant. The first check
                // above stays prompt; only the steady-state phase shifts.
                delay(AgentSchedule.staggerMs(applicationContext, COMONTOR_INTERVAL_MS))
                while (isActive) {
                    delay(COMONTOR_INTERVAL_MS)
                    ensureBound()
                    callComonitor()
                }
            }
    }

    /**
     * Peer-start loop (issue #61): periodically ensure Shizuku is up on any assigned Fire target
     * over external ADB. Runs in the app process — no local Shizuku binder required — so it works
     * even on a peer whose own Shizuku is down. A no-op (fast NO_TARGETS) on devices with no
     * peer.json.
     */
    private fun startPeerStartLoop() {
        if (peerStartJob?.isActive == true) return
        peerStartJob =
            scope.launch {
                // Show any target-side reminder immediately (a target device runs
                // this loop too, with no peer.json of its own).
                updateActionNotifications()
                // Let the network / Tailscale settle after boot before the first
                // attempt; the interval loop then keeps a dropped peer covered.
                delay(PEERSTART_INITIAL_DELAY_MS)
                var staggered = false
                while (isActive) {
                    runPeerStart()
                    // While a one-time authorization is outstanding (this device is
                    // a peer awaiting approval, or a target still showing its
                    // reminder), retry fast so the operator can finish it quickly.
                    val urgent =
                        PeerStartState.anyAuthPending(applicationContext) ||
                            AuthorizeReminder.isPresent(applicationContext)
                    if (urgent) {
                        delay(PEERSTART_PENDING_INTERVAL_MS)
                    } else {
                        // One-time per-device phase stagger (ADR-006), applied on
                        // the first settled cycle — never delays urgent retries or
                        // the first post-boot check.
                        if (!staggered) {
                            staggered = true
                            delay(
                                AgentSchedule.staggerMs(applicationContext, PEERSTART_INTERVAL_MS)
                            )
                        }
                        delay(PEERSTART_INTERVAL_MS)
                    }
                }
            }
    }

    private suspend fun runPeerStart() {
        try {
            val results = withContext(Dispatchers.IO) { PeerStarter.startAll(applicationContext) }
            for (r in results) {
                Log.i(TAG, "peerstart ${r.target} -> ${r.outcome} ${r.detail}")
            }
        } catch (t: Throwable) {
            Log.e(TAG, "peerstart loop error", t)
        }
        updateActionNotifications()
    }

    /** One-off handsets-start against an explicit target (issue #121's manual-trigger path). */
    private suspend fun runHandsetsStart(host: String, adbPort: Int, handsetsPort: Int) {
        try {
            val result =
                withContext(Dispatchers.IO) {
                    val key = PeerStarter.loadKey(applicationContext)
                    HandsetsStarter.ensureHandsets(
                        applicationContext,
                        PeerTarget(host, adbPort),
                        key,
                        handsetsPort,
                    )
                }
            Log.i(TAG, "handsetsstart ${result.target} -> ${result.outcome} ${result.detail}")
        } catch (t: Throwable) {
            Log.e(TAG, "handsetsstart error", t)
        }
    }

    /**
     * Post/cancel the "action needed" notifications (issue #61 activation UX): on a **peer**, an
     * authorization-pending nag while any assigned target awaits its one-time "Always allow"; on a
     * **target**, a reminder to approve that dialog. Both re-alert each cycle so they keep
     * surfacing until done, and auto-cancel once resolved.
     */
    private fun updateActionNotifications() {
        val nm = getSystemService(NotificationManager::class.java) ?: return
        val pending = PeerStartState.pendingTargets(applicationContext)
        if (pending.isNotEmpty()) {
            nm.notify(PEER_NAG_NOTIFICATION_ID, buildPeerNagNotification(pending))
        } else {
            nm.cancel(PEER_NAG_NOTIFICATION_ID)
        }
        if (AuthorizeReminder.isPresent(applicationContext)) {
            nm.notify(TARGET_REMINDER_NOTIFICATION_ID, buildTargetReminderNotification())
        } else {
            nm.cancel(TARGET_REMINDER_NOTIFICATION_ID)
        }
    }

    private fun buildPeerNagNotification(targets: List<String>): Notification {
        val retry =
            PendingIntent.getBroadcast(
                this,
                1,
                Intent(this, PeerStartReceiver::class.java).setAction(ACTION_PEER_START_NOW),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        return NotificationCompat.Builder(this, ACTION_CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_peer_auth_title))
            .setContentText(
                getString(R.string.notification_peer_auth_text, targets.joinToString(", "))
            )
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText(
                        getString(R.string.notification_peer_auth_text, targets.joinToString(", "))
                    )
            )
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(retry)
            .setOnlyAlertOnce(false)
            .setAutoCancel(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
    }

    private fun buildTargetReminderNotification(): Notification {
        val open =
            PendingIntent.getActivity(
                this,
                2,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        return NotificationCompat.Builder(this, ACTION_CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_target_reminder_title))
            .setContentText(getString(R.string.notification_target_reminder_text))
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText(getString(R.string.notification_target_reminder_text))
            )
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentIntent(open)
            .setOnlyAlertOnce(false)
            .setAutoCancel(false)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
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
                )
                .apply {
                    description = getString(R.string.notification_channel_desc)
                    setShowBadge(false)
                }
        nm.createNotificationChannel(channel)

        // Higher-importance channel for the one-time peer-start authorization
        // prompts (issue #61) so they surface (heads-up) until acted on.
        val actionChannel =
            NotificationChannel(
                    ACTION_CHANNEL_ID,
                    getString(R.string.notification_action_channel_name),
                    NotificationManager.IMPORTANCE_HIGH,
                )
                .apply {
                    description = getString(R.string.notification_action_channel_desc)
                    setShowBadge(true)
                }
        nm.createNotificationChannel(actionChannel)
    }

    private fun startAsForeground(bound: Boolean, needPermission: Boolean = false) {
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

    private fun updateNotification(bound: Boolean, needPermission: Boolean = false) {
        val nm = getSystemService(NotificationManager::class.java) ?: return
        nm.notify(NOTIFICATION_ID, buildNotification(bound, needPermission))
    }

    private fun buildNotification(bound: Boolean, needPermission: Boolean): Notification {
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
        private const val ACTION_CHANNEL_ID = "stayturgid_agent_action"
        private const val NOTIFICATION_ID = 7101
        private const val PEER_NAG_NOTIFICATION_ID = 7102
        private const val TARGET_REMINDER_NOTIFICATION_ID = 7103
        /** 5 minutes; override later via config if needed. */
        const val PING_INTERVAL_MS: Long = 5 * 60 * 1000L

        /** Co-monitor cadence while screen on (Phase 2). */
        const val COMONTOR_INTERVAL_MS: Long = 20 * 60 * 1000L

        /**
         * Poll interval while retrying the initial post-boot Shizuku bind. Boot-time bind is async
         * and can take longer than a single fixed delay under full-boot system load (observed 2.5s+
         * on real device boots — see
         * docs/operations/sessions/session-2026-07-25-k1-verification.md).
         */
        const val INITIAL_BIND_POLL_MS: Long = 2_000L

        /**
         * Total time to keep retrying the initial bind before falling back to the steady-state
         * [COMONTOR_INTERVAL_MS] loop. Increased to 5 minutes (300_000L) to cover the full
         * exponential backoff window of Shizuku's BootRetryWorker (from PR 262).
         */
        const val INITIAL_BIND_RETRY_MS: Long = 300_000L

        /** Delay before the first peer-start attempt, letting Tailscale settle. */
        const val PEERSTART_INITIAL_DELAY_MS: Long = 30_000L

        /** Peer-start re-check cadence (screen-independent) when all is settled. */
        const val PEERSTART_INTERVAL_MS: Long = 20 * 60 * 1000L

        /** Faster cadence while a one-time authorization is still outstanding. */
        const val PEERSTART_PENDING_INTERVAL_MS: Long = 3 * 60 * 1000L

        const val ACTION_STOP = "org.stayturgid.agent.action.STOP"
        const val ACTION_PING_NOW = "org.stayturgid.agent.action.PING_NOW"
        const val ACTION_REPAIR_NOW = "org.stayturgid.agent.action.REPAIR_NOW"
        const val ACTION_PEER_START_NOW = "org.stayturgid.agent.action.PEER_START_NOW"
        const val ACTION_HANDSETS_START_NOW = "org.stayturgid.agent.action.HANDSETS_START_NOW"
        const val EXTRA_TARGET_HOST = "target_host"

        /**
         * The target device's **ADB** port (what [AdbClient] connects to) — not the daemon's own
         * listen port below. Defaults to [PeerTarget.DEFAULT_ADB_PORT] (5555), matching every other
         * [PeerTarget] in this codebase.
         */
        const val EXTRA_TARGET_ADB_PORT = "target_adb_port"

        /**
         * The port the Handsets daemon itself listens on once launched (`hs.jar`'s own port arg) —
         * distinct from [EXTRA_TARGET_ADB_PORT] above. Defaults to
         * [HandsetsStartCommands.DEFAULT_PORT] (9012).
         */
        const val EXTRA_HANDSETS_PORT = "handsets_port"

        fun start(context: Context) {
            val intent = Intent(context, HostService::class.java)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, HostService::class.java).apply { action = ACTION_STOP }
            context.startService(intent)
        }

        fun pingNow(context: Context) {
            val intent = Intent(context, HostService::class.java).apply { action = ACTION_PING_NOW }
            ContextCompat.startForegroundService(context, intent)
        }

        fun repairNow(context: Context) {
            val intent =
                Intent(context, HostService::class.java).apply { action = ACTION_REPAIR_NOW }
            ContextCompat.startForegroundService(context, intent)
        }

        fun peerStartNow(context: Context) {
            val intent =
                Intent(context, HostService::class.java).apply { action = ACTION_PEER_START_NOW }
            ContextCompat.startForegroundService(context, intent)
        }

        /**
         * Headless trigger for a one-off handsets-start (issue #121) against an explicit
         * [targetHost] — [targetAdbPort] is the device's **ADB** port ([AdbClient] connects there),
         * [handsetsPort] is the port the daemon itself listens on once launched; these are
         * distinct. Unlike peer-start, this has no fleet-wide config to iterate, mirroring the
         * manual, single-target semantics of the original `fire_peer_help.py handsets-start
         * --target ... --port ...` CLI verb.
         */
        fun handsetsStartNow(
            context: Context,
            targetHost: String,
            targetAdbPort: Int = PeerTarget.DEFAULT_ADB_PORT,
            handsetsPort: Int = HandsetsStartCommands.DEFAULT_PORT,
        ) {
            val intent =
                Intent(context, HostService::class.java).apply {
                    action = ACTION_HANDSETS_START_NOW
                    putExtra(EXTRA_TARGET_HOST, targetHost)
                    putExtra(EXTRA_TARGET_ADB_PORT, targetAdbPort)
                    putExtra(EXTRA_HANDSETS_PORT, handsetsPort)
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
