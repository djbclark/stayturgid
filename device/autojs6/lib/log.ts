// @ts-nocheck
var config = require("./config.js");

function ts() {
  var d = new Date();
  function pad(n) {
    return (n < 10 ? "0" : "") + n;
  }
  var mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()];
  return mon + " " + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}

/** ISO 8601 timestamp for JSONL/OTel schema. */
function tsISO() {
  var d = new Date();
  function pad(n) {
    return (n < 10 ? "0" : "") + n;
  }
  function pad3(n) {
    return (n < 10 ? "00" : n < 100 ? "0" : "") + n;
  }
  return (
    d.getFullYear() +
    "-" +
    pad(d.getMonth() + 1) +
    "-" +
    pad(d.getDate()) +
    "T" +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes()) +
    ":" +
    pad(d.getSeconds()) +
    "." +
    pad3(d.getMilliseconds()) +
    "Z"
  );
}

var LOG_KEEP_LINES = 500;
var LOG_TRIM_OVER = 1000;

function trimLogIfNeeded(logPath) {
  try {
    if (!files.exists(logPath)) return;
    var content = String(files.read(logPath));
    var lines = content.split("\n");
    // Drop trailing empty from final newline
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    if (lines.length <= LOG_TRIM_OVER) return;
    var kept = lines.slice(-LOG_KEEP_LINES);
    files.write(logPath, kept.join("\n") + "\n");
  } catch (e) {
    /* best effort */
  }
}

/**
 * Build a JSONL entry conforming to the universal OTel log schema.
 * Fields: timestamp, level, hostname, tag, pid, tid, message
 */
function buildJsonlEntry(line, profile) {
  var hostname = profile && profile.id ? profile.id : "unknown";
  // Extract tag from [tag] pattern at the start of the message if present.
  var tagMatch = String(line).match(/^\[([^\]]+)\]/);
  var tag = tagMatch ? tagMatch[1] : "watchdog";
  return JSON.stringify({
    timestamp: tsISO(),
    level: "info",
    hostname: hostname,
    tag: tag,
    pid: 0,
    tid: 0,
    message: String(line),
  });
}

function append(line) {
  var msg = ts() + " " + line;
  console.log(msg);
  try {
    var profile = config.detectDeviceProfile();
    var paths = config.pathsFor(profile);
    var logPath = paths.watchdogLog;
    var logDir = String(logPath).replace(/\/[^/]+$/, "");
    files.ensureDir(logDir + "/");
    // Dual-write: legacy text format
    files.append(logPath, msg + "\n");
    trimLogIfNeeded(logPath);
    // Dual-write: structured JSONL format
    try {
      files.append(paths.watchdogJsonl, buildJsonlEntry(line, profile) + "\n");
    } catch (je) {
      /* best effort — JSONL write failure must not break legacy logging */
    }
  } catch (e) {
    console.error("log append failed: " + e);
  }
  return msg;
}

/**
 * Atomically write or merge a status object into the shared state.json.
 * source: e.g. "repair" or "comonitor"
 * statusObj: key/value status map (port, shizuku, sshd, a11y, shell, wifi, etc.)
 *
 * Atomic write is simulated by writing to state.json.tmp then renaming.
 * In AutoJs6 we do not have fs.rename, so we use files.write directly
 * (best effort — partial writes are an extremely small window vs. the 20-min interval).
 */
function writeState(source, statusObj) {
  try {
    var profile = config.detectDeviceProfile();
    var statePath = config.pathsFor(profile).watchdogState;
    config.ensureParentDir(statePath);

    // Read current state (may be empty/missing).
    var current = {};
    try {
      if (files.exists(statePath)) {
        current = JSON.parse(String(files.read(statePath))) || {};
      }
    } catch (pe) {
      current = {};
    }

    // Merge the source namespace with a fresh timestamp.
    var entry = {};
    for (var k in statusObj) {
      entry[k] = statusObj[k];
    }
    entry.timestamp = tsISO();
    current[source] = entry;

    // Write atomically: write to tmp then overwrite final path.
    var tmpPath = statePath + ".tmp";
    files.write(tmpPath, JSON.stringify(current) + "\n");
    // AutoJs6 `files` has no rename; overwrite directly as best effort.
    files.write(statePath, JSON.stringify(current) + "\n");
  } catch (e) {
    /* best effort — state.json write failure must not break the watchdog */
  }
}

