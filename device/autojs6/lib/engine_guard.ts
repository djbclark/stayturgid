// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
/**
 * Ensure at most one stayturgid main.js engine is running.
 * Shared by main.js (startup) and boot-launcher.js.
 */
export const MAIN = "/sdcard/stayturgid/autojs6/main.js";

export function findMainEngines(): Engine[] {
  return runtime.engines.all().filter((engine) => {
    // String(...) coercion is required: engine.getSource() is a Java string
    // via Rhino's LiveConnect wrapper, which doesn't carry JS String.prototype
    // methods (indexOf, etc.) until explicitly coerced to a native JS string.
    const src = String(engine.getSource() || "");
    return src.indexOf(MAIN) >= 0 || src.indexOf("stayturgid/autojs6/main.js") >= 0;
  });
}

/**
 * Stop duplicate main.js engines. Keeps the current engine when identifiable.
 * Returns the number of engines force-stopped.
 */
export function dedupeMainEngines(): number {
  let self: Engine | null = null;
  try {
    self = engines.myEngine();
  } catch {
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
  // Plain indexed loop, not for...of: this Rhino build's interpreted mode
  // doesn't support the for...of iterator protocol.
  for (let i = 0; i < existing.length; i++) {
    const engine = existing[i];
    if (engine.id === self.id) {
      continue;
    }
    try {
      engine.forceStop();
      stopped++;
    } catch {
      /* ignore */
    }
  }
  return stopped;
}
