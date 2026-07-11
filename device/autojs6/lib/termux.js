var config = require("./config.js");
var log = require("./log.js");

var TERMUX_PKG = "com.termux";
var RUN_SERVICE = "com.termux.app.RunCommandService";
var RUN_ACTION = "com.termux.RUN_COMMAND";

/**
 * Invoke stayturgid_repair.py in Termux.
 *
 * Primary: RUN_COMMAND intent (needs AutoJs6 v6.4.1+ with
 * com.termux.permission.RUN_COMMAND granted + allow-external-apps=true).
 * Fallback: touch <sd>/run/repair_now for repair-bridge.sh (2s poll).
 */
function invokeRepair(profile) {
    profile = profile || config.detectDeviceProfile();
    var paths = config.pathsFor(profile);
    var triggerFile = paths.triggerFile;
    var beforeMs = log.latestRepairTimestampMs() || 0;
    var runCommand = tryRunCommand();
    var start = Date.now();
    var triggerArmed = false;

    // Immediate trigger only when RUN_COMMAND could not start at all.
    if (!runCommand.started) {
        tryTriggerFile(triggerFile);
        triggerArmed = true;
    }

    var deadline = Date.now() + 12000;
    while (Date.now() < deadline) {
        sleep(500);
        // Delayed backup trigger if RUN_COMMAND started but no fresh STATUS yet.
        if (!triggerArmed && runCommand.started && (Date.now() - start) > 5000) {
            tryTriggerFile(triggerFile);
            triggerArmed = true;
        }
        var afterMs = log.latestRepairTimestampMs();
        if (afterMs !== null && afterMs > beforeMs) {
            return {
                ok: true,
                fresh: true,
                method: runCommand.started ? "run_command" : "trigger_file",
                beforeMs: beforeMs,
                afterMs: afterMs,
            };
        }
    }

    if (!triggerArmed) {
        tryTriggerFile(triggerFile);
    }

    log.append("[watchdog] termux bridge timeout method="
        + (runCommand.started ? "run_command" : "trigger_file")
        + (runCommand.error ? " err=" + runCommand.error : ""));
    return { ok: false, fresh: false, method: runCommand.started ? "run_command" : "trigger_file" };
}

function tryRunCommand() {
    try {
        app.startService({
            action: RUN_ACTION,
            packageName: TERMUX_PKG,
            className: RUN_SERVICE,
            extras: {
                "com.termux.RUN_COMMAND_PATH": config.REPAIR_SCRIPT,
                "com.termux.RUN_COMMAND_BACKGROUND": "true",
                "com.termux.RUN_COMMAND_WORKDIR": config.TERMUX_HOME,
            },
        });
        return { started: true };
    } catch (e) {
        return { started: false, error: String(e) };
    }
}

function tryTriggerFile(triggerFile) {
    try {
        files.ensureDir(files.getParent(triggerFile) + "/");   // self-heal if run/ was deleted
        files.write(triggerFile, String(Date.now()));
    } catch (e) {
        log.append("[watchdog] trigger file write failed: " + e);
    }
}

function bridgeFailed(invokeResult) {
    if (!invokeResult || !invokeResult.fresh) return true;
    return log.latestRepairStatus() === null;
}

module.exports = {
    invokeRepair: invokeRepair,
    bridgeFailed: bridgeFailed,
};
