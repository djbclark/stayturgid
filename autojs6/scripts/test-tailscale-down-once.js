/**
 * Tailscale-down probe + watchdog cycle + relaunch (Mac script force-stops first).
 * Pair with: autojs6/mac/test-tailscale-down.sh
 */
"auto";

var config = require("../lib/config.js");
var guard = require("../lib/guard.js");
var log = require("../lib/log.js");
var tailscale = require("../lib/tailscale.js");
var watchdog = require("../lib/watchdog.js");

guard.enforce();

var profile = config.detectDeviceProfile();

function waitForUp(maxMs) {
    var deadline = Date.now() + maxMs;
    while (Date.now() < deadline) {
        var ts = tailscale.check(profile);
        if (ts.up) return ts;
        sleep(2000);
    }
    return tailscale.check(profile);
}

log.append("[watchdog] tailscale-down-test probe start (autojs6)");

var down = tailscale.check(profile);
log.append("[watchdog] tailscale-down-test probe tun=" + down.tun + " ping=" + down.ping + " up=" + down.up);

if (!down.up) {
    watchdog.runCycle("tailscale-down-live", profile);
}

var relaunched = tailscale.relaunch(profile);
sleep(2000);
var after = waitForUp(45000);

log.append("[watchdog] tailscale-down-test after-relaunch tun=" + after.tun + " ping=" + after.ping
    + " up=" + after.up + " relaunched=" + relaunched);
toast("tailscale-down probe up=" + after.up);
