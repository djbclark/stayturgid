/**
 * Unit tests for autojs6/lib/log.js under node, with a files{} shim standing
 * in for the AutoJs6 global. Emits TAP. Exit 0 = pass.
 *
 * Covers CODE-REVIEW.md L12: timestamps must parse as local time via
 * component construction, not Date.parse (local-vs-UTC ambiguous).
 */
"use strict";
var fs = require("fs"), os = require("os"), path = require("path");

var repo = path.resolve(__dirname, "..", "..");
var tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stlog-"));
var mapped = function (p) { return path.join(tmp, String(p).replace(/\//g, "_")); };

var ensureDirCalls = [];
global.files = {
    exists: function (p) { return fs.existsSync(mapped(p)); },
    read:   function (p) { return fs.readFileSync(mapped(p), "utf8"); },
    append: function (p, s) { fs.appendFileSync(mapped(p), s); },
    write:  function (p, s) { fs.writeFileSync(mapped(p), s); },
    // AutoJs6 files.ensureDir(path) expects a directory (trailing slash). The
    // shim records the raw argument so tests can assert log.append() passes the
    // log's *directory*, not the file path (CODE-REVIEW ensureDir regression).
    ensureDir: function (p) { ensureDirCalls.push(String(p)); },
};

var n = 0, failed = 0;
function ok(cond, desc) {
    n++;
    console.log((cond ? "ok " : "not ok ") + n + " - " + desc);
    if (!cond) failed++;
}
function stamp(d) {
    function p(x) { return (x < 10 ? "0" : "") + x; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate())
        + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
}

var config = require(path.join(repo, "autojs6", "lib", "config.js"));
var log = require(path.join(repo, "autojs6", "lib", "log.js"));

// parseStatusLine
var s = log.parseStatusLine(
    "2026-07-06 01:02:03 [repair] STATUS port=open shizuku=up sshd=restarted shell=yes rc=0");
ok(s !== null && s.port === "open" && s.shizuku === "up" && s.sshd === "restarted",
    "parseStatusLine extracts port/shizuku/sshd");
ok(s.shell === "yes", "parseStatusLine extracts shell when present");
ok(log.parseStatusLine("garbage line") === null, "parseStatusLine rejects non-STATUS lines");

var full = log.parseStatusLine(
    "2026-07-09 19:00:00 [comonitor] STATUS port=skip shizuku=up sshd=up a11y=repaired shell=no wifi=skip");
ok(full !== null && full.a11y === "repaired" && full.wifi === "skip",
    "parseStatusLine extracts a11y/wifi from comonitor STATUS");

// latestRepairStatus picks the most recent STATUS
var now = new Date();
var old = new Date(Date.now() - 20 * 60 * 1000);
files.write(config.WATCHDOG_LOG,
    stamp(old) + " [repair] STATUS port=CLOSED_NO_SHELL shizuku=down sshd=up shell=no rc=1\n"
    + stamp(now) + " [repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0\n");
var latest = log.latestRepairStatus();
ok(latest !== null && latest.port === "open", "latestRepairStatus returns most recent STATUS");

// L12 regression: local-time parse, no UTC skew
var ts = log.latestRepairTimestampMs();
ok(ts !== null && Math.abs(ts - now.getTime()) < 2000,
    "latestRepairTimestampMs matches local wall clock (no UTC skew)");
ok(log.isRepairLoopStale() === false, "fresh [repair] line => not stale");

files.write(config.WATCHDOG_LOG,
    stamp(old) + " [repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0\n");
ok(log.isRepairLoopStale() === true, "20-min-old [repair] line => stale (threshold 15 min)");

files.write(config.WATCHDOG_LOG, "no repair lines here\n");
ok(log.isRepairLoopStale() === true, "log without [repair] lines => stale");
ok(log.latestRepairStatus() === null, "log without STATUS lines => null status");

// ensureDir regression: append() must ensure the log's DIRECTORY, not the file
// path. Passing the file path to files.ensureDir would create a directory that
// shadows the log file (files.append then fails / self-heal never works).
ensureDirCalls.length = 0;
var written = log.append("[repair] STATUS port=open shizuku=up sshd=up shell=yes rc=0");
ok(ensureDirCalls.length >= 1, "append() calls files.ensureDir before writing");
var dirArg = ensureDirCalls[ensureDirCalls.length - 1];
ok(/\/logs\/?$/.test(dirArg) && dirArg.indexOf("watchdog.log") < 0,
    "append() ensures the log directory, not the log file path");
ok(log.readWatchdogLog().indexOf(written) >= 0,
    "append() writes the timestamped line to the watchdog log");

console.log("1.." + n);
process.exit(failed ? 1 : 0);
