/**
 * One-shot setup probe — logs Shizuku operational state to watchdog.log.
 * Invoked from control/tools/autojs6/enable_autojs6_shizuku.py during fleet setup only.
 */
var log = require("../lib/log.js");
var sh = require("../lib/shizuku_shell.js");

var hasPerm = false;
var running = false;
var operational = false;
try {
    if (typeof shizuku !== "undefined") {
        if (typeof shizuku.hasPermission === "function") {
            hasPerm = shizuku.hasPermission();
        }
        if (typeof shizuku.isRunning === "function") {
            running = shizuku.isRunning();
        }
        operational = sh.isOperational();
    }
} catch (e) {
    log.append("[setup] shizuku probe error: " + e);
}
log.append("[setup] shizuku operational=" + operational
    + " hasPermission=" + hasPerm + " isRunning=" + running);
