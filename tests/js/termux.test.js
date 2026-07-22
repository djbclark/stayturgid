// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Regression test for termux.js's RUN_COMMAND fallback: RUN_COMMAND_BACKGROUND
 * must reach Termux as a real boolean extra, not a string — see stayturgid#34.
 * A string-typed extra silently resolves to Termux's getBooleanExtra()
 * default of false (Bundle type mismatches are swallowed, not thrown), which
 * runs the repair command in the foreground and pops Termux to the front
 * instead of running it in the background.
 */
const Module = require("module");
const path = require("path");
const repo = path.resolve(__dirname, "..", "..");
class FakeIntent {
  constructor(action) {
    this.extras = [];
    this.action = action;
  }
  setClassName(packageName, className) {
    this.className = { packageName, className };
    return this;
  }
  putExtra(name, value) {
    this.extras.push({ name, value });
    return this;
  }
}
let startedIntent = null;
global.android = {
  content: { Intent: FakeIntent },
};
global.context = {
  startService: (intent) => {
    startedIntent = intent;
  },
};
// Stub termux.js's module-level deps before requiring it — only the Intent
// construction in tryRunCommand() is under test here.
const ModuleInternals = Module;
const origLoad = ModuleInternals._load;
ModuleInternals._load = (request, parent) => {
  if (request === "./config.js" || request.endsWith("/config.js")) {
    return {
      REPAIR_SCRIPT: "/data/data/com.termux/files/home/.stayturgid/bin/stayturgid_repair.py",
      TERMUX_HOME: "/data/data/com.termux/files/home",
      ensureParentDir: () => {},
      detectDeviceProfile: () => ({}),
      pathsFor: () => ({ triggerFile: "/tmp/stayturgid-test-trigger" }),
    };
  }
  if (request === "./log.js" || request.endsWith("/log.js")) {
    return {
      append: (line) => line,
      latestRepairTimestampMs: () => null,
    };
  }
  if (request === "./shizuku_shell.js" || request.endsWith("/shizuku_shell.js")) {
    return {
      isOperational: () => false,
      exec: () => ({ code: 1, result: "" }),
    };
  }
  return origLoad(request, parent);
};
const termux = require(path.join(repo, "device", "autojs6", "lib", "termux.js"));
ModuleInternals._load = origLoad;
let n = 0;
let failed = 0;
function ok(cond, desc) {
  n++;
  console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
  if (!cond) failed++;
}
const result = termux.tryRunCommand();
ok(result.started === true, "tryRunCommand() reports started");
ok(startedIntent !== null, "context.startService() was called with the built intent");
// `startedIntent` is only ever reassigned inside the context.startService
// closure above, which TS's control-flow analysis doesn't follow (same
// caveat as boot-launcher.test.ts) — restore its actual declared type.
const capturedIntent = startedIntent;
const bg = capturedIntent?.extras.find((e) => e.name === "com.termux.RUN_COMMAND_BACKGROUND");
ok(bg !== undefined, "RUN_COMMAND_BACKGROUND extra was set");
ok(
  bg?.value === true && typeof bg.value === "boolean",
  "RUN_COMMAND_BACKGROUND is a real boolean, not a string (stayturgid#34)",
);
ok(capturedIntent?.className?.packageName === "com.termux", "intent targets com.termux");
ok(capturedIntent?.className?.className === "com.termux.app.RunCommandService", "intent targets RunCommandService");
ok(capturedIntent?.action === "com.termux.RUN_COMMAND", "intent action is RUN_COMMAND");
console.log("1.." + n);
process.exit(failed === 0 ? 0 : 1);
