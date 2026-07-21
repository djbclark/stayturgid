/**
 * Log Tailscale probe results (tun0 + coord ping) and optional relaunch dry-run.
 * Usage: run from AutoJs6 while mode=autojs6.
 */
"auto";

import config = require("../lib/config.js");
import guard = require("../lib/guard.js");
import log = require("../lib/log.js");
import tailscale = require("../lib/tailscale.js");

guard.enforce();

const profile = config.detectDeviceProfile();
const ts = tailscale.check(profile);
log.append("[watchdog] tailscale-probe-test tun=" + ts.tun + " ping=" + ts.ping + " up=" + ts.up);
toast("tailscale probe up=" + ts.up + " tun=" + ts.tun + " ping=" + ts.ping);
