// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Regression test for boot-launcher.js child working-directory handling.
 * AutoJs6 otherwise inherits scripts/ and main.js cannot load ./lib/*.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const repo = path.resolve(__dirname, "..", "..");
const source = fs.readFileSync(path.join(repo, "device", "autojs6", "scripts", "boot-launcher.js"), "utf8");
const main = "/sdcard/stayturgid/autojs6/main.js";
class ExecutionConfig {
  constructor() {
    this.workingDirectory = null;
  }
  setWorkingDirectory(value) {
    this.workingDirectory = value;
  }
}
let execution = null;
const sandbox = {
  require(name) {
    if (name === "../lib/engine_guard.js") {
      return {
        MAIN: main,
        findMainEngines: () => [],
        dedupeMainEngines: () => 0,
      };
    }
    if (name === "../lib/config.js") {
      return { WATCHDOG_LOG: "/sdcard/stayturgid/logs/watchdog.log" };
    }
    throw new Error("unexpected require: " + name);
  },
  files: {},
  // Rhino's CommonJS module loader always wraps a loaded script with its own
  // `module`/`exports` (confirmed: org.mozilla.javascript.commonjs.module,
  // the real implementation behind AutoJs6's require()). tsc's compiled
  // output now references `exports` unconditionally (the __esModule stamp
  // every ES-module-syntax .ts file gets under CommonJS output, regardless
  // of whether it has real exports) — this sandbox has to provide one too,
  // matching what the real loader always does.
  exports: {},
  engines: {
    execScriptFile: (script, config) => {
      execution = { script, config };
    },
  },
  org: {
    autojs: {
      autojs: {
        execution: { ExecutionConfig },
      },
    },
  },
};
vm.runInNewContext(source, sandbox, { filename: "boot-launcher.js" });
// `execution` is only ever assigned inside the `engines.execScriptFile` closure
// above, which TS's control-flow analysis doesn't follow — it computes
// `execution`'s flow type here as bare `null` even after the closure has run.
// The assertion restores its actual declared type.
const result = execution;
const passed =
  result !== null &&
  result.script === main &&
  result.config instanceof ExecutionConfig &&
  result.config.workingDirectory === "/sdcard/stayturgid/autojs6";
console.log((passed ? "ok" : "not ok") + " 1 - child runs from AutoJs6 project directory");
console.log("1..1");
process.exit(passed ? 0 : 1);
