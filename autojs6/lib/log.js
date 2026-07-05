var config = require("./config.js");

function ts() {
    var d = new Date();
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-"
        + pad(d.getMonth() + 1) + "-"
        + pad(d.getDate()) + " "
        + pad(d.getHours()) + ":"
        + pad(d.getMinutes()) + ":"
        + pad(d.getSeconds());
}

function append(line) {
    var msg = ts() + " " + line;
    console.log(msg);
    try {
        files.append(config.WATCHDOG_LOG, msg + "\n");
    } catch (e) {
        console.error("log append failed: " + e);
    }
    return msg;
}

function readWatchdogLog() {
    if (!files.exists(config.WATCHDOG_LOG)) return "";
    try {
        return String(files.read(config.WATCHDOG_LOG));
    } catch (e) {
        return "";
    }
}

function parseStatusLine(line) {
    var m = String(line).match(/port=(\S+)\s+shizuku=(\S+)\s+sshd=(\S+)/);
    if (!m) return null;
    return { port: m[1], shizuku: m[2], sshd: m[3] };
}

function latestRepairStatus() {
    var content = readWatchdogLog();
    if (!content) return null;
    var lines = content.split("\n");
    for (var i = lines.length - 1; i >= 0; i--) {
        if (lines[i].indexOf("[repair] STATUS") >= 0) {
            return parseStatusLine(lines[i]);
        }
    }
    return null;
}

function latestRepairTimestampMs() {
    var content = readWatchdogLog();
    if (!content) return null;
    var lines = content.split("\n");
    for (var i = lines.length - 1; i >= 0; i--) {
        if (lines[i].indexOf("[repair]") >= 0) {
            var m = lines[i].match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
            if (m) {
                return Date.parse(m[1].replace(" ", "T"));
            }
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
