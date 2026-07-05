/**
 * Locked-screen catastrophic path — mirrors 7a Tasker behavior:
 * notification can fire from watchdog, but accessibility cannot tap Shizuku Start.
 *
 * Turns screen off, runs catastrophic UI repair, restores screen, logs outcome.
 * Requires: mode=autojs6, accessibility enabled, unlocked device before start.
 */
"auto";

var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var log = require("../lib/log.js");
var repair = require("../lib/repair.js");

guard.enforce();
auto.waitFor();

var profile = config.detectDeviceProfile();

log.append("[watchdog] locked-screen catastrophic test start (autojs6)");

// Lock without waking first (wakeUp before POWER would re-toggle off).
log.append("[watchdog] locked-screen test screenOnBefore=" + device.isScreenOn());
shell("input keyevent 26", true);
sleep(2000);

var screenOn = device.isScreenOn();
log.append("[watchdog] locked-screen test screenOnAfterLock=" + screenOn);

var ok = repair.repairCatastrophic(profile);
log.append("[watchdog] locked-screen catastrophic finished ok=" + ok + " screenOn=" + device.isScreenOn());

// Restore screen for operator
shell("input keyevent 26", true);
sleep(500);
device.wakeUp();

toast("locked-screen catastrophic test ok=" + ok + " — check log + notifications");
