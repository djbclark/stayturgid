/**
 * Unit tests for device/autojs6/lib/comonitor.js under node (files{} + shizuku shims).
 * Emits TAP. Exit 0 = pass.
 */
"use strict";
var fs = require("fs"), os = require("os"), path = require("path");

var repo = path.resolve(__dirname, "..", "..");
var tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stcom-"));
var mapped = function (p) { return path.join(tmp, String(p).replace(/\//g, "_")); };

global.files = {
    exists: function (p) { return fs.existsSync(mapped(p)); },
    read:   function (p) { return fs.readFileSync(mapped(p), "utf8"); },
    append: function (p, s) { fs.appendFileSync(mapped(p), s); },
    write:  function (p, s) { fs.writeFileSync(mapped(p), s); },
    ensureDir: function () {},
};
global.console = console;
global.sleep = function () {};
global.shell = function () { return { code: 1, result: "" }; };
global.auto = { service: null };

var n = 0, failed = 0;
function ok(cond, desc) {
    n++;
    console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
    if (!cond) failed++;
}

// Stub shizuku_shell before requiring comonitor (watchdog deps pull it in).
var shizukuState = { operational: true, cmds: [] };
var Module = require("module");
var origLoad = Module._load;
Module._load = function (request, parent) {
    if (request === "./shizuku_shell.js" || request.endsWith("/shizuku_shell.js")) {
        return {
            isOperational: function () { return shizukuState.operational; },
            exec: function (cmd) {
                shizukuState.cmds.push(cmd);
                if (cmd.indexOf("pgrep -x sshd") >= 0 || cmd.indexOf("[s]shd") >= 0) {
                    return { code: 0, result: "" };
                }
                if (cmd.indexOf("pgrep -f '[s]hizuku_server'") >= 0) {
                    return { code: 0, result: "" };
                }
                if (cmd.indexOf("enabled_accessibility_services") >= 0
                        && cmd.indexOf("settings get") >= 0) {
                    return { code: 0, result: "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher" };
                }
                if (cmd.indexOf("adb_wifi_enabled") >= 0 && cmd.indexOf("get") >= 0) {
                    return { code: 0, result: "1" };
                }
                if (cmd.indexOf("id -u") >= 0) {
                    return { code: 0, result: "2000" };
                }
                return { code: 0, result: "" };
            },
        };
    }
    if (request === "./notify.js" || request.endsWith("/notify.js")) {
        return { show: function () {}, clear: function () {} };
    }
    if (request === "./repair.js" || request.endsWith("/repair.js")) {
        return { repairCatastrophic: function () { return true; } };
    }
    return origLoad.apply(this, arguments);
};

var comonitor = require(path.join(repo, "device", "autojs6", "lib", "comonitor.js"));
var log = require(path.join(repo, "device", "autojs6", "lib", "log.js"));

ok(typeof comonitor.probeA11y === "function", "probeA11y exported");

var profile = { id: "s24", sdRoot: "/sdcard/stayturgid", notifyTag: "" };
var result = comonitor.run(profile, { force: true, reason: "test" });
ok(result !== null, "comonitor.run returns a status object when forced");
ok(result.sshd === "up" || result.sshd === "restarted", "comonitor probes sshd");
ok(result.shizuku === "up", "comonitor probes shizuku");
ok(result.a11y === "up", "comonitor probes a11y (detection only)");
ok(result.port === "open", "comonitor probes shell 5555 on non-split");

// Fire / split-storage: skip localhost:5555
var fire = { id: "hd8", sdRoot: "/data/data/com.termux/files/home/.stayturgid/shared" };
var fireResult = comonitor.run(fire, { force: true, reason: "split-storage" });
ok(fireResult.port === "skip", "split-storage skips localhost:5555");
ok(fireResult.wifi === "skip", "split-storage skips wifi flag");

// Without force and with fresh Termux repair, defer
var config = require(path.join(repo, "device", "autojs6", "lib", "config.js"));
function stamp(d) {
    function p(x) { return (x < 10 ? "0" : "") + x; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate())
        + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
}
files.write(config.WATCHDOG_LOG,
    stamp(new Date()) + " [repair] STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up rc=0\n");
ok(log.isRepairLoopStale() === false, "fresh repair for defer test");
ok(comonitor.run(profile, { force: false }) === null,
    "comonitor defers when Termux repair is fresh and force=false");

// Periodic path (force=true) always runs — fleet parity
var periodic = comonitor.run(profile, { force: true, reason: "periodic" });
ok(periodic !== null && periodic.port === "open",
    "comonitor force=true runs even when Termux repair is fresh");

// log.js accepts [comonitor] STATUS
files.write(config.WATCHDOG_LOG,
    stamp(new Date()) + " [comonitor] STATUS port=skip shizuku=up sshd=up a11y=up shell=no wifi=skip\n");
var st = log.latestRepairStatus();
ok(st !== null && st.port === "skip" && st.a11y === "up",
    "latestRepairStatus accepts [comonitor] STATUS with a11y");
ok(log.isRepairLoopStale() === true,
    "[comonitor] alone does not count as Termux repair freshness");

console.log("1.." + n);
process.exit(failed ? 1 : 0);
