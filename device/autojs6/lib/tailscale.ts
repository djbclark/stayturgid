import log = require("./log.js");
import sh = require("./shizuku_shell.js");

import type { DeviceProfile } from "./config.js";

export const COORD_PING_HOST = "100.100.100.100";
const DEFAULT_PKG = "com.tailscale.ipn";
const DEFAULT_ACTIVITY = "com.tailscale.ipn.MainActivity";

type TailscaleProfile = Pick<DeviceProfile, "tailscaleIp" | "tailscalePackage" | "tailscaleActivity">;

function isTunUp(profile: TailscaleProfile): boolean {
  const ip = sh.exec("ip -4 addr show tun0 2>/dev/null");
  if (ip.code === 0 && ip.result && ip.result.indexOf("inet ") >= 0) {
    return true;
  }
  const proc = sh.exec("cat /proc/net/dev");
  if (proc.result && proc.result.indexOf("tun0:") >= 0) {
    return true;
  }
  if (profile.tailscaleIp) {
    const selfPing = sh.exec("ping -c 1 -W 2 " + profile.tailscaleIp);
    return selfPing.code === 0;
  }
  return false;
}

export interface TailscaleHealth {
  up: boolean;
  tun: boolean;
  ping: boolean;
}

/**
 * Check Tailscale tunnel health: tun0 has traffic + coord server pings.
 */
export function check(profile: TailscaleProfile): TailscaleHealth {
  const tunUp = isTunUp(profile);
  const ping = sh.exec("ping -c 1 -W 2 " + COORD_PING_HOST);
  const pingOk = ping.code === 0;
  return {
    up: tunUp && pingOk,
    tun: tunUp,
    ping: pingOk,
  };
}

/** Relaunch Tailscale so always-on VPN can re-establish tun0. */
export function relaunch(profile: TailscaleProfile): boolean {
  const pkg = profile.tailscalePackage || DEFAULT_PKG;
  const cls = profile.tailscaleActivity || DEFAULT_ACTIVITY;
  try {
    app.startActivity({
      packageName: pkg,
      className: cls,
      flags: ["activity_new_task"],
    });
    log.append("[watchdog] tailscale relaunch via " + pkg + "/" + cls);
    return true;
  } catch (e) {
    const r = sh.exec("am start -n " + pkg + "/" + cls);
    if (r.code === 0) {
      log.append("[watchdog] tailscale relaunch via shizuku/am start");
      return true;
    }
    log.append("[watchdog] tailscale relaunch failed: " + e);
    return false;
  }
}
