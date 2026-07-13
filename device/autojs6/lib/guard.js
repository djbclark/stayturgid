// @heals: A11Y-AUTOJS6
var config = require("./config.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var log = require("./log.js");

// Authoritative, permission-free check: AutoJs6's own accessibility service
// instance is non-null exactly when the service is enabled AND bound. The old
// approach — `settings get secure enabled_accessibility_services` via the
// app-uid shell — silently fails (reading secure settings needs shell/system
// uid), so it ALWAYS reported "disabled" and thrashed a repair every cycle.
function autoJs6AccessibilityEnabled() {
    try {
        if (typeof auto !== "undefined" && auto.service) return true;
    } catch (e) { /* fall through to the settings probe */ }
    // Fallback (best effort): if a privileged read happens to work, use it.
    // Run in a thread with a timeout to avoid blocking the watchdog cycle
    // if the settings daemon hangs (observed on Fire OS).
    try {
        var shellResult = { code: -1, result: "" };
        var t = threads.start(function () {
            try {
                var r = shell("settings get secure enabled_accessibility_services", false);
                shellResult.code = r.code;
                shellResult.result = String(r.result || "");
            } catch (e) { /* thread-local failure */ }
        });
        t.join(5000);
        if (shellResult.code === 0) {
            var list = shellResult.result.trim();
            return list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0;
        }
    } catch (e2) { /* ignore */ }
    return false;
}

/**
 * Best-effort accessibility check for the watchdog — DEGRADES, never blocks.
 *
 * When accessibility is off: on split-storage, co-monitor probes via Shizuku.
 * On normal hosts, invokes Termux repair to check status. The watchdog cycle
 * always proceeds (sshd/Tailscale/comonitor still run without a11y).
 *
 * No longer automatically re-enables accessibility — the user must enable
 * AutoJs6 in Settings > Accessibility > AutoJs6.
 */
function enforce(profile) {
    profile = profile || config.detectDeviceProfile();
    if (autoJs6AccessibilityEnabled()) {
        notify.clear("a11y-blocked");
        return;
    }

    if (config.splitStorage(profile)) {
        log.append("[watchdog] split-storage: a11y off — co-monitor will probe via Shizuku");
        try {
            var comonitor = require("./comonitor.js");
            comonitor.run(profile, { force: true, reason: "a11y-off-split" });
        } catch (e) {
            log.append("[watchdog] comonitor a11y attempt failed: " + e);
        }
        if (autoJs6AccessibilityEnabled()) {
            notify.clear("a11y-blocked");
            return;
        }
    } else {
        log.append("[watchdog] accessibility disabled — checking repair status");
        // Check if Termux repair already detected and logged this.
        termux.invokeRepair(profile);
        var deadline = Date.now() + 20000;
        while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
            sleep(2000);
        }
        if (autoJs6AccessibilityEnabled()) {
            log.append("[watchdog] accessibility restored by user");
            notify.clear("a11y-blocked");
            return;
        }
    }

    // Still off — user must enable manually.
    log.append("[watchdog] accessibility still off — user must re-enable in Settings");
    notify.show(
        "AutoJs6 accessibility disabled",
        "Open Settings > Accessibility > AutoJs6 to re-enable. "
            + "sshd/Tailscale self-heal still runs without a11y.",
        "a11y-blocked"
    );
}

function statusReport() {
    return {
        autojs6A11y: autoJs6AccessibilityEnabled(),
    };
}

module.exports = {
    enforce: enforce,
    statusReport: statusReport,
    autoJs6AccessibilityEnabled: autoJs6AccessibilityEnabled,
};
