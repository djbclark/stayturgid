// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MAIN = void 0;
exports.findMainEngines = findMainEngines;
exports.dedupeMainEngines = dedupeMainEngines;
/**
 * Ensure at most one stayturgid main.js engine is running.
 * Shared by main.js (startup) and boot-launcher.js.
 */
exports.MAIN = "/sdcard/stayturgid/autojs6/main.js";
function findMainEngines() {
  return runtime.engines.all().filter((engine) => {
    const src = engine.getSource() || "";
    return src.indexOf(exports.MAIN) >= 0 || src.indexOf("stayturgid/autojs6/main.js") >= 0;
  });
}
/**
 * Stop duplicate main.js engines. Keeps the current engine when identifiable.
 * Returns the number of engines force-stopped.
 */
function dedupeMainEngines() {
  let self = null;
  try {
    self = engines.myEngine();
  } catch (_a) {
    /* best effort */
  }
  if (!self) {
    return 0;
  }
  const existing = findMainEngines();
  if (existing.length <= 1) {
    return 0;
  }
  let stopped = 0;
  for (const engine of existing) {
    if (engine.id === self.id) {
      continue;
    }
    try {
      engine.forceStop();
      stopped++;
    } catch (_b) {
      /* ignore */
    }
  }
  return stopped;
}
