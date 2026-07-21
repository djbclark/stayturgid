// @generated
// @ts-nocheck
/**
 * Regression test for boot-launcher.js child working-directory handling.
 * AutoJs6 otherwise inherits scripts/ and main.js cannot load ./lib/*.
 */
"use strict";
var fs = require("fs");
var path = require("path");
var vm = require("vm");
var repo = path.resolve(__dirname, "..", "..");
var source = fs.readFileSync(path.join(repo, "device", "autojs6", "scripts", "boot-launcher.js"), "utf8");
var main = "/sdcard/stayturgid/autojs6/main.js";
var execution = null;
function ExecutionConfig() {
  this.workingDirectory = null;
}
ExecutionConfig.prototype.setWorkingDirectory = function (value) {
  this.workingDirectory = String(value);
};
var sandbox = {
  require: function (name) {
    if (name === "../lib/engine_guard.js") {
      return {
        MAIN: main,
        findMainEngines: function () {
          return [];
        },
        dedupeMainEngines: function () {
          return 0;
        },
      };
    }
    if (name === "../lib/config.js") {
      return { WATCHDOG_LOG: "/sdcard/stayturgid/logs/watchdog.log" };
    }
    throw new Error("unexpected require: " + name);
  },
  files: {},
  engines: {
    execScriptFile: function (script, config) {
      execution = { script: script, config: config };
    },
  },
  org: {
    autojs: {
      autojs: {
        execution: { ExecutionConfig: ExecutionConfig },
      },
    },
  },
};
vm.runInNewContext(source, sandbox, { filename: "boot-launcher.js" });
var passed =
  execution !== null &&
  execution.script === main &&
  execution.config instanceof ExecutionConfig &&
  execution.config.workingDirectory === "/sdcard/stayturgid/autojs6";
console.log((passed ? "ok" : "not ok") + " 1 - child runs from AutoJs6 project directory");
console.log("1..1");
process.exit(passed ? 0 : 1);
