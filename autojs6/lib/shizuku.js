var log = require("./log.js");

var SHIZUKU_PKG = "moe.shizuku.privileged.api";

function launchManager(profile) {
    var pkg = profile.shizukuPackage || SHIZUKU_PKG;
    var cls = profile.shizukuActivity || "moe.shizuku.manager.MainActivity";
    app.startActivity({
        packageName: pkg,
        className: cls,
        flags: ["activity_new_task"],
    });
    sleep(3000);
}

function findStartButton() {
    var selectors = [
        function () { return text("Start").findOne(4000); },
        function () { return desc("Start").findOne(3000); },
        function () { return textContains("Start via").findOne(3000); },
        function () { return textMatches(/start/i).className("android.widget.Button").findOne(3000); },
        function () { return textMatches(/^start$/i).findOne(3000); },
    ];
    for (var i = 0; i < selectors.length; i++) {
        try {
            var node = selectors[i]();
            if (node) return node;
        } catch (e) { /* try next */ }
    }
    return null;
}

/**
 * Catastrophic recovery: launch Shizuku manager and tap the wireless-debug
 * "Start" button via accessibility (replaces Tasker+AutoInput gesture).
 * Requires an unlocked screen — same caveat as the Tasker path.
 */
function tapStartButton(profile) {
    launchManager(profile);
    var btn = findStartButton();
    if (btn) {
        btn.click();
        log.append("[watchdog] shizuku Start tapped (text match)");
        sleep(5000);
        return true;
    }
    if (profile.shizukuStartCoords) {
        click(profile.shizukuStartCoords.x, profile.shizukuStartCoords.y);
        log.append("[watchdog] shizuku Start tapped (coords fallback "
            + profile.shizukuStartCoords.x + "," + profile.shizukuStartCoords.y + ")");
        sleep(5000);
        return true;
    }
    log.append("[watchdog] shizuku Start button not found");
    return false;
}

/**
 * Samsung fallback: open wireless debugging settings and toggle the master switch.
 * Best-effort; only used when profile.samsungWirelessDebugFallback is true.
 */
function enableWirelessDebuggingUi(profile) {
    if (!profile.samsungWirelessDebugFallback) return false;
    try {
        app.startActivity({
            action: "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
            flags: ["activity_new_task"],
        });
        sleep(2000);
        var entry = textContains("Wireless debugging").findOne(5000)
            || textContains("Wireless Debugging").findOne(3000);
        if (entry) {
            entry.click();
            sleep(1500);
        }
        var toggle = className("android.widget.Switch").findOne(3000)
            || descContains("Wireless debugging").findOne(3000);
        if (toggle && !toggle.checked()) {
            toggle.click();
            log.append("[watchdog] wireless debugging toggle tapped (Samsung fallback)");
            sleep(2000);
            return true;
        }
    } catch (e) {
        log.append("[watchdog] wireless debug UI fallback failed: " + e);
    }
    return false;
}

module.exports = {
    tapStartButton: tapStartButton,
    enableWirelessDebuggingUi: enableWirelessDebuggingUi,
};
