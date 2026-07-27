package org.stayturgid.agent

import android.content.Context
import java.io.File

/**
 * A marker on a **target** device (e.g. hd8) telling its own agent to show a "when the
 * Allow-USB-debugging dialog appears, tick Always allow + Allow" reminder, so the operator standing
 * at the target knows to approve the peer's one-time authorization (issue #61 activation UX).
 *
 * The marker is a file in the agent's external files dir (app-readable, and writable over ADB by a
 * peer / by the provisioning tool). It is set when a peer is assigned to this device and cleared by
 * the peer over the authorized connection once peer-start succeeds
 * ([PeerStarter.clearTargetReminder]).
 */
object AuthorizeReminder {
    const val FILE_NAME = "authorize_reminder"

    /** Both agent ids, so a peer can clear the marker without knowing the target's build. */
    private val AGENT_PACKAGES = listOf("org.stayturgid.agent", "org.stayturgid.agent.debug")

    /** True if this device has been asked to prompt for peer-start approval. */
    fun isPresent(context: Context): Boolean {
        if (File(context.filesDir, FILE_NAME).exists()) return true
        val extDir = context.getExternalFilesDir(null) ?: return false
        return File(extDir, FILE_NAME).exists()
    }

    fun clear(context: Context) {
        runCatching { File(context.filesDir, FILE_NAME).delete() }
        val extDir = context.getExternalFilesDir(null) ?: return
        runCatching { File(extDir, FILE_NAME).delete() }
    }

    /**
     * A shell command a peer runs on the target (over ADB, uid 2000) to remove the marker for
     * whichever agent build is installed. Uses run-as for internal storage (Fire OS compatible)
     * with external storage fallback. Package-independent and idempotent.
     */
    fun clearCommand(): String =
        AGENT_PACKAGES.joinToString("; ") { pkg ->
            "run-as $pkg rm -f files/$FILE_NAME 2>/dev/null; rm -f /sdcard/Android/data/$pkg/files/$FILE_NAME 2>/dev/null"
        }
}
