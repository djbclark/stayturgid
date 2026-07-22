// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
// @heals: PORT5555-OPEN SHIZUKU-HEADLESS
import shizukuLog = require("./log.js");
import shizukuSh = require("./shizuku_shell.js");

import type { DeviceProfile } from "./config.js";

function serverRunning(): boolean {
  // HEADLESS_STATUS on Samsung returns result=0 even when running
  // (Samsung freezes the Java broadcast receiver). Fall back to pgrep.
  const r = shizukuSh.exec("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null");
  if (r.code === 0 && r.result.indexOf("result=1") >= 0) {
    return true;
  }
  const p = shizukuSh.exec("pgrep -f '[s]hizuku_server'");
  return p.code === 0 && p.result.trim().length > 0;
}

/**
 * Best-effort wireless-debug / adbd enable via Shizuku shell (no manager UI).
 * Returns true when localhost:5555 answers after the attempt.
 *
 * Steps (in order):
 *   1. Enable developer options (belt-and-suspenders).
 *   2. Enable USB ADB (some ROMs require this before wifi ADB).
 *   3. Enable wireless debugging — triggers AdbService ContentObserver.
 *   4. Force adbd to listen on TCP 5555 (legacy mode).
 *   5. Connect local ADB client to the local adbd.
 *   6. Verify shell uid 2000 on localhost:5555.
 */
function tryShellWirelessRepair(): boolean {
  if (!shizukuSh.isOperational()) {
    return false;
  }
  shizukuLog.append("[watchdog] shizuku shell: trying wireless-debug repair");
  // Read before write — avoid redundant settings triggers and adbd restart
  const dev = shizukuSh.exec("settings get global development_settings_enabled");
  if (dev.result.trim() !== "1") {
    shizukuSh.exec("settings put global development_settings_enabled 1");
  }
  const adbEn = shizukuSh.exec("settings get global adb_enabled");
  if (adbEn.result.trim() !== "1") {
    shizukuSh.exec("settings put global adb_enabled 1");
  }
  const wifiEn = shizukuSh.exec("settings get global adb_wifi_enabled");
  if (wifiEn.result.trim() !== "1") {
    shizukuSh.exec("settings put global adb_wifi_enabled 1");
  }
  const curPort = shizukuSh.exec("getprop service.adb.tcp.port");
  if (curPort.result.trim() !== "5555") {
    shizukuSh.exec("setprop service.adb.tcp.port 5555");
    sleep(1000);
  }
  sleep(2000);
  shizukuSh.exec("adb connect 127.0.0.1:5555");
  sleep(1000);
  const uid = shizukuSh.exec("adb -s localhost:5555 shell id -u");
  if (uid.code === 0 && uid.result.trim() === "2000") {
    shizukuLog.append("[watchdog] shizuku shell: localhost:5555 shell uid 2000");
    return true;
  }
  return false;
}

/**
 * Headless start via operator/Shizuku HEADLESS_START broadcast.
 * The fork has built-in retry logic (3 attempts, 5s delay).
 */
function headlessStart(): boolean {
  if (!shizukuSh.isOperational()) {
    return false;
  }
  shizukuLog.append("[watchdog] shizuku headless: sending HEADLESS_START broadcast");
  shizukuSh.exec("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START");
  sleep(5000);
  return serverRunning();
}

/**
 * Catastrophic path: shell repair, then HEADLESS_START broadcast
 * (with built-in retry logic in the fork).
 *
 * NOTE: `profile` is accepted for interface parity with repair.ts's caller
 * but unused — pre-existing behavior, not this rewrite's call to change.
 */
function repairCatastrophic(_profile: DeviceProfile): boolean {
  if (serverRunning() && tryShellWirelessRepair()) {
    return true;
  }
  if (tryShellWirelessRepair()) {
    return true;
  }
  if (headlessStart()) {
    shizukuLog.append("[watchdog] shizuku headless start succeeded");
    if (tryShellWirelessRepair()) {
      return true;
    }
    return serverRunning();
  }
  shizukuLog.append("[watchdog] shizuku headless start failed after retries");
  return false;
}

export { headlessStart, repairCatastrophic, serverRunning, tryShellWirelessRepair };
