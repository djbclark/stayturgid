// @generated
"use strict";
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
/**
 * stayturgid AutoJs6 watchdog — entry point.
 *
 * Enable AutoJs6 accessibility, then run this script (or use boot-launcher.js from Termux:Boot).
 * Optional: AutoJs6 timed task every 20 min + run on boot for main.js.
 */
"auto";
// Plain `require()` calls, not `import x = require(...)`: this file has no
// `import`/`export` syntax anywhere, so tsc emits it as a script rather than
// a CommonJS module — no `Object.defineProperty(exports, "__esModule", ...)`
// stamp. That stamp is only safe for files actually loaded via require();
// main.js is the raw entry script AutoJs6 executes directly (never
// require()'d), and it has no `exports`/`module` object in that context.
const mainConfig = require("./lib/config.js");
const guard = require("./lib/guard.js");
const watchdog = require("./lib/watchdog.js");
const mainLog = require("./lib/log.js");
const engineGuard = require("./lib/engine_guard.js");
// detectDeviceProfile() cannot throw (its only internal try/catch is around
// the device.json file read, which it already swallows) — no defensive
// try/catch needed around this call.
const profile = mainConfig.detectDeviceProfile();
try {
  mainConfig.ensureDirs(profile); // create shared dirs (self-heal)
} catch (_a) {
  /* best effort — cycles mkdir on demand too */
}
if (profile.usingGenericDefaults) {
  mainLog.append("[watchdog] WARNING: device.json missing — device=generic; run Ansible fleet deploy for tap coords");
}
// Keep script process alive under Doze (AutoJs6 6.6+)
try {
  if (typeof timers !== "undefined" && timers.keepAlive) {
    timers.keepAlive();
  }
} catch (e) {
  mainLog.append("[watchdog] timers.keepAlive unavailable: " + e);
}
// Run one guarded cycle.
function safeCycle(trigger) {
  try {
    guard.enforce(profile);
    watchdog.runCycle(trigger, profile);
  } catch (e) {
    mainLog.append("[watchdog] " + trigger + " cycle error: " + e);
  }
}
mainLog.append("[watchdog] stayturgid AutoJs6 started device=" + (profile.id || "?"));
const stopped = engineGuard.dedupeMainEngines();
if (stopped > 0) {
  mainLog.append("[watchdog] stopped " + stopped + " duplicate main.js engine(s)");
}
safeCycle("boot"); // covers manual launch + boot auto-start
// Every 20 minutes — the loop is ALWAYS established, even if the boot cycle
// above hit trouble, so the watchdog self-recovers on the next tick.
setInterval(() => {
  safeCycle("interval");
}, mainConfig.INTERVAL_MS);
// Keep the script process alive (AutoJs6 stops when the main thread exits)
setInterval(() => {}, 60000);
