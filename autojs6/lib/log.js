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
        var profile = config.detectDeviceProfile();
        var logPath = config.pathsFor(profile).watchdogLog;
        var logDir = String(logPath).replace(/\/[^/]+$/, "");
        files.ensureDir(logDir + "/");
        files.append(logPath, msg + "\n");
    } catch (e) {
        console.error("log append failed: " + e);
    }
    return msg;
}

function readWatchdogLog() {
    var profile = config.detectDeviceProfile();
    var logPath = config.pathsFor(profile).watchdogLog;
    if (!files.exists(logPath)) return "";
    try {
        return String(files.read(logPath));
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
            // Construct from components: Date.parse of a no-offset ISO string
            // is local-vs-UTC ambiguous across JS engine versions.
            var m = lines[i].match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
            if (m) {
                return new Date(
                    Number(m[1]), Number(m[2]) - 1, Number(m[3]),
                    Number(m[4]), Number(m[5]), Number(m[6])
                ).getTime();
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
