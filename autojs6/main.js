/**
 * stayturgid AutoJs6 watchdog — entry point.
 *
 * Mutually exclusive with Tasker+AutoInput. Set automation mode first:
 *   echo autojs6 > /sdcard/stayturgid_automation_mode.txt
 * Then disable Tasker + AutoInput accessibility and enable AutoJs6's.
 *
 * Configure AutoJs6: Settings → keep running after volume-up / stable mode;
 * optionally add a Timed task (every 20 min) + boot trigger pointing here.
 */
"auto";

var config = require("./lib/config.js");
var guard = require("./lib/guard.js");
var watchdog = require("./lib/watchdog.js");
var log = require("./lib/log.js");

guard.enforce();
auto.waitFor();

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

// Every 20 minutes — same cadence as ADB_Interval_Check
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
