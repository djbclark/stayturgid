// @ts-nocheck
/**
 * Log Tailscale probe results (tun0 + coord ping) and optional relaunch dry-run.
 * Usage: run from AutoJs6 while mode=autojs6.
 */
"auto";

var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var log = require("../lib/log.js");
var tailscale = require("../lib/tailscale.js");

guard.enforce();

var profile = config.detectDeviceProfile();
var ts = tailscale.check(profile);
log.append("[watchdog] tailscale-probe-test tun=" + ts.tun + " ping=" + ts.ping + " up=" + ts.up);
toast("tailscale probe up=" + ts.up + " tun=" + ts.tun + " ping=" + ts.ping);
