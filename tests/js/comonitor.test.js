// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Unit tests for device/autojs6/lib/comonitor.js under node (files{} + shizuku shims).
 * Emits TAP. Exit 0 = pass.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const Module = require("module");
const repo = path.resolve(__dirname, "..", "..");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stcom-"));
const mapped = (p) => path.join(tmp, p.replace(/\//g, "_"));
global.files = {
  exists(p) {
    if (p === "/sdcard/stayturgid/state/device.json") return true;
    return fs.existsSync(mapped(p));
  },
  read(p) {
    if (p === "/sdcard/stayturgid/state/device.json") {
      return JSON.stringify({ id: "oneui-device", sdRoot: "/sdcard/stayturgid" });
    }
    return fs.readFileSync(mapped(p), "utf8");
  },
  append(p, s) {
    fs.appendFileSync(mapped(p), s);
  },
  write(p, s) {
    fs.writeFileSync(mapped(p), s);
  },
  ensureDir() {},
};
global.sleep = () => {};
global.shell = () => ({ code: 1, result: "" });
global.auto = { service: null };
let n = 0;
let failed = 0;
function ok(cond, desc) {
  n++;
  console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
  if (!cond) failed++;
}
// Stub shizuku_shell before requiring comonitor (watchdog deps pull it in).
// Module._load is a private Node API with no public typings — the double
// assertion through `unknown` is the narrowest way to reach it.
const shizukuState = { operational: true, cmds: [] };
const ModuleInternals = Module;
const origLoad = ModuleInternals._load;
ModuleInternals._load = (request, parent) => {
  if (request === "./shizuku_shell.js" || request.endsWith("/shizuku_shell.js")) {
    return {
      isOperational: () => shizukuState.operational,
      exec: (cmd) => {
        shizukuState.cmds.push(cmd);
        if (cmd.indexOf("pgrep -x sshd") >= 0 || cmd.indexOf("[s]shd") >= 0) {
          return { code: 0, result: "" };
        }
        if (cmd.indexOf("pgrep -f '[s]hizuku_server'") >= 0) {
          return { code: 0, result: "" };
        }
        if (cmd.indexOf("enabled_accessibility_services") >= 0 && cmd.indexOf("settings get") >= 0) {
          return {
            code: 0,
            result: "org.autojs.autojs6/org.autojs.autojs.core.accessibility.AccessibilityServiceUsher",
          };
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
    return { show: () => {}, clear: () => {} };
  }
  if (request === "./repair.js" || request.endsWith("/repair.js")) {
    return { repairCatastrophic: () => true };
  }
  return origLoad.call(Module, request, parent);
};
const comonitor = require(path.join(repo, "device", "autojs6", "lib", "comonitor.js"));
const log = require(path.join(repo, "device", "autojs6", "lib", "log.js"));
ok(typeof comonitor.probeA11y === "function", "probeA11y exported");
const profile = { id: "oneui-device", sdRoot: "/sdcard/stayturgid", notifyTag: "" };
// Sticky candidate: auto present, service null, settings lists AutoJs6 → degraded (not hard FAILED)
global.auto = { service: null };
const sticky = comonitor.run(profile, { force: true, reason: "sticky" });
ok(
  sticky !== null && sticky.a11y === "degraded",
  "comonitor reports a11y degraded when settings list ON but auto.service null (sticky candidate)",
);
// Bound: auto.service truthy → up
global.auto = { service: {} };
const result = comonitor.run(profile, { force: true, reason: "test" });
ok(result !== null, "comonitor.run returns a status object when forced");
ok(result !== null && (result.sshd === "up" || result.sshd === "restarted"), "comonitor probes sshd");
ok(result !== null && result.shizuku === "up", "comonitor probes shizuku");
ok(result !== null && result.a11y === "up", "comonitor probes a11y when auto.service bound");
ok(result !== null && result.port === "open", "comonitor probes shell 5555 on non-split");
// comonitor.run() should persist status to state.json via writeState
const comonitorConfig = require(path.join(repo, "device", "autojs6", "lib", "config.js"));
const statePath = comonitorConfig.pathsFor(profile).watchdogState;
let stateContent = "";
try {
  stateContent = fs.readFileSync(mapped(statePath), "utf8");
} catch {
  /* ignore */
}
let stateObj = null;
try {
  stateObj = JSON.parse(stateContent);
} catch {
  /* ignore */
}
ok(
  stateObj !== null && !!stateObj.comonitor && typeof stateObj.comonitor.port === "string",
  "comonitor.run() writes comonitor.port to state.json via writeState",
);
ok(
  stateObj !== null && !!stateObj.comonitor && typeof stateObj.comonitor.timestamp === "string",
  "comonitor.run() includes timestamp in state.json comonitor namespace",
);
// Fire / split-storage: skip localhost:5555
const fire = { id: "fireos-device", sdRoot: "/data/data/com.termux/files/home/.stayturgid/shared" };
const fireResult = comonitor.run(fire, { force: true, reason: "split-storage" });
ok(fireResult !== null && fireResult.port === "skip", "split-storage skips localhost:5555");
ok(fireResult !== null && fireResult.wifi === "skip", "split-storage skips wifi flag");
// Without force and with fresh Termux repair, defer
const config = require(path.join(repo, "device", "autojs6", "lib", "config.js"));
function stamp(d) {
  const p = (x) => (x < 10 ? "0" : "") + x;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
files.write(
  config.WATCHDOG_LOG,
  stamp(new Date()) + " [repair] STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up rc=0\n",
);
ok(log.isRepairLoopStale() === false, "fresh repair for defer test");
ok(comonitor.run(profile, { force: false }) === null, "comonitor defers when Termux repair is fresh and force=false");
// Periodic path (force=true) always runs — fleet parity
const periodic = comonitor.run(profile, { force: true, reason: "periodic" });
ok(periodic !== null && periodic.port === "open", "comonitor force=true runs even when Termux repair is fresh");
// log.js accepts [comonitor] STATUS
files.write(
  config.WATCHDOG_LOG,
  stamp(new Date()) + " [comonitor] STATUS port=skip shizuku=up sshd=up a11y=up shell=no wifi=skip\n",
);
const st = log.latestRepairStatus();
ok(st !== null && st.port === "skip" && st.a11y === "up", "latestRepairStatus accepts [comonitor] STATUS with a11y");
ok(log.isRepairLoopStale() === true, "[comonitor] alone does not count as Termux repair freshness");
console.log("1.." + n);
process.exit(failed ? 1 : 0);
