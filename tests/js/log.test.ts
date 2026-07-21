/**
 * Unit tests for device/autojs6/lib/log.js under node, with a files{} shim standing
 * in for the AutoJs6 global. Emits TAP. Exit 0 = pass.
 *
 * Covers CODE-REVIEW.md L12: timestamps must parse as local time via
 * component construction, not Date.parse (local-vs-UTC ambiguous).
 */
import fs = require("fs");
import os = require("os");
import path = require("path");

declare global {
  // `var` is required here — TS global augmentation blocks don't accept let/const.
  var files: {
    exists(p: string): boolean;
    read(p: string): string;
    append(p: string, s: string): void;
    write(p: string, s: string): void;
    ensureDir(p: string): void;
  };
}

interface RepairStatus {
  port: string;
  shizuku: string | null;
  sshd: string | null;
  a11y?: string;
  shell?: string;
  wifi?: string;
}

interface DevicePaths {
  watchdogJsonl: string;
  watchdogState: string;
}

interface ConfigModule {
  WATCHDOG_LOG: string;
  pathsFor(profile: unknown): DevicePaths;
  detectDeviceProfile(): unknown;
  parentDir(filePath: string): string;
  ensureParentDir(filePath: string): string;
}

interface LogModule {
  parseStatusLine(line: string): RepairStatus | null;
  latestRepairStatus(): RepairStatus | null;
  latestRepairTimestampMs(): number | null;
  isRepairLoopStale(): boolean;
  append(line: string): string;
  readWatchdogLog(): string;
  writeState(source: string, statusObj: Record<string, unknown>): void;
}

