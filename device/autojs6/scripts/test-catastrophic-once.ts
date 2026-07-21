/**
 * Validate catastrophic UI repair (Shizuku Start tap) without breaking port 5555.
 * Mirrors the CLOSED_NO_SHELL branch in watchdog.js — use when 5555 cannot be
 * safely taken down (e.g. oneui-device Shizuku auto-restart).
 *
 * Requires: unlocked screen, AutoJs6 accessibility, mode=autojs6.
 */
"auto";

import config = require("../lib/config.js");
import guard = require("../lib/guard.js");
import log = require("../lib/log.js");
import repair = require("../lib/repair.js");

guard.enforce();
// The "auto" directive above guarantees AutoJs6 has populated this global.
auto!.waitFor();

const profile = config.detectDeviceProfile();
log.append("[watchdog] catastrophic UI test start (autojs6)");
const ok = repair.repairCatastrophic(profile);
log.append("[watchdog] catastrophic UI test finished ok=" + ok + " (autojs6)");
toast("catastrophic UI test done ok=" + ok + " — check watchdog log");
