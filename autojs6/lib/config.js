/** Shared constants and device profile resolution.
 *
 * The device profile is DATA, not code: Ansible renders
 * /sdcard/stayturgid/state/device.json from the inventory taxonomy
 * (ansible/inventory/hosts.yml + group_vars layers). Nothing in this repo's
 * code names a specific device; without the JSON a generic profile applies
 * (no tap-coordinate fallback, no self-ping — degraded but functional).
 */

// Single stayturgid root per filesystem. SD_ROOT is created by the ensureDirs()
// call below so a user-deleted directory self-heals before we read/write.
var SD_ROOT = "/sdcard/stayturgid";
var TERMUX_HOME = "/data/data/com.termux/files/home";
var DEVICE_JSON = SD_ROOT + "/state/device.json";
var WATCHDOG_LOG = SD_ROOT + "/logs/watchdog.log";
var REPAIR_SCRIPT = TERMUX_HOME + "/.stayturgid/bin/stayturgid-repair.sh";

/** mkdir -p the shared-storage subdirs the watchdog writes (self-healing). */
function ensureDirs() {
    ["state", "logs", "run", "tmp"].forEach(function (d) {
        try { files.ensureDir(SD_ROOT + "/" + d + "/"); } catch (e) { /* best effort */ }
    });
}

var INTERVAL_MS = 20 * 60 * 1000;
var STALE_REPAIR_MS = 15 * 60 * 1000;
var NOTIFY_CHANNEL = "stayturgid";

var AUTOJS6_A11Y = "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher";

var PROFILE_DEFAULTS = {
    id: "generic",
    label: "unknown device",
    notifyTag: "",
    shizukuPackage: "moe.shizuku.privileged.api",
    shizukuActivity: "moe.shizuku.manager.MainActivity",
    shizukuStartCoords: null,
    tailscaleIp: null,
    tailscalePackage: "com.tailscale.ipn",
    tailscaleActivity: "com.tailscale.ipn.MainActivity",
    wirelessDebugUiFallback: false,
};

function detectDeviceProfile() {
    var profile = {};
    try {
        if (files.exists(DEVICE_JSON)) {
            profile = JSON.parse(String(files.read(DEVICE_JSON))) || {};
        }
    } catch (e) {
        console.warn("[stayturgid] unreadable " + DEVICE_JSON + ": " + e);
        profile = {};
    }
    if (!profile.id) {
        console.warn("[stayturgid] no device profile at " + DEVICE_JSON
            + " — run the Ansible fleet deploy; using generic defaults");
    }
    var merged = {};
    for (var k in PROFILE_DEFAULTS) {
        merged[k] = (profile[k] !== undefined && profile[k] !== null)
            ? profile[k] : PROFILE_DEFAULTS[k];
    }
    // legacy field name kept for shizuku.js compatibility
    merged.samsungWirelessDebugFallback = merged.wirelessDebugUiFallback;
    return merged;
}

module.exports = {
    SD_ROOT: SD_ROOT,
    DEVICE_JSON: DEVICE_JSON,
    WATCHDOG_LOG: WATCHDOG_LOG,
    REPAIR_SCRIPT: REPAIR_SCRIPT,
    TERMUX_HOME: TERMUX_HOME,
    INTERVAL_MS: INTERVAL_MS,
    STALE_REPAIR_MS: STALE_REPAIR_MS,
    NOTIFY_CHANNEL: NOTIFY_CHANNEL,
    AUTOJS6_A11Y: AUTOJS6_A11Y,
    PROFILE_DEFAULTS: PROFILE_DEFAULTS,
    ensureDirs: ensureDirs,
    detectDeviceProfile: detectDeviceProfile,
};
