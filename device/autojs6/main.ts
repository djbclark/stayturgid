/**
 * stayturgid AutoJs6 watchdog — entry point.
 *
 * Enable AutoJs6 accessibility, then run this script (or use boot-launcher.js from Termux:Boot).
 * Optional: AutoJs6 timed task every 20 min + run on boot for main.js.
 */
"auto";

import config = require("./lib/config.js");
import guard = require("./lib/guard.js");
import watchdog = require("./lib/watchdog.js");
import log = require("./lib/log.js");
import engineGuard = require("./lib/engine_guard.js");

// detectDeviceProfile() cannot throw (its only internal try/catch is around
// the device.json file read, which it already swallows) — no defensive
// try/catch needed around this call.
const profile = config.detectDeviceProfile();

try {
  config.ensureDirs(profile); // create shared dirs (self-heal)
} catch {
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
function safeCycle(trigger: string): void {
  try {
    guard.enforce(profile);
    watchdog.runCycle(trigger, profile);
  } catch (e) {
    log.append("[watchdog] " + trigger + " cycle error: " + e);
  }
}

log.append("[watchdog] stayturgid AutoJs6 started device=" + (profile.id || "?"));
const stopped = engineGuard.dedupeMainEngines();
if (stopped > 0) {
  log.append("[watchdog] stopped " + stopped + " duplicate main.js engine(s)");
}
safeCycle("boot"); // covers manual launch + boot auto-start

// Every 20 minutes — the loop is ALWAYS established, even if the boot cycle
// above hit trouble, so the watchdog self-recovers on the next tick.
setInterval(() => {
  safeCycle("interval");
}, config.INTERVAL_MS);

// Keep the script process alive (AutoJs6 stops when the main thread exits)
setInterval(() => {}, 60000);
