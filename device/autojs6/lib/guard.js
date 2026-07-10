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
 * Best-effort accessibility for the watchdog — DEGRADES, never blocks.
 *
 * Self-healing: the Termux repair script re-enables the service through the
 * privileged 5555 shell (append-only). We trigger a repair and wait briefly.
 *
 * Critically this returns whether or not a11y comes back — it must NEVER call
 * auto.waitFor() (which blocks forever if the service won't attach). Blocking
 * here froze the entire watchdog on a device where auto.service stayed null,
 * killing even the non-a11y work (sshd/Tailscale/repair via RUN_COMMAND). The
 * caller runs the cycle regardless; a11y-dependent steps no-op when it's off.
 */
function enforce(profile) {
    profile = profile || config.detectDeviceProfile();
    if (autoJs6AccessibilityEnabled()) {
        notify.clear("a11y-blocked");
        return;
    }

    if (config.splitStorage(profile)) {
        log.append("[watchdog] split-storage: a11y off — co-monitor will try Shizuku merge");
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
        notify.show(
            "stayturgid AutoJs6 degraded",
            "Accessibility is off — sshd/Tailscale self-heal still runs, but on-screen "
                + "repairs are paused. Enable the AutoJs6 accessibility service to restore.",
            "a11y-blocked"
        );
        return;
    }

    log.append("[watchdog] accessibility disabled — invoking repair to re-enable");
    termux.invokeRepair(profile);
    var deadline = Date.now() + 20000;
    while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
        sleep(2000);
    }

    if (autoJs6AccessibilityEnabled()) {
        log.append("[watchdog] accessibility restored by repair");
        notify.clear("a11y-blocked");
        return;
    }

    // Still off — proceed with a degraded cycle rather than freezing.
    log.append("[watchdog] accessibility still off — running degraded (no UI repair)");
    notify.show(
        "stayturgid AutoJs6 degraded",
        "Accessibility is off — sshd/Tailscale self-heal still runs, but on-screen "
            + "repairs are paused. Enable the AutoJs6 accessibility service to restore.",
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
