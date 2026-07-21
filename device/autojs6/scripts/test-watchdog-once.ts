/**
 * Run a single watchdog cycle (no 20-min interval). For manual testing.
 * Usage: run from AutoJs6 while mode=autojs6 and accessibility is enabled.
 */
"auto";

import config = require("../lib/config.js");
import guard = require("../lib/guard.js");
import watchdog = require("../lib/watchdog.js");

guard.enforce();
// The "auto" directive above guarantees AutoJs6 has populated this global.
auto!.waitFor();

const profile = config.detectDeviceProfile();
watchdog.runCycle("manual-test", profile);
toast("stayturgid watchdog test cycle done — check /sdcard/stayturgid/logs/watchdog.log");
