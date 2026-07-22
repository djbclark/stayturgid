/**
 * Regression test for guard.js's Termux-repair nudge gate: invokeRepair()
 * must only fire when Termux's own boot loop looks stale, not on every
 * cycle just because AutoJs6 accessibility is off/sticky — a state Termux
 * repair can't fix (policy G3: never settings-put accessibility) and that
 * can persist indefinitely, which previously forced the Shizuku/RUN_COMMAND
 * fallback chain every single watchdog cycle regardless of Termux's actual
 * health. See stayturgid#34.
 */
import Module = require("module");
import path = require("path");

const repo = path.resolve(__dirname, "..", "..");

// guard.ts's a11y-off branch polls a real Date.now()-based deadline for up to
// 20s. Advancing a virtual clock on every call lets that loop resolve near-
// instantly instead of blocking this test for up to 20 real seconds.
let virtualNow = 1_000_000;
Date.now = (): number => {
  virtualNow += 3000;
  return virtualNow;
};

let repairLoopStale = false;
let invokeRepairCalls = 0;

const ModuleInternals = Module as unknown as { _load: (request: string, parent: unknown) => unknown };
const origLoad = ModuleInternals._load;
ModuleInternals._load = (request: string, parent: unknown): unknown => {
  if (request === "./config.js" || request.endsWith("/config.js")) {
    return {
      detectDeviceProfile: (): Record<string, never> => ({}),
      splitStorage: (): boolean => false,
      AUTOJS6_A11Y: "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher",
    };
  }
  if (request === "./notify.js" || request.endsWith("/notify.js")) {
    return { show: (): void => {}, clear: (): void => {} };
  }
  if (request === "./termux.js" || request.endsWith("/termux.js")) {
    return {
      invokeRepair: (): { ok: boolean; fresh: boolean; method: string } => {
        invokeRepairCalls++;
        return { ok: false, fresh: false, method: "trigger_file" };
      },
    };
  }
  if (request === "./log.js" || request.endsWith("/log.js")) {
    return {
      append: (line: string): string => line,
      isRepairLoopStale: (): boolean => repairLoopStale,
    };
  }
  if (request === "./comonitor.js" || request.endsWith("/comonitor.js")) {
    return { run: (): null => null };
  }
  return origLoad(request, parent);
};

(global as unknown as { auto: unknown }).auto = { service: null };
(global as unknown as { threads: unknown }).threads = {
  start: (fn: () => void): { join(): void } => {
    fn();
    return { join: (): void => {} };
  },
};
(global as unknown as { shell: unknown }).shell = (): { code: number; result: string } => ({ code: 1, result: "" });
(global as unknown as { sleep: unknown }).sleep = (): void => {};

const guard = require(path.join(repo, "device", "autojs6", "lib", "guard.js")) as {
  enforce(profile?: unknown): void;
};

ModuleInternals._load = origLoad;

let n = 0;
let failed = 0;
function ok(cond: boolean, desc: string): void {
  n++;
  console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
  if (!cond) failed++;
}

repairLoopStale = false;
invokeRepairCalls = 0;
guard.enforce();
ok(
  invokeRepairCalls === 0,
  "does not nudge Termux repair when its boot loop is fresh (a11y off/sticky alone is not enough)",
);

repairLoopStale = true;
invokeRepairCalls = 0;
guard.enforce();
ok(invokeRepairCalls === 1, "nudges Termux repair once when its boot loop is stale");

console.log("1.." + n);
process.exit(failed === 0 ? 0 : 1);
