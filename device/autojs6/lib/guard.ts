// Rhino gotchas (redeclaration collisions, for...of, exports stamp, Java-string coercion): see docs/architecture/components/autojs6.md "Rhino JS-engine gotchas" before editing.
// @heals: A11Y-AUTOJS6
import guardConfig = require("./config.js");
import guardNotify = require("./notify.js");
import guardTermux = require("./termux.js");
import guardLog = require("./log.js");
import guardComonitor = require("./comonitor.js");

import type { DeviceProfile } from "./config.js";

interface ShellProbeResult {
  code: number;
  result: string;
}

/** Run a shell probe on a worker thread with a timeout, so a hung settings daemon (seen on Fire OS) cannot block the watchdog cycle. */
function probeAccessibilitySettings(): ShellProbeResult {
  const probe: ShellProbeResult = { code: -1, result: "" };
  try {
    const thread = threads.start(() => {
      try {
        const r = shell("settings get secure enabled_accessibility_services", false);
        probe.code = r.code;
        probe.result = r.result;
      } catch {
        /* thread-local failure */
      }
    });
    thread.join(5000);
  } catch {
    /* ignore */
  }
  return probe;
}

// Authoritative, permission-free check: AutoJs6's own accessibility service
// instance is non-null exactly when the service is enabled AND bound.
//
// Important: when `auto` exists but `auto.service` is null, do NOT fall back to
// `settings get secure enabled_accessibility_services`. Android can leave the
// component listed (Settings switch ON) while the service is not bound — the
// sticky/malfunctioning state. Trusting the settings list false-positives "up"
// and skips the user OFF→ON notification.
export function autoJs6AccessibilityEnabled(): boolean {
  try {
    if (typeof auto !== "undefined") {
      if (auto.service) return true;
      // Engine present: bound service is the only truth. Settings-list fallback
      // would hide sticky ON (enabled but not running).
      return false;
    }
  } catch {
    /* fall through to the settings probe only when `auto` is unavailable */
  }
  // Fallback (best effort): if a privileged read happens to work, use it.
  const probe = probeAccessibilitySettings();
  if (probe.code === 0) {
    const list = probe.result.trim();
    return Boolean(list && list !== "null" && list.indexOf(guardConfig.AUTOJS6_A11Y) >= 0);
  }
  return false;
}

/** True when Settings lists AutoJs6 but `auto.service` is not bound (sticky). */
export function isMalfunctioning(): boolean {
  try {
    if (typeof auto === "undefined" || auto.service) return false;
  } catch {
    return false;
  }
  const probe = probeAccessibilitySettings();
  if (probe.code !== 0) return false;
  const list = probe.result.trim();
  return Boolean(list && list !== "null" && list.indexOf(guardConfig.AUTOJS6_A11Y) >= 0);
}

const A11Y_TOGGLE_MSG =
  "Open Settings > Accessibility > AutoJs6: if already ON, turn OFF then ON again. " +
  "sshd/Tailscale self-heal still runs without a11y.";

/**
 * Best-effort accessibility check for the watchdog — DEGRADES, never blocks.
 *
 * When accessibility is off or sticky: on split-storage, co-monitor probes via
 * Shizuku. On normal hosts, invokes Termux repair to check status. The watchdog
 * cycle always proceeds (sshd/Tailscale/comonitor still run without a11y).
 *
 * Never `settings put` accessibility automatically (policy G3). User must
 * enable or cycle AutoJs6 in Settings. AutoJs6 fork may rebind via privileged
 * restartService when WRITE_SECURE_SETTINGS is granted.
 */
export function enforce(profile?: DeviceProfile): void {
  const resolvedProfile = profile || guardConfig.detectDeviceProfile();
  if (autoJs6AccessibilityEnabled()) {
    guardNotify.clear("a11y-blocked");
    guardNotify.clear("a11y-stale");
    return;
  }

  const sticky = isMalfunctioning();
  if (sticky) {
    guardLog.append("[watchdog] accessibility STICKY (Settings ON, service not bound) — user must toggle OFF then ON");
  }

  if (guardConfig.splitStorage(resolvedProfile)) {
    guardLog.append("[watchdog] split-storage: a11y off/sticky — co-monitor will probe via Shizuku");
    try {
      guardComonitor.run(resolvedProfile, { force: true, reason: sticky ? "a11y-sticky-split" : "a11y-off-split" });
    } catch (e) {
      guardLog.append("[watchdog] comonitor a11y attempt failed: " + e);
    }
    if (autoJs6AccessibilityEnabled()) {
      guardNotify.clear("a11y-blocked");
      guardNotify.clear("a11y-stale");
      return;
    }
  } else {
    guardLog.append(
      sticky
        ? "[watchdog] accessibility sticky — checking repair status"
        : "[watchdog] accessibility disabled — checking repair status",
    );
    // Only nudge Termux repair when its own boot loop looks stale/dead.
    // a11y off/sticky can persist for a long time (it can't be fixed here —
    // policy G3, user must toggle it), and invokeRepair() falls through to
    // the Shizuku/RUN_COMMAND chain when Termux's own loop isn't already
    // handling things. Without this gate, a persistently degraded a11y state
    // alone forces that fallback chain every single cycle, independent of
    // Termux's actual health — see stayturgid#34.
    if (guardLog.isRepairLoopStale()) {
      guardTermux.invokeRepair(resolvedProfile);
    }
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
      sleep(2000);
    }
    if (autoJs6AccessibilityEnabled()) {
      guardLog.append("[watchdog] accessibility restored by user");
      guardNotify.clear("a11y-blocked");
      guardNotify.clear("a11y-stale");
      return;
    }
  }

  // Still off or sticky — user must enable / cycle manually.
  if (sticky) {
    guardLog.append("[watchdog] accessibility still sticky — user must toggle OFF then ON");
    guardNotify.show("AutoJs6 accessibility stuck (ON but not bound)", A11Y_TOGGLE_MSG, "a11y-stale");
  } else {
    guardLog.append("[watchdog] accessibility still off — user must re-enable in Settings");
    guardNotify.show("AutoJs6 accessibility disabled", A11Y_TOGGLE_MSG, "a11y-blocked");
  }
}

export interface A11yStatusReport {
  autojs6A11y: boolean;
  autojs6A11yMalfunctioning: boolean;
}

export function statusReport(): A11yStatusReport {
  return {
    autojs6A11y: autoJs6AccessibilityEnabled(),
    autojs6A11yMalfunctioning: isMalfunctioning(),
  };
}
