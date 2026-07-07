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
    try {
        var r = shell("settings get secure enabled_accessibility_services", false);
        if (r && r.code === 0) {
            var list = String(r.result || "").trim();
            return list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0;
        }
    } catch (e2) { /* ignore */ }
    return false;
}

/**
 * Require AutoJs6 accessibility before running the watchdog.
 *
 * Self-healing: the Termux repair script re-enables the service through the
 * privileged 5555 shell (append-only). We trigger a repair and wait; the
 * (coalescing, counted) notification fires only when the fix FAILS.
 */
function enforce() {
    if (autoJs6AccessibilityEnabled()) {
        notify.clear("a11y-blocked");
        return;
    }

    log.append("[watchdog] accessibility disabled — invoking repair to re-enable");
    termux.invokeRepair();
    var deadline = Date.now() + 20000;
    while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
        sleep(2000);
    }

    if (autoJs6AccessibilityEnabled()) {
        log.append("[watchdog] accessibility restored by repair");
        notify.clear("a11y-blocked");
        auto.waitFor();   // returns immediately once the service binds
        return;
    }

    notify.show(
        "stayturgid AutoJs6 blocked",
        "Accessibility auto-repair failed — enable the AutoJs6 accessibility "
            + "service by hand, then restart main.js.",
        "a11y-blocked"
    );
    auto.waitFor();
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
