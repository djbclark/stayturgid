var log = require("./log.js");
var sh = require("./shizuku_shell.js");

var DEFAULT_PKG = "com.tailscale.ipn";
var DEFAULT_ACTIVITY = "com.tailscale.ipn.MainActivity";
var COORD_PING_HOST = "100.100.100.100";

function isTunUp(profile) {
  var ip = sh.exec("ip -4 addr show tun0 2>/dev/null");
  if (ip.code === 0 && ip.result && String(ip.result).indexOf("inet ") >= 0) {
    return true;
  }
  var proc = sh.exec("cat /proc/net/dev");
  if (proc.result && String(proc.result).indexOf("tun0:") >= 0) {
    return true;
  }
  if (profile && profile.tailscaleIp) {
    var selfPing = sh.exec("ping -c 1 -W 2 " + profile.tailscaleIp);
    return selfPing.code === 0;
  }
  return false;
}

/**
 * Check Tailscale tunnel health: tun0 has traffic + coord server pings.
 */
function check(profile) {
  var tunUp = isTunUp(profile);
  var ping = sh.exec("ping -c 1 -W 2 " + COORD_PING_HOST);
  var pingOk = ping.code === 0;
  return {
    up: tunUp && pingOk,
    tun: tunUp,
    ping: pingOk,
  };
}

/** Relaunch Tailscale so always-on VPN can re-establish tun0. */
function relaunch(profile) {
  var pkg = (profile && profile.tailscalePackage) || DEFAULT_PKG;
  var cls = (profile && profile.tailscaleActivity) || DEFAULT_ACTIVITY;
  try {
    app.startActivity({
      packageName: pkg,
      className: cls,
      flags: ["activity_new_task"],
    });
    log.append("[watchdog] tailscale relaunch via " + pkg + "/" + cls);
    return true;
  } catch (e) {
    var r = sh.exec("am start -n " + pkg + "/" + cls);
    if (r.code === 0) {
      log.append("[watchdog] tailscale relaunch via shizuku/am start");
      return true;
    }
    log.append("[watchdog] tailscale relaunch failed: " + e);
    return false;
  }
}

module.exports = {
  check: check,
  relaunch: relaunch,
  COORD_PING_HOST: COORD_PING_HOST,
};
