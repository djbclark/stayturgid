// @ts-nocheck
var log = require("./log.js");

/**
 * Run a shell command via AutoJs6's Shizuku API when operational, else shell().
 * Requires Shizuku drawer toggle ON in AutoJs6 (see docs/modules/autojs6.md).
 */
function isOperational() {
  try {
    if (typeof shizuku === "undefined" || typeof shizuku !== "function") {
      return false;
    }
    if (typeof shizuku.isOperational === "function") {
      return shizuku.isOperational();
    }
    if (typeof shizuku.state !== "undefined") {
      var st = shizuku.state;
      return st === true || st === "ready" || st === "operational";
    }
    var probe = shizuku("true");
    return probe && probe.code === 0;
  } catch (e) {
    return false;
  }
}

function exec(cmd) {
  if (isOperational()) {
    try {
      return shizuku(cmd);
    } catch (e) {
      log.append("[watchdog] shizuku exec failed: " + e);
    }
  }
  return shell(cmd, false);
}

module.exports = {
  isOperational: isOperational,
  exec: exec,
};
