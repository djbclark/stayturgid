// @generated
"use strict";
// @ts-nocheck
/**
 * Boot helper: start main.js if not already running.
 * Invoked from Termux:Boot (start-autojs6-watchdog.sh), bridges.py --mode autojs6
 * (trigger file), or AutoJs6 timed/broadcast task.
 *
 * No "auto" directive: this launcher doesn't need accessibility.
 */
var engineGuard = require("../lib/engine_guard.js");
var config = require("../lib/config.js");
var MAIN = engineGuard.MAIN;
var STALE_WATCHDOG_MS = 25 * 60 * 1000;
function latestWatchdogCycleMs() {
  var logPath = config.WATCHDOG_LOG;
  if (!files.exists(logPath)) return null;
  try {
    var lines = String(files.read(logPath)).split("\n");
    for (var i = lines.length - 1; i >= 0; i--) {
      if (lines[i].indexOf("[watchdog] cycle start") >= 0) {
        var m = lines[i].match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
        if (m) {
          return new Date(
            Number(m[1]),
            Number(m[2]) - 1,
            Number(m[3]),
            Number(m[4]),
            Number(m[5]),
            Number(m[6]),
          ).getTime();
        }
      }
    }
  } catch (e) {
    /* best effort */
  }
  return null;
}
function watchdogStale() {
  var last = latestWatchdogCycleMs();
  if (last === null) return true;
  return Date.now() - last > STALE_WATCHDOG_MS;
}
function launchIfNeeded() {
  var existing = engineGuard.findMainEngines();
  if (existing.length === 1 && !watchdogStale()) {
    return;
  }
  if (existing.length === 1 && watchdogStale()) {
    existing[0].forceStop();
  } else if (existing.length > 1) {
    engineGuard.dedupeMainEngines();
  }
  // execScriptFile otherwise inherits this launcher's scripts/ working
  // directory.  main.js loads ./lib/*, so give the child its own directory
  // explicitly instead of letting every relative require resolve one level
  // too low.
  var childConfig = new org.autojs.autojs.execution.ExecutionConfig();
  childConfig.setWorkingDirectory(MAIN.substring(0, MAIN.lastIndexOf("/")));
  engines.execScriptFile(MAIN, childConfig);
}
launchIfNeeded();
