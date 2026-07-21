// @generated
"use strict";
// @ts-nocheck
/**
 * Validate stale repair-loop detection without a 15-minute wait.
 * Injects a synthetic [repair] log line 20 minutes in the past, then runs one
 * watchdog cycle — expect "Repair loop stale" notification.
 *
 * Requires: mode=autojs6, accessibility enabled.
 */
"auto";
var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var log = require("../lib/log.js");
var watchdog = require("../lib/watchdog.js");
guard.enforce();
auto.waitFor();
function pad(n) {
  return (n < 10 ? "0" : "") + n;
}
var stale = new Date(Date.now() - 20 * 60 * 1000);
var stamp =
  stale.getFullYear() +
  "-" +
  pad(stale.getMonth() + 1) +
  "-" +
  pad(stale.getDate()) +
  " " +
  pad(stale.getHours()) +
  ":" +
  pad(stale.getMinutes()) +
  ":" +
  pad(stale.getSeconds());
var synthetic = stamp + " [repair] STATUS port=open shizuku=up sshd=up shell=yes (synthetic-stale-test)";
var prior = log.readWatchdogLog();
var kept = prior.split("\n").filter(function (line) {
  return line.length > 0 && line.indexOf("[repair]") < 0;
});
kept.push(synthetic);
files.write(config.WATCHDOG_LOG, kept.join("\n") + "\n");
log.append("[watchdog] stale-loop test injected line at " + stamp + " isStaleBefore=" + log.isRepairLoopStale());
var profile = config.detectDeviceProfile();
watchdog.runCycle("stale-loop-test", profile);
var staleAfter = log.isRepairLoopStale();
log.append("[watchdog] stale-loop test finished isStaleAfterInvoke=" + staleAfter);
toast("stale-loop test done — expect Repair loop stale notification");
