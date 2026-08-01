package org.stayturgid.agent

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.app.ActivityCompat
import rikka.shizuku.Shizuku

/**
 * Guided one-time setup: shows only the outstanding [SetupStep]s (see [SetupSignals] /
 * [outstandingSetupSteps]) as cards with an explanation and a button that does as much of the work
 * as possible for the operator, instead of leaving them to hunt through Settings/other apps
 * manually.
 *
 * Rebuilds the whole screen from [render] rather than keeping view fields around — this is a
 * rarely-refreshed screen, so the simplicity is worth more than preserving scroll position across a
 * refresh.
 */
class SetupActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        render()
    }

    override fun onResume() {
        super.onResume()
        // Re-check on every resume (matches MainActivity's refreshActionState() pattern) so a
        // step completed in another app (Shizuku, Settings) disappears the moment the operator
        // comes back — no manual refresh needed.
        render()
    }

    private fun render() {
        val steps = outstandingSetupSteps(SetupSignals.capture(this))
        setContentView(ScrollView(this).apply { addView(buildRoot(steps)) })
    }

    private fun buildRoot(steps: List<SetupStep>): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(ROOT_PADDING, ROOT_PADDING, ROOT_PADDING, ROOT_PADDING)
            addView(
                TextView(this@SetupActivity).apply {
                    text = getString(R.string.setup_title)
                    textSize = TITLE_TEXT_SIZE
                    typeface = Typeface.DEFAULT_BOLD
                }
            )
            addView(
                TextView(this@SetupActivity).apply {
                    text = getString(R.string.setup_intro)
                    textSize = INTRO_TEXT_SIZE
                    setPadding(0, INTRO_TOP_PADDING, 0, INTRO_BOTTOM_PADDING)
                }
            )
            if (steps.isEmpty()) {
                addView(buildAllSetCard())
            } else {
                steps.forEachIndexed { index, step ->
                    if (index > 0) addView(buildDivider())
                    addView(buildStepCard(step))
                }
            }
            addView(buildDivider())
            addView(
                Button(this@SetupActivity).apply {
                    text = getString(R.string.setup_return_to_main)
                    setOnClickListener {
                        // finish() only, not startActivity(MainActivity): MainActivity is
                        // singleTop, but that only reuses it when it's already frontmost, not
                        // merely present in the back stack below us. Explicitly relaunching it
                        // would create a fresh instance via onCreate(), which re-runs
                        // maybeAutoLaunchGuidedSetup() and bounces straight back here whenever a
                        // step is still outstanding — the common case, since that's the whole
                        // reason this screen is showing. Finishing reveals the existing paused
                        // MainActivity via onResume() instead, which doesn't re-trigger the
                        // auto-launch. If there's no MainActivity underneath (e.g. this screen was
                        // opened fresh from the notification), finishing just returns to whatever
                        // was there before, which is fine.
                        finish()
                    }
                }
            )
        }

    private fun buildStepCard(step: SetupStep): View =
        when (step) {
            SetupStep.START_SHIZUKU ->
                stepCard(
                    getString(R.string.setup_step_shizuku_title),
                    getString(R.string.setup_step_shizuku_body),
                    getString(R.string.setup_step_shizuku_action),
                    ::openShizukuApp,
                )
            SetupStep.GRANT_SHIZUKU_PERMISSION ->
                stepCard(
                    getString(R.string.setup_step_permission_title),
                    getString(R.string.setup_step_permission_body),
                    getString(R.string.setup_step_permission_action),
                    ::requestShizukuPermission,
                )
            SetupStep.ENABLE_NOTIFICATIONS -> notificationsStepCard()
            SetupStep.ENABLE_WIRELESS_DEBUGGING ->
                stepCard(
                    getString(R.string.setup_step_wireless_title),
                    getString(R.string.setup_step_wireless_body),
                    getString(R.string.setup_step_wireless_action),
                    ::openDeveloperOptions,
                )
        }

    private fun notificationsStepCard(): View {
        val useSettingsFallback = notificationsPermanentlyDenied()
        val actionTextRes =
            if (useSettingsFallback) {
                R.string.setup_step_notifications_action_settings
            } else {
                R.string.setup_step_notifications_action_request
            }
        val actionText = getString(actionTextRes)
        return stepCard(
            getString(R.string.setup_step_notifications_title),
            getString(R.string.setup_step_notifications_body),
            actionText,
        ) {
            if (useSettingsFallback) openNotificationSettings() else requestPostNotifications()
        }
    }

    private fun stepCard(
        title: String,
        body: String,
        actionText: String,
        onClick: () -> Unit,
    ): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
            addView(
                TextView(this@SetupActivity).apply {
                    text = "$PENDING_GLYPH $title"
                    textSize = STEP_TITLE_TEXT_SIZE
                    typeface = Typeface.DEFAULT_BOLD
                }
            )
            addView(
                TextView(this@SetupActivity).apply {
                    text = body
                    textSize = STEP_BODY_TEXT_SIZE
                    setPadding(0, BODY_TOP_PADDING, 0, BODY_BOTTOM_PADDING)
                }
            )
            addView(
                Button(this@SetupActivity).apply {
                    text = actionText
                    setOnClickListener { onClick() }
                }
            )
        }

    private fun buildAllSetCard(): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
            addView(
                TextView(this@SetupActivity).apply {
                    text = getString(R.string.setup_all_set_title)
                    textSize = STEP_TITLE_TEXT_SIZE
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(ALL_SET_TEXT_COLOR)
                }
            )
            addView(
                TextView(this@SetupActivity).apply {
                    text = getString(R.string.setup_all_set_body)
                    textSize = STEP_BODY_TEXT_SIZE
                    setPadding(0, BODY_TOP_PADDING, 0, 0)
                }
            )
        }

    private fun buildDivider(): View =
        View(this).apply {
            layoutParams =
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, DIVIDER_HEIGHT_PX)
            setBackgroundColor(DIVIDER_COLOR)
        }

    private fun openShizukuApp() {
        val launchIntent = packageManager.getLaunchIntentForPackage(PeerConfig.DEFAULT_SHIZUKU_PKG)
        if (launchIntent == null) {
            Toast.makeText(this, getString(R.string.setup_shizuku_not_installed), Toast.LENGTH_LONG)
                .show()
            return
        }
        startActivity(launchIntent)
    }

    @Suppress("TooGenericExceptionCaught") // Shizuku.requestPermission's binder call can throw
    // arbitrary RemoteException/IllegalStateException subtypes depending on daemon state —
    // MainActivity.requestShizuku() catches the same way for the same reason.
    private fun requestShizukuPermission() {
        if (Shizuku.isPreV11()) {
            Toast.makeText(this, getString(R.string.setup_shizuku_prev11), Toast.LENGTH_LONG).show()
            return
        }
        if (Shizuku.shouldShowRequestPermissionRationale()) {
            Toast.makeText(this, getString(R.string.setup_shizuku_rationale), Toast.LENGTH_LONG)
                .show()
        }
        try {
            Shizuku.requestPermission(REQUEST_SHIZUKU)
        } catch (t: Throwable) {
            Log.e(TAG, "requestPermission", t)
            Toast.makeText(this, "requestPermission failed: ${t.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun requestPostNotifications() {
        setupPrefs().edit().putBoolean(PREF_NOTIF_REQUESTED, true).apply()
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQUEST_NOTIF,
        )
    }

    private fun notificationsPermanentlyDenied(): Boolean {
        val alreadyAsked = setupPrefs().getBoolean(PREF_NOTIF_REQUESTED, false)
        val canShowRationale =
            ActivityCompat.shouldShowRequestPermissionRationale(
                this,
                Manifest.permission.POST_NOTIFICATIONS,
            )
        return alreadyAsked && !canShowRationale
    }

    private fun openNotificationSettings() {
        val intent =
            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
            }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            val message = getString(R.string.setup_notification_settings_unavailable)
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
    }

    private fun openDeveloperOptions() {
        try {
            startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS))
        } catch (_: ActivityNotFoundException) {
            val message = getString(R.string.setup_dev_options_unavailable)
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
    }

    private fun setupPrefs() = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)

    companion object {
        private const val TAG = "StayTurgidSetup"
        private const val REQUEST_SHIZUKU = 9101
        private const val REQUEST_NOTIF = 9102
        private const val PREFS_NAME = "setup_state"
        private const val PREF_NOTIF_REQUESTED = "post_notifications_requested"

        /**
         * MainActivity's own pre-existing POST_NOTIFICATIONS request (fired on every launch, before
         * the operator ever reaches this screen) must record the same flag this screen checks —
         * otherwise [notificationsPermanentlyDenied] never sees `alreadyAsked = true` even after
         * Android has already permanently suppressed the rationale, and the "Enable notifications"
         * button silently no-ops instead of falling back to Settings (caught in PR #177 review).
         */
        fun markPostNotificationsRequested(context: Context) {
            context
                .getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putBoolean(PREF_NOTIF_REQUESTED, true)
                .apply()
        }

        private const val PENDING_GLYPH = "○"

        private const val ROOT_PADDING = 48
        private const val CARD_PADDING = 32
        private const val TITLE_TEXT_SIZE = 24f
        private const val INTRO_TEXT_SIZE = 15f
        private const val INTRO_TOP_PADDING = 8
        private const val INTRO_BOTTOM_PADDING = 24
        private const val STEP_TITLE_TEXT_SIZE = 18f
        private const val STEP_BODY_TEXT_SIZE = 14f
        private const val BODY_TOP_PADDING = 8
        private const val BODY_BOTTOM_PADDING = 16
        private const val DIVIDER_HEIGHT_PX = 2
        private const val DIVIDER_COLOR = 0x33808080
        private val ALL_SET_TEXT_COLOR = Color.parseColor("#2E7D32")
    }
}
