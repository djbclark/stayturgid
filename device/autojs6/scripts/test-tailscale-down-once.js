// @generated
"use strict";
/**
 * Tailscale-down probe + relaunch (Mac script force-stops first).
 * Pair with: control/tools/autojs6/test_tailscale_down.py
 *
 * One-shot test script — skips guard.enforce() and full watchdog.runCycle()
 * so the Mac driver gets log lines within ~60s (relaunch + waitForUp only).
 */
"auto";
Object.defineProperty(exports, "__esModule", { value: true });
const config = require("../lib/config.js");
const log = require("../lib/log.js");
const tailscale = require("../lib/tailscale.js");
const profile = config.detectDeviceProfile();
config.ensureDirs(profile);
function waitForUp(maxMs) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const ts = tailscale.check(profile);
    if (ts.up) return ts;
    sleep(2000);
  }
  return tailscale.check(profile);
}
log.append("[watchdog] tailscale-down-test probe start (autojs6)");
const down = tailscale.check(profile);
log.append("[watchdog] tailscale-down-test probe tun=" + down.tun + " ping=" + down.ping + " up=" + down.up);
const relaunched = tailscale.relaunch(profile);
sleep(2000);
const after = waitForUp(45000);
log.append(
  "[watchdog] tailscale-down-test after-relaunch tun=" +
    after.tun +
    " ping=" +
    after.ping +
    " up=" +
    after.up +
    " relaunched=" +
    relaunched,
);
toast("tailscale-down probe up=" + after.up);
