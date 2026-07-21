// @ts-nocheck
var termux = require("./termux.js");

/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
function repairCatastrophic(profile) {
  return require("./shizuku.js").repairCatastrophic(profile);
}

module.exports = {
  repairCatastrophic: repairCatastrophic,
  invokeTermuxRepair: termux.invokeRepair,
};
