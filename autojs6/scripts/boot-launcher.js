/**
 * Boot helper: start main.js if not already running.
 * Invoked from Termux:Boot (start-autojs6-watchdog.sh) or AutoJs6 timed/broadcast task.
 *
 * No "auto" directive: this launcher doesn't need accessibility, and it runs
 * every 5 min from the boot loop — requesting a11y here would bounce the user
 * to Settings repeatedly whenever the service is off (main.js handles a11y).
 */

var MAIN = "/sdcard/stayturgid/autojs6/main.js";
var STALE_WATCHDOG_MS = 25 * 60 * 1000;

function latestWatchdogCycleMs() {
    var logPath = "/sdcard/stayturgid/logs/watchdog.log";
    if (!files.exists(logPath)) return null;
    try {
        var lines = String(files.read(logPath)).split("\n");
        for (var i = lines.length - 1; i >= 0; i--) {
            if (lines[i].indexOf("[watchdog] cycle start") >= 0) {
                var m = lines[i].match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
                if (m) {
                    return new Date(
                        Number(m[1]), Number(m[2]) - 1, Number(m[3]),
                        Number(m[4]), Number(m[5]), Number(m[6])
                    ).getTime();
                }
            }
        }
    } catch (e) { /* best effort */ }
    return null;
}

function watchdogStale() {
    var last = latestWatchdogCycleMs();
    if (last === null) return true;
    return (Date.now() - last) > STALE_WATCHDOG_MS;
}

function findMainEngines() {
    var out = [];
    var engines = runtime.engines.all();
    for (var i = 0; i < engines.length; i++) {
        var src = String(engines[i].getSource() || "");
        if (src.indexOf(MAIN) >= 0 || src.indexOf("stayturgid/autojs6/main.js") >= 0) {
            out.push(engines[i]);
        }
    }
    return out;
}

var existing = findMainEngines();
if (existing.length === 1 && !watchdogStale()) {
    exit();
}
if (existing.length === 1 && watchdogStale()) {
    existing[0].forceStop();
}
if (existing.length > 1) {
    for (var j = 0; j < existing.length; j++) {
        existing[j].forceStop();
    }
}
engines.execScriptFile(MAIN);
