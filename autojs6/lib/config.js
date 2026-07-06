/** Shared constants and device profile resolution. */

var DEVICE_FILE = "/sdcard/stayturgid_device.txt";
var WATCHDOG_LOG = "/sdcard/stayturgid_watchdog.log";
var REPAIR_SCRIPT = "/data/data/com.termux/files/home/stayturgid-repair.sh";
var TERMUX_HOME = "/data/data/com.termux/files/home";

var INTERVAL_MS = 20 * 60 * 1000;
var STALE_REPAIR_MS = 15 * 60 * 1000;
var NOTIFY_CHANNEL = "stayturgid";

var AUTOJS6_A11Y = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher";

function readOverrideDeviceId() {
    if (!files.exists(DEVICE_FILE)) return null;
    try {
        return String(files.read(DEVICE_FILE)).trim();
    } catch (e) {
        return null;
    }
}

function detectDeviceProfile() {
    var override = readOverrideDeviceId();
    if (override === "p7a") return require("../devices/p7a.js");
    if (override === "s24") return require("../devices/s24.js");

    var model = String(device.model || "").toLowerCase();
    var product = String(device.product || "").toLowerCase();
    if (model.indexOf("pixel") >= 0 && (model.indexOf("7a") >= 0 || product.indexOf("lynx") >= 0)) {
        return require("../devices/p7a.js");
    }
    if (model.indexOf("sm-s921") >= 0 || model.indexOf("s24") >= 0) {
        return require("../devices/s24.js");
    }
    // Unknown hardware: p7a profile is a guess (wrong tailscaleIp/coords).
    console.warn("[stayturgid] unrecognized device model=" + model
        + " product=" + product + " — defaulting to p7a profile");
    return require("../devices/p7a.js");
}

module.exports = {
    DEVICE_FILE: DEVICE_FILE,
    WATCHDOG_LOG: WATCHDOG_LOG,
    REPAIR_SCRIPT: REPAIR_SCRIPT,
    TERMUX_HOME: TERMUX_HOME,
    INTERVAL_MS: INTERVAL_MS,
    STALE_REPAIR_MS: STALE_REPAIR_MS,
    NOTIFY_CHANNEL: NOTIFY_CHANNEL,
    AUTOJS6_A11Y: AUTOJS6_A11Y,
    detectDeviceProfile: detectDeviceProfile,
};
