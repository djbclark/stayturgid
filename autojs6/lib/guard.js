var config = require("./config.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var log = require("./log.js");

function getEnabledAccessibilityServices() {
    var r = shell("settings get secure enabled_accessibility_services", false);
    if (r.code !== 0) return "";
    return String(r.result || "").trim();
}

function a11yEnabled(serviceId) {
    var list = getEnabledAccessibilityServices();
    if (!list || list === "null") return false;
    return list.indexOf(serviceId) >= 0;
}

function autoJs6AccessibilityEnabled() {
    return a11yEnabled(config.AUTOJS6_A11Y);
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
    getEnabledAccessibilityServices: getEnabledAccessibilityServices,
};
