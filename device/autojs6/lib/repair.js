// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.invokeTermuxRepair = void 0;
exports.repairCatastrophic = repairCatastrophic;
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
const repairTermux = require("./termux.js");
const repairShizuku = require("./shizuku.js");
/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
function repairCatastrophic(profile) {
  return repairShizuku.repairCatastrophic(profile);
}
exports.invokeTermuxRepair = repairTermux.invokeRepair;
