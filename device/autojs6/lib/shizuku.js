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
 * Headless start via djbclark/Shizuku HEADLESS_START broadcast.
 * Uses shizuku shell (privileged) to send the broadcast — no UI needed.
 */
function headlessStart() {
    if (!sh.isOperational()) {
        return false;
    }
    log.append("[watchdog] shizuku headless: sending HEADLESS_START broadcast");
    sh.exec("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START");
    sleep(3000);
    return sh.exec("pgrep -f shizuku_server").code === 0;
}

/**
 * Catastrophic recovery via accessibility tap (last resort — requires unlocked
 * screen). Only reached when shell and HEADLESS_START both fail.
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
    log.append("[watchdog] shizuku Start button not found");
    return false;
}

/**
 * Catastrophic path: shell repair, then HEADLESS_START broadcast,
 * then accessibility UI tap as last resort.
 */
function repairCatastrophic(profile) {
    if (serverRunning() && tryShellWirelessRepair()) {
        return true;
    }
    if (tryShellWirelessRepair()) {
        return true;
    }
    // djbclark/Shizuku fork: HEADLESS_START broadcast starts the server
    // and ensures wireless ADB without any UI interaction.
    if (headlessStart()) {
        log.append("[watchdog] shizuku headless start succeeded");
        if (tryShellWirelessRepair()) {
            return true;
        }
        return serverRunning();
    }
    // Last resort: accessibility UI tap (requires unlocked screen).
    var ok = tapStartButton(profile);
    if (!ok) {
        ok = tapStartButton(profile);  // retry once
    }
    return ok;
}

module.exports = {
    headlessStart: headlessStart,
    tapStartButton: tapStartButton,
    repairCatastrophic: repairCatastrophic,
    tryShellWirelessRepair: tryShellWirelessRepair,
    serverRunning: serverRunning,
};
