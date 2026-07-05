var config = require("./config.js");
var log = require("./log.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var repair = require("./repair.js");

/**
 * One watchdog cycle — mirrors ADB_Core_Watchdog v3 division of labor:
 *   Termux boot loop  → shell repairs every 5 min
 *   This layer        → real-time repair invoke + catastrophic UI + notifications
 */
function runCycle(trigger, profile) {
    var tag = profile.notifyTag || "";
    var time = log.append("[watchdog] cycle start trigger=" + trigger + " (autojs6)");

    // Real-time Termux repair (like Termux:Tasker act0)
    var invoke = termux.invokeRepair();
    var status = invoke.fresh ? log.latestRepairStatus() : null;
    var port = status ? status.port : "BRIDGE_FAIL";
    var sshd = status ? status.sshd : "unknown";

    log.append("[watchdog] port=" + port + " sshd=" + sshd + " invoke="
        + (invoke.ok ? "ok" : "fail") + " method=" + (invoke.method || "?") + " (autojs6)");

    if (!invoke.ok || port === "BRIDGE_FAIL" || termux.bridgeFailed(invoke)) {
        notify.show(
            "⚠ Watchdog bridge failed " + tag,
            time + " — Termux RUN_COMMAND returned no fresh STATUS; check allow-external-apps "
                + "and stayturgid-repair.sh on device."
        );
        return;
    }

    if (sshd === "down" || sshd === "FAILED") {
        notify.show(
            "⚠ SSH daemon down " + tag,
            time + " — Termux sshd not running (repair couldn't restore it). "
                + "SSH in via ADB/Tailscale and run: sshd"
        );
    }

    if (log.isRepairLoopStale()) {
        notify.show(
            "⚠ Repair loop stale " + tag,
            time + " — No [repair] log line in 15+ min; Termux boot loop may be dead. "
                + "Open Termux or reboot."
        );
    }

    if (port === "CLOSED_NO_SHELL") {
        notify.show(
            "⚠ ADB 5555 down — auto-repairing " + tag,
            time + " — port 5555 unreachable + no shell. Launching Shizuku + tapping Start. "
                + "If it persists, reboot."
        );
        repair.repairCatastrophic(profile);
        // Re-invoke repair to pick up any restored shell channel
        termux.invokeRepair();
        var after = log.latestRepairStatus();
        if (after && after.port === "CLOSED_NO_SHELL") {
            log.append("[watchdog] catastrophic repair finished but port still CLOSED_NO_SHELL");
        }
    }
}

module.exports = { runCycle: runCycle };
