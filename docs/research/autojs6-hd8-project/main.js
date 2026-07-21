// @generated
"use strict";
// @ts-nocheck
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
var engineGuard = require("./lib/engine_guard.js");
var profile;
try {
  profile = config.detectDeviceProfile();
} catch (e) {
  profile = {};
}
try {
  config.ensureDirs(profile); // create shared dirs (self-heal)
} catch (e) {
  /* best effort — cycles mkdir on demand too */
}
if (profile.usingGenericDefaults) {
  log.append("[watchdog] WARNING: device.json missing — device=generic; run Ansible fleet deploy for tap coords");
}
// Keep script process alive under Doze (AutoJs6 6.6+)
try {
  if (typeof timers !== "undefined" && timers.keepAlive) {
    timers.keepAlive();
  }
} catch (e) {
  log.append("[watchdog] timers.keepAlive unavailable: " + e);
}
// Run one guarded cycle.
function safeCycle(trigger) {
  try {
    guard.enforce(profile);
    watchdog.runCycle(trigger, profile);
  } catch (e) {
    log.append("[watchdog] " + trigger + " cycle error: " + e);
  }
}
log.append("[watchdog] stayturgid AutoJs6 started device=" + (profile.id || "?"));
var stopped = engineGuard.dedupeMainEngines();
if (stopped > 0) {
  log.append("[watchdog] stopped " + stopped + " duplicate main.js engine(s)");
}
safeCycle("boot"); // covers manual launch + boot auto-start
// Every 20 minutes — the loop is ALWAYS established, even if the boot cycle
// above hit trouble, so the watchdog self-recovers on the next tick.
setInterval(function () {
  safeCycle("interval");
}, config.INTERVAL_MS);
setTimeout(function () {
  try {
    toast("stayturgid main.js still running after 1 minute");
    log.append("[watchdog] delayed startup toast emitted");
  } catch (e) {
    log.append("[watchdog] delayed toast unavailable: " + e);
  }
}, 60000);
// Keep the script process alive (AutoJs6 stops when the main thread exits)
setInterval(function () {}, 60000);
