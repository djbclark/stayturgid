// @generated
"use strict";
/**
 * Validate stale repair-loop detection without a 15-minute wait.
 * Injects a synthetic [repair] log line 20 minutes in the past, then runs one
 * watchdog cycle — expect "Repair loop stale" notification.
 *
 * Requires: mode=autojs6, accessibility enabled.
 */
"auto";
Object.defineProperty(exports, "__esModule", { value: true });
const config = require("../lib/config.js");
const guard = require("../lib/guard.js");
const log = require("../lib/log.js");
const watchdog = require("../lib/watchdog.js");
guard.enforce();
// The "auto" directive above guarantees AutoJs6 has populated this global.
auto.waitFor();
function pad(n) {
  return (n < 10 ? "0" : "") + n;
}
const stale = new Date(Date.now() - 20 * 60 * 1000);
const stamp =
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
const synthetic = stamp + " [repair] STATUS port=open shizuku=up sshd=up shell=yes (synthetic-stale-test)";
const prior = log.readWatchdogLog();
const kept = prior.split("\n").filter((line) => line.length > 0 && line.indexOf("[repair]") < 0);
kept.push(synthetic);
files.write(config.WATCHDOG_LOG, kept.join("\n") + "\n");
log.append("[watchdog] stale-loop test injected line at " + stamp + " isStaleBefore=" + log.isRepairLoopStale());
const profile = config.detectDeviceProfile();
watchdog.runCycle("stale-loop-test", profile);
const staleAfter = log.isRepairLoopStale();
log.append("[watchdog] stale-loop test finished isStaleAfterInvoke=" + staleAfter);
toast("stale-loop test done — expect Repair loop stale notification");
