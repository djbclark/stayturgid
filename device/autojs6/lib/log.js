var config = require("./config.js");

function ts() {
    var d = new Date();
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    var mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()];
    return mon + " "
        + pad(d.getDate()) + " "
        + pad(d.getHours()) + ":"
        + pad(d.getMinutes()) + ":"
        + pad(d.getSeconds());
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

function append(line) {
    var msg = ts() + " " + line;
    console.log(msg);
    try {
        var profile = config.detectDeviceProfile();
        var logPath = config.pathsFor(profile).watchdogLog;
        var logDir = String(logPath).replace(/\/[^/]+$/, "");
        files.ensureDir(logDir + "/");
        files.append(logPath, msg + "\n");
        trimLogIfNeeded(logPath);
    } catch (e) {
        console.error("log append failed: " + e);
    }
    return msg;
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
    return new Date(
        Number(m[1]), Number(m[2]) - 1, Number(m[3]),
        Number(m[4]), Number(m[5]), Number(m[6])
    ).getTime();
}

function latestRepairStatus() {
    var content = readWatchdogLog();
    if (!content) return null;
    var lines = content.split("\n");
    var comonitorFallback = null;
    for (var i = lines.length - 1; i >= 0; i--) {
        // Prefer Termux [repair] STATUS for bridge decisions. A bad
        // [comonitor] STATUS must not trigger CLOSED_NO_SHELL UI repair.
        if (lines[i].indexOf("[repair] STATUS") >= 0) {
            return parseStatusLine(lines[i]);
        }
        if (comonitorFallback === null
                && lines[i].indexOf("[comonitor] STATUS") >= 0) {
            comonitorFallback = parseStatusLine(lines[i]);
        }
    }
    return comonitorFallback;
}

function latestRepairTimestampMs() {
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
    return (Date.now() - last) > config.STALE_REPAIR_MS;
}

module.exports = {
    append: append,
    readWatchdogLog: readWatchdogLog,
    parseStatusLine: parseStatusLine,
    latestRepairStatus: latestRepairStatus,
    latestRepairTimestampMs: latestRepairTimestampMs,
    isRepairLoopStale: isRepairLoopStale,
};
