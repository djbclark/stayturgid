var config = require("./config.js");
var log = require("./log.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var repair = require("./repair.js");
var tailscale = require("./tailscale.js");

/**
 * One watchdog cycle — mirrors ADB_Core_Watchdog v3 division of labor:
 *   Termux boot loop  → shell repairs every 5 min
 *   This layer        → real-time repair invoke + catastrophic UI + notifications
 *
 * Notifications use stable per-condition keys: a persistent outage updates one
 * notification instead of stacking new ones, and recovery clears it.
 */
function runCycle(trigger, profile) {
    var tag = profile.notifyTag || "";
    var split = config.splitStorage(profile);
    var time = log.append("[watchdog] cycle start trigger=" + trigger + " (autojs6)");

    if (split) {
        // Termux boot loop + repair-bridge own repair; AutoJs6 cannot read Termux-private logs.
        notify.clear("stale");
        notify.clear("bridge");
        log.append("[watchdog] split-storage: boot loop owns repair; skipping Termux bridge (autojs6)");
    } else {
        // Stale boot loop: check before real-time invoke (invoke refreshes [repair] timestamps).
        if (log.isRepairLoopStale()) {
            notify.show(
                "⚠ Repair loop stale " + tag,
                time + " — No [repair] log line in 15+ min; Termux boot loop may be dead. "
                    + "Open Termux or reboot.",
                "stale"
            );
        } else {
            notify.clear("stale");
        }

        // Real-time Termux repair via RUN_COMMAND / trigger file
        var invoke = termux.invokeRepair(profile);
        var status = invoke.fresh ? log.latestRepairStatus() : null;
        var port = status ? status.port : "BRIDGE_FAIL";
        var sshd = status ? status.sshd : "unknown";

        log.append("[watchdog] port=" + port + " sshd=" + sshd + " invoke="
            + (invoke.ok ? "ok" : "fail") + " method=" + (invoke.method || "?") + " (autojs6)");

        if (!invoke.ok || port === "BRIDGE_FAIL" || termux.bridgeFailed(invoke)) {
            notify.show(
                "⚠ Watchdog bridge failed " + tag,
                time + " — Termux RUN_COMMAND returned no fresh STATUS; check allow-external-apps "
                    + "and stayturgid-repair.sh on device.",
                "bridge"
            );
            return;
        }
        notify.clear("bridge");

        if (sshd === "down" || sshd === "FAILED") {
            notify.show(
                "⚠ SSH daemon down " + tag,
                time + " — Termux sshd not running (repair couldn't restore it). "
                    + "SSH in via ADB/Tailscale and run: sshd",
                "sshd"
            );
        } else {
            notify.clear("sshd");
        }
    }

    var ts;
    if (profile.tailscaleEnabled === false) {
        notify.clear("tailscale");
        log.append("[watchdog] tailscale checks disabled (not on tailnet yet) (autojs6)");
    } else {
        ts = tailscale.check(profile);
        log.append("[watchdog] tailscale tun=" + ts.tun + " ping=" + ts.ping + " up=" + ts.up);
        if (!ts.up) {
            notify.show(
                "⚠ Tailscale down " + tag,
                time + " — tun0 or ping " + tailscale.COORD_PING_HOST + " failed; relaunching Tailscale.",
                "tailscale"
            );
            tailscale.relaunch(profile);
        } else {
            notify.clear("tailscale");
        }
    }

    if (!split) {
        var status2 = log.latestRepairStatus();
        var port2 = status2 ? status2.port : null;
        if (port2 === "CLOSED_NO_SHELL") {
            notify.show(
                "⚠ ADB 5555 down — auto-repairing " + tag,
                time + " — port 5555 unreachable + no shell. Launching Shizuku + tapping Start. "
                    + "If it persists, reboot.",
                "adb5555"
            );
            repair.repairCatastrophic(profile);
            termux.invokeRepair(profile);
            var after = log.latestRepairStatus();
            if (after && after.port === "CLOSED_NO_SHELL") {
                log.append("[watchdog] catastrophic repair finished but port still CLOSED_NO_SHELL");
            }
        } else {
            notify.clear("adb5555");
        }
    } else {
        notify.clear("adb5555");
    }
}

module.exports = { runCycle: runCycle };
