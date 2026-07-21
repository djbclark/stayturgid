// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.invokeTermuxRepair = void 0;
exports.repairCatastrophic = repairCatastrophic;
const termux = require("./termux.js");
const shizuku = require("./shizuku.js");
/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
function repairCatastrophic(profile) {
  return shizuku.repairCatastrophic(profile);
}
exports.invokeTermuxRepair = termux.invokeRepair;
