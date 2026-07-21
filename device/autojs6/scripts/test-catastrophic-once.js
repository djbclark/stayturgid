// @generated
"use strict";
// @ts-nocheck
/**
 * Validate catastrophic UI repair (Shizuku Start tap) without breaking port 5555.
 * Mirrors the CLOSED_NO_SHELL branch in watchdog.js — use when 5555 cannot be
 * safely taken down (e.g. oneui-device Shizuku auto-restart).
 *
 * Requires: unlocked screen, AutoJs6 accessibility, mode=autojs6.
 */
"auto";
var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var log = require("../lib/log.js");
var repair = require("../lib/repair.js");
guard.enforce();
auto.waitFor();
var profile = config.detectDeviceProfile();
log.append("[watchdog] catastrophic UI test start (autojs6)");
var ok = repair.repairCatastrophic(profile);
log.append("[watchdog] catastrophic UI test finished ok=" + ok + " (autojs6)");
toast("catastrophic UI test done ok=" + ok + " — check watchdog log");
