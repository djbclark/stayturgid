// @generated
"use strict";
// @ts-nocheck
// @heals: PORT5555-OPEN SHIZUKU-HEADLESS
var log = require("./log.js");
var sh = require("./shizuku_shell.js");
function serverRunning() {
  // HEADLESS_STATUS on Samsung returns result=0 even when running
  // (Samsung freezes the Java broadcast receiver). Fall back to pgrep.
  var r = sh.exec("am broadcast -a moe.shizuku.privileged.api.HEADLESS_STATUS 2>/dev/null");
  if (r && r.code === 0 && r.result && r.result.indexOf("result=1") >= 0) {
    return true;
  }
  var p = sh.exec("pgrep -f '[s]hizuku_server'");
  return p && p.code === 0 && String(p.result || "").trim().length > 0;
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
function tryShellWirelessRepair() {
  if (!sh.isOperational()) {
    return false;
  }
  log.append("[watchdog] shizuku shell: trying wireless-debug repair");
  // Read before write — avoid redundant settings triggers and adbd restart
  var dev = sh.exec("settings get global development_settings_enabled");
  if (!dev || String(dev.result || "").trim() !== "1") {
    sh.exec("settings put global development_settings_enabled 1");
  }
  var adbEn = sh.exec("settings get global adb_enabled");
  if (!adbEn || String(adbEn.result || "").trim() !== "1") {
    sh.exec("settings put global adb_enabled 1");
  }
  var wifiEn = sh.exec("settings get global adb_wifi_enabled");
  if (!wifiEn || String(wifiEn.result || "").trim() !== "1") {
    sh.exec("settings put global adb_wifi_enabled 1");
  }
  var curPort = sh.exec("getprop service.adb.tcp.port");
  if (!curPort || String(curPort.result || "").trim() !== "5555") {
    sh.exec("setprop service.adb.tcp.port 5555");
    sleep(1000);
  }
  sleep(2000);
  sh.exec("adb connect 127.0.0.1:5555");
  sleep(1000);
  var uid = sh.exec("adb -s localhost:5555 shell id -u");
  if (uid && uid.code === 0 && String(uid.result || "").trim() === "2000") {
    log.append("[watchdog] shizuku shell: localhost:5555 shell uid 2000");
    return true;
  }
  return false;
}
/**
 * Headless start via operator/Shizuku HEADLESS_START broadcast.
 * The fork has built-in retry logic (3 attempts, 5s delay).
 */
function headlessStart() {
  if (!sh.isOperational()) {
    return false;
  }
  log.append("[watchdog] shizuku headless: sending HEADLESS_START broadcast");
  sh.exec("am broadcast -a moe.shizuku.privileged.api.HEADLESS_START");
  sleep(5000);
  return serverRunning();
}
/**
 * Catastrophic path: shell repair, then HEADLESS_START broadcast
 * (with built-in retry logic in the fork).
 */
function repairCatastrophic(profile) {
  if (serverRunning() && tryShellWirelessRepair()) {
    return true;
  }
  if (tryShellWirelessRepair()) {
    return true;
  }
  if (headlessStart()) {
    log.append("[watchdog] shizuku headless start succeeded");
    if (tryShellWirelessRepair()) {
      return true;
    }
    return serverRunning();
  }
  log.append("[watchdog] shizuku headless start failed after retries");
  return false;
}
module.exports = {
  headlessStart: headlessStart,
  repairCatastrophic: repairCatastrophic,
  tryShellWirelessRepair: tryShellWirelessRepair,
  serverRunning: serverRunning,
};