const repo = path.resolve(__dirname, "..", "..");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stlog-"));
const mapped = (p: string): string => path.join(tmp, p.replace(/\//g, "_"));

const ensureDirCalls: string[] = [];
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
  // AutoJs6 files.ensureDir(path) expects a directory (trailing slash). The
  // shim records the raw argument so tests can assert log.append() passes the
  // log's *directory*, not the file path (CODE-REVIEW ensureDir regression).
  ensureDir(p) {
    ensureDirCalls.push(p);
  },
};

let n = 0;
let failed = 0;
function ok(cond: boolean, desc: string): void {
  n++;
  console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
  if (!cond) failed++;
}
function stamp(d: Date): string {
  const p = (x: number) => (x < 10 ? "0" : "") + x;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

const config = require(path.join(repo, "device", "autojs6", "lib", "config.js")) as ConfigModule;
const log = require(path.join(repo, "device", "autojs6", "lib", "log.js")) as LogModule;

// parseStatusLine
const s = log.parseStatusLine("2026-07-06 01:02:03 [repair] STATUS port=open shizuku=up sshd=restarted shell=yes rc=0");
ok(
  s !== null && s.port === "open" && s.shizuku === "up" && s.sshd === "restarted",
  "parseStatusLine extracts port/shizuku/sshd",
);
ok(s !== null && s.shell === "yes", "parseStatusLine extracts shell when present");
ok(log.parseStatusLine("garbage line") === null, "parseStatusLine rejects non-STATUS lines");

const full = log.parseStatusLine(
  "2026-07-09 19:00:00 [comonitor] STATUS port=skip shizuku=up sshd=up a11y=repaired shell=no wifi=skip",
);
ok(
  full !== null && full.a11y === "repaired" && full.wifi === "skip",
  "parseStatusLine extracts a11y/wifi from comonitor STATUS",
);

// latestRepairStatus picks the most recent [repair] STATUS
const now = new Date();
const old = new Date(Date.now() - 20 * 60 * 1000);
files.write(
  config.WATCHDOG_LOG,
  stamp(old) +
    " [repair] STATUS port=CLOSED_NO_SHELL shizuku=down sshd=up shell=no rc=1\n" +
    stamp(now) +
    " [repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0\n",
);
const latest = log.latestRepairStatus();
ok(latest !== null && latest.port === "open", "latestRepairStatus returns most recent STATUS");

// Prefer [repair] over newer [comonitor]
files.write(
  config.WATCHDOG_LOG,
  stamp(now) +
    " [repair] STATUS port=open shizuku=up sshd=up a11y=up shell=yes wifi=up rc=0\n" +
    stamp(now) +
    " [comonitor] STATUS port=CLOSED_NO_SHELL shizuku=up sshd=up a11y=up shell=no wifi=up\n",
);
const prefer = log.latestRepairStatus();
ok(prefer !== null && prefer.port === "open", "latestRepairStatus prefers [repair] over newer [comonitor]");

// L12 regression: local-time parse, no UTC skew
const ts = log.latestRepairTimestampMs();
ok(
  ts !== null && Math.abs(ts - now.getTime()) < 2000,
  "latestRepairTimestampMs matches local wall clock (no UTC skew)",
);
ok(log.isRepairLoopStale() === false, "fresh [repair] line => not stale");

files.write(config.WATCHDOG_LOG, stamp(old) + " [repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0\n");
ok(log.isRepairLoopStale() === true, "20-min-old [repair] line => stale (threshold 15 min)");

files.write(config.WATCHDOG_LOG, "no repair lines here\n");
ok(log.isRepairLoopStale() === true, "log without [repair] lines => stale");
ok(log.latestRepairStatus() === null, "log without STATUS lines => null status");

// ensureDir regression: append() must ensure the log's DIRECTORY, not the file
// path. Passing the file path to files.ensureDir would create a directory that
// shadows the log file (files.append then fails / self-heal never works).
ensureDirCalls.length = 0;
const written = log.append("[repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0");
ok(ensureDirCalls.length >= 1, "append() calls files.ensureDir before writing");
const dirArg = ensureDirCalls[ensureDirCalls.length - 1];
ok(
  /\/logs\/?$/.test(dirArg) && dirArg.indexOf("watchdog.log") < 0,
  "append() ensures the log directory, not the log file path",
);
ok(log.readWatchdogLog().indexOf(written) >= 0, "append() writes the timestamped line to the watchdog log");

// JSONL dual-write: append() should also write a valid JSON line to watchdog.jsonl
const watchdogJsonlPath = config.pathsFor(config.detectDeviceProfile()).watchdogJsonl;
let jsonlContent = "";
try {
  jsonlContent = fs.readFileSync(mapped(watchdogJsonlPath), "utf8");
} catch {
  /* ignore */
}
const jsonlLines = jsonlContent.split("\n").filter((l) => l.trim());
ok(jsonlLines.length > 0, "append() dual-writes at least one JSONL line to watchdog.jsonl");
if (jsonlLines.length > 0) {
  let parsed: { timestamp?: unknown; message?: unknown; hostname?: unknown } | null = null;
  try {
    parsed = JSON.parse(jsonlLines[jsonlLines.length - 1]);
  } catch {
    /* ignore */
  }
  ok(parsed !== null && typeof parsed.timestamp === "string", "JSONL line has a timestamp field");
  ok(parsed !== null && typeof parsed.message === "string", "JSONL line has a message field");
  ok(parsed !== null && parsed.hostname === "oneui-device", "JSONL line contains hostname from device profile");
}

// writeState: writes state.json with source namespace and timestamp
log.writeState("repair", { port: "open", shizuku: "up", sshd: "up", shell: "yes" });
const statePath = config.pathsFor(config.detectDeviceProfile()).watchdogState;
let stateContent = "";
try {
  stateContent = fs.readFileSync(mapped(statePath), "utf8");
} catch {
  /* ignore */
}
let stateObj: { repair?: { port?: unknown; timestamp?: unknown } } | null = null;
try {
  stateObj = JSON.parse(stateContent);
} catch {
  /* ignore */
}
ok(
  stateObj !== null && !!stateObj.repair && stateObj.repair.port === "open",
  "writeState() persists repair.port to state.json",
);
ok(
  stateObj !== null && !!stateObj.repair && typeof stateObj.repair.timestamp === "string",
  "writeState() adds a timestamp to the state entry",
);

// latestRepairStatus() prefers state.json over log scanning
// Clear the watchdog log so any result must come from state.json
files.write(config.WATCHDOG_LOG, "no status lines here\n");
const fromState = log.latestRepairStatus();
ok(fromState !== null && fromState.port === "open", "latestRepairStatus() reads from state.json when available");

// H10 regression: AutoJs6 does not provide files.getParent(). The shared helper
// must derive the directory using plain string operations and ensure the parent
// of a missing state/trigger file without treating the file path as a directory.
ok(
  config.parentDir("/sdcard/stayturgid/run/repair_now") === "/sdcard/stayturgid/run",
  "parentDir derives the trigger directory without files.getParent",
);
ok(
  config.parentDir("/sdcard/stayturgid/state/notify_state.json") === "/sdcard/stayturgid/state",
  "parentDir derives the notification directory without files.getParent",
);
ensureDirCalls.length = 0;
config.ensureParentDir("/sdcard/stayturgid/run/repair_now");
ok(
  ensureDirCalls[ensureDirCalls.length - 1] === "/sdcard/stayturgid/run/",
  "ensureParentDir creates the missing trigger directory",
);

console.log("1.." + n);
process.exit(failed ? 1 : 0);
