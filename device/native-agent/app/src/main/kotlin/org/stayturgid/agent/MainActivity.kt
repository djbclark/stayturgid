package org.stayturgid.agent

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import rikka.shizuku.Shizuku

/**
 * Permission + control UI only. Host work lives in [HostService].
 */
class MainActivity : ComponentActivity() {
    private lateinit var status: TextView

    private val binderListener =
        Shizuku.OnBinderReceivedListener { refreshStatus() }

    private val binderDeadListener =
        Shizuku.OnBinderDeadListener { refreshStatus() }

    private val permissionListener =
        Shizuku.OnRequestPermissionResultListener { _, _ ->
            refreshStatus()
            if (hasShizukuPermission()) {
                HostService.start(this)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        maybeRequestPostNotifications()

        val root =
            LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(48, 48, 48, 48)
            }
        root.addView(
            TextView(this).apply {
                text = getString(R.string.app_name)
                textSize = 24f
            },
        )
        root.addView(
            TextView(this).apply {
                text = buildSummary()
                textSize = 18f
                setTextIsSelectable(true)
                setPadding(0, 8, 0, 28)
            },
        )
        status =
            TextView(this).apply {
                textSize = 15f
                setTextIsSelectable(true)
            }
        root.addView(
            TextView(this).apply {
                text = getString(R.string.main_status_heading)
                textSize = 20f
            },
        )
        root.addView(status)
        root.addView(
            Button(this).apply {
                text = getString(R.string.main_copy_diagnostics)
                setOnClickListener {
                    val diagnostics = buildSummary() + "\n" + status.text
                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    clipboard.setPrimaryClip(ClipData.newPlainText("stayturgid-agent diagnostics", diagnostics))
                    Toast.makeText(this@MainActivity, "Diagnostics copied", Toast.LENGTH_SHORT).show()
                }
            },
        )
        root.addView(
            TextView(this).apply {
                text = getString(R.string.main_hint)
                textSize = 13f
                setPadding(0, 24, 0, 24)
            },
        )
        root.addView(
            Button(this).apply {
                text = getString(R.string.main_request_shizuku)
                setOnClickListener { requestShizuku() }
            },
        )
        root.addView(
            Button(this).apply {
                text = getString(R.string.main_start)
                setOnClickListener {
                    if (!hasShizukuPermission()) {
                        requestShizuku()
                    }
                    HostService.start(this@MainActivity)
                    Toast.makeText(this@MainActivity, "Host starting", Toast.LENGTH_SHORT).show()
                    refreshStatus()
                }
            },
        )
        root.addView(
            Button(this).apply {
                text = getString(R.string.main_stop)
                setOnClickListener {
                    HostService.stop(this@MainActivity)
                    Toast.makeText(this@MainActivity, "Host stop requested", Toast.LENGTH_SHORT).show()
                    refreshStatus()
                }
            },
        )
        root.addView(
            Button(this).apply {
                text = "Ping now"
                setOnClickListener {
                    HostService.pingNow(this@MainActivity)
                    Toast.makeText(this@MainActivity, "Ping requested", Toast.LENGTH_SHORT).show()
                }
            },
        )
        root.addView(
            Button(this).apply {
                text = "Run co-monitor now"
                setOnClickListener {
                    HostService.pingNow(this@MainActivity)
                    Toast.makeText(
                        this@MainActivity,
                        "Ping+comonitor requested (see agent.log)",
                        Toast.LENGTH_SHORT,
                    ).show()
                }
            },
        )
        root.addView(
            Button(this).apply {
                text = "Catastrophic repair now"
                setOnClickListener {
                    HostService.repairNow(this@MainActivity)
                    Toast.makeText(
                        this@MainActivity,
                        "Catastrophic repair requested",
                        Toast.LENGTH_SHORT,
                    ).show()
                }
            },
        )
        setContentView(ScrollView(this).apply { addView(root) })

        Shizuku.addBinderReceivedListenerSticky(binderListener)
        Shizuku.addBinderDeadListener(binderDeadListener)
        Shizuku.addRequestPermissionResultListener(permissionListener)
        refreshStatus()
        // App-context FGS start (shell am start-foreground-service is denied on API 34+).
        HostService.start(this)
    }

