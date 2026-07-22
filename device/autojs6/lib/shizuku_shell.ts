// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
import shizukuShellLog = require("./log.js");

/**
 * Run a shell command via AutoJs6's Shizuku API when operational, else shell().
 * Requires Shizuku drawer toggle ON in AutoJs6 (see docs/modules/autojs6.md).
 */
export function isOperational(): boolean {
  try {
    if (typeof shizuku === "undefined" || typeof shizuku !== "function") {
      return false;
    }
    if (typeof shizuku.isOperational === "function") {
      return shizuku.isOperational();
    }
    if (typeof shizuku.state !== "undefined") {
      const st = shizuku.state;
      return st === true || st === "ready" || st === "operational";
    }
    const probe = shizuku("true");
    return probe.code === 0;
  } catch {
    return false;
  }
}

export function exec(cmd: string): ShellResult {
  if (isOperational() && shizuku) {
    try {
      return shizuku(cmd);
    } catch (e) {
      shizukuShellLog.append("[watchdog] shizuku exec failed: " + e);
    }
  }
  return shell(cmd, false);
}
