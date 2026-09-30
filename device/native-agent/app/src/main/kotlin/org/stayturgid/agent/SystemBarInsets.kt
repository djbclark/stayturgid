package org.stayturgid.agent

import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * targetSdk 35+ draws every activity edge-to-edge, behind the status and navigation bars. With
 * 3-button navigation the bar is opaque and tall, so the last button on the main screen sat under
 * it and couldn't be tapped (#307, Galaxy S25). Gesture navigation hid the problem because its bar
 * is a thin handle.
 */
object SystemBarInsets {
    /** Blank space after the last control, beyond the inset, so it never ends flush with a bar. */
    private const val BOTTOM_SPACER_DP = 96

    private val BAR_TYPES =
        WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()

    /**
     * Pads [scroll] by the system-bar and display-cutout insets. clipToPadding=false keeps content
     * scrolling behind the bars while letting it scroll clear of them at either end.
     */
    fun applyTo(scroll: ScrollView) {
        scroll.clipToPadding = false
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { view, insets ->
            val bars = insets.getInsets(BAR_TYPES)
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
    }

    /** Appends an empty spacer to [root] (the operator asked for blank room at the bottom). */
    fun addBottomSpacer(root: LinearLayout) {
        val height = (BOTTOM_SPACER_DP * root.resources.displayMetrics.density).toInt()
        root.addView(
            View(root.context),
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, height),
        )
    }
}
