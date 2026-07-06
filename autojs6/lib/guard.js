var config = require("./config.js");
var notify = require("./notify.js");

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

/** Require AutoJs6 accessibility before running the watchdog. */
function enforce() {
    if (!autoJs6AccessibilityEnabled()) {
        notify.show(
            "stayturgid AutoJs6 blocked",
            "Enable AutoJs6 accessibility service, then restart main.js."
        );
        auto.waitFor();
    }
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
