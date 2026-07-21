// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * One-shot setup probe — logs Shizuku operational state to watchdog.log.
 * Invoked from control/tools/autojs6/enable_autojs6_shizuku.py during fleet setup only.
 */
const log = require("../lib/log.js");
const sh = require("../lib/shizuku_shell.js");
let hasPerm = false;
let running = false;
let operational = false;
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
log.append("[setup] shizuku operational=" + operational + " hasPermission=" + hasPerm + " isRunning=" + running);
