/**
 * Test Termux repair bridge only — does NOT enforce mode guard.
 * Run from AutoJs6 while Tasker can stay active (tests bridge, not full watchdog).
 */
"auto";

var termux = require("../lib/termux.js");
var log = require("../lib/log.js");

toast("Testing Termux bridge…");
var result = termux.invokeRepair();
var status = log.latestRepairStatus();
var line = log.append("[test] bridge ok=" + result.ok + " method=" + (result.method || "?")
    + " status=" + (status ? status.port : "none"));

toast(result.ok ? "Bridge OK: " + result.method : "Bridge FAIL");
console.log(line);
console.log(JSON.stringify(result));
console.log(JSON.stringify(status));