    override fun onDestroy() {
        Shizuku.removeBinderReceivedListener(binderListener)
        Shizuku.removeBinderDeadListener(binderDeadListener)
        Shizuku.removeRequestPermissionResultListener(permissionListener)
        super.onDestroy()
    }

    private fun refreshStatus() {
        val lines =
            buildList {
                add("applicationId=${BuildConfig.APPLICATION_ID}")
                add("versionName=${BuildConfig.VERSION_NAME}")
                add("versionCode=${BuildConfig.VERSION_CODE}")
                add("buildType=${BuildConfig.BUILD_TYPE}")
                add("buildTimeUtc=${BuildConfig.BUILD_TIME_UTC}")
                add("revision=${BuildConfig.BUILD_REVISION}")
                add("treeState=${BuildConfig.BUILD_TREE_STATE}")
                add("android=${Build.VERSION.RELEASE} sdk=${Build.VERSION.SDK_INT}")
                add("device=${Build.MANUFACTURER} ${Build.MODEL}")
                add("shizukuBinder=${Shizuku.pingBinder()}")
                if (Shizuku.pingBinder()) {
                    add("shizukuVersion=${runCatching { Shizuku.getVersion() }.getOrElse { -1 }}")
                    add("shizukuUid=${runCatching { Shizuku.getUid() }.getOrElse { -1 }}")
                }
                add("shizukuPermission=${hasShizukuPermission()}")
                add("postNotifications=${hasPostNotifications()}")
                add("intervalMs=${HostService.PING_INTERVAL_MS}")
            }
        status.text = lines.joinToString("\n")
    }

    private fun buildSummary(): String =
        "${BuildConfig.VERSION_NAME}\n" +
            "build ${BuildConfig.VERSION_CODE} • ${BuildConfig.BUILD_TIME_UTC}\n" +
            "revision ${BuildConfig.BUILD_REVISION} (${BuildConfig.BUILD_TREE_STATE})"

    private fun hasShizukuPermission(): Boolean {
        if (!Shizuku.pingBinder()) return false
        return try {
            Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
        } catch (t: Throwable) {
            Log.w(TAG, "checkSelfPermission", t)
            false
        }
    }

    private fun requestShizuku() {
        if (!Shizuku.pingBinder()) {
            Toast.makeText(this, "Start Shizuku first", Toast.LENGTH_LONG).show()
            return
        }
        if (Shizuku.isPreV11()) {
            Toast.makeText(this, "Shizuku pre-v11 not supported", Toast.LENGTH_LONG).show()
            return
        }
        if (hasShizukuPermission()) {
            Toast.makeText(this, "Already granted", Toast.LENGTH_SHORT).show()
            return
        }
        if (Shizuku.shouldShowRequestPermissionRationale()) {
            Toast.makeText(this, "Grant stayturgid-agent in Shizuku app", Toast.LENGTH_LONG).show()
        }
        try {
            Shizuku.requestPermission(REQUEST_SHIZUKU)
        } catch (t: Throwable) {
            Log.e(TAG, "requestPermission", t)
            Toast.makeText(this, "requestPermission failed: ${t.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun hasPostNotifications(): Boolean {
        if (Build.VERSION.SDK_INT < 33) return true
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun maybeRequestPostNotifications() {
        if (Build.VERSION.SDK_INT < 33) return
        if (hasPostNotifications()) return
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQUEST_NOTIF,
        )
    }

    companion object {
        private const val TAG = "StayTurgidMain"
        private const val REQUEST_SHIZUKU = 9001
        private const val REQUEST_NOTIF = 9002
    }
}
