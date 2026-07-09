var config = require("./config.js");
var log = require("./log.js");
var notify = require("./notify.js");
var termux = require("./termux.js");
var repair = require("./repair.js");
var tailscale = require("./tailscale.js");
var comonitor = require("./comonitor.js");

/**
 * One watchdog cycle — Termux-primary + AutoJs6 co-monitor redundancy:
 *   Termux boot loop  → routine repair every 5 min (authoritative when healthy)
 *   This layer        → notifications, Tailscale, catastrophic Shizuku repair;
 *                       comonitor.js always re-probes the same STATUS surface
 *                       via shizuku() on every host (parity across the fleet).
 */
function runCycle(trigger, profile) {
    var tag = profile.notifyTag || "";
    var split = config.splitStorage(profile);
    var time = log.append("[watchdog] cycle start trigger=" + trigger + " (autojs6)");
    var termuxStale = log.isRepairLoopStale();
    var comonitorReason = "periodic";

    if (split) {
        notify.clear("stale");
        notify.clear("bridge");
        log.append("[watchdog] split-storage: Termux bridge skipped — co-monitor via Shizuku");
        comonitorReason = "split-storage";
    } else {
        if (termuxStale) {
            notify.show(
                "⚠ Repair loop stale " + tag,
                time + " — No [repair] log line in 15+ min; Termux boot loop may be dead. "
                    + "AutoJs6 co-monitor will probe via Shizuku.",
                "stale"
            );
            comonitorReason = "termux-stale";
        } else {
            notify.clear("stale");
        }

        var status = log.latestRepairStatus();
        var port = status ? status.port : null;
        var sshd = status ? status.sshd : "unknown";

        if (port === "CLOSED_NO_SHELL") {
            notify.show(
                "⚠ ADB 5555 down — auto-repairing " + tag,
                time + " — port 5555 unreachable + no shell. Trying Shizuku shell, "
                    + "then UI Start tap. If it persists, reboot.",
                "adb5555"
            );
            repair.repairCatastrophic(profile);
            termux.invokeRepair(profile);
            var after = log.latestRepairStatus();
            if (after && after.port === "CLOSED_NO_SHELL") {
                log.append("[watchdog] catastrophic repair finished but port still CLOSED_NO_SHELL");
                comonitorReason = "closed-no-shell";
            }
        } else {
            notify.clear("adb5555");

            if (termuxStale) {
                var invoke = termux.invokeRepair(profile);
                status = invoke.fresh ? log.latestRepairStatus() : status;
                port = status ? status.port : "BRIDGE_FAIL";
                sshd = status ? status.sshd : "unknown";
                log.append("[watchdog] port=" + port + " sshd=" + sshd + " invoke="
                    + (invoke.ok ? "ok" : "fail") + " method=" + (invoke.method || "?")
                    + " (autojs6 stale-loop)");
                if (!invoke.ok || port === "BRIDGE_FAIL" || termux.bridgeFailed(invoke)) {
                    notify.show(
                        "⚠ Watchdog bridge failed " + tag,
                        time + " — Termux RUN_COMMAND returned no fresh STATUS; "
                            + "co-monitor taking over via Shizuku.",
                        "bridge"
                    );
                    comonitorReason = "bridge-fail";
                } else {
                    notify.clear("bridge");
                    if (sshd === "down" || sshd === "FAILED"
                            || (status && status.shizuku === "down")) {
                        comonitorReason = "post-bridge-unhealthy";
                    }
                }
            } else {
                notify.clear("bridge");
                log.append("[watchdog] termux repair fresh — co-monitor still verifies (autojs6)");
            }

            if (sshd === "down" || sshd === "FAILED") {
                notify.show(
                    "⚠ SSH daemon down " + tag,
                    time + " — Termux sshd not running (repair couldn't restore it). "
                        + "SSH in via ADB/Tailscale and run: sshd",
                    "sshd"
                );
                comonitorReason = "sshd-down";
            } else {
                notify.clear("sshd");
            }
        }
    }

    // Fleet parity: every host runs the same Shizuku co-monitor each cycle.
    comonitor.run(profile, { force: true, reason: comonitorReason });

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
}

module.exports = { runCycle: runCycle };
