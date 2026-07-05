var log = require("./log.js");
var termux = require("./termux.js");
var shizuku = require("./shizuku.js");

/**
 * Run the catastrophic repair path when port 5555 is down and no privileged shell
 * is reachable from Termux (CLOSED_NO_SHELL).
 */
function repairCatastrophic(profile) {
    var ok = shizuku.tapStartButton(profile);
    if (!ok && profile.samsungWirelessDebugFallback) {
        shizuku.enableWirelessDebuggingUi(profile);
        ok = shizuku.tapStartButton(profile);
    }
    return ok;
}

module.exports = {
    repairCatastrophic: repairCatastrophic,
    invokeTermuxRepair: termux.invokeRepair,
};
