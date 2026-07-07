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

try {
    config.ensureDirs();   // create /sdcard/stayturgid/{state,logs,run,tmp} (self-heal)
} catch (e) { /* best effort — cycles mkdir on demand too */ }

// Keep script process alive under Doze (AutoJs6 6.6+)
try {
    if (typeof timers !== "undefined" && timers.keepAlive) {
        timers.keepAlive();
    }
} catch (e) {
    log.append("[watchdog] timers.keepAlive unavailable: " + e);
}

var profile;
try {
    profile = config.detectDeviceProfile();
} catch (e) {
    profile = {};
    log.append("[watchdog] profile detect failed: " + e);
}

// Run one guarded cycle. NOTHING here may throw uncaught: an uncaught error in
// startup used to kill main.js before the interval loop was ever set up (no
// periodic cycles at all + an AutoJs6 error toast) — the cause of a stalled
// watchdog. guard.enforce degrades instead of blocking; this catches the rest.
function safeCycle(trigger) {
    try {
        guard.enforce();
        watchdog.runCycle(trigger, profile);
    } catch (e) {
        log.append("[watchdog] " + trigger + " cycle error: " + e);
    }
}

log.append("[watchdog] stayturgid AutoJs6 started device=" + (profile.id || "?"));
safeCycle("boot");   // covers manual launch + boot auto-start

// Every 20 minutes — the loop is ALWAYS established, even if the boot cycle
// above hit trouble, so the watchdog self-recovers on the next tick.
setInterval(function () { safeCycle("interval"); }, config.INTERVAL_MS);

// Keep the script process alive (AutoJs6 stops when the main thread exits)
setInterval(function () {}, 60000);
