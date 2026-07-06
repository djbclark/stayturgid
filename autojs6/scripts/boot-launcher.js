/**
 * Boot helper: start main.js if not already running.
 * Invoked from Termux:Boot (start-autojs6-watchdog.sh) or AutoJs6 timed/broadcast task.
 */
"auto";

var MAIN = "/sdcard/Scripts/stayturgid/main.js";

function mainAlreadyRunning() {
    var engines = runtime.engines.all();
    for (var i = 0; i < engines.length; i++) {
        var src = String(engines[i].getSource() || "");
        if (src.indexOf("stayturgid/main.js") >= 0) return true;
    }
    return false;
}

if (mainAlreadyRunning()) {
    exit();
}
engines.execScriptFile(MAIN);
