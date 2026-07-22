// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runCycle = runCycle;
// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
// @heals: TAILSCALE-VPN
const watchdogConfig = require("./config.js");
const watchdogLog = require("./log.js");
const watchdogNotify = require("./notify.js");
const watchdogTermux = require("./termux.js");
const watchdogRepair = require("./repair.js");
const tailscale = require("./tailscale.js");
const watchdogComonitor = require("./comonitor.js");
/**
 * One watchdog cycle — Termux-primary + AutoJs6 co-monitor redundancy:
 *   Termux boot loop  → routine repair every 5 min (authoritative when healthy)
 *   This layer        → notifications, Tailscale, catastrophic Shizuku repair;
 *                       comonitor.js always re-probes the same STATUS surface
 *                       via shizuku() on every host (parity across the fleet).
 */
function runCycle(trigger, profile) {
  const tag = profile.notifyTag || "";
  const split = watchdogConfig.splitStorage(profile);
  const time = watchdogLog.append("[watchdog] cycle start trigger=" + trigger + " (autojs6)");
  try {
    const p = watchdogConfig.pathsFor(profile);
    files.ensureDir(p.watchdogStamp.replace(/\/[^/]+$/, "") + "/");
    files.write(p.watchdogStamp, time + " trigger=" + trigger + "\n");
  } catch (e) {
    watchdogLog.append("[watchdog] stamp write failed: " + e);
  }
  const termuxStale = watchdogLog.isRepairLoopStale();
  let comonitorReason = "periodic";
  if (split) {
    watchdogNotify.clear("stale");
    watchdogNotify.clear("bridge");
    watchdogLog.append("[watchdog] split-storage: Termux bridge skipped — co-monitor via Shizuku");
    comonitorReason = "split-storage";
  } else {
    if (termuxStale) {
      watchdogNotify.show(
        "⚠ Repair loop stale " + tag,
        time +
          " — No [repair] log line in 15+ min; Termux boot loop may be dead. AutoJs6 co-monitor will probe via Shizuku.",
        "stale",
      );
      comonitorReason = "termux-stale";
    } else {
      watchdogNotify.clear("stale");
    }
    let status = watchdogLog.latestRepairStatus();
    const port = status ? status.port : null;
    if (port === "CLOSED_NO_SHELL") {
      watchdogNotify.show(
        "⚠ ADB 5555 down — auto-repairing " + tag,
        time + " — port 5555 unreachable + no shell. Trying Shizuku shell, then UI Start tap. If it persists, reboot.",
        "adb5555",
      );
      watchdogRepair.repairCatastrophic(profile);
      watchdogTermux.invokeRepair(profile);
      const after = watchdogLog.latestRepairStatus();
      if (after && after.port === "CLOSED_NO_SHELL") {
        watchdogLog.append("[watchdog] catastrophic repair finished but port still CLOSED_NO_SHELL");
        comonitorReason = "closed-no-shell";
      }
    } else {
      watchdogNotify.clear("adb5555");
      if (termuxStale) {
        const invoke = watchdogTermux.invokeRepair(profile);
        status = invoke.fresh ? watchdogLog.latestRepairStatus() : status;
        const invokedPort = status ? status.port : "BRIDGE_FAIL";
        const invokedSshd = status ? status.sshd : "unknown";
        watchdogLog.append(
          "[watchdog] port=" +
            invokedPort +
            " sshd=" +
            invokedSshd +
            " invoke=" +
            (invoke.ok ? "ok" : "fail") +
            " method=" +
            invoke.method +
            " (autojs6 stale-loop)",
        );
        if (!invoke.ok || invokedPort === "BRIDGE_FAIL" || watchdogTermux.bridgeFailed(invoke)) {
          watchdogNotify.show(
            "⚠ Watchdog bridge failed " + tag,
            time + " — Termux RUN_COMMAND returned no fresh STATUS; co-monitor taking over via Shizuku.",
            "bridge",
          );
          comonitorReason = "bridge-fail";
        } else {
          watchdogNotify.clear("bridge");
          // invokedSshd comes from Termux's stayturgid_repair.py STATUS line
          // (via watchdogLog.latestRepairStatus()), which can genuinely write
          // sshd=FAILED (see device/termux/py/stayturgid_repair.py) — unlike
          // comonitor.ts's own SshdStatus below, this is not a closed union.
          if (invokedSshd === "down" || invokedSshd === "FAILED" || (status && status.shizuku === "down")) {
            comonitorReason = "post-bridge-unhealthy";
          }
        }
      } else {
        watchdogNotify.clear("bridge");
        watchdogLog.append("[watchdog] termux repair fresh — co-monitor still verifies (autojs6)");
      }
    }
  }
  // Fleet parity: every host runs the same Shizuku co-monitor each cycle.
  const comonitorStatus = watchdogComonitor.run(profile, { force: true, reason: comonitorReason });
  if (comonitorStatus && comonitorStatus.sshd === "down") {
    watchdogNotify.show(
      "⚠ SSH daemon down " + tag,
      time + " — Fresh co-monitor probe still sees sshd down. SSH in via ADB/Tailscale and run: sshd",
      "sshd",
    );
  } else {
    watchdogNotify.clear("sshd");
  }
  if (profile.tailscaleEnabled === false) {
    watchdogNotify.clear("tailscale");
    watchdogLog.append("[watchdog] tailscale checks disabled (not on tailnet yet) (autojs6)");
  } else {
    const ts = tailscale.check(profile);
    watchdogLog.append("[watchdog] tailscale tun=" + ts.tun + " ping=" + ts.ping + " up=" + ts.up);
    if (!ts.up) {
      watchdogNotify.show(
        "⚠ Tailscale down " + tag,
        time + " — tun0 or ping " + tailscale.COORD_PING_HOST + " failed; relaunching Tailscale.",
        "tailscale",
      );
      tailscale.relaunch(profile);
    } else {
      watchdogNotify.clear("tailscale");
    }
  }
}
