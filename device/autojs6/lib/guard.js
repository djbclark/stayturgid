// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.autoJs6AccessibilityEnabled = autoJs6AccessibilityEnabled;
exports.isMalfunctioning = isMalfunctioning;
exports.enforce = enforce;
exports.statusReport = statusReport;
// @heals: A11Y-AUTOJS6
const config = require("./config.js");
const notify = require("./notify.js");
const termux = require("./termux.js");
const log = require("./log.js");
const comonitor = require("./comonitor.js");
/** Run a shell probe on a worker thread with a timeout, so a hung settings daemon (seen on Fire OS) cannot block the watchdog cycle. */
function probeAccessibilitySettings() {
  const probe = { code: -1, result: "" };
  try {
    const thread = threads.start(() => {
      try {
        const r = shell("settings get secure enabled_accessibility_services", false);
        probe.code = r.code;
        probe.result = r.result;
      } catch (_a) {
        /* thread-local failure */
      }
    });
    thread.join(5000);
  } catch (_a) {
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
function autoJs6AccessibilityEnabled() {
  try {
    if (typeof auto !== "undefined") {
      if (auto.service) return true;
      // Engine present: bound service is the only truth. Settings-list fallback
      // would hide sticky ON (enabled but not running).
      return false;
    }
  } catch (_a) {
    /* fall through to the settings probe only when `auto` is unavailable */
  }
  // Fallback (best effort): if a privileged read happens to work, use it.
  const probe = probeAccessibilitySettings();
  if (probe.code === 0) {
    const list = probe.result.trim();
    return Boolean(list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0);
  }
  return false;
}
/** True when Settings lists AutoJs6 but `auto.service` is not bound (sticky). */
function isMalfunctioning() {
  try {
    if (typeof auto === "undefined" || auto.service) return false;
  } catch (_a) {
    return false;
  }
  const probe = probeAccessibilitySettings();
  if (probe.code !== 0) return false;
  const list = probe.result.trim();
  return Boolean(list && list !== "null" && list.indexOf(config.AUTOJS6_A11Y) >= 0);
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
function enforce(profile) {
  const resolvedProfile = profile || config.detectDeviceProfile();
  if (autoJs6AccessibilityEnabled()) {
    notify.clear("a11y-blocked");
    notify.clear("a11y-stale");
    return;
  }
  const sticky = isMalfunctioning();
  if (sticky) {
    log.append("[watchdog] accessibility STICKY (Settings ON, service not bound) — user must toggle OFF then ON");
  }
  if (config.splitStorage(resolvedProfile)) {
    log.append("[watchdog] split-storage: a11y off/sticky — co-monitor will probe via Shizuku");
    try {
      comonitor.run(resolvedProfile, { force: true, reason: sticky ? "a11y-sticky-split" : "a11y-off-split" });
    } catch (e) {
      log.append("[watchdog] comonitor a11y attempt failed: " + e);
    }
    if (autoJs6AccessibilityEnabled()) {
      notify.clear("a11y-blocked");
      notify.clear("a11y-stale");
      return;
    }
  } else {
    log.append(
      sticky
        ? "[watchdog] accessibility sticky — checking repair status"
        : "[watchdog] accessibility disabled — checking repair status",
    );
    // Check if Termux repair already detected and logged this.
    termux.invokeRepair(resolvedProfile);
    const deadline = Date.now() + 20000;
    while (Date.now() < deadline && !autoJs6AccessibilityEnabled()) {
      sleep(2000);
    }
    if (autoJs6AccessibilityEnabled()) {
      log.append("[watchdog] accessibility restored by user");
      notify.clear("a11y-blocked");
      notify.clear("a11y-stale");
      return;
    }
  }
  // Still off or sticky — user must enable / cycle manually.
  if (sticky) {
    log.append("[watchdog] accessibility still sticky — user must toggle OFF then ON");
    notify.show("AutoJs6 accessibility stuck (ON but not bound)", A11Y_TOGGLE_MSG, "a11y-stale");
  } else {
    log.append("[watchdog] accessibility still off — user must re-enable in Settings");
    notify.show("AutoJs6 accessibility disabled", A11Y_TOGGLE_MSG, "a11y-blocked");
  }
}
function statusReport() {
  return {
    autojs6A11y: autoJs6AccessibilityEnabled(),
    autojs6A11yMalfunctioning: isMalfunctioning(),
  };
}
