// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.COORD_PING_HOST = void 0;
exports.check = check;
exports.relaunch = relaunch;
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
const tailscaleLog = require("./log.js");
const tailscaleSh = require("./shizuku_shell.js");
exports.COORD_PING_HOST = "100.100.100.100";
const DEFAULT_PKG = "com.tailscale.ipn";
const DEFAULT_ACTIVITY = "com.tailscale.ipn.MainActivity";
function isTunUp(profile) {
  const ip = tailscaleSh.exec("ip -4 addr show tun0 2>/dev/null");
  if (ip.code === 0 && ip.result && ip.result.indexOf("inet ") >= 0) {
    return true;
  }
  const proc = tailscaleSh.exec("cat /proc/net/dev");
  if (proc.result && proc.result.indexOf("tun0:") >= 0) {
    return true;
  }
  if (profile.tailscaleIp) {
    const selfPing = tailscaleSh.exec("ping -c 1 -W 2 " + profile.tailscaleIp);
    return selfPing.code === 0;
  }
  return false;
}
/**
 * Check Tailscale tunnel health: tun0 has traffic + coord server pings.
 */
function check(profile) {
  const tunUp = isTunUp(profile);
  const ping = tailscaleSh.exec("ping -c 1 -W 2 " + exports.COORD_PING_HOST);
  const pingOk = ping.code === 0;
  return {
    up: tunUp && pingOk,
    tun: tunUp,
    ping: pingOk,
  };
}
/** Relaunch Tailscale so always-on VPN can re-establish tun0. */
function relaunch(profile) {
  const pkg = profile.tailscalePackage || DEFAULT_PKG;
  const cls = profile.tailscaleActivity || DEFAULT_ACTIVITY;
  try {
    app.startActivity({
      packageName: pkg,
      className: cls,
      flags: ["activity_new_task"],
    });
    tailscaleLog.append("[watchdog] tailscale relaunch via " + pkg + "/" + cls);
    return true;
  } catch (e) {
    const r = tailscaleSh.exec("am start -n " + pkg + "/" + cls);
    if (r.code === 0) {
      tailscaleLog.append("[watchdog] tailscale relaunch via shizuku/am start");
      return true;
    }
    tailscaleLog.append("[watchdog] tailscale relaunch failed: " + e);
    return false;
  }
}
