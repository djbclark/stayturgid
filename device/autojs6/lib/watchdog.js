// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runCycle = runCycle;
// @heals: TAILSCALE-VPN
const config = require("./config.js");
const log = require("./log.js");
const notify = require("./notify.js");
const termux = require("./termux.js");
const repair = require("./repair.js");
const tailscale = require("./tailscale.js");
const comonitor = require("./comonitor.js");
/**
 * One watchdog cycle — Termux-primary + AutoJs6 co-monitor redundancy:
 *   Termux boot loop  → routine repair every 5 min (authoritative when healthy)
 *   This layer        → notifications, Tailscale, catastrophic Shizuku repair;
 *                       comonitor.js always re-probes the same STATUS surface
 *                       via shizuku() on every host (parity across the fleet).
 */
function runCycle(trigger, profile) {
  const tag = profile.notifyTag || "";
  const split = config.splitStorage(profile);
  const time = log.append("[watchdog] cycle start trigger=" + trigger + " (autojs6)");
  try {
    const p = config.pathsFor(profile);
    files.ensureDir(p.watchdogStamp.replace(/\/[^/]+$/, "") + "/");
    files.write(p.watchdogStamp, time + " trigger=" + trigger + "\n");
  } catch (e) {
    log.append("[watchdog] stamp write failed: " + e);
  }
  const termuxStale = log.isRepairLoopStale();
  let comonitorReason = "periodic";
  if (split) {
    notify.clear("stale");
    notify.clear("bridge");
    log.append("[watchdog] split-storage: Termux bridge skipped — co-monitor via Shizuku");
    comonitorReason = "split-storage";
  } else {
    if (termuxStale) {
      notify.show(
        "⚠ Repair loop stale " + tag,
        time +
          " — No [repair] log line in 15+ min; Termux boot loop may be dead. AutoJs6 co-monitor will probe via Shizuku.",
        "stale",
      );
      comonitorReason = "termux-stale";
    } else {
      notify.clear("stale");
    }
    let status = log.latestRepairStatus();
    const port = status ? status.port : null;
    if (port === "CLOSED_NO_SHELL") {
      notify.show(
        "⚠ ADB 5555 down — auto-repairing " + tag,
        time + " — port 5555 unreachable + no shell. Trying Shizuku shell, then UI Start tap. If it persists, reboot.",
        "adb5555",
      );
      repair.repairCatastrophic(profile);
      termux.invokeRepair(profile);
      const after = log.latestRepairStatus();
      if (after && after.port === "CLOSED_NO_SHELL") {
        log.append("[watchdog] catastrophic repair finished but port still CLOSED_NO_SHELL");
        comonitorReason = "closed-no-shell";
      }
    } else {
      notify.clear("adb5555");
      if (termuxStale) {
        const invoke = termux.invokeRepair(profile);
        status = invoke.fresh ? log.latestRepairStatus() : status;
        const invokedPort = status ? status.port : "BRIDGE_FAIL";
        const invokedSshd = status ? status.sshd : "unknown";
        log.append(
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
        if (!invoke.ok || invokedPort === "BRIDGE_FAIL" || termux.bridgeFailed(invoke)) {
          notify.show(
            "⚠ Watchdog bridge failed " + tag,
            time + " — Termux RUN_COMMAND returned no fresh STATUS; co-monitor taking over via Shizuku.",
            "bridge",
          );
          comonitorReason = "bridge-fail";
        } else {
          notify.clear("bridge");
          // invokedSshd comes from Termux's stayturgid_repair.py STATUS line
          // (via log.latestRepairStatus()), which can genuinely write
          // sshd=FAILED (see device/termux/py/stayturgid_repair.py) — unlike
          // comonitor.ts's own SshdStatus below, this is not a closed union.
          if (invokedSshd === "down" || invokedSshd === "FAILED" || (status && status.shizuku === "down")) {
            comonitorReason = "post-bridge-unhealthy";
          }
        }
      } else {
        notify.clear("bridge");
        log.append("[watchdog] termux repair fresh — co-monitor still verifies (autojs6)");
      }
    }
  }
  // Fleet parity: every host runs the same Shizuku co-monitor each cycle.
  const comonitorStatus = comonitor.run(profile, { force: true, reason: comonitorReason });
  if (comonitorStatus && comonitorStatus.sshd === "down") {
    notify.show(
      "⚠ SSH daemon down " + tag,
      time + " — Fresh co-monitor probe still sees sshd down. SSH in via ADB/Tailscale and run: sshd",
      "sshd",
    );
  } else {
    notify.clear("sshd");
  }
  if (profile.tailscaleEnabled === false) {
    notify.clear("tailscale");
    log.append("[watchdog] tailscale checks disabled (not on tailnet yet) (autojs6)");
  } else {
    const ts = tailscale.check(profile);
    log.append("[watchdog] tailscale tun=" + ts.tun + " ping=" + ts.ping + " up=" + ts.up);
    if (!ts.up) {
      notify.show(
        "⚠ Tailscale down " + tag,
        time + " — tun0 or ping " + tailscale.COORD_PING_HOST + " failed; relaunching Tailscale.",
        "tailscale",
      );
      tailscale.relaunch(profile);
    } else {
      notify.clear("tailscale");
    }
  }
}
