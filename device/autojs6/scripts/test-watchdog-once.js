/**
 * Run a single watchdog cycle (no 20-min interval). For manual testing.
 * Usage: run from AutoJs6 while mode=autojs6 and accessibility is enabled.
 */
"auto";

var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var watchdog = require("../lib/watchdog.js");

guard.enforce();
auto.waitFor();

var profile = config.detectDeviceProfile();
watchdog.runCycle("manual-test", profile);
toast("stayturgid watchdog test cycle done — check /sdcard/stayturgid/logs/watchdog.log");
