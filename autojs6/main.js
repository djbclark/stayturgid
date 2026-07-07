/**
 * stayturgid AutoJs6 watchdog — entry point.
 *
 * Enable AutoJs6 accessibility, then run this script (or use boot-launcher.js from Termux:Boot).
 * Optional: AutoJs6 timed task every 20 min + run on boot for main.js.
 */
"auto";

var config = require("./lib/config.js");
var guard = require("./lib/guard.js");
var watchdog = require("./lib/watchdog.js");
var log = require("./lib/log.js");

config.ensureDirs();   // create /sdcard/stayturgid/{state,logs,run,tmp} (self-heal)
guard.enforce();       // waits for accessibility itself when disabled

// Keep script process alive under Doze (AutoJs6 6.6+)
try {
    if (typeof timers !== "undefined" && timers.keepAlive) {
        timers.keepAlive();
    }
} catch (e) {
    log.append("[watchdog] timers.keepAlive unavailable: " + e);
}

var profile = config.detectDeviceProfile();
log.append("[watchdog] stayturgid AutoJs6 started device=" + profile.id);

// First run (covers manual launch and boot if AutoJs6 auto-starts this project)
watchdog.runCycle("boot", profile);

// Every 20 minutes
setInterval(function () {
    try {
        guard.enforce();
        watchdog.runCycle("interval", profile);
    } catch (e) {
        log.append("[watchdog] interval error: " + e);
    }
}, config.INTERVAL_MS);

// Keep the script process alive (AutoJs6 stops when the main thread exits)
setInterval(function () {}, 60000);
