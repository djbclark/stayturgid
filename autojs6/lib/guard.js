var config = require("./config.js");
var notify = require("./notify.js");

function readMode() {
    if (!files.exists(config.MODE_FILE)) return "tasker";
    try {
        return String(files.read(config.MODE_FILE)).trim().toLowerCase();
    } catch (e) {
        return "tasker";
    }
}

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

function conflictingTaskerStackEnabled() {
    return a11yEnabled(config.TASKER_A11Y) || a11yEnabled(config.AUTOINPUT_A11Y);
}

function autoJs6AccessibilityEnabled() {
    return a11yEnabled(config.AUTOJS6_A11Y);
}

/**
 * Enforce mutual exclusivity: refuse to run unless mode=autojs6 and the
 * Tasker+AutoInput accessibility stack is not active.
 */
function enforce() {
    var mode = readMode();
    if (mode !== "autojs6") {
        notify.show(
            "stayturgid AutoJs6 blocked",
            "Automation mode is '" + mode + "'. Write 'autojs6' to "
                + config.MODE_FILE + " (or run mac/set-automation-mode.sh autojs6)."
        );
        exit();
    }
    if (conflictingTaskerStackEnabled()) {
        notify.show(
            "stayturgid AutoJs6 blocked",
            "Disable Tasker + AutoInput accessibility services before using AutoJs6 mode."
        );
        exit();
    }
    if (!autoJs6AccessibilityEnabled()) {
        notify.show(
            "stayturgid AutoJs6 blocked",
            "Enable AutoJs6 accessibility service, then restart this script."
        );
        auto.waitFor();
    }
}

/**
 * Helper used by mode-switch scripts: list what must be toggled.
 */
function statusReport() {
    return {
        mode: readMode(),
        taskerA11y: a11yEnabled(config.TASKER_A11Y),
        autoinputA11y: a11yEnabled(config.AUTOINPUT_A11Y),
        autojs6A11y: autoJs6AccessibilityEnabled(),
    };
}

module.exports = {
    readMode: readMode,
    enforce: enforce,
    statusReport: statusReport,
    conflictingTaskerStackEnabled: conflictingTaskerStackEnabled,
    getEnabledAccessibilityServices: getEnabledAccessibilityServices,
};
