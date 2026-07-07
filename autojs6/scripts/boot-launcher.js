/**
 * Boot helper: start main.js if not already running.
 * Invoked from Termux:Boot (start-autojs6-watchdog.sh) or AutoJs6 timed/broadcast task.
 *
 * No "auto" directive: this launcher doesn't need accessibility, and it runs
 * every 5 min from the boot loop — requesting a11y here would bounce the user
 * to Settings repeatedly whenever the service is off (main.js handles a11y).
 */

var MAIN = "/sdcard/stayturgid/autojs6/main.js";

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
if (existing.length === 1) {
    exit();
}
if (existing.length > 1) {
    for (var j = 0; j < existing.length; j++) {
        existing[j].forceStop();
    }
}
engines.execScriptFile(MAIN);
