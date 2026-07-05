var log = require("./log.js");

var DEFAULT_PKG = "com.tailscale.ipn";
var DEFAULT_ACTIVITY = "com.tailscale.ipn.MainActivity";
var COORD_PING_HOST = "100.100.100.100";

function isTunUp(profile) {
    var ip = shell("ip -4 addr show tun0 2>/dev/null", false);
    if (ip.code === 0 && ip.result && String(ip.result).indexOf("inet ") >= 0) {
        return true;
    }
    var proc = shell("cat /proc/net/dev", false);
    if (proc.result && String(proc.result).indexOf("tun0:") >= 0) {
        return true;
    }
    if (profile && profile.tailscaleIp) {
        var selfPing = shell("ping -c 1 -W 2 " + profile.tailscaleIp, false);
        return selfPing.code === 0;
    }
    return false;
}

/**
 * Check Tailscale tunnel health: tun0 has traffic + coord server pings.
 */
function check(profile) {
    var tunUp = isTunUp(profile);
    var ping = shell("ping -c 1 -W 2 " + COORD_PING_HOST, false);
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
        var r = shell("am start -n " + pkg + "/" + cls, false);
        if (r.code === 0) {
            log.append("[watchdog] tailscale relaunch via am start");
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
