// @generated
"use strict";
/**
 * Test the Termux repair bridge in isolation (bridge only, not the full watchdog).
 */
"auto";
Object.defineProperty(exports, "__esModule", { value: true });
const termux = require("../lib/termux.js");
const log = require("../lib/log.js");
toast("Testing Termux bridge…");
const result = termux.invokeRepair();
const status = log.latestRepairStatus();
const line = log.append(
  "[test] bridge ok=" + result.ok + " method=" + result.method + " status=" + (status ? status.port : "none"),
);
toast(result.ok ? "Bridge OK: " + result.method : "Bridge FAIL");
console.log(line);
console.log(JSON.stringify(result));
console.log(JSON.stringify(status));