/** Read state.json; return parsed object or null. */
function _readState() {
  try {
    var profile = config.detectDeviceProfile();
    var statePath = config.pathsFor(profile).watchdogState;
    if (files.exists(statePath)) {
      return JSON.parse(String(files.read(statePath))) || null;
    }
  } catch (e) {
    /* ignore */
  }
  return null;
}

/** Read watchdog log; prefer a tail when the file is large (FUSE / battery). */
function readWatchdogLog() {
  var profile = config.detectDeviceProfile();
  var logPath = config.pathsFor(profile).watchdogLog;
  if (!files.exists(logPath)) return "";
  try {
    var content = String(files.read(logPath));
    var lines = content.split("\n");
    if (lines.length > LOG_TRIM_OVER) {
      return lines.slice(-LOG_KEEP_LINES).join("\n");
    }
    return content;
  } catch (e) {
    return "";
  }
}

function parseStatusLine(line) {
  var s = String(line);
  var m = s.match(/port=(\S+)\s+shizuku=(\S+)\s+sshd=(\S+)/);
  if (!m) return null;
  var out = { port: m[1], shizuku: m[2], sshd: m[3] };
  var a11y = s.match(/\ba11y=(\S+)/);
  var shell = s.match(/\bshell=(\S+)/);
  var wifi = s.match(/\bwifi=(\S+)/);
  if (a11y) out.a11y = a11y[1];
  if (shell) out.shell = shell[1];
  if (wifi) out.wifi = wifi[1];
  return out;
}

function _lineTimestampMs(line) {
  var m = String(line).match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6])).getTime();
}

/**
 * Read the latest repair status.
 * Prefers state.json["repair"] for O(1) read; falls back to log-scan for
 * backwards compatibility when the state file is absent or corrupt.
 */
function latestRepairStatus() {
  // --- Primary: state.json ---
  var state = _readState();
  if (state && state.repair && state.repair.port) {
    return {
      port: state.repair.port,
      shizuku: state.repair.shizuku || null,
      sshd: state.repair.sshd || null,
      a11y: state.repair.a11y || null,
      shell: state.repair.shell || null,
      wifi: state.repair.wifi || null,
    };
  }

  // --- Fallback: legacy log scan ---
  var content = readWatchdogLog();
  if (!content) return null;
  var lines = content.split("\n");
  var comonitorFallback = null;
  for (var i = lines.length - 1; i >= 0; i--) {
    // Prefer Termux [repair] STATUS for bridge decisions. A bad
    // [comonitor] STATUS must not trigger CLOSED_NO_SHELL UI repair.
    if (lines[i].indexOf("[repair]") >= 0 && lines[i].indexOf("STATUS") >= 0) {
      return parseStatusLine(lines[i]);
    }
    if (comonitorFallback === null && lines[i].indexOf("[comonitor]") >= 0 && lines[i].indexOf("STATUS") >= 0) {
      comonitorFallback = parseStatusLine(lines[i]);
    }
  }
  return comonitorFallback;
}

/**
 * Return the millisecond timestamp of the most recent Termux [repair] run.
 * Prefers state.json["repair"].timestamp; falls back to log-scan.
 */
function latestRepairTimestampMs() {
  // --- Primary: state.json ---
  var state = _readState();
  if (state && state.repair && state.repair.timestamp) {
    try {
      var t = new Date(state.repair.timestamp).getTime();
      if (!isNaN(t)) return t;
    } catch (e) {
      /* fall through */
    }
  }

  // --- Fallback: legacy log scan ---
  var content = readWatchdogLog();
  if (!content) return null;
  var lines = content.split("\n");
  for (var i = lines.length - 1; i >= 0; i--) {
    // Termux [repair] is authoritative freshness; [comonitor] does not
    // count as "Termux alive" (would hide a dead boot loop).
    if (lines[i].indexOf("[repair]") >= 0) {
      var lineTs = _lineTimestampMs(lines[i]);
      if (lineTs !== null) return lineTs;
    }
  }
  return null;
}

function isRepairLoopStale() {
  var last = latestRepairTimestampMs();
  if (last === null) return true;
  return Date.now() - last > config.STALE_REPAIR_MS;
}

module.exports = {
  append: append,
  writeState: writeState,
  readWatchdogLog: readWatchdogLog,
  parseStatusLine: parseStatusLine,
  latestRepairStatus: latestRepairStatus,
  latestRepairTimestampMs: latestRepairTimestampMs,
  isRepairLoopStale: isRepairLoopStale,
};
