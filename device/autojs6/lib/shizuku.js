var log = require("./log.js");
var sh = require("./shizuku_shell.js");

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

function serverRunning() {
    var r = sh.exec("pgrep -f shizuku_server");
    return r && r.code === 0 && String(r.result || "").trim().length > 0;
}

/**
 * Best-effort wireless-debug / adbd enable via Shizuku shell (no manager UI).
 * Returns true when localhost:5555 answers after the attempt.
 *
 * Steps (in order):
 *   1. Enable developer options (belt-and-suspenders).
 *   2. Enable USB ADB (some ROMs require this before wifi ADB).
 *   3. Enable wireless debugging — triggers AdbService ContentObserver.
 *   4. Force adbd to listen on TCP 5555 (legacy mode).
 *   5. Connect local ADB client to the local adbd.
 *   6. Verify shell uid 2000 on localhost:5555.
 */
function tryShellWirelessRepair() {
    if (!sh.isOperational()) {
        return false;
    }
    log.append("[watchdog] shizuku shell: trying wireless-debug repair");
    sh.exec("settings put global development_settings_enabled 1");
    sh.exec("settings put global adb_enabled 1");
    sh.exec("settings put global adb_wifi_enabled 1");
    sleep(2000);
    sh.exec("setprop service.adb.tcp.port 5555");
    sleep(1000);
    sh.exec("adb connect 127.0.0.1:5555");
    sleep(1000);
    var uid = sh.exec("adb -s localhost:5555 shell id -u");
    if (uid && uid.code === 0 && String(uid.result || "").trim() === "2000") {
        log.append("[watchdog] shizuku shell: localhost:5555 shell uid 2000");
        return true;
    }
    return false;
}

/**
 * Catastrophic recovery: launch Shizuku manager and tap the wireless-debug
 * "Start" button via accessibility. Requires an unlocked screen.
 *
 * WHY this function still exists (no non-UI alternative):
 *   - Shizuku (official) has no hidden intent/API to restart its daemon or
 *     toggle wireless debugging. The only headless path is
 *     /sdcard/Android/data/moe.shizuku.privileged.api/start.sh, which itself
 *     requires a working ADB/root shell — the exact resource we are trying
 *     to re-establish (chicken-and-egg problem).
 *   - settings put global adb_wifi_enabled 1 does not stick on Fire OS,
 *     leaving UI tap as the only recovery path on those devices.
 *   - Community forks (timschneeb/ShizukuExt-SystemUID, thedjchi/Shizuku)
 *     add start/stop intents, but switching forks is a separate fleet decision.
 *   - This function is only reached after two failed shell repair attempts,
 *     so it is a deliberate last resort, not the primary path.
 */
function tapStartButton(profile) {
    if (!device.isScreenOn()) {
        log.append("[watchdog] shizuku Start skipped — screen off (unlock for UI tap)");
        return false;
    }
    launchManager(profile);
    var btn = findStartButton();
    if (btn) {
        btn.click();
        log.append("[watchdog] shizuku Start tapped (text match)");
        sleep(5000);
        return true;
    }
    // Blind-coordinate fallback only when the manager is actually foreground —
    // otherwise we'd tap random coordinates in whatever app is open.
    var fg = String(currentPackage() || "");
    if (fg !== (profile.shizukuPackage || SHIZUKU_PKG)) {
        log.append("[watchdog] shizuku Start skipped — manager not foreground (fg=" + fg + ")");
        return false;
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
        if (!entry) {
            log.append("[watchdog] wireless debug entry not found — skipping toggle");
            return false;
        }
        entry.click();
        sleep(1500);
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

/**
 * Catastrophic path: Shizuku shell first (no GUI), then accessibility UI tap.
 */
function repairCatastrophic(profile) {
    if (serverRunning() && tryShellWirelessRepair()) {
        return true;
    }
    if (tryShellWirelessRepair()) {
        return true;
    }
    var ok = tapStartButton(profile);
    if (!ok && profile.samsungWirelessDebugFallback) {
        enableWirelessDebuggingUi(profile);
        ok = tapStartButton(profile);
    }
    return ok;
}

module.exports = {
    tapStartButton: tapStartButton,
    enableWirelessDebuggingUi: enableWirelessDebuggingUi,
    repairCatastrophic: repairCatastrophic,
    tryShellWirelessRepair: tryShellWirelessRepair,
    serverRunning: serverRunning,
};
