/**
 * Ensure at most one stayturgid main.js engine is running.
 * Shared by main.js (startup) and boot-launcher.js.
 */
var MAIN = "/sdcard/stayturgid/autojs6/main.js";

function findMainEngines() {
  var out = [];
  var all = runtime.engines.all();
  for (var i = 0; i < all.length; i++) {
    var src = String(all[i].getSource() || "");
    if (src.indexOf(MAIN) >= 0 || src.indexOf("stayturgid/autojs6/main.js") >= 0) {
      out.push(all[i]);
    }
  }
  return out;
}

/**
 * Stop duplicate main.js engines. Keeps the current engine when identifiable.
 * @returns {number} engines force-stopped
 */
function dedupeMainEngines() {
  var self = null;
  try {
    self = engines.myEngine();
  } catch (e) {
    /* best effort */
  }
  if (!self) {
    return 0;
  }
  var existing = findMainEngines();
  if (existing.length <= 1) {
    return 0;
  }
  var stopped = 0;
  for (var i = 0; i < existing.length; i++) {
    if (self && existing[i].id === self.id) {
      continue;
    }
    try {
      existing[i].forceStop();
      stopped++;
    } catch (e2) {
      /* ignore */
    }
  }
  return stopped;
}

module.exports = {
  MAIN: MAIN,
  findMainEngines: findMainEngines,
  dedupeMainEngines: dedupeMainEngines,
};
