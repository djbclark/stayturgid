// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
import repairTermux = require("./termux.js");
import repairShizuku = require("./shizuku.js");

import type { DeviceProfile } from "./config.js";

/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
export function repairCatastrophic(profile: DeviceProfile): boolean {
  return repairShizuku.repairCatastrophic(profile);
}

export const invokeTermuxRepair = repairTermux.invokeRepair;
