import termux = require("./termux.js");
import shizuku = require("./shizuku.js");

import type { DeviceProfile } from "./config.js";

/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
export function repairCatastrophic(profile: DeviceProfile): boolean {
  return shizuku.repairCatastrophic(profile);
}

export const invokeTermuxRepair = termux.invokeRepair;
