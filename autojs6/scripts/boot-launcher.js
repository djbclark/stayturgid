/**
 * AutoJs6 broadcast task: run on app startup (Task tab → Timed task → Broadcast).
 * Starts main.js only when mode=autojs6 and main is not already running.
 */
"auto";

var config = require("../lib/config.js");
var MAIN = "/sdcard/Scripts/stayturgid/main.js";

function readMode() {
    if (!files.exists(config.MODE_FILE)) return "tasker";
    return String(files.read(config.MODE_FILE)).trim().toLowerCase();
}

function mainAlreadyRunning() {
    var engines = runtime.engines.all();
    for (var i = 0; i < engines.length; i++) {
        var src = String(engines[i].getSource() || "");
        if (src.indexOf("stayturgid/main.js") >= 0) return true;
    }
    return false;
}

if (readMode() !== "autojs6") {
    exit();
}
if (mainAlreadyRunning()) {
    exit();
}
engines.execScriptFile(MAIN);
