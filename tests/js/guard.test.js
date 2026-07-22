// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Regression test for guard.js's Termux-repair nudge gate: invokeRepair()
 * must only fire when Termux's own boot loop looks stale, not on every
 * cycle just because AutoJs6 accessibility is off/sticky — a state Termux
 * repair can't fix (policy G3: never settings-put accessibility) and that
 * can persist indefinitely, which previously forced the Shizuku/RUN_COMMAND
 * fallback chain every single watchdog cycle regardless of Termux's actual
 * health. See stayturgid#34.
 */
const Module = require("module");
const path = require("path");
const repo = path.resolve(__dirname, "..", "..");
// guard.ts's a11y-off branch polls a real Date.now()-based deadline for up to
// 20s. Advancing a virtual clock on every call lets that loop resolve near-
// instantly instead of blocking this test for up to 20 real seconds.
let virtualNow = 1000000;
Date.now = () => {
  virtualNow += 3000;
  return virtualNow;
};
let repairLoopStale = false;
let invokeRepairCalls = 0;
const ModuleInternals = Module;
const origLoad = ModuleInternals._load;
ModuleInternals._load = (request, parent) => {
  if (request === "./config.js" || request.endsWith("/config.js")) {
    return {
      detectDeviceProfile: () => ({}),
      splitStorage: () => false,
      AUTOJS6_A11Y: "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher",
    };
  }
  if (request === "./notify.js" || request.endsWith("/notify.js")) {
    return { show: () => {}, clear: () => {} };
  }
  if (request === "./termux.js" || request.endsWith("/termux.js")) {
    return {
      invokeRepair: () => {
        invokeRepairCalls++;
        return { ok: false, fresh: false, method: "trigger_file" };
      },
    };
  }
  if (request === "./log.js" || request.endsWith("/log.js")) {
    return {
      append: (line) => line,
      isRepairLoopStale: () => repairLoopStale,
    };
  }
  if (request === "./comonitor.js" || request.endsWith("/comonitor.js")) {
    return { run: () => null };
  }
  return origLoad(request, parent);
};
global.auto = { service: null };
global.threads = {
  start: (fn) => {
    fn();
    return { join: () => {} };
  },
};
global.shell = () => ({ code: 1, result: "" });
global.sleep = () => {};
const guard = require(path.join(repo, "device", "autojs6", "lib", "guard.js"));
ModuleInternals._load = origLoad;
let n = 0;
let failed = 0;
function ok(cond, desc) {
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
